"""Plan -> Motion dry runs on a copy of the sim. (S-04, PLAN §4)

plan_to_motion() executes a list of PlanSteps against a COPY of the caller's
MjData (mj_copyData) and samples the contract's Motion object: gripper path,
timestamps, held object, tilt, speed, plus end_state relations (on/near/
above/inside with dist_cm) for objects the plan moved. The caller's data is
never touched; the copy is discarded afterwards.

Relation geometry uses world-space AABBs per body (exact for axis-aligned
boxes, conservative otherwise; C-02 refines these into true predicates).
`a` is always a moved object, `b` a prop or the counter; unmoved pairs are
omitted by design.

Usage:
    uv run python -m sim.motion --demo knife_handover
"""

from __future__ import annotations

import argparse

import mujoco
import numpy as np
from PIL import Image

from sim.ik import GRASP_OFFSET
from sim.primitives import (
    PRIMITIVES,
    Clock,
    PrimitiveError,
    PrimState,
)
from sim.world import OUT_DIR, load_scene, render

DOWN = [0.0, 1.0, 0.0, 0.0]  # gripper-down hand quat (wxyz)

KNIFE_HANDOVER_PLAN = [
    {"id": "s1", "primitive": "move_to",
     "args": {"pose": [0.33, -0.17, 0.18, *DOWN]},
     "serves_instruction": "give me the knife",
     "why": "hover above the knife handle"},
    {"id": "s2", "primitive": "move_to",
     "args": {"pose": [0.33, -0.17, 0.10, *DOWN]},
     "serves_instruction": "give me the knife",
     "why": "descend to grasp height"},
    {"id": "s3", "primitive": "grasp",
     "args": {"object_id": "chef_knife"},
     "serves_instruction": "give me the knife",
     "why": "take hold of the knife"},
    {"id": "s4", "primitive": "move_to",
     "args": {"pose": [0.33, -0.17, 0.30, *DOWN]},
     "serves_instruction": "give me the knife",
     "why": "lift clear of the counter"},
    {"id": "s5", "primitive": "set_speed",
     "args": {"speed": "slow"},
     "serves_instruction": "give me the knife",
     "why": "carry the sharp object slowly"},
    {"id": "s6", "primitive": "move_to",
     "args": {"pose": [0.55, -0.35, 0.35, *DOWN]},
     "serves_instruction": "give me the knife",
     "why": "carry to the handover point"},
    {"id": "s7", "primitive": "stop", "args": {},
     "serves_instruction": "give me the knife",
     "why": "hold for the human to take"},
]

DEMOS = {"knife_handover": KNIFE_HANDOVER_PLAN}

MOVED_EPS = 1e-3  # (m) displacement that counts as "moved"
NEAR_GAP = 0.10  # (m) surface gap that counts as "near"
ON_BAND = 0.015  # (m) vertical tolerance for "on"


def _grasp_pose(model: mujoco.MjModel, data: mujoco.MjData) -> list[float]:
    hand_id = model.body("hand").id
    gp = data.xpos[hand_id] + data.xmat[hand_id].reshape(3, 3) @ np.array(
        [0.0, 0.0, GRASP_OFFSET])
    return [float(v) for v in gp] + [float(v) for v in data.xquat[hand_id]]


def _geom_world_aabb(model: mujoco.MjModel, data: mujoco.MjData,
                     geom_id: int):
    """World-frame (lo, hi) box for a geom (None for unbounded types)."""
    typ = model.geom_type[geom_id]
    size = model.geom_size[geom_id]
    rot = data.geom_xmat[geom_id].reshape(3, 3)
    center = data.geom_xpos[geom_id]
    if typ == mujoco.mjtGeom.mjGEOM_MESH:
        mid = model.geom_dataid[geom_id]
        v0, n = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
        verts = model.mesh_vert[v0:v0 + n] * size
        lo_l, hi_l = verts.min(axis=0), verts.max(axis=0)
        corners = np.stack(
            np.meshgrid(*zip(lo_l, hi_l))).reshape(3, -1).T
        world = corners @ rot.T + center
        return world.min(axis=0), world.max(axis=0)
    if typ == mujoco.mjtGeom.mjGEOM_BOX:
        half = size.copy()
    elif typ == mujoco.mjtGeom.mjGEOM_SPHERE:
        half = np.array([size[0]] * 3)
    elif typ == mujoco.mjtGeom.mjGEOM_CAPSULE:
        half = np.array([size[0], size[0], size[0] + size[1]])
    elif typ == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
        half = size.copy()
    elif typ == mujoco.mjtGeom.mjGEOM_CYLINDER:
        half = np.array([size[0], size[0], size[1]])
    else:
        return None  # planes, hfields: unbounded, skipped
    extent = np.abs(rot) @ half
    return center - extent, center + extent


