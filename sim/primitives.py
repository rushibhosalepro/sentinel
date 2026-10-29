"""Robot action primitives for the kitchen scene. (S-03, PLAN §4)

move_to(pose), grasp(object_id), release(), tilt(deg), set_speed(slow|normal),
stop() — the only actions a planner may use.

Kinematic rollout model: primitives write joint/object qpos directly and call
mj_forward; the sim is NEVER stepped here. Time is virtual (a Clock) and
motion.py samples the rollout through on_sample callbacks. Grasp is a
kinematic attach (the held body is dragged with the gripper); a released
object freezes where it is. Honest contact dynamics — falls, spills, drops —
belong to Phase 3 preflight (sentinel/preflight.py), not to this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim.ik import (
    DOWN_QUAT,
    HAND_BODY,
    IKFailed,
    grasp_point,
    mat_to_quat_wxyz,
    quat_wxyz_to_mat,
    solve_pose,
)

SPEEDS = {"slow": 0.15, "normal": 0.5}  # Cartesian m/s
ORI_SPEED = 1.5  # rad/s for reorientation within a move_to
SAMPLE_DT = 0.05  # caller sampling cadence (s)
TILT_RATE = 90.0  # deg/s
FINGER_DUR = 0.4  # grasp/release finger animation (s)
OPEN_Q = 0.04  # finger slide: fully open (matches home key)
CLOSED_Q = 0.02  # finger slide: closed around a handle-sized object
GRASP_REACH = 0.06  # max grasp-point to object-geom-center distance (m)
FINGER_JOINTS = ("finger_joint1", "finger_joint2")


class PrimitiveError(Exception):
    """Base class for honest primitive failures (bad aim, bad args)."""


class GraspFailed(PrimitiveError):
    """grasp() called while holding, out of reach, or on a missing object."""


class Clock:
    """Mutable virtual-time cell shared by a primitive rollout."""

    def __init__(self) -> None:
        self.t = 0.0


@dataclass
class PrimState:
    held: str | None = None
    hold_offset: np.ndarray | None = None  # T_grasp^-1 @ T_obj at grasp time
    tilt_deg: float = 0.0  # hand fingertip-axis angle from straight down
    speed: str = "normal"
    stopped: bool = False
    tilt_cache: dict = field(default_factory=dict)  # round(deg, 1) -> qpos
    tilt_last_q: np.ndarray | None = None  # config when the last tilt ended


def _hand_pose(model: mujoco.MjModel, data: mujoco.MjData):
    hand_id = model.body(HAND_BODY).id
    return (data.xpos[hand_id].copy(),
            data.xquat[hand_id].copy())


def _se3(pos: np.ndarray, quat_wxyz: np.ndarray) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = quat_wxyz_to_mat(quat_wxyz)
    t[:3, 3] = pos
    return t


def _tilt_of_quat(quat_wxyz: np.ndarray) -> float:
    """Angle (deg) between the hand fingertip axis (+z) and straight down."""
    z = quat_wxyz_to_mat(quat_wxyz) @ np.array([0.0, 0.0, 1.0])
    cosang = float(np.clip(-z[2], -1.0, 1.0))
    return float(np.degrees(np.arccos(cosang)))


def _finger_adrs(model: mujoco.MjModel) -> list[int]:
    return [model.jnt(name).qposadr for name in FINGER_JOINTS]


def free_qposadr(model: mujoco.MjModel, body_name: str) -> int:
    """qpos address of a free-joint body's (pos, quat); GraspFailed if none."""
    body_id = model.body(body_name).id
    jadr = model.body_jntadr[body_id]
    if jadr < 0 or model.jnt_type[jadr] != mujoco.mjtJoint.mjJNT_FREE:
        raise GraspFailed(f"{body_name} has no free joint (not graspable)")
    return model.jnt_qposadr[jadr]


def _free_qposadr(model: mujoco.MjModel, body_name: str) -> int:
    return free_qposadr(model, body_name)


def _drag_held(model: mujoco.MjModel, data: mujoco.MjData, state: PrimState):
    """Re-apply the grasp offset so the held body follows the gripper."""
    if state.held is None:
        return
    pos, quat = _hand_pose(model, data)
    t = _se3(pos, quat) @ state.hold_offset
    adr = _free_qposadr(model, state.held)
    data.qpos[adr:adr + 3] = t[:3, 3]
    data.qpos[adr + 3:adr + 7] = mat_to_quat_wxyz(t[:3, :3])


