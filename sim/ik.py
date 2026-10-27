"""Mink IK for the day-1 scene: gripper 10 cm above the mug. (P0-05)

End-effector note: menagerie's `panda.xml` defines no site (only the `mjx_*`
variants define a "gripper" site), and MJCF can't inject a site into an
included body. So we track a *virtual grasp point*: the `hand`-body frame
translated +GRASP_OFFSET along its +z axis — the same placement as the
menagerie mjx "gripper" site (0, 0, 0.1), between the fingertips.

Usage:
    uv run python -m sim.ik --demo   # solves IK, saves out/day1_ik.png
"""

from __future__ import annotations

import argparse

import mink
import mujoco
import numpy as np
from PIL import Image

from sim.world import OUT_DIR, load_scene, render

HAND_BODY = "hand"
MUG_BODY = "mug"
GRASP_OFFSET = 0.10  # grasp point above the hand origin along hand +z (m)
TARGET_HEIGHT = 0.10  # grasp point above the mug body origin (m)

SOLVER = "daqp"
DT = 0.05
MAX_ITERS = 500
POS_TOL = 1e-4


def grasp_point(model: mujoco.MjModel, q: np.ndarray) -> np.ndarray:
    """World position of the virtual grasp point at configuration q."""
    data = mujoco.MjData(model)
    data.qpos[:] = q
    mujoco.mj_forward(model, data)
    hand_id = model.body(HAND_BODY).id
    return data.xpos[hand_id] + data.xmat[hand_id].reshape(3, 3) @ np.array(
        [0.0, 0.0, GRASP_OFFSET]
    )


def solve_above_mug(
    model: mujoco.MjModel,
    q0: np.ndarray | None = None,
    height: float = TARGET_HEIGHT,
) -> tuple[np.ndarray, dict]:
    """Solve IK so the grasp point sits `height` above the mug, gripper down.

    Returns (q_solution, info). Raises mink.NoSolutionFound if a QP fails.
    """
    if q0 is None:
        q0 = np.zeros(model.nq)
    data = mujoco.MjData(model)
    data.qpos[:] = q0
    mujoco.mj_forward(model, data)
    grasp_target = data.body(MUG_BODY).xpos + np.array([0.0, 0.0, height])

    # Gripper-down hand orientation: hand +z (fingertip axis) -> world -z.
    # With this orientation, grasp = hand_pos - (0,0,GRASP_OFFSET).
    down = mink.SO3.from_x_radians(np.pi)
    hand_target = grasp_target + np.array([0.0, 0.0, GRASP_OFFSET])
    target = mink.SE3.from_rotation_and_translation(down, hand_target)

    config = mink.Configuration(model, q0)
    ee_task = mink.FrameTask(
        HAND_BODY, "body",
        position_cost=1.0, orientation_cost=1.0, lm_damping=1.0,
    )
    ee_task.set_target(target)
    posture = mink.PostureTask(model, cost=1e-3)
    posture.set_target(q0)
    tasks = [ee_task, posture]

    iters = 0
    for iters in range(1, MAX_ITERS + 1):
        vel = mink.solve_ik(config, tasks, DT, SOLVER)
        config.integrate_inplace(vel, DT)
        err = ee_task.compute_error(config)
        if float(np.linalg.norm(err[:3])) < POS_TOL:
            break
    q = config.q.copy()
    achieved = grasp_point(model, q)
    info = {
        "iters": iters,
        "pos_err": float(np.linalg.norm(err[:3])),
        "ori_err": float(np.linalg.norm(err[3:])),
        "grasp_target": grasp_target,
        "grasp_achieved": achieved,
    }
    return q, info


def main() -> None:
    parser = argparse.ArgumentParser(description="IK demo: hover over the mug.")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return
    model, data = load_scene("day1")
    q, info = solve_above_mug(model, data.qpos.copy())
    data.qpos[:] = q
    mujoco.mj_forward(model, data)
    rgb = render(model, data)["rgb"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "day1_ik.png"
    Image.fromarray(rgb).save(path)
    print(f"saved {path}")
    print(f"iters={info['iters']} pos_err={info['pos_err']:.2e} "
          f"ori_err={info['ori_err']:.2e}")
    print(f"grasp target   {info['grasp_target']}")
    print(f"grasp achieved {info['grasp_achieved']}")


if __name__ == "__main__":
    main()
