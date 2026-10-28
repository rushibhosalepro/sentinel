"""Live hand_to execution: offer, wait, transfer, retract, retreat.

A hand_to step expands, in our code, into a static sub-plan (slow, optional
knife turn, offer move 25 cm short of the hand, release, retract) plus
runtime interpretation: the person reaches for the held object when the
offer starts, the release waits for their hand (5 cm, timeout keeps
holding), the object transfers to the hand, and the person carries it back
while the arm retracts.

Unlike the baked S-07 scenarios, live execution is a state machine stepped
with an explicit dt: the wait adapts to the actual hand (F1 can move it
mid-plan). Headless tests step it with fixed dt (deterministic); the viewer
steps it with wall dt. The worker pre-plays each hand-over on a scratch
copy so later segments dry-run from the true end state.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim.human import reach_to_counter, retreat_to_park, step_f6
from sim.ik import mat_to_quat_wxyz, quat_wxyz_to_mat
from sim.play import (END_HOLD_T, HAND_BODY, HANDLE_GEOM, HANDOVER_TIMEOUT,
                      KNIFE_BODY, REACH_DURATION, RETREAT_DURATION, ROBOT_HAND,
                      TAKE_DIST, attach_to_hand, drag_with_hand, retract_plan,
                      rollout_frames)
from sim.primitives import PrimitiveError

STANDOFF_M = 0.25  # offer stops this short of the hand, gripper-side
STEP_DT = 0.05  # headless stepping grid

# Reachable ring around the base column (planner prompt workspace).
REACH_MIN, REACH_MAX = 0.15, 0.80
# Offers clamp well inside the ring: at the edge the arm can reach the
# offer turned but can neither lift nor un-turn there (wrist singularity
# at full straight-ahead stretch). The person's analytic arm spans
# PARK_X 1.45 -> hover x 0.62 in S-07, so it bridges the extra gap.
OFFER_MAX = 0.60
Z_MIN, Z_MAX = 0.06, 0.80


class HandoverError(Exception):
    """hand_to cannot run (absent person, empty gripper, unreachable offer)."""


@dataclass
class LiveHandover:
    step_id: str
    person: str
    obj: str
    model: mujoco.MjModel
    data: mujoco.MjData  # live data (viewer) or test data (headless)
    motion: dict
    frames: np.ndarray
    times: np.ndarray
    t_offer: float  # person starts reaching here
    t_rel: float  # release (wait) starts here
    rel_idx: int  # first release sample
    pre_idx: int  # last held sample (frozen while waiting)
    aim: np.ndarray  # static take point (handle, or object origin)
    reach_origin: np.ndarray  # hand pos when triggered
    timeout: float = HANDOVER_TIMEOUT
    hold_t: float = END_HOLD_T
    verbose: bool = True
    # Runtime state (fresh() resets; the worker template never steps).
    tau: float = 0.0
    transferred: bool = False
    transfer_offset: np.ndarray | None = None
    retreat_origin: np.ndarray | None = None
    take_tau: float | None = None
    reported: bool = False
    f6: dict | None = None  # F6 intrusion state (L-07); None when idle

    def fresh(self, data) -> "LiveHandover":
        """Rebind to `data` with pristine runtime state."""
        return dataclasses.replace(
            self, data=data, tau=0.0, transferred=False,
            transfer_offset=None, retreat_origin=None, take_tau=None,
            reported=False, f6=None)


def offer_target(gripper_pos, hand_pos) -> np.ndarray:
    """25 cm short of the hand from the gripper side, clamped reachable."""
    gripper_pos = np.asarray(gripper_pos, dtype=float)
    hand_pos = np.asarray(hand_pos, dtype=float)
    d = hand_pos - gripper_pos
    n = float(np.linalg.norm(d))
    d = d / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])
    target = hand_pos - STANDOFF_M * d
    r = float(np.linalg.norm(target[:2]))
    if r > OFFER_MAX:
        target[:2] *= OFFER_MAX / r
    elif r < REACH_MIN and r > 1e-9:
        target[:2] *= REACH_MIN / r
    target[2] = min(max(float(target[2]), Z_MIN), Z_MAX)
    return target


def blade_faces_person(model, data) -> bool:
    """True when the knife tip is person-side (+x) of the handle."""
    gid = model.geom(HANDLE_GEOM).id
    hx = data.geom_xpos[gid][0]
    bid = model.geom("chef_knife_blade").id
    tip_local = (model.geom_pos[bid]
                 + np.array([model.geom_size[bid][0], 0.0, 0.0]))
    kid = model.body(KNIFE_BODY).id
    tip = data.xpos[kid] + data.xmat[kid].reshape(3, 3) @ tip_local
    return float(tip[0]) > float(hx)


def aim_point(model, data, obj: str) -> np.ndarray:
    """Take point: knife handle, else the object origin."""
    if obj == KNIFE_BODY:
        return data.geom_xpos[model.geom(HANDLE_GEOM).id].copy()
    return data.xpos[model.body(obj).id].copy()


def split_segments(steps: list[dict]) -> list[tuple[str, list | dict]]:
    """Split a plan at hand_to steps into prim runs and hand-overs."""
    segments: list[tuple[str, list | dict]] = []
    run: list[dict] = []
    for s in steps:
        if s["primitive"] == "hand_to":
            if run:
                segments.append(("prims", run))
                run = []
            segments.append(("handover", s))
        else:
            run.append(s)
    if run:
        segments.append(("prims", run))
    return segments


def expand_hand_to(model, data, step: dict, obj: str, home_pos, home_quat,
                   instruction: str) -> list[dict]:
    """Static expansion of one hand_to against the current live state."""
    hid = step["id"]
    serves = step.get("serves_instruction", instruction)
    grip_id = model.body(ROBOT_HAND).id
    grip_pos = data.xpos[grip_id].copy()
    grip_quat = data.xquat[grip_id].copy()
    hand_pos = data.xpos[model.body(HAND_BODY).id].copy()
    target = offer_target(grip_pos, hand_pos)
    offer_quat = grip_quat
    sub = [{"id": f"{hid}:slow",
            "primitive": "set_speed", "args": {"speed": "slow"},
            "serves_instruction": serves,
            "why": "slow for the hand-over"}]
    if obj == KNIFE_BODY and blade_faces_person(model, data):
        turned = (Rotation.from_euler("z", 180, degrees=True)
                  * Rotation.from_matrix(quat_wxyz_to_mat(grip_quat)))
        offer_quat = mat_to_quat_wxyz(turned.as_matrix())
        sub.append({"id": f"{hid}:turn", "primitive": "move_to",
                    "args": {"pose": [*grip_pos, *offer_quat]},
                    "serves_instruction": serves,
                    "why": "turn the handle toward the person"})
    sub.append({"id": f"{hid}:offer", "primitive": "move_to",
                "args": {"pose": [*target, *offer_quat]},
                "serves_instruction": serves,
                "why": "offer 25 cm short of the hand"})
    sub.append({"id": f"{hid}:release", "primitive": "release", "args": {},
                "serves_instruction": serves,
                "why": "release on the take"})
    sub.extend(retract_plan(home_pos, home_quat, target, offer_quat,
                            serves=serves, tag=f"{hid}:",
                            via_pos=grip_pos))
    return sub


def _sample_index(sample_steps: list[str], step_id: str) -> int:
    for i, sid in enumerate(sample_steps):
        if sid == step_id:
            return i
    raise HandoverError(f"expansion lost step {step_id}")


def build_live_handover(model, data, step: dict, obj: str, home_pos,
                        home_quat, instruction: str,
                        timeout: float = HANDOVER_TIMEOUT) -> LiveHandover:
    """Dry-run one hand_to expansion; take resolves live during stepping."""
    hid = step["id"]
    sub = expand_hand_to(model, data, step, obj, home_pos, home_quat,
                         instruction)
    motion, frames, times = rollout_frames(
        model, data, sub, derived_from=f"live:{hid}", initial_held=obj)
    rel_idx = _sample_index(motion["sample_steps"], f"{hid}:release")
    offer_idx = _sample_index(motion["sample_steps"], f"{hid}:offer")
    tmp = mujoco.MjData(model)
    mujoco.mj_copyData(tmp, model, data)
    tmp.qpos[:] = frames[rel_idx]
    mujoco.mj_forward(model, tmp)
    return LiveHandover(
        step_id=hid, person=step["args"]["person"], obj=obj,
        model=model, data=data, motion=motion, frames=frames, times=times,
        t_offer=float(times[offer_idx]), t_rel=float(times[rel_idx]),
        rel_idx=rel_idx, pre_idx=max(rel_idx - 1, 0),
        aim=aim_point(model, tmp, obj),
        reach_origin=data.xpos[model.body(HAND_BODY).id].copy(),
        timeout=timeout)


def _frame_at(times, frames, t):
    idx = int(np.searchsorted(times, t, side="right") - 1)
    return frames[min(max(idx, 0), len(frames) - 1)]


def step_handover(lh: LiveHandover, dt: float) -> tuple[str, bool]:
    """Advance one hand-over by dt; returns (phase, done)."""
    dt = max(float(dt), 0.0)
    lh.tau += dt
    tau, model, data = lh.tau, lh.model, lh.data
    hand_id = model.body(HAND_BODY).id

    def drive_person() -> None:
        if lh.f6 is not None:
            if step_f6(model, data, lh.f6, dt):
                lh.f6 = None
        else:
            reach_to_counter(model, data, tau, lh.t_offer,
                             REACH_DURATION, lh.aim, face=lh.aim,
                             origin=lh.reach_origin)

    if not lh.transferred and lh.take_tau is None:
        if tau < lh.t_rel:
            data.qpos[:] = _frame_at(lh.times, lh.frames, tau)
            drive_person()
            return "offer", False
        data.qpos[:] = lh.frames[lh.pre_idx]  # keep holding
        drive_person()
        gap = float(np.linalg.norm(data.xpos[hand_id] - lh.aim))
        if gap < TAKE_DIST:
            lh.transfer_offset = attach_to_hand(model, data, lh.obj)
            lh.retreat_origin = data.xpos[hand_id].copy()
            lh.transferred = True
            lh.take_tau = tau
            lh.f6 = None
            if lh.verbose:
                print(f"hand-over taken at t={tau:.2f} s")
        elif tau - lh.t_rel >= lh.timeout:
            if lh.f6 is not None:
                drive_person()
            if lh.verbose and not lh.reported:
                lh.reported = True
                print("hand-over not taken (hand never within 5 cm)")
            done = tau >= lh.t_rel + lh.timeout + lh.hold_t
            return "holding", done
        else:
            return "wait", False
    data.qpos[:] = _frame_at(lh.times, lh.frames, tau)
    retreat_to_park(model, data, tau, start_t=lh.take_tau,
                    duration=RETREAT_DURATION, origin=lh.retreat_origin)
    drag_with_hand(model, data, lh.obj, lh.transfer_offset)
    tail = max(float(lh.times[-1]) - lh.take_tau, RETREAT_DURATION)
    return "retreat", tau >= lh.take_tau + tail + lh.hold_t


def concat_motions(motions: list[dict]) -> dict:
    """Concatenate segment motions into the instruction's Motion."""
    out = {"body": "arm", "path": [], "t": [], "held": [], "tilt": [],
           "speed": [], "sample_steps": [], "end_state": [],
           "derived_from": "", "step_ids": []}
    off = 0.0
    for m in motions:
        n = len(m["path"])
        out["path"].extend(m["path"])
        out["t"].extend([round(off + v, 4) for v in m["t"]])
        out["held"].extend(m["held"])
        out["tilt"].extend(m["tilt"])
        out["speed"].extend(m["speed"])
        out["sample_steps"].extend(m["sample_steps"])
        out["step_ids"].extend(m["step_ids"])
        out["end_state"] = m["end_state"]
        off = out["t"][-1] if n else off
        if not out["derived_from"]:
            out["derived_from"] = m["derived_from"]
    return out


