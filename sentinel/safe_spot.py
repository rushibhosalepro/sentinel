"""C-09: computed liquid safe spot (fills the {safe_spot} hint template).

Grid search over counter spots: keep those >= rule range + margin
from every electronic's AABB, clear of other objects, inside the
workspace ring, and where a tilt-30 pour builds through the same
plan_to_motion build preflight uses. Nearest to the cup's current
spot wins; None when the counter is too crowded.
"""

from __future__ import annotations

import numpy as np

from sentinel.preflight import COUNTER_X, COUNTER_Y
from sentinel.relations import aabb_xz_gap
from sim.motion import plan_to_motion
from sim.primitives import PrimitiveError

GRID_STEP = 0.05
WITHIN_M = 0.15  # mirrors liquid_above_electronic within_cm (pinned test)
MARGIN_M = 0.04  # extra clearance over the rule range
OCCUPY_M = 0.05  # edge clearance from other objects
CUP_EXCLUDE_M = 0.05  # skip ~current cup spot (a no-op "move" re-BLOCKs)
R_MIN, R_MAX = 0.15, 0.80  # workspace ring from the base column
EDGE_INSET = 0.05  # keep the cup body on the counter
ABOVE_Z = 0.45
MOUTH_Z = 0.25
STAGING = [0.25, 0.05, 0.45]  # prompt staging point (planner.py)
DOWN = [0.0, 1.0, 0.0, 0.0]  # gripper-down quat (wxyz)


def _axis(lo: float, hi: float) -> list[float]:
    n = int(round((hi - lo) / GRID_STEP))
    return [round(lo + i * GRID_STEP, 2) for i in range(n + 1)]


_XS = _axis(COUNTER_X[0] + EDGE_INSET, COUNTER_X[1] - EDGE_INSET)
_YS = _axis(COUNTER_Y[0] + EDGE_INSET, COUNTER_Y[1] - EDGE_INSET)


def _node_xy(node) -> np.ndarray:
    return np.asarray(node["pos"][:2], dtype=float)


def _ext(node) -> list:
    return node.get("extent") or [0.0, 0.0, 0.0]


def candidate_spots(graph: dict) -> list[tuple[float, float]]:
    """Grid spots passing the geometry filters, nearest-to-cup first.

    Pure graph geometry (no IK): electronics range + margin, object
    occupancy, workspace ring + counter rect. No cup in graph -> [].
    """
    cup = graph.get("objects", {}).get("cup")
    if cup is None:
        return []
    cpos = _node_xy(cup)
    elec = [(oid, _node_xy(n), _ext(n))
            for oid, n in graph["objects"].items()
            if "electronic" in n.get("properties", [])]
    others = [(oid, _node_xy(n), _ext(n))
              for oid, n in graph["objects"].items() if oid != "cup"]
    need = WITHIN_M + MARGIN_M
    out = []
    for x in _XS:
        for y in _YS:
            pt = np.array([x, y])
            if not R_MIN <= float(np.hypot(x, y)) <= R_MAX:
                continue
            if float(np.linalg.norm(pt - cpos)) < CUP_EXCLUDE_M:
                continue
            if any(aabb_xz_gap(pt, epos, ext) < need
                   for _, epos, ext in elec):
                continue
            if any(aabb_xz_gap(pt, opos, oext) < OCCUPY_M
                   for _, opos, oext in others):
                continue
            out.append((x, y, float(np.linalg.norm(pt - cpos))))
    out.sort(key=lambda s: s[2])
    return [(x, y) for x, y, _ in out]


def pour_builds(model, data, x: float, y: float) -> bool:
    """A tilt-30 pour builds here (same build preflight replays)."""
    plan = [
        {"id": "spot-s1", "primitive": "move_to",
         "args": {"pose": STAGING + DOWN}},
        {"id": "spot-s2", "primitive": "move_to",
         "args": {"pose": [x, y, ABOVE_Z] + DOWN}},
        {"id": "spot-s3", "primitive": "move_to",
         "args": {"pose": [x, y, MOUTH_Z] + DOWN}},
        {"id": "spot-s4", "primitive": "tilt", "args": {"deg": 30}},
        {"id": "spot-s5", "primitive": "tilt", "args": {"deg": 0}},
    ]
    try:
        plan_to_motion(model, data, plan, derived_from="safe_spot")
    except PrimitiveError:
        return False
    return True


def find_safe_spot(model, data, graph: dict) -> tuple | None:
    """Nearest-to-cup spot that passes geometry and builds, else None."""
    for x, y in candidate_spots(graph):
        if pour_builds(model, data, x, y):
            return (x, y)
    return None
