"""Scripted human paths driving the mocap person. (S-05)

The hand paths are time-parametrised position scripts with cosine easing:
before start_t the hand holds its park pose (read from the model), then it
moves to the target over `duration`, then it holds. Every step also orients
the hand along the forearm (fingers point elbow -> wrist, palm down).

The hand belongs to a full procedural person standing at the +x end of the
counter, facing -x: a leaning torso (head, torso, static right arm), static
legs, and a left arm posed every step by two-bone IK from the torso's
shoulder to the scripted hand. The live loop calls these every step with the
current sim time; the Phase 1 demo uses reach_to_counter to bring the hand to
the handover point while the person leans in.
"""

from __future__ import annotations

import mujoco
import numpy as np

HAND_BODY = "human_hand"
TORSO_BODY = "human_torso"
UPPER_ARM_BODY = "human_upper_arm"
FOREARM_BODY = "human_forearm"
HANDOVER_HOVER = (0.62, -0.35, 0.33)  # near the S-04 handover point

# Full-body rig (world-frame metres, matches kitchen.xml).
HIP = np.array([1.44, -0.14, -0.02])  # torso pivot the lean rotates about
SHOULDER_LOCAL = np.array([-0.01, -0.21, 0.57])  # left shoulder in torso frame
UPPER_LEN = 0.32  # shoulder -> elbow
FORE_LEN = 0.34  # elbow -> wrist (palm centre)
LEAN_MAX = np.radians(22.0)  # torso pitch at full reach (rad, toward -x)
PARK_X = 1.45  # hand x at rest (test-pinned); reach spans PARK_X -> hover x
ELBOW_HINT = np.array([0.15, -0.45, -0.88])  # elbow flares out-down-back
FACE_UP_BLEND = 0.08  # up-bias (m) keeping palm-down as the hand arrives


def _mocap_id(model: mujoco.MjModel, body: str = HAND_BODY) -> int:
    return model.body_mocapid[model.body(body).id]


def park_pos(model: mujoco.MjModel) -> np.ndarray:
    """The hand's parked position (initial mocap pos from the model)."""
    tmp = mujoco.MjData(model)
    return tmp.mocap_pos[_mocap_id(model)].copy()


def _ease(alpha: float) -> float:
    alpha = min(1.0, max(0.0, alpha))
    return 0.5 - 0.5 * np.cos(np.pi * alpha)


def _pitch_y(phi: float) -> np.ndarray:
    """Quat (wxyz) for a rotation of phi about +y. Negative tips toward -x."""
    return np.array([np.cos(phi / 2), 0.0, np.sin(phi / 2), 0.0])


def _rot_y(v: np.ndarray, phi: float) -> np.ndarray:
    c, s = float(np.cos(phi)), float(np.sin(phi))
    x, y, z = (float(v[0]), float(v[1]), float(v[2]))
    return np.array([c * x + s * z, y, -s * x + c * z])


def _quat_from_z(d: np.ndarray) -> np.ndarray:
    """Quat (wxyz) rotating +z onto direction d (arm segments aim +z)."""
    d = np.asarray(d, dtype=float)
    d = d / np.linalg.norm(d)
    axis = np.cross([0.0, 0.0, 1.0], d)
    s, c = float(np.linalg.norm(axis)), float(d[2])
    if s < 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0]) if c > 0 \
            else np.array([0.0, 1.0, 0.0, 0.0])
    half = np.arctan2(s, c) / 2.0
    return np.array([np.cos(half), *(np.sin(half) * axis / s)])


def _elbow_pos(s: np.ndarray, w: np.ndarray, hint: np.ndarray) -> np.ndarray:
    """Two-bone IK: elbow between shoulder s and wrist w (exact lengths)."""
    a = np.asarray(w, dtype=float) - np.asarray(s, dtype=float)
    raw = float(np.linalg.norm(a))
    a = a / raw if raw > 1e-9 else np.array([1.0, 0.0, 0.0])
    d = min(max(raw, abs(UPPER_LEN - FORE_LEN) + 1e-6),
            UPPER_LEN + FORE_LEN - 1e-6)
    x = (UPPER_LEN ** 2 - FORE_LEN ** 2 + d ** 2) / (2 * d)
    h = float(np.sqrt(max(UPPER_LEN ** 2 - x ** 2, 0.0)))
    n = np.asarray(hint, dtype=float) - float(np.dot(hint, a)) * a
    if float(np.linalg.norm(n)) < 1e-6:  # hint parallel to arm: any normal
        n = np.cross(a, [0.0, 0.0, 1.0])
        if float(np.linalg.norm(n)) < 1e-6:
            n = np.cross(a, [0.0, 1.0, 0.0])
    n = n / float(np.linalg.norm(n))
    return np.asarray(s, dtype=float) + a * x + n * h


