"""Ground-truth scene graph from simulator state + props.yaml. (G-01)

build_ground_truth() snapshots the world into a networkx MultiDiGraph following
graph/schema.py: Object nodes for every prop (plus the counter, which is
scene geometry rather than a graspable prop), Person nodes for each role,
BodyPart nodes for the robot gripper and the human hand, Property nodes from
props.yaml, and HAS / OWNED_BY / HOLDS / ON / NEAR / ABOVE / INSIDE edges.
Every edge carries ts; NEAR edges carry dist_cm.

Decisions: the visible hand belongs to the owner (they instruct and receive
handovers); the visitor has a Person node but no body parts (not present).
The gripper is a BodyPart with no Person parent (the robot is not a person).
HOLDS connects BodyPart -> Object (PLAN §4 wins over research/02's Robot
node, which is not a §4 node type). The floor is skipped (nothing rests on
it in the kitchen scenes).

Usage:
    uv run python -m graph.scene_graph --demo kitchen   # prints the graph
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import networkx as nx
import numpy as np
import yaml

from graph.schema import (
    EDGE_ABOVE,
    EDGE_HAS,
    EDGE_HOLDS,
    EDGE_INSIDE,
    EDGE_NEAR,
    EDGE_ON,
    EDGE_OWNED_BY,
    NODE_BODYPART,
    NODE_OBJECT,
    NODE_PERSON,
    NODE_PROPERTY,
    bodypart_id,
    new_graph,
    object_id,
    person_id,
    property_id,
)
from sim.geometry import (
    ABOVE_MIN_M,
    NEAR_GAP_M,
    ON_BAND_M,
    aabb_gap,
    aabbs_xy_overlap,
    body_aabb,
    free_bodies,
)
from sim.world import SCENES_DIR, load_scene

GRIPPER_BODY = "hand"
HUMAN_BODY = "human_hand"
COUNTER_BODY = "counter"

ASSOC_GATE_M = 0.25  # max centroid distance for detection-to-track match


def load_props(path: Path | None = None) -> dict:
    path = path or SCENES_DIR / "props.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


RELATION_TYPES = {EDGE_ON, EDGE_NEAR, EDGE_ABOVE, EDGE_INSIDE}


def recompute_relations(g: nx.MultiDiGraph, ts: float) -> int:
    """Replace all relation edges from node bbox3d attrs. (G-04)

    Shared by the GT builder and the SAM tracker: both store a world-space
    AABB on every Object/BodyPart node, and relations are derived from
    those boxes alone -- never from the sim. Stale nodes keep their last
    known box, so their relations persist as best-known estimates.
    """
    old = [(a, b, k) for a, b, k, d in g.edges(keys=True, data=True)
           if d.get("type") in RELATION_TYPES]
    for a, b, k in old:
        g.remove_edge(a, b, k)
    boxes = {}
    for node, attrs in g.nodes(data=True):
        if attrs.get("type") in (NODE_OBJECT, NODE_BODYPART) and "bbox3d" in attrs:
            xyz = attrs["bbox3d"]
            boxes[node] = (np.array(xyz[:3]), np.array(xyz[3:]))
    n = 0
    for a, b, rel, dist_cm in _relation_edges(boxes, ts):
        g.add_edge(a, b, type=rel, dist_cm=dist_cm, ts=ts)
        n += 1
    return n


def _relation_edges(boxes: dict[str, tuple], ts: float) -> list[tuple]:
    """Directed relation edges over {node_id: (lo, hi)} boxes (G-01/G-04)."""
    edges = []
    for a in sorted(boxes):
        lo_a, hi_a = boxes[a]
        if np.isinf(lo_a).any():
            continue
        for b in sorted(boxes):
            if b == a:
                continue
            lo_b, hi_b = boxes[b]
            if np.isinf(lo_b).any():
                continue
            if bool((lo_a >= lo_b).all() and (hi_a <= hi_b).all()):
                clear = min(float(np.min(lo_a - lo_b)),
                            float(np.min(hi_b - hi_a)))
                edges.append((a, b, EDGE_INSIDE,
                              round(max(0.0, clear) * 100, 2)))
            vgap = float(lo_a[2] - hi_b[2])
            if abs(vgap) <= ON_BAND_M and aabbs_xy_overlap(
                    lo_a, hi_a, lo_b, hi_b):
                edges.append((a, b, EDGE_ON,
                              round(max(0.0, vgap) * 100, 2)))
            elif vgap > ABOVE_MIN_M and aabbs_xy_overlap(
                    lo_a, hi_a, lo_b, hi_b):
                edges.append((a, b, EDGE_ABOVE, round(vgap * 100, 2)))
            gap = aabb_gap(lo_a, hi_a, lo_b, hi_b)
            if gap < NEAR_GAP_M:
                edges.append((a, b, EDGE_NEAR, round(gap * 100, 2)))
    return edges


def build_ground_truth(model, data, props: dict | None = None,
                       held: dict[str, str] | None = None,
                       ts: float | None = None) -> nx.MultiDiGraph:
    """Snapshot (model, data) into a scene graph.

    `held` maps holder bodypart id -> object id (e.g. from a rollout's
    PrimState); `ts` defaults to data.time.
    """
    props = props if props is not None else load_props()
    ts = data.time if ts is None else ts
    held = held or {}
    held_objects = set(held.values())
    g = new_graph()

    for role, spec in props["people"].items():
        g.add_node(person_id(role), type=NODE_PERSON, role=role, name=role,
                   authorised=list(spec.get("authorised", [])))

    for name, spec in props["objects"].items():
        body_id = model.body(name).id
        lo, hi = body_aabb(model, data, body_id)
        g.add_node(object_id(name), type=NODE_OBJECT, label=spec["label"],
                   track_id=name, pos=data.xpos[body_id].tolist(),
                   bbox3d=[*lo.tolist(), *hi.tolist()], conf=1.0,
                   last_seen=ts, held=name in held_objects,
                   owner=spec["owner"])
        for prop in spec["properties"]:
            pid = property_id(prop)
            if not g.has_node(pid):
                g.add_node(pid, type=NODE_PROPERTY, name=prop)
            g.add_edge(object_id(name), pid, type=EDGE_HAS, ts=ts)
        g.add_edge(object_id(name), person_id(spec["owner"]),
                   type=EDGE_OWNED_BY, ts=ts)

    if COUNTER_BODY in [mujoco.mj_id2name(
            model, mujoco.mjtObj.mjOBJ_BODY, i)
            for i in range(model.nbody)]:
        body_id = model.body(COUNTER_BODY).id
        lo, hi = body_aabb(model, data, body_id)
        g.add_node(object_id(COUNTER_BODY), type=NODE_OBJECT,
                   label="counter", track_id=COUNTER_BODY,
                   pos=data.xpos[body_id].tolist(),
                   bbox3d=[*lo.tolist(), *hi.tolist()], conf=1.0,
                   last_seen=ts, held=False, owner="owner")

    gripper = bodypart_id(GRIPPER_BODY)
    gid = model.body(GRIPPER_BODY).id
    glo, ghi = body_aabb(model, data, gid)
    g.add_node(gripper, type=NODE_BODYPART, kind="gripper",
               pos=data.xpos[gid].tolist(), velocity=[0.0, 0.0, 0.0],
               bbox3d=[*glo.tolist(), *ghi.tolist()], last_seen=ts)
    hand = bodypart_id(HUMAN_BODY)
    hid = model.body(HUMAN_BODY).id
    hlo, hhi = body_aabb(model, data, hid)
    g.add_node(hand, type=NODE_BODYPART, kind="hand",
               pos=data.xpos[hid].tolist(), velocity=[0.0, 0.0, 0.0],
               bbox3d=[*hlo.tolist(), *hhi.tolist()], last_seen=ts)
    g.add_edge(person_id("owner"), hand, type=EDGE_HAS, ts=ts)

    for holder, obj in held.items():
        g.add_edge(holder, obj, type=EDGE_HOLDS, ts=ts)

    recompute_relations(g, ts)  # same code path as the SAM graph (G-04)
    return g


def init_perception_graph(model, data, props: dict | None = None,
                            ts: float | None = None) -> nx.MultiDiGraph:
    """Empty SAM-built graph: static priors only (persons, counter, gripper).

    Prop Object nodes appear once a detection associates to them
    (update_from_detections); the counter and gripper come from the static
    map + proprioception, so they are never stale. The human hand is added
    by G-05 once seen.
    """
    props = props if props is not None else load_props()
    ts = data.time if ts is None else ts
    g = new_graph()
    g.graph["props"] = props
    for role, spec in props["people"].items():
        g.add_node(person_id(role), type=NODE_PERSON, role=role, name=role,
                   authorised=list(spec.get("authorised", [])))
    body_id = model.body(COUNTER_BODY).id
    lo, hi = body_aabb(model, data, body_id)
    g.add_node(object_id(COUNTER_BODY), type=NODE_OBJECT, label="counter",
               track_id=COUNTER_BODY, pos=data.xpos[body_id].tolist(),
               bbox3d=[*lo.tolist(), *hi.tolist()], conf=1.0,
               last_seen=ts, stale=False, static=True, held=False,
               owner="owner")
    gid = model.body(GRIPPER_BODY).id
    glo, ghi = body_aabb(model, data, gid)
    g.add_node(bodypart_id(GRIPPER_BODY), type=NODE_BODYPART, kind="gripper",
               pos=data.xpos[gid].tolist(), velocity=[0.0, 0.0, 0.0],
               bbox3d=[*glo.tolist(), *ghi.tolist()], last_seen=ts)
    # G-05: the safety-critical hand node is pre-created at its parked pose
    # (stale until first observed) so hand-vs-object edges always resolve.
    hid = model.body(HUMAN_BODY).id
    hlo, hhi = body_aabb(model, data, hid)
    g.add_node(bodypart_id(HUMAN_BODY), type=NODE_BODYPART, kind="hand",
               pos=data.xpos[hid].tolist(), velocity=[0.0, 0.0, 0.0],
               bbox3d=[*hlo.tolist(), *hhi.tolist()],
               person_predicted=[], stale=True, last_seen=None)
    g.add_edge(person_id("owner"), bodypart_id(HUMAN_BODY),
               type=EDGE_HAS, ts=ts)
    return g


def upsert_object(g: nx.MultiDiGraph, props: dict, obj: str,
                  det, ts: float) -> None:
    """Spawn or refresh a matched Object node from a detection. (G-09)"""
    spec = props["objects"][obj]
    node = object_id(obj)
    attrs = dict(type=NODE_OBJECT, label=spec["label"], track_id=obj,
                 pos=np.asarray(det.centroid).tolist(),
                 bbox3d=[*np.asarray(det.bbox_min).tolist(),
                         *np.asarray(det.bbox_max).tolist()],
                 conf=float(det.conf), last_seen=ts, stale=False,
                 tracked=True, held=False, owner=spec["owner"])
    if node in g.nodes and g.nodes[node].get("tracked"):
        g.nodes[node].update(attrs)
        return
    g.add_node(node, **attrs)
    for prop in spec["properties"]:
        pid = property_id(prop)
        if not g.has_node(pid):
            g.add_node(pid, type=NODE_PROPERTY, name=prop)
        g.add_edge(node, pid, type=EDGE_HAS, ts=ts)
    g.add_edge(node, person_id(spec["owner"]), type=EDGE_OWNED_BY, ts=ts)


def spawn_unknown(g: nx.MultiDiGraph, label: str, det, ts: float,
                  idx: int = 0) -> str:
    """Spawn an unknown_object node (no properties, no owner). (G-09)

    Returns the node id ("unknown_object", "unknown_object_2", ...).
    """
    node = "unknown_object" if idx == 0 else f"unknown_object_{idx + 1}"
    g.add_node(node, type=NODE_OBJECT, label=label, track_id=node,
               pos=np.asarray(det.centroid).tolist(),
               bbox3d=[*np.asarray(det.bbox_min).tolist(),
                       *np.asarray(det.bbox_max).tolist()],
               conf=float(det.conf), last_seen=ts, stale=False,
               tracked=True, held=False, owner=None, unknown=True)
    return node


def build_perception_graph(model, data, detections,
                           props: dict | None = None,
                           ts: float | None = None) -> nx.MultiDiGraph:
    """Full G-09 graph: priors + matched objects + unknowns + relations.

    Detections carry `match` (props id or None); duplicates are demoted
    to unknown (highest confidence keeps the id). Pure (no network).
    """
    props = props if props is not None else load_props()
    ts = data.time if ts is None else ts
    g = init_perception_graph(model, data, props, ts)
    taken: set[str] = set()
    unknowns = 0
    for det in sorted(detections, key=lambda d: -d.conf):
        oid = det.match
        if oid is not None and (oid in taken
                                or oid not in props["objects"]):
            oid = None
        if oid is None:
            spawn_unknown(g, det.label or det.prompt, det, ts, unknowns)
            unknowns += 1
        else:
            taken.add(oid)
            upsert_object(g, props, oid, det, ts)
    recompute_relations(g, ts)
    return g


def update_from_detections(g: nx.MultiDiGraph, detections,
                           ts: float) -> dict:
    """Associate detections to Object nodes (label + nearest position).

    Greedy by confidence: each detection goes to the nearest tracked
    candidate within ASSOC_GATE_M, else spawns an untracked candidate
    (primary prompt first), else is dropped as a duplicate. Detections
    whose prompt no object lists (e.g. "hand", wired in G-05) are dropped.
    Tracked nodes missed this frame stay in the graph as stale=True:
    object permanence, never delete. Returns assignment stats.
    """
    props = g.graph["props"]
    candidates: dict[str, list] = {}
    for obj, spec in props["objects"].items():
        for i, prompt in enumerate(spec.get("prompts", [spec["label"]])):
            candidates.setdefault(prompt, []).append((obj, i == 0))

    assigned, dropped, updated = [], [], set()
    for det in sorted(detections, key=lambda d: (-d.conf, d.prompt)):
        cands = candidates.get(det.prompt, [])
        if not cands:
            dropped.append((det.prompt, "no-listing-object"))
            continue
        best, bestd = None, ASSOC_GATE_M
        for obj, _ in cands:
            if obj in g.nodes and g.nodes[obj].get("tracked"):
                d = float(np.linalg.norm(
                    np.asarray(det.centroid)
                    - np.asarray(g.nodes[obj]["pos"])))
                if d < bestd:
                    best, bestd = obj, d
        if best is None:
            for obj, is_primary in sorted(cands,
                                          key=lambda c: (not c[1], c[0])):
                if obj not in g.nodes or not g.nodes[obj].get("tracked"):
                    best = obj
                    break
        if best is None or best in updated:
            dropped.append((det.prompt, "duplicate"))
            continue
        if best not in g.nodes or not g.nodes[best].get("tracked"):
            upsert_object(g, props, best, det, ts)
        else:
            node = g.nodes[best]
            node["pos"] = np.asarray(det.centroid).tolist()
            node["bbox3d"] = [*np.asarray(det.bbox_min).tolist(),
                              *np.asarray(det.bbox_max).tolist()]
            node["conf"] = float(det.conf)
            node["last_seen"] = ts
            node["stale"] = False
        updated.add(best)
        assigned.append((det.prompt, best))

    stale = []
    for node, attrs in g.nodes(data=True):
        if (attrs.get("type") == NODE_OBJECT and attrs.get("tracked")
                and not attrs.get("static") and node not in updated):
            attrs["stale"] = True
            stale.append(node)
    n_rel = recompute_relations(g, ts)  # same code path as GT (G-04)
    return {"assigned": assigned, "dropped": dropped, "stale": stale,
            "relations": n_rel}


def update_hand_track(g: nx.MultiDiGraph, track, ts: float, pos) -> dict:
    """Fuse one hand observation into bp:human_hand. (G-05)

    Translates the last-known box by the position delta (the hand's shape
    is rigid), stores velocity + person_predicted from the track, and
    refreshes relations so hand-vs-object edges stay current.
    """
    est = track.update(ts, pos)
    node = g.nodes[bodypart_id(HUMAN_BODY)]
    delta = np.asarray(est["pos"]) - np.asarray(node["pos"])
    lo = np.asarray(node["bbox3d"][:3]) + delta
    hi = np.asarray(node["bbox3d"][3:]) + delta
    node.update(pos=est["pos"], velocity=est["velocity"],
                person_predicted=est["predicted"],
                bbox3d=[*lo.tolist(), *hi.tolist()],
                stale=False, last_seen=ts)
    recompute_relations(g, ts)
    return est


def print_graph(g: nx.MultiDiGraph) -> None:
    kinds: dict[str, int] = {}
    for _, attrs in g.nodes(data=True):
        kinds[attrs["type"]] = kinds.get(attrs["type"], 0) + 1
    print(f"nodes={g.number_of_nodes()} {kinds} edges={g.number_of_edges()}")
    rels = [(a, d["type"], b, d.get("dist_cm"))
            for a, b, d in g.edges(data=True)
            if d["type"] in (EDGE_ON, EDGE_NEAR, EDGE_ABOVE, EDGE_INSIDE)]
    print(f"relations ({len(rels)}):")
    for a, rel, b, dist in sorted(rels):
        print(f"  {rel:6s} {a} {b} "
              + (f"{dist} cm" if dist is not None else ""))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print GT and SAM scene graphs side by side.")
    parser.add_argument("--demo", choices=["kitchen"])
    args = parser.parse_args()
    if args.demo != "kitchen":
        parser.print_help()
        return
    from perception.detections import detections_from_cache
    from perception.lift3d import camera_params
    from sim.world import OUT_DIR, render

    model, data = load_scene("kitchen")
    gt = build_ground_truth(model, data)
    print("=== ground truth ===")
    print_graph(gt)

    image_path = OUT_DIR / "kitchen_front.png"
    frame = render(model, data, camera="front", width=640, height=480)
    depth = frame["depth"]
    cam = camera_params(model, data, "front", 640, 480)
    try:
        dets = detections_from_cache(image_path, depth, cam)
    except FileNotFoundError as e:
        print(f"=== SAM graph ===\nskipped: {e}")
        return
    sam_g = init_perception_graph(model, data)
    stats = update_from_detections(sam_g, dets, ts=data.time)
    print("=== SAM (from cache, no network) ===")
    print(f"detections={len(dets)} assigned={len(stats['assigned'])} "
          f"dropped={len(stats['dropped'])} stale={len(stats['stale'])}")
    print_graph(sam_g)


if __name__ == "__main__":
    main()
