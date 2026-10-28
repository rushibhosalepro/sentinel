"""C-06: preflight replays the plan on a sim copy (kinematic rollout).

Catches what no rule names: drops (release in air), spills (tilt with
liquid away from a vessel), fragile objects ending near the counter edge,
and the empty arm contacting a person. Excluded from the 100 ms check
budget (it re-runs the rollout). Contact knocks need dynamic replay and
are out of scope (L-07 territory); the rollout is kinematic.
"""

from __future__ import annotations

import mujoco
import numpy as np

from sentinel.check import RELEASE_AIR_Z_M
from sentinel.relations import person_at
from sim.motion import plan_to_motion

# Counter top: pos (0.3, 0, -0.02), size (0.55, 0.35, 0.02) in kitchen.xml.
COUNTER_X = (-0.25, 0.85)
COUNTER_Y = (-0.35, 0.35)
COUNTER_TOP_Z = 0.0
EDGE_CM = 3.0
CONTACT_CM = 8.0
SPILL_TILT_DEG = 20.0
VESSEL_XZ_CM = 10.0
MOVED_CM = 1.0
VESSELS = {"cup"}  # + any object with the "vessel" property
DROP_BLOCK_PROPS = {"sharp", "heavy", "hot"}


def _props(graph, obj) -> list:
    node = graph["objects"].get(obj)
    return [] if node is None else list(node.get("properties", []))


def _on_counter(pos) -> bool:
    return (COUNTER_X[0] <= pos[0] <= COUNTER_X[1]
            and COUNTER_Y[0] <= pos[1] <= COUNTER_Y[1])


def _edge_gap_cm(pos) -> float:
    dx = min(pos[0] - COUNTER_X[0], COUNTER_X[1] - pos[0])
    dy = min(pos[1] - COUNTER_Y[0], COUNTER_Y[1] - pos[1])
    return min(dx, dy) * 100.0


def _vessels(graph) -> list:
    out = []
    for oid, node in graph["objects"].items():
        if oid in VESSELS or "vessel" in node.get("properties", []):
            out.append(np.asarray(node["pos"], dtype=float))
    return out


def preflight(plan, model, data, graph) -> dict:
    """Replay plan; return {"kind", "findings"} (rule/node/t/detail)."""
    hand_id = model.body("hand").id
    vessels = _vessels(graph)
    start = {b: data.xpos[model.body(b).id].copy()
             for b in graph["objects"] if _body(model, b)}
    findings = []
    fired = set()
    held_now = [None]
    track = {}

    def flag(rule, node, t, detail, kind):
        if rule in fired:
            return
        fired.add(rule)
        findings.append({"rule": rule, "node": node, "t": t,
                         "detail": detail, "_kind": kind})

    def hook(m, sim, state, ts):
        mujoco.mj_forward(model, sim)
        for b in start:
            track[b] = sim.xpos[model.body(b).id].copy()
        grip = sim.xpos[hand_id]
        for pid in graph["people"]:
            loc = person_at(graph, pid, ts)
            for part in ("hand", "torso"):
                gap = float(np.linalg.norm(grip - loc[part])) * 100.0
                if gap <= CONTACT_CM:
                    flag("preflight_contact", pid, ts,
                         f"gripper {gap:.0f} cm from {pid}'s {part}",
                         "BLOCK")
        if state.held and "liquid" in _props(graph, state.held) \
                and float(state.tilt_deg) > SPILL_TILT_DEG:
            ok = any(float(np.linalg.norm(grip[:2] - v[:2])) * 100.0
                     <= VESSEL_XZ_CM and grip[2] > v[2] for v in vessels)
            if not ok:
                flag("preflight_spill", state.held, ts,
                     f"pouring {state.held} with no vessel below", "BLOCK")
        if held_now[0] is not None and state.held is None:
            obj = held_now[0]
            pos = sim.xpos[model.body(obj).id].copy()
            sev = "BLOCK" if DROP_BLOCK_PROPS & set(_props(graph, obj)) \
                else "ASK"
            if float(pos[2]) > RELEASE_AIR_Z_M:
                flag("preflight_drop", obj, ts,
                     f"released {obj} at {pos[2] * 100.0:.0f} cm: will "
                     f"fall", sev)
            elif not _on_counter(pos):
                flag("preflight_drop", obj, ts,
                     f"released {obj} off the counter edge: will fall",
                     sev)
        held_now[0] = state.held

    motion = plan_to_motion(model, data, plan,
                               derived_from="preflight", on_sample=hook)
    end_t = motion["t"][-1]
    for b, pos in track.items():
        if "fragile" not in _props(graph, b):
            continue
        moved = float(np.linalg.norm(pos - start[b])) * 100.0
        if moved < MOVED_CM:
            continue
        if _on_counter(pos) and _edge_gap_cm(pos) <= EDGE_CM:
            flag("preflight_edge", b, end_t,
                 f"fragile {b} ends {_edge_gap_cm(pos):.0f} cm from the "
                 f"counter edge", "ASK")
    kind = "ALLOW"
    order = {"ALLOW": 0, "ASK": 1, "BLOCK": 2}
    for f in findings:
        if order[f["_kind"]] > order[kind]:
            kind = f["_kind"]
        del f["_kind"]
    return {"kind": kind, "findings": findings}


def _body(model, name) -> bool:
    try:
        model.body(name)
        return True
    except KeyError:
        return False