def _quat_from_mat(m: np.ndarray) -> np.ndarray:
    """Quat (wxyz) for a rotation matrix (Shepperd's branches)."""
    m = np.asarray(m, dtype=float)
    t = float(m[0, 0] + m[1, 1] + m[2, 2])
    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        return np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s,
                         (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        return np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s,
                         (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    if m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        return np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s,
                         0.25 * s, (m[1, 2] + m[2, 1]) / s])
    s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
    return np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s,
                     (m[1, 2] + m[2, 1]) / s, 0.25 * s])


def _hand_quat(elbow: np.ndarray, wrist: np.ndarray,
               face=None) -> np.ndarray:
    """Hand orientation: fingers (+y) along elbow -> wrist.

    Palm (-z) faces `face` when given (S-07: the knife handle), settling to
    palm-down as the hand arrives; otherwise palm-down throughout.
    """
    wrist = np.asarray(wrist, dtype=float)
    y = wrist - np.asarray(elbow, dtype=float)
    y = y / float(np.linalg.norm(y))
    refs = []
    if face is not None:
        refs.append(wrist - np.asarray(face, dtype=float)
                    + FACE_UP_BLEND * np.array([0.0, 0.0, 1.0]))
    refs.append(np.array([0.0, 0.0, 1.0]))
    refs.append(np.array([-1.0, 0.0, 0.0]))
    for ref in refs:
        z = ref - float(np.dot(ref, y)) * y
        if float(np.linalg.norm(z)) > 1e-6:
            break
    z = z / float(np.linalg.norm(z))
    x = np.cross(y, z)
    return _quat_from_mat(np.column_stack([x, y, z]))


def pose_body(model: mujoco.MjModel, data: mujoco.MjData,
              face=None) -> None:
    """Pose torso + left arm + hand orientation from the hand mocap target.

    The torso leans toward -x in proportion to the hand's reach, then the
    arm segments are aimed shoulder -> elbow -> wrist and the hand is yawed
    onto the forearm (facing `face` when given). Reads the hand mocap pos
    and writes its quat; the caller runs mj_forward afterwards.
    """
    hand = data.mocap_pos[_mocap_id(model)].copy()
    span = PARK_X - HANDOVER_HOVER[0]
    e = float(np.clip((PARK_X - hand[0]) / span, 0.0, 1.0))
    lean = -LEAN_MAX * e
    mid = _mocap_id(model, TORSO_BODY)
    data.mocap_pos[mid] = HIP
    data.mocap_quat[mid] = _pitch_y(lean)
    s = HIP + _rot_y(SHOULDER_LOCAL, lean)
    el = _elbow_pos(s, hand, ELBOW_HINT)
    mid = _mocap_id(model, UPPER_ARM_BODY)
    data.mocap_pos[mid] = s
    data.mocap_quat[mid] = _quat_from_z((el - s) / UPPER_LEN)
    mid = _mocap_id(model, FOREARM_BODY)
    data.mocap_pos[mid] = el
    data.mocap_quat[mid] = _quat_from_z((hand - el) / FORE_LEN)
    data.mocap_quat[_mocap_id(model)] = _hand_quat(el, hand, face)


def _drive(model, data, origin, target, t, start_t, duration,
           face=None) -> None:
    alpha = 0.0 if duration <= 0 else (t - start_t) / duration
    pos = (1.0 - _ease(alpha)) * np.asarray(origin, dtype=float) \
        + _ease(alpha) * np.asarray(target, dtype=float)
    mid = _mocap_id(model)
    data.mocap_pos[mid] = pos
    pose_body(model, data, face)  # also yaws the hand onto the forearm
    mujoco.mj_forward(model, data)


def reach_to_counter(model, data, t: float, start_t: float = 0.0,
                     duration: float = 2.0, target=HANDOVER_HOVER,
                     face=None, origin=None) -> None:
    """Reach toward `target` over [start_t, start_t+duration].

    Before start_t the hand holds wherever it is (no teleports); after the
    window it holds the target exactly. The palm faces `face` when given.
    `origin` fixes the path start (None = current pose each call, which
    converges faster on fine stepping; a fixed array makes the path a pure
    function of t, identical on every stepping grid).
    """
    if origin is None:
        origin = data.mocap_pos[_mocap_id(model)].copy()
    _drive(model, data, origin, target, t, start_t, duration, face)


def retreat_to_park(model, data, t: float, start_t: float = 0.0,
                    duration: float = 2.0, origin=None) -> None:
    """Return from the current pose to the model's park pose.

    `origin` fixes the path start (None = current pose each call; a fixed
    array makes the path a pure function of t).
    """
    if origin is None:
        origin = data.mocap_pos[_mocap_id(model)].copy()
    _drive(model, data, origin, park_pos(model), t, start_t, duration)
