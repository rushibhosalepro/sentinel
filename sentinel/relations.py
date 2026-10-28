"""C-02: pure predicates over Motion samples x scene graph.

No sim, no LLM. A carried object's pose is recovered kinematically: the
grasp offset (T_grip^-1 @ T_obj) is captured from the graph pose at the
grasp sample, then re-applied to each later gripper pose -- the same math
the rollout uses to drag held bodies (`sim/primitives._drag_held`).

Graph dict contract (built from props + live sim state by the caller):
  {"objects": {id: {"pos": [x,y,z], "quat": [w,x,y,z],
                    "properties": [...], "owner": str|None, "conf": float}},
   "people": {id: {"hand": [x,y,z], "torso": [x,y,z], "hand_vel": [x,y,z],
                   "authorised": [...], "role": str}}}
Distances are in metres; findings report centimetres.
"""

from __future__ import annotations

import numpy as np

KNIFE_BODY = "chef_knife"
# Knife-body-frame keypoints, pinned against the model in test_relations.
KNIFE_TIP_LOCAL = np.array([0.175, 0.0, 0.002])
KNIFE_HANDLE_LOCAL = np.array([-0.055, 0.0, 0.006])

# Person velocity is extrapolated at most this far (G-05 prediction cap).
PREDICT_CAP_S = 3.0
# A release within this of a live hand counts as into the hand (S-07 take
# is 5 cm; the extra 5 cm is the perception/registration allowance).
RELEASE_INTO_HAND_CM = 10.0
# hand_to expansions tag their release step "<hid>:release"; the expansion
# waits for the take (timeout keeps holding), so a tagged release is into
# the taker's hand by construction.
HANDOVER_RELEASE_TAG = ":release"


def _quat_to_mat(q) -> np.ndarray:
    w, x, y, z = (float(v) for v in q)
    n = w * w + x * x + y * y + z * z
    s = 2.0 / n if n > 1e-12 else 0.0
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w),
         1 - s * (x * x + y * y)]])


def _se3(pos, quat) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = _quat_to_mat(quat)
    t[:3, 3] = np.asarray(pos, dtype=float)
    return t


def _grip_se3(motion, i) -> np.ndarray:
    pose = motion["path"][i]
    return _se3(pose[:3], pose[3:])


def grasp_index(motion, obj: str) -> int | None:
    """First sample holding obj (None if never held)."""
    for i, held in enumerate(motion["held"]):
        if held == obj:
            return i
    return None


def grasp_offset(motion, graph, obj: str) -> np.ndarray | None:
    """T_grip^-1 @ T_obj at the grasp sample (None if never held)."""
    g = grasp_index(motion, obj)
    if g is None:
        return None
    node = graph["objects"][obj]
    return np.linalg.inv(_grip_se3(motion, g)) @ _se3(node["pos"],
                                                      node["quat"])


def carried_point(motion, graph, obj: str, i: int,
                  local=(0.0, 0.0, 0.0)) -> np.ndarray | None:
    """World pos of an object-local point at sample i (None if not held)."""
    if motion["held"][i] != obj:
        return None
    off = grasp_offset(motion, graph, obj)
    if off is None:
        return None
    p = _grip_se3(motion, i) @ off @ np.array([*local, 1.0])
    return p[:3]


def knife_geometry(motion, graph, i: int) -> dict | None:
    """Blade tip + handle world positions (None unless holding the knife)."""
    if motion["held"][i] != KNIFE_BODY:
        return None
    tip = carried_point(motion, graph, KNIFE_BODY, i, KNIFE_TIP_LOCAL)
    handle = carried_point(motion, graph, KNIFE_BODY, i, KNIFE_HANDLE_LOCAL)
    return {"tip": tip, "handle": handle}


def person_at(graph, pid: str, t: float) -> dict:
    """Hand/torso at time t (hand velocity extrapolated, capped)."""
    p = graph["people"][pid]
    dt = min(max(float(t), 0.0), PREDICT_CAP_S)
    hand = np.asarray(p["hand"], dtype=float) \
        + np.asarray(p.get("hand_vel", (0.0, 0.0, 0.0))) * dt
    return {"hand": hand, "torso": np.asarray(p["torso"], dtype=float)}


