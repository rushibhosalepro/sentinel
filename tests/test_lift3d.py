"""G-03: lift round-trips against simulator ground truth (no network)."""

import numpy as np

from perception.lift3d import backproject, camera_params, lift_mask, project
from sim.world import load_scene, render


def test_project_backproject_roundtrip():
    model, data = load_scene("kitchen")
    cam = camera_params(model, data)
    rng = np.random.default_rng(0)
    pts = np.array([[0.3, 0.0, 0.2]]) + rng.uniform(-0.3, 0.3, (20, 3))
    pts[:, 2] = np.abs(pts[:, 2]) + 0.05  # in front of the counter
    u, v, d = project(pts, cam)
    assert np.all(d > 0)
    back = backproject(u, v, d, cam)
    assert np.allclose(back, pts, atol=1e-9)


def test_lift_sim_masks_match_gt():
    model, data = load_scene("kitchen")
    frames = render(model, data, camera="front")
    depth, seg = frames["depth"], frames["seg"]
    cam = camera_params(model, data)
    for obj, tol in (("cup", 0.05), ("apple", 0.05), ("laptop", 0.08)):
        body_id = model.body(obj).id
        geom_ids = {g for g in range(model.ngeom)
                    if model.geom_bodyid[g] == body_id}
        mask = np.isin(seg[:, :, 0], list(geom_ids))
        assert mask.sum() > 100, obj
        centroid, lo, hi, n = lift_mask(mask, depth, cam)
        # Reference: mean GT geom center (body origins sit at counter level,
        # while the lifted centroid is a visible-surface median).
        ref = np.array([data.geom_xpos[g] for g in geom_ids]).mean(axis=0)
        err = float(np.linalg.norm(centroid - ref))
        assert err < tol, (obj, err)
        assert n == mask.sum()


def test_lift_rejects_empty_masks():
    model, data = load_scene("kitchen")
    cam = camera_params(model, data)
    depth = np.full((480, 640), 2.0, dtype=np.float32)
    assert lift_mask(np.zeros((480, 640), bool), depth, cam) is None
    tiny = np.zeros((480, 640), bool)
    tiny[100, 100] = True
    assert lift_mask(tiny, depth, cam) is None


def test_projected_center_lands_on_mask():
    model, data = load_scene("kitchen")
    frames = render(model, data, camera="front")
    cam = camera_params(model, data)
    body_id = model.body("cup").id
    geom_ids = {g for g in range(model.ngeom)
                if model.geom_bodyid[g] == body_id}
    mask = np.isin(frames["seg"][:, :, 0], list(geom_ids))
    u, v, _ = project(data.xpos[body_id], cam)
    u, v = int(round(float(u))), int(round(float(v)))
    assert mask[max(0, v - 3):v + 4, max(0, u - 3):u + 4].any()
