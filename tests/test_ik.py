"""P0-07: after mink IK, the grasp point is within 1 cm of the target.

Plus the IK staged fallback: perceived targets at joint limits still
solve. Live sam run (Nov 2): perceived jug/cup sat 2-4 cm off truth
with joint2 pinned, flooring the solver at 7.5/12.5 mm against the
1 mm tolerance for 4 straight rounds. move_to now retries once at
FALLBACK_TOL (2 cm); orientation tolerance never loosens.
"""

import numpy as np
import pytest

from sim.ik import (
    DOWN_QUAT,
    FALLBACK_TOL,
    IKFailed,
    MUG_RIM_Z,
    TARGET_HEIGHT,
    grasp_point,
    solve_above_mug,
    solve_pose,
)
from sim.world import load_scene


def test_hover_above_mug():
    model, data = load_scene("day1")
    q, _info = solve_above_mug(model, data.qpos.copy())
    target = data.body("mug").xpos + np.array(
        [0.0, 0.0, MUG_RIM_Z + TARGET_HEIGHT]
    )
    achieved = grasp_point(model, q)
    assert float(np.linalg.norm(achieved - target)) < 0.01

# Exact endpoints from the failed live run (seeded from staging).
PERCEIVED = {"jug": [-0.149, 0.184, 0.2],
             "cup": [0.147, 0.18, 0.25]}
TRUTH = {"jug": [-0.15, 0.22, 0.25], "cup": [0.15, 0.2, 0.25]}


@pytest.fixture(scope="module")
def staged():
    model, data = load_scene("kitchen")
    q, _ = solve_pose(model, data.qpos.copy(),
                      np.array([0.25, 0.05, 0.45]), DOWN_QUAT,
                      pos_tol=1e-3)
    return model, q


def test_tight_only_still_fails_perceived(staged):
    model, q1 = staged
    for tgt in PERCEIVED.values():
        with pytest.raises(IKFailed):
            solve_pose(model, q1, np.array(tgt), DOWN_QUAT,
                       pos_tol=1e-3)


@pytest.mark.parametrize("name", ["jug", "cup"])
def test_fallback_solves_perceived(staged, name, capsys):
    model, q1 = staged
    q, info = solve_pose(model, q1, np.array(PERCEIVED[name]),
                         DOWN_QUAT, pos_tol=1e-3,
                         fallback_tol=FALLBACK_TOL)
    assert info.get("slack") is True
    assert info["pos_err"] < FALLBACK_TOL
    assert info["ori_err"] < 1e-2  # orientation never loosens
    assert "IK slack" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["jug", "cup"])
def test_truth_needs_no_fallback(staged, name, capsys):
    model, q1 = staged
    _, info = solve_pose(model, q1, np.array(TRUTH[name]), DOWN_QUAT,
                         pos_tol=1e-3, fallback_tol=FALLBACK_TOL)
    assert info.get("slack", False) is False
    assert info["pos_err"] < 1e-3
    assert "IK slack" not in capsys.readouterr().out


def test_truly_unreachable_still_raises(staged):
    model, q1 = staged
    with pytest.raises(IKFailed):
        solve_pose(model, q1, np.array([2.0, 2.0, 2.0]), DOWN_QUAT,
                   pos_tol=1e-3, fallback_tol=FALLBACK_TOL,
                   max_iters=100)


def test_base_column_target_fails_even_with_fallback(staged):
    # Live s21 [0, 0.15, 0.3] (r = 0.15 m): floors near 7 cm from ANY
    # seed, so tolerance is not the fix — the planner must keep
    # targets r >= 0.20 m (prompt workspace rule). Guards the
    # distinction: slack rescues joint-limit floors, not bad targets.
    model, q1 = staged
    with pytest.raises(IKFailed):
        solve_pose(model, q1, np.array([0.0, 0.15, 0.3]), DOWN_QUAT,
                   pos_tol=1e-3, fallback_tol=FALLBACK_TOL)