def nearest_person_part(point, graph, t: float) -> tuple:
    """(person id, 'hand'|'torso', dist_m) closest to point at time t."""
    point = np.asarray(point, dtype=float)
    best = (None, None, float("inf"))
    for pid in graph["people"]:
        loc = person_at(graph, pid, t)
        for part in ("hand", "torso"):
            d = float(np.linalg.norm(point - loc[part]))
            if d < best[2]:
                best = (pid, part, d)
    return best


def measure_blade(motion, graph, i: int) -> dict | None:
    """Tip/handle gap to the nearest person part (None if no knife held).

    `toward` is the S-07 discriminator: the tip is closer than the handle.
    """
    geo = knife_geometry(motion, graph, i)
    if geo is None:
        return None
    t = motion["t"][i]
    pid, part, tip_m = nearest_person_part(geo["tip"], graph, t)
    loc = person_at(graph, pid, t)[part]
    handle_m = float(np.linalg.norm(geo["handle"] - loc))
    return {"tip_cm": tip_m * 100.0, "handle_cm": handle_m * 100.0,
            "toward": tip_m < handle_m, "person": pid, "part": part}


def _held_keypoints(motion, graph, obj: str, i: int) -> list:
    pts = [carried_point(motion, graph, obj, i)]
    if obj == KNIFE_BODY:
        geo = knife_geometry(motion, graph, i)
        pts += [geo["tip"], geo["handle"]]
    return pts


def measure_held(motion, graph, i: int) -> dict | None:
    """Closest held-geometry gap to a person (None if empty-handed)."""
    obj = motion["held"][i]
    if obj is None:
        return None
    t = motion["t"][i]
    best = (None, None, float("inf"))
    for pt in _held_keypoints(motion, graph, obj, i):
        pid, part, d = nearest_person_part(pt, graph, t)
        if d < best[2]:
            best = (pid, part, d)
    return {"gap_cm": best[2] * 100.0, "obj": obj, "person": best[0],
            "part": best[1]}


def measure_held_electronic(motion, graph, i: int) -> dict | None:
    """Closest held-origin gap to an electronic (None if empty-handed)."""
    obj = motion["held"][i]
    if obj is None:
        return None
    pt = carried_point(motion, graph, obj, i)
    best = (None, float("inf"))
    for eid, node in graph["objects"].items():
        if "electronic" not in node.get("properties", []):
            continue
        d = float(np.linalg.norm(pt - np.asarray(node["pos"])))
        if d < best[1]:
            best = (eid, d)
    if best[0] is None:
        return None
    return {"gap_cm": best[1] * 100.0, "obj": obj, "electronic": best[0]}


def release_events(motion, graph) -> list[dict]:
    """held obj->None transitions with the release pose from the last hold."""
    out = []
    held = motion["held"]
    for i in range(1, len(held)):
        if held[i - 1] is not None and held[i] is None:
            obj = held[i - 1]
            out.append({"idx": i, "t": motion["t"][i],
                        "step_id": motion["sample_steps"][i], "obj": obj,
                        "pos": carried_point(motion, graph, obj, i - 1)})
    return out


def release_into_hand(ev: dict, graph) -> tuple[bool, str | None]:
    """(into_hand, person): tagged hand_to release, or a live hand nearby."""
    if ev["step_id"].endswith(HANDOVER_RELEASE_TAG):
        pid, _, _ = nearest_person_part(ev["pos"], graph, ev["t"])
        return True, pid
    pid, part, d = nearest_person_part(ev["pos"], graph, ev["t"])
    if part == "hand" and d * 100.0 <= RELEASE_INTO_HAND_CM:
        return True, pid
    return False, None


def recipient_authorised(graph, pid: str) -> bool:
    """True when the person's scopes approve any handover."""
    return "all" in graph["people"][pid].get("authorised", [])


def held_ids(motion) -> list[str]:
    """Unique non-None held ids, in order of first appearance."""
    out = []
    for h in motion["held"]:
        if h is not None and h not in out:
            out.append(h)
    return out


def conf_of(graph, obj: str) -> float | None:
    """Perception confidence for obj (None if not in the graph)."""
    node = graph["objects"].get(obj)
    return None if node is None else float(node.get("conf", 1.0))