def _rollout(duration: float, clock: Clock, on_sample, apply) -> None:
    """Linear-then-sample rollout: constant honest speed, dense sampling."""
    t0 = clock.t
    n = max(1, int(np.ceil(duration / SAMPLE_DT)))
    for i in range(n + 1):
        alpha = i / n
        apply(alpha)
        clock.t = t0 + alpha * duration
        on_sample(clock.t)


def _object_geom_ids(model: mujoco.MjModel, body_name: str) -> list[int]:
    body_id = model.body(body_name).id
    return [g for g in range(model.ngeom)
            if model.geom_bodyid[g] == body_id]


def move_to(model, data, state, pose, clock, on_sample) -> None:
    """IK to a [x, y, z, qw, qx, qy, qz] hand pose at the current speed.

    Position tolerance is 1 mm: grasps need 6 cm and placements cm, so
    sub-mm misses are noise, not traps (real traps miss by cm).
    """
    pose = np.asarray(pose, dtype=float)
    if pose.shape != (7,):
        raise PrimitiveError(f"pose must have 7 elements, got {pose.shape}")
    pos, quat = pose[:3], pose[3:] / np.linalg.norm(pose[3:])
    q0 = data.qpos.copy()
    try:
        q_target, _ = solve_pose(model, q0, pos, quat, pos_tol=1e-3)
    except IKFailed as e:
        raise PrimitiveError(f"move_to {pos}: {e}") from e
    hand_pos, hand_quat = _hand_pose(model, data)
    cart = float(np.linalg.norm(pos - hand_pos))
    r_now = Rotation.from_quat(hand_quat[[1, 2, 3, 0]])
    r_tgt = Rotation.from_quat(quat[[1, 2, 3, 0]])
    ori = float((r_tgt * r_now.inv()).magnitude())
    duration = max(cart / SPEEDS[state.speed], ori / ORI_SPEED)

    def apply(alpha: float) -> None:
        data.qpos[:] = (1.0 - alpha) * q0 + alpha * q_target
        mujoco.mj_forward(model, data)
        _drag_held(model, data, state)
        mujoco.mj_forward(model, data)

    _rollout(duration, clock, on_sample, apply)
    state.tilt_deg = _tilt_of_quat(_hand_pose(model, data)[1])


def capture_hold(model, data, state, object_id) -> None:
    """Start holding: T_hand^-1 @ T_obj from the current poses (no checks)."""
    adr = _free_qposadr(model, object_id)  # raises if not graspable
    hand_pos, hand_quat = _hand_pose(model, data)
    obj_pos = data.qpos[adr:adr + 3]
    obj_quat = data.qpos[adr + 3:adr + 7]
    state.hold_offset = (np.linalg.inv(_se3(hand_pos, hand_quat))
                         @ _se3(obj_pos, obj_quat))
    state.held = object_id


def grasp(model, data, state, object_id, clock, on_sample) -> None:
    """Kinematic attach: fails unless the gripper is within GRASP_REACH
    of the object surface (approximate), already holding, or unknown."""
    if state.held is not None:
        raise GraspFailed(f"already holding {state.held}")
    try:
        geom_ids = _object_geom_ids(model, object_id)
    except KeyError as e:
        raise GraspFailed(f"unknown object {object_id!r}") from e
    if not geom_ids:
        raise GraspFailed(f"{object_id} has no geoms")
    adr = _free_qposadr(model, object_id)  # raises if not graspable
    gp = grasp_point(model, data.qpos.copy())
    # Approximate distance to the object surface: center distance minus the
    # geom's bounding-sphere radius. Catches gross misses (grasping thin
    # air); fine grasp feasibility is out of scope for kinematic rollout.
    dist = min(float(np.linalg.norm(data.geom_xpos[g] - gp)
                     - np.linalg.norm(model.geom_size[g]))
               for g in geom_ids)
    if dist > GRASP_REACH:
        raise GraspFailed(
            f"{object_id} {dist:.2f} m from gripper (reach {GRASP_REACH} m)")

    capture_hold(model, data, state, object_id)

    fadrs = _finger_adrs(model)
    f0 = data.qpos[fadrs].copy()

    def apply(alpha: float) -> None:
        data.qpos[fadrs] = (1.0 - alpha) * f0 + alpha * CLOSED_Q
        mujoco.mj_forward(model, data)
        _drag_held(model, data, state)
        mujoco.mj_forward(model, data)

    _rollout(FINGER_DUR, clock, on_sample, apply)


