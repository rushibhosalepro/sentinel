"""P0-07: after mink IK, the grasp point is within 1 cm of the target."""

import numpy as np

from sim.ik import MUG_RIM_Z, TARGET_HEIGHT, grasp_point, solve_above_mug
from sim.world import load_scene


def test_hover_above_mug():
    model, data = load_scene("day1")
    q, _info = solve_above_mug(model, data.qpos.copy())
    target = data.body("mug").xpos + np.array(
        [0.0, 0.0, MUG_RIM_Z + TARGET_HEIGHT]
    )
    achieved = grasp_point(model, q)
    assert float(np.linalg.norm(achieved - target)) < 0.01
