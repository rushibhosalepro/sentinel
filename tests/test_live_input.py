"""Input handling for loop.live: control chars are stripped, empties ignored."""

import numpy as np

from graph.scene_graph import load_props
from loop.live import CUP_NEAR_LAPTOP, KEY_F3, KEY_F4, _apply_preset, _clean_line
from sentinel.graph_view import graph_snapshot
from sim.world import load_scene


def test_clean_line_strips_controls():
    assert _clean_line("give me the knife") == "give me the knife"
    assert _clean_line("  wave hi  ") == "wave hi"
    assert _clean_line("\x16") == ""  # pasted ^V
    assert _clean_line("\x00\x01\x02") == ""
    assert _clean_line("  \x16  ") == ""
    assert _clean_line("") == ""
    assert _clean_line("pour\x00 water") == "pour water"
    assert _clean_line("quit") == "quit"


def test_f3_f4_keycodes():
    assert (KEY_F3, KEY_F4) == (292, 293)


def test_apply_preset_moves_and_restores_cup():
    model, data = load_scene("kitchen")
    home = {"qpos": data.qpos.copy()}
    cid = model.body("cup").id
    cup0 = data.xpos[cid].copy()
    _apply_preset(model, data, home, "cup_next_to_laptop")
    assert np.allclose(data.xpos[cid], CUP_NEAR_LAPTOP)
    # Close enough to matter: inside the liquid rule's AABB trigger range
    # (origin distance misses the 32 cm-wide laptop).
    lnode = graph_snapshot(model, data, load_props())["objects"]["laptop"]
    le, (ex, ey, _) = np.asarray(lnode["pos"][:2]), lnode["extent"]
    dx = max(0.0, abs(data.xpos[cid][0] - le[0]) - ex)
    dy = max(0.0, abs(data.xpos[cid][1] - le[1]) - ey)
    assert float(np.hypot(dx, dy)) <= 0.15
    _apply_preset(model, data, home, "default")
    assert np.allclose(data.xpos[cid], cup0)
