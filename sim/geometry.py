"""Shared world-space geometry: AABBs, gaps, relation thresholds. (G-01)

Used by sim/motion.py (end_state) and graph/scene_graph.py (relations) so
both sides compute the same numbers. Thresholds follow research/02 §3:
ON = bottom within 2 cm of the top + footprint overlap; NEAR = gap < 30 cm
(the exact distance always rides on the edge); ABOVE = higher + overlap.
"""

from __future__ import annotations

import mujoco
import numpy as np

ON_BAND_M = 0.02  # vertical tolerance for ON (m)
NEAR_GAP_M = 0.30  # surface gap that counts as NEAR (m)
ABOVE_MIN_M = 0.005  # minimum vertical gap for ABOVE (m)


def geom_world_aabb(model: mujoco.MjModel, data: mujoco.MjData,
                    geom_id: int):
    """World-frame (lo, hi) box for a geom (None for unbounded types)."""
    typ = model.geom_type[geom_id]
    size = model.geom_size[geom_id]
    rot = data.geom_xmat[geom_id].reshape(3, 3)
    center = data.geom_xpos[geom_id]
    if typ == mujoco.mjtGeom.mjGEOM_MESH:
        mid = model.geom_dataid[geom_id]
        v0, n = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
        verts = model.mesh_vert[v0:v0 + n] * size
        lo_l, hi_l = verts.min(axis=0), verts.max(axis=0)
        corners = np.stack(
            np.meshgrid(*zip(lo_l, hi_l))).reshape(3, -1).T
        world = corners @ rot.T + center
        return world.min(axis=0), world.max(axis=0)
    if typ == mujoco.mjtGeom.mjGEOM_BOX:
        half = size.copy()
    elif typ == mujoco.mjtGeom.mjGEOM_SPHERE:
        half = np.array([size[0]] * 3)
    elif typ == mujoco.mjtGeom.mjGEOM_CAPSULE:
        half = np.array([size[0], size[0], size[0] + size[1]])
    elif typ == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
        half = size.copy()
    elif typ == mujoco.mjtGeom.mjGEOM_CYLINDER:
        half = np.array([size[0], size[0], size[1]])
    else:
        return None  # planes, hfields: unbounded, skipped
    extent = np.abs(rot) @ half
    return center - extent, center + extent


def body_aabb(model: mujoco.MjModel, data: mujoco.MjData,
              body_id: int) -> tuple[np.ndarray, np.ndarray]:
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for g in range(model.ngeom):
        if model.geom_bodyid[g] != body_id:
            continue
        box = geom_world_aabb(model, data, g)
        if box is None:
            continue
        lo = np.minimum(lo, box[0])
        hi = np.maximum(hi, box[1])
    return lo, hi


def aabb_gap(lo1, hi1, lo2, hi2) -> float:
    sep = np.maximum(np.maximum(lo2 - hi1, lo1 - hi2), 0.0)
    return float(np.linalg.norm(sep))


def aabbs_xy_overlap(lo1, hi1, lo2, hi2) -> bool:
    return bool(lo1[0] <= hi2[0] and lo2[0] <= hi1[0]
                and lo1[1] <= hi2[1] and lo2[1] <= hi1[1])


def free_bodies(model: mujoco.MjModel) -> list[str]:
    """Names of bodies attached by a free joint (graspable props)."""
    names = []
    for body_id in range(model.nbody):
        jadr = model.body_jntadr[body_id]
        if jadr >= 0 and model.jnt_type[jadr] == mujoco.mjtJoint.mjJNT_FREE:
            names.append(mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id))
    return names