def release(model, data, state, clock, on_sample) -> None:
    """Detach. The object freezes in place (no drop dynamics in rollout)."""
    if state.held is None:
        on_sample(clock.t)
        return
    state.held = None
    state.hold_offset = None
    fadrs = _finger_adrs(model)
    f0 = data.qpos[fadrs].copy()

    def apply(alpha: float) -> None:
        data.qpos[fadrs] = (1.0 - alpha) * f0 + alpha * OPEN_Q
        mujoco.mj_forward(model, data)

    _rollout(FINGER_DUR, clock, on_sample, apply)


def tilt(model, data, state, deg, clock, on_sample) -> None:
    """Pitch the hand to an absolute `deg` from straight-down (pour angle).

    Solved in <=30° hops from the current config: a single 70° endpoint
    solve gets seed-trapped at extended reach (same disease as the 180°
    knife flip, same cure as the retract half-turns). Position tolerance
    is 2.5 cm for tilt only: the recorded pour plans plateau the
    solver at ~2.0 cm from the tilted target, so 1 cm still fails.
    A pour is an orientation task; the angle keeps ORI_TOL, the mouth
    may shift a little. (B-08)

    Round trips replay: each visited angle records its config, and a
    tilt back to a visited angle with an undisturbed arm replays the
    recorded config instead of solving fresh (fresh solves wander ~3 rad
    and strand the arm in joint limits). Anything between the tilts
    falls back to a fresh solve.
    """
    deg = float(deg)
    span = deg - state.tilt_deg
    if abs(span) < 1e-9:
        on_sample(clock.t)
        return

    def blend(q0, q1, duration) -> None:
        def apply(alpha: float) -> None:
            data.qpos[:] = (1.0 - alpha) * q0 + alpha * q1
            mujoco.mj_forward(model, data)
            _drag_held(model, data, state)
            mujoco.mj_forward(model, data)
        _rollout(duration, clock, on_sample, apply)

    q_entry = data.qpos.copy()
    want = round(deg, 1)
    cache = state.tilt_cache
    if (want in cache and state.tilt_last_q is not None
            and np.allclose(q_entry, state.tilt_last_q)):
        blend(q_entry, cache[want], abs(span) / TILT_RATE)
        state.tilt_deg = _tilt_of_quat(_hand_pose(model, data)[1])
        state.tilt_last_q = data.qpos.copy()
        return
    cache[round(state.tilt_deg, 1)] = q_entry
    n = max(1, int(np.ceil(abs(span) / 30.0)))
    r_down = quat_wxyz_to_mat(DOWN_QUAT)
    hand_pos, _ = _hand_pose(model, data)
    for k in range(1, n + 1):
        d = state.tilt_deg + span * k / n
        r_tgt = (r_down
                 @ Rotation.from_euler("y", d, degrees=True).as_matrix())
        q0 = data.qpos.copy()
        try:
            q_target, _ = solve_pose(model, q0, hand_pos,
                                     mat_to_quat_wxyz(r_tgt),
                                     pos_tol=2.5e-2)
        except IKFailed as e:
            raise PrimitiveError(f"tilt({deg}): {e}") from e
        blend(q0, q_target, abs(span) / n / TILT_RATE)
        cache[round(d, 1)] = data.qpos.copy()
    state.tilt_deg = _tilt_of_quat(_hand_pose(model, data)[1])
    state.tilt_last_q = data.qpos.copy()


def set_speed(model, data, state, speed, clock, on_sample) -> None:
    """Set the Cartesian speed for subsequent moves (instant)."""
    if speed not in SPEEDS:
        raise PrimitiveError(
            f"speed must be one of {sorted(SPEEDS)}, got {speed!r}")
    state.speed = speed
    on_sample(clock.t)


def stop(model, data, state, clock, on_sample) -> None:
    """Halt the plan: motion.py executes no further steps after this."""
    state.stopped = True
    on_sample(clock.t)


PRIMITIVES = {
    "move_to": move_to,
    "grasp": grasp,
    "release": release,
    "tilt": tilt,
    "set_speed": set_speed,
    "stop": stop,
}