def build_execution_script(model, data, steps: list[dict], home_pos,
                           home_quat, instruction: str,
                           present=frozenset({"owner"})):
    """Dry-run segments left-to-right off an evolved scratch.

    Returns (script, None) or (None, why). Each script entry is
    ("prims", {motion, frames, times}) or ("handover", LiveHandover
    template bound to `data`). Hand-overs are pre-played on the scratch
    so later segments start from the true end state; a timeout ends the
    script (the live run reports "not taken").
    """
    script: list[tuple] = []
    scratch = mujoco.MjData(model)
    mujoco.mj_copyData(scratch, model, data)
    motions: list[dict] = []
    held = None
    outcome = "ok"
    for kind, payload in split_segments(steps):
        if kind == "prims":
            try:
                motion, frames, times = rollout_frames(
                    model, scratch, payload,
                    derived_from=f"live:{instruction[:40]}")
            except PrimitiveError as e:
                return None, f"cannot build Motion: {e}"
            script.append(("prims", {"motion": motion, "frames": frames,
                                    "times": times}))
            motions.append(motion)
            scratch.qpos[:] = frames[-1]
            mujoco.mj_forward(model, scratch)
            held = motion["held"][-1]
        else:
            person = payload["args"]["person"]
            if person not in present:
                return None, f"person '{person}' is not here"
            if held is None:
                return None, "hand_to with empty gripper"
            try:
                template = build_live_handover(
                    model, scratch, payload, held, home_pos, home_quat,
                    instruction)
            except (PrimitiveError, HandoverError) as e:
                return None, f"cannot build hand-over: {e}"
            preview = template.fresh(scratch)
            preview.verbose = False
            guard = 0
            while True:
                _, done = step_handover(preview, STEP_DT)
                guard += 1
                if done or guard > 5000:
                    break
            motions.append(template.motion)
            script.append(("handover", {"lh": template.fresh(data),
                                        "hid": payload["id"]}))
            if not preview.transferred:
                outcome = "not taken"
                break
            held = None
    return {"segments": script, "motion": concat_motions(motions),
            "outcome": outcome}, None