def _body_aabb(model: mujoco.MjModel, data: mujoco.MjData,
               body_id: int) -> tuple[np.ndarray, np.ndarray]:
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for g in range(model.ngeom):
        if model.geom_bodyid[g] != body_id:
            continue
        box = _geom_world_aabb(model, data, g)
        if box is None:
            continue
        lo = np.minimum(lo, box[0])
        hi = np.maximum(hi, box[1])
    return lo, hi


def _aabb_gap(lo1, hi1, lo2, hi2) -> float:
    sep = np.maximum(np.maximum(lo2 - hi1, lo1 - hi2), 0.0)
    return float(np.linalg.norm(sep))


def _free_bodies(model: mujoco.MjModel) -> list[str]:
    names = []
    for body_id in range(model.nbody):
        jadr = model.body_jntadr[body_id]
        if jadr >= 0 and model.jnt_type[jadr] == mujoco.mjtJoint.mjJNT_FREE:
            names.append(mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id))
    return names


def _xy_overlap(lo1, hi1, lo2, hi2) -> bool:
    return bool(lo1[0] <= hi2[0] and lo2[0] <= hi1[0]
                and lo1[1] <= hi2[1] and lo2[1] <= hi1[1])


def _end_state(model, data, moved: list[str]) -> list[dict]:
    others = _free_bodies(model) + ["counter"]
    out = []
    for a in sorted(moved):
        lo_a, hi_a = _body_aabb(model, data, model.body(a).id)
        for b in sorted(set(others) - {a}):
            lo_b, hi_b = _body_aabb(model, data, model.body(b).id)
            if np.isinf(lo_a).any() or np.isinf(lo_b).any():
                continue  # unbounded geometry; no relations
            if bool((lo_a >= lo_b).all() and (hi_a <= hi_b).all()):
                clear = min(float(np.min(lo_a - lo_b)),
                            float(np.min(hi_b - hi_a)))
                out.append({"rel": "inside", "a": a, "b": b,
                            "dist_cm": round(max(0.0, clear) * 100, 2)})
            vgap = float(lo_a[2] - hi_b[2])
            if abs(vgap) <= ON_BAND and _xy_overlap(lo_a, hi_a, lo_b, hi_b):
                out.append({"rel": "on", "a": a, "b": b,
                            "dist_cm": round(max(0.0, vgap) * 100, 2)})
            elif vgap > 0.005 and _xy_overlap(lo_a, hi_a, lo_b, hi_b):
                out.append({"rel": "above", "a": a, "b": b,
                            "dist_cm": round(vgap * 100, 2)})
            gap = _aabb_gap(lo_a, hi_a, lo_b, hi_b)
            if gap < NEAR_GAP:
                out.append({"rel": "near", "a": a, "b": b,
                            "dist_cm": round(gap * 100, 2)})
    return out


