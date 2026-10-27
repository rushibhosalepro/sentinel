"""2D mask + depth -> 3D detections for a MuJoCo camera. (G-03)

MuJoCo depth reads are perpendicular -Z distances in meters, so a pixel
(u, v, d) backprojects to ((u-cx)*d/fx, (v-cy)*d/fy, -d) in the camera
frame, then to world with the camera pose. Rendered arrays are used as-is:
mujoco.Renderer flips RGB, depth, and seg identically, so pixel indexing
is consistent across them.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np

MIN_MASK_PIXELS = 5
MAX_DEPTH_M = 100.0


@dataclass(frozen=True)
class CamParams:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    pos: np.ndarray  # camera origin in world
    mat: np.ndarray  # 3x3 camera axes in world (columns)


@dataclass
class Detection:
    prompt: str
    conf: float
    box2d: tuple[float, float, float, float]
    centroid: np.ndarray  # world (3,)
    bbox_min: np.ndarray  # world (3,)
    bbox_max: np.ndarray  # world (3,)
    n_points: int


def camera_params(model: mujoco.MjModel, data: mujoco.MjData,
                  camera: str = "front",
                  width: int = 640, height: int = 480) -> CamParams:
    cid = model.camera(camera).id
    fovy = float(model.cam_fovy[cid])
    f = (height / 2.0) / np.tan(np.radians(fovy) / 2.0)
    return CamParams(
        width=width, height=height, fx=f, fy=f,
        cx=width / 2.0, cy=height / 2.0,
        pos=data.cam_xpos[cid].copy(),
        mat=data.cam_xmat[cid].reshape(3, 3).copy(),
    )


def backproject(u: np.ndarray, v: np.ndarray, d: np.ndarray,
                cam: CamParams) -> np.ndarray:
    # Note the v sign: array row 0 is the TOP of the image (the renderer
    # flips GL output), while camera +Y points up.
    u, v, d = (np.asarray(a, dtype=float) for a in (u, v, d))
    pts_cam = np.stack([(u - cam.cx) * d / cam.fx,
                        (cam.cy - v) * d / cam.fy,
                        -d], axis=-1)
    return cam.pos + pts_cam @ cam.mat.T


def project(points: np.ndarray, cam: CamParams):
    """World (3,) or (N,3) -> (u, v, d); d is perpendicular depth (m).

    (u, v) are pixel coords with row 0 at the image top, matching the
    renderer's flipped output arrays.
    """
    pts = np.asarray(points, dtype=float)
    rel = pts - cam.pos
    pcam = rel @ cam.mat
    d = -pcam[..., 2]
    u = cam.fx * pcam[..., 0] / d + cam.cx
    v = cam.cy - cam.fy * pcam[..., 1] / d
    return u, v, d


def lift_mask(mask: np.ndarray, depth: np.ndarray, cam: CamParams,
              min_pixels: int = MIN_MASK_PIXELS):
    """Lift a boolean image mask to (centroid, bbox_min, bbox_max, n).

    Median centroid (robust to mask bleed); min/max box. Returns None when
    fewer than min_pixels valid depth readings fall inside the mask.
    """
    valid = (np.asarray(mask, dtype=bool)
             & np.isfinite(depth)
             & (depth > 1e-3) & (depth < MAX_DEPTH_M))
    vs, us = np.nonzero(valid)
    if len(us) < min_pixels:
        return None
    pts = backproject(us, vs, depth[vs, us], cam)
    return (np.median(pts, axis=0), pts.min(axis=0), pts.max(axis=0), len(us))
