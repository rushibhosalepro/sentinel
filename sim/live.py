"""Passive-viewer demo: arm loops home <-> hover-above-mug. (P0-05 viz)

Run with:
    uv run python -m sim.live           # opens a window (needs a display)
    uv run python -m sim.live --check   # headless smoke test (no window)
"""

from __future__ import annotations

import argparse
import time

import mujoco
import numpy as np

from sim.ik import solve_above_mug
from sim.world import load_scene

HALF_PERIOD = 2.0  # seconds each way
FPS = 50


def interpolate(q_home: np.ndarray, q_hover: np.ndarray, alpha: float) -> np.ndarray:
    """Cosine-eased joint interpolation; alpha=0 -> home, 1 -> hover."""
    s = 0.5 - 0.5 * np.cos(np.pi * np.clip(alpha, 0.0, 1.0))
    return (1.0 - s) * q_home + s * q_hover


def solve_poses(model: mujoco.MjModel, q_home: np.ndarray):
    q_hover, info = solve_above_mug(model, q_home)
    print(f"hover solved: iters={info['iters']} pos_err={info['pos_err']:.2e}")
    return q_home, q_hover


def main() -> None:
    parser = argparse.ArgumentParser(description="Loop home <-> hover in a viewer.")
    parser.add_argument("--check", action="store_true",
                        help="solve IK + verify interpolation without a window")
    args = parser.parse_args()

    model, data = load_scene("day1")
    q_home, q_hover = solve_poses(model, data.qpos.copy())
    if args.check:
        assert np.allclose(interpolate(q_home, q_hover, 0.0), q_home)
        assert np.allclose(interpolate(q_home, q_hover, 1.0), q_hover)
        mid = interpolate(q_home, q_hover, 0.5)
        assert np.allclose(mid, 0.5 * (q_home + q_hover))
        print(f"check ok: {model.nq} dofs, "
              f"joint3 home->hover delta {q_hover[2] - q_home[2]:+.3f} rad")
        return

    import mujoco.viewer

    viewer = mujoco.viewer.launch_passive(model, data)
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = model.camera("front").id
    print("Looping home <-> hover. Close the window to stop.")
    dt = 1.0 / FPS
    t0 = time.time()
    next_t = t0
    try:
        while viewer.is_running():
            t = (time.time() - t0) % (2 * HALF_PERIOD)
            phase = t / HALF_PERIOD  # 0..2 (there and back)
            alpha = phase if phase <= 1.0 else 2.0 - phase
            with viewer.lock():
                data.qpos[:] = interpolate(q_home, q_hover, alpha)
                mujoco.mj_forward(model, data)
            viewer.sync()
            next_t += dt
            delay = next_t - time.time()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.time()  # slipped; don't spiral
    except KeyboardInterrupt:
        pass
    finally:
        viewer.close()


if __name__ == "__main__":
    main()
