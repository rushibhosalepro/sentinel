"""C-09: computed liquid safe spot (grid search, no hard-coded coords)."""

import numpy as np

from sentinel.check import load_rulebook
from sentinel.relations import aabb_xz_gap
from sentinel.safe_spot import (CUP_EXCLUDE_M, MARGIN_M, WITHIN_M,
                                candidate_spots, find_safe_spot)
from sim.world import load_scene

DOWN = [0.0, 1.0, 0.0, 0.0]


def _node(pos, props=(), extent=None):
    return {"pos": list(pos), "quat": list(DOWN), "extent": extent,
            "properties": list(props), "owner": "owner", "conf": 1.0}


def _graph(**over):
    g = {"objects": {
        "cup": _node([0.35, 0.06, 0.04]),
        "laptop": _node([0.6, -0.02, 0.0], ("electronic",),
                        [0.16, 0.129, 0.107]),
        "phone": _node([0.45, 0.28, 0.004], ("electronic",),
                       [0.035, 0.07, 0.005]),
        "jug": _node([-0.15, 0.22, 0.1], ("liquid",)),
    }}
    g["objects"].update(over)
    return g


def test_within_mirrors_rulebook():
    rule = next(r for r in load_rulebook()
                if r["id"] == "liquid_above_electronic")
    assert rule["when"]["held_near_electronic"]["within_cm"] == WITHIN_M * 100


def test_candidates_clear_margin_nearest_first():
    spots = candidate_spots(_graph())
    assert spots, "F3-like scene must offer spots"
    need = WITHIN_M + MARGIN_M
    for s in spots:
        pt = np.array(s)
        for eid in ("laptop", "phone"):
            n = _graph()["objects"][eid]
            assert aabb_xz_gap(pt, np.asarray(n["pos"]),
                               n["extent"]) >= need - 1e-9
    dists = [float(np.hypot(s[0] - 0.35, s[1] - 0.06)) for s in spots]
    assert dists == sorted(dists)
    assert all(d >= CUP_EXCLUDE_M for d in dists)


def test_candidates_skip_occupied_and_off_workspace():
    g = _graph(blocker=_node([0.20, 0.15, 0.05], (),
                             [0.03, 0.03, 0.03]))
    spots = candidate_spots(g)
    assert (0.20, 0.15) not in spots  # occupied by blocker
    assert (0.0, 0.0) not in spots  # r < 0.15 inner workspace
    assert (-0.05, 0.0) not in spots


def test_no_cup_returns_empty():
    g = _graph()
    del g["objects"]["cup"]
    assert candidate_spots(g) == []


def test_crowded_counter_returns_none():
    g = {"objects": {
        "cup": _node([0.35, 0.06, 0.04]),
        "wall": _node([0.3, 0.0, 0.0], ("electronic",),
                      [1.0, 1.0, 0.1]),
    }}
    assert candidate_spots(g) == []
    model, data = load_scene("kitchen")
    assert find_safe_spot(model, data, g) is None
