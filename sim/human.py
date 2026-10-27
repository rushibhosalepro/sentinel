"""Scripted human-hand paths driving the human_hand mocap body. (S-05)

Paths are time-parametrised position scripts with cosine easing: before
start_t the hand holds its park pose (read from the model), then it moves
to the target over `duration`, then it holds. Orientation stays identity
(wrist articulation is out of scope for Phase 1).

The live loop calls these every step with the current sim time; the Phase 1
demo uses reach_to_counter to bring the hand to the handover point.
"""

from __future__ import annotations

import mujoco
import numpy as np

HAND_BODY = "human_hand"
HANDOVER_HOVER = (0.62, -0.35, 0.33)  # near the S-04 handover point


def _mocap_id(model: mujoco.MjModel) -> int:
    return model.body_mocapid[model.body(HAND_BODY).id]


def park_pos(model: mujoco.MjModel) -> np.ndarray:
    """The hand's parked position (initial mocap pos from the model)."""
    tmp = mujoco.MjData(model)
    return tmp.mocap_pos[_mocap_id(model)].copy()


def _ease(alpha: float) -> float:
    alpha = min(1.0, max(0.0, alpha))
    return 0.5 - 0.5 * np.cos(np.pi * alpha)


def _drive(model, data, origin, target, t, start_t, duration) -> None:
    alpha = 0.0 if duration <= 0 else (t - start_t) / duration
    pos = (1.0 - _ease(alpha)) * np.asarray(origin, dtype=float) \
        + _ease(alpha) * np.asarray(target, dtype=float)
    mid = _mocap_id(model)
    data.mocap_pos[mid] = pos
    data.mocap_quat[mid] = (1.0, 0.0, 0.0, 0.0)
    mujoco.mj_forward(model, data)


def reach_to_counter(model, data, t: float, start_t: float = 0.0,
                     duration: float = 2.0,
                     target=HANDOVER_HOVER) -> None:
    """Reach toward `target` over [start_t, start_t+duration].

    Before start_t the hand holds wherever it is (no teleports); after the
    window it holds the target exactly.
    """
    _drive(model, data, data.mocap_pos[_mocap_id(model)].copy(),
           target, t, start_t, duration)


def retreat_to_park(model, data, t: float, start_t: float = 0.0,
                    duration: float = 2.0) -> None:
    """Return from the current pose to the model's park pose."""
    _drive(model, data, data.mocap_pos[_mocap_id(model)].copy(),
           park_pos(model), t, start_t, duration)
