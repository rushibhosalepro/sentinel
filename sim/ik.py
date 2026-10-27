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
from scipy.spatial.transform import Rotation

from sim.world import OUT_DIR, load_scene, render

HAND_BODY = "hand"
MUG_BODY = "mug"
GRASP_OFFSET = 0.10  # grasp point above the hand origin along hand +z (m)
MUG_RIM_Z = 0.096  # mug rim height above the table (coffee surface, day1.xml)
TARGET_HEIGHT = 0.10  # grasp point above the mug rim (m)

# Gripper-down hand orientation (wxyz): hand +z (fingertip axis) -> world -z.
DOWN_QUAT = np.array([0.0, 1.0, 0.0, 0.0])

SOLVER = "daqp"
DT = 0.05
MAX_ITERS = 500
POS_TOL = 1e-4
ORI_TOL = 1e-2  # rad; enforced when orientation_cost > 0


class IKFailed(Exception):
    """mink could not reach the target pose (QP failure or no convergence)."""


def quat_wxyz_to_mat(quat: np.ndarray) -> np.ndarray:
    xyzw = np.asarray(quat, dtype=float)[[1, 2, 3, 0]]
    return Rotation.from_quat(xyzw / np.linalg.norm(xyzw)).as_matrix()


def mat_to_quat_wxyz(mat: np.ndarray) -> np.ndarray:
    xyzw = Rotation.from_matrix(np.asarray(mat, dtype=float)).as_quat()
    return xyzw[[3, 0, 1, 2]]


def grasp_point(model: mujoco.MjModel, q: np.ndarray) -> np.ndarray:
    """World position of the virtual grasp point at configuration q."""
    data = mujoco.MjData(model)
    data.qpos[:] = q
    mujoco.mj_forward(model, data)
    hand_id = model.body(HAND_BODY).id
    return data.xpos[hand_id] + data.xmat[hand_id].reshape(3, 3) @ np.array(
        [0.0, 0.0, GRASP_OFFSET]
    )


def solve_pose(
    model: mujoco.MjModel,
    q0: np.ndarray,
    target_pos: np.ndarray,
    target_quat_wxyz: np.ndarray,
    orientation_cost: float = 1.0,
    max_iters: int = MAX_ITERS,
    pos_tol: float = POS_TOL,
) -> tuple[np.ndarray, dict]:
    """Solve IK for the hand body at (target_pos, target_quat_wxyz).

    Returns (q_solution, info). Raises IKFailed on QP failure or when the
    position (or orientation, if weighted) error stays above tolerance.
    """
    target = mink.SE3.from_rotation_and_translation(
        mink.SO3.from_matrix(quat_wxyz_to_mat(target_quat_wxyz)),
        np.asarray(target_pos, dtype=float),
    )
    config = mink.Configuration(model, np.asarray(q0, dtype=float))
    ee_task = mink.FrameTask(
        HAND_BODY, "body",
        position_cost=1.0, orientation_cost=orientation_cost, lm_damping=1.0,
    )
    ee_task.set_target(target)
    posture = mink.PostureTask(model, cost=1e-3)
    posture.set_target(np.asarray(q0, dtype=float))
    tasks = [ee_task, posture]

    iters = 0
    err = np.zeros(6)
    for iters in range(1, max_iters + 1):
        try:
            vel = mink.solve_ik(config, tasks, DT, SOLVER)
        except mink.NoSolutionFound as e:
            raise IKFailed(f"QP failed at iter {iters}: {e}") from e
        config.integrate_inplace(vel, DT)
        err = ee_task.compute_error(config)
        if float(np.linalg.norm(err[:3])) < pos_tol:
            break
    info = {
        "iters": iters,
        "pos_err": float(np.linalg.norm(err[:3])),
        "ori_err": float(np.linalg.norm(err[3:])),
    }
    if info["pos_err"] > pos_tol:
        raise IKFailed(
            f"pos_err {info['pos_err']:.2e} > {pos_tol:.2e} "
            f"after {iters} iters")
    if orientation_cost > 0 and info["ori_err"] > ORI_TOL:
        raise IKFailed(
            f"ori_err {info['ori_err']:.2e} > {ORI_TOL:.2e} "
            f"after {iters} iters")
    return config.q.copy(), info


def solve_above_mug(
    model: mujoco.MjModel,
    q0: np.ndarray | None = None,
    height: float = TARGET_HEIGHT,
) -> tuple[np.ndarray, dict]:
    """Solve IK so the grasp point sits `height` above the mug rim, gripper down.

    Returns (q_solution, info). Raises IKFailed if the target is unreachable.
    """
    if q0 is None:
        q0 = np.zeros(model.nq)
    data = mujoco.MjData(model)
    data.qpos[:] = q0
    mujoco.mj_forward(model, data)
    grasp_target = data.body(MUG_BODY).xpos + np.array(
        [0.0, 0.0, MUG_RIM_Z + height]
    )

    # With the gripper-down orientation, grasp = hand_pos - (0,0,GRASP_OFFSET).
    hand_target = grasp_target + np.array([0.0, 0.0, GRASP_OFFSET])
    q, info = solve_pose(model, q0, hand_target, DOWN_QUAT)
    info["grasp_target"] = grasp_target
    info["grasp_achieved"] = grasp_point(model, q)
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
