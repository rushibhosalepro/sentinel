"""P0-07: the day1 scene loads; RGB/depth/seg renders are shaped and non-blank."""

import numpy as np

from sim.world import HEIGHT, WIDTH, load_scene, render

MUG_GEOMS = ("body", "coffee", "handle_v", "handle_top", "handle_bot")


def test_bodies_exist():
    model, _ = load_scene("day1")
    assert model.body("mug").id > 0
    assert model.body("knife").id > 0
    assert model.camera("front").id == 0


def test_renders():
    model, data = load_scene("day1")
    frames = render(model, data)
    rgb, depth, seg = frames["rgb"], frames["depth"], frames["seg"]

    assert rgb.shape == (HEIGHT, WIDTH, 3) and rgb.dtype == np.uint8
    assert rgb.std() > 10  # not a blank frame

    assert depth.shape == (HEIGHT, WIDTH)
    assert np.isfinite(depth).all()
    assert 0.5 < depth.min() < 3.0  # closest surface ~1.3 m (table edge)

    assert seg.shape == (HEIGHT, WIDTH, 2)
    mug_ids = {model.geom(f"mug_{n}").id for n in MUG_GEOMS}
    seen = set(np.unique(seg[:, :, 0])) - {-1}
    assert mug_ids <= seen  # every mug geom visible from the front camera
    assert len(seen) > 10