def plan_to_motion(model, data, plan, derived_from=None, on_sample=None):
    """Execute plan steps on a COPY of data; return the §4 Motion dict.

    `on_sample(model, sim_data, prim_state, t)` is an optional extra hook
    invoked after each contract sample (used by demos for extra tracks).
    Raises PrimitiveError on unknown primitives, bad args, or IK failures.
    """
    sim = mujoco.MjData(model)
    mujoco.mj_copyData(sim, model, data)
    state, clock = PrimState(), Clock()
    initial = {b: sim.body(b).xpos.copy() for b in _free_bodies(model)}

    path, t, held, tilt, speed, step_ids = [], [], [], [], [], []

    def sampler(ts: float) -> None:
        path.append(_grasp_pose(model, sim))
        t.append(round(float(ts), 4))
        held.append(state.held)
        tilt.append(round(float(state.tilt_deg), 2))
        speed.append(state.speed)
        if on_sample is not None:
            on_sample(model, sim, state, ts)

    for step in plan:
        prim = step.get("primitive")
        if prim not in PRIMITIVES:
            raise PrimitiveError(
                f"step {step.get('id')}: unknown primitive {prim!r}")
        args = step.get("args", {}) or {}
        try:
            if prim == "move_to":
                PRIMITIVES[prim](model, sim, state, args["pose"],
                                 clock, sampler)
            elif prim == "grasp":
                PRIMITIVES[prim](model, sim, state, args["object_id"],
                                 clock, sampler)
            elif prim == "tilt":
                PRIMITIVES[prim](model, sim, state, args["deg"],
                                 clock, sampler)
            elif prim == "set_speed":
                PRIMITIVES[prim](model, sim, state, args["speed"],
                                 clock, sampler)
            else:
                PRIMITIVES[prim](model, sim, state, clock, sampler)
        except KeyError as e:
            raise PrimitiveError(
                f"step {step.get('id')}: missing arg {e}") from e
        except PrimitiveError as e:
            raise PrimitiveError(f"step {step.get('id')}: {e}") from e
        step_ids.append(step.get("id"))
        if state.stopped:
            break

    moved = [b for b in initial
             if float(np.linalg.norm(sim.body(b).xpos - initial[b])) > MOVED_EPS
             or b in set(held)]
    return {
        "body": "arm",
        "path": path,
        "t": t,
        "held": held,
        "tilt": tilt,
        "speed": speed,
        "end_state": _end_state(model, sim, moved),
        "derived_from": derived_from,
        "step_ids": step_ids,
    }


def demo_knife_handover() -> None:
    model, data = load_scene("kitchen")
    knife_home = data.body("chef_knife").xpos.copy()
    human_home = data.body("human_hand").xpos.copy()
    robot_d, human_d, snaps = [], [], []

    def hook(m, sim, state, ts):
        knife = sim.body("chef_knife").xpos
        robot_d.append(float(np.linalg.norm(
            knife - sim.body("hand").xpos)))
        human_d.append(float(np.linalg.norm(knife - sim.body("human_hand").xpos)))
        snap = mujoco.MjData(m)
        mujoco.mj_copyData(snap, m, sim)
        snaps.append(snap)

    motion = plan_to_motion(model, data, KNIFE_HANDOVER_PLAN,
                            derived_from="demo:knife_handover",
                            on_sample=hook)
    print(f"steps: {len(motion['step_ids'])} {motion['step_ids']}")
    print(f"duration: {motion['t'][-1]:.2f} s, samples: {len(motion['t'])}")
    print(f"held at end: {motion['held'][-1]}")
    print(f"min knife->robot-hand: {min(robot_d):.3f} m")
    print(f"min knife->human-hand: {min(human_d):.3f} m "
          f"(hand parked at {np.round(human_home, 2).tolist()})")
    print(f"knife started at {np.round(knife_home, 3).tolist()}")
    print(f"end_state ({len(motion['end_state'])}):")
    for rel in motion["end_state"]:
        print(f"  {rel['rel']:6s} {rel['a']} {rel['b']} {rel['dist_cm']} cm")

    picks = np.linspace(0, len(snaps) - 1, 6).round().astype(int)
    frames = []
    for i in picks:
        frames.append(render(model, snaps[i], camera="front")["rgb"])
    strip = Image.fromarray(np.concatenate(frames, axis=1))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    strip_path = OUT_DIR / "knife_handover_strip.png"
    strip.save(strip_path)
    print(f"saved {strip_path} {strip.size}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan -> Motion dry-run demo.")
    parser.add_argument("--demo", choices=list(DEMOS))
    args = parser.parse_args()
    if args.demo == "knife_handover":
        demo_knife_handover()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
