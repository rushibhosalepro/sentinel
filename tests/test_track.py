"""G-03: association (label + nearest position) and permanence (stale)."""

import numpy as np
import pytest

from graph.scene_graph import init_perception_graph, update_from_detections
from perception.lift3d import Detection
from sim.world import load_scene


@pytest.fixture(scope="module")
def ctx():
    model, data = load_scene("kitchen")
    gt = {b: data.xpos[model.body(b).id].copy()
          for b in ("cup", "jug", "sponge", "sticky_note")}
    return model, data, gt


def _det(prompt, conf, centroid):
    c = np.asarray(centroid, dtype=float)
    return Detection(prompt=prompt, conf=conf, box2d=(0, 0, 10, 10),
                     centroid=c, bbox_min=c - 0.03, bbox_max=c + 0.03,
                     n_points=100)


def test_frame1_spawns_primary_and_alias(ctx):
    model, data, gt = ctx
    g = init_perception_graph(model, data)
    stats = update_from_detections(g, [
        _det("cup", 0.57, gt["cup"]),
        _det("cup", 0.51, gt["jug"]),
        _det("sticky note", 0.74, gt["sticky_note"]),
        _det("sponge", 0.63, gt["sponge"]),
        _det("sticky note", 0.63, gt["sponge"]),  # confusion duplicate
    ], ts=1.0)
    assert ("cup", "cup") in stats["assigned"]
    assert ("cup", "jug") in stats["assigned"]
    assert ("sticky note", "sticky_note") in stats["assigned"]
    assert ("sponge", "sponge") in stats["assigned"]
    assert ("sticky note", "duplicate") in stats["dropped"]
    assert np.allclose(g.nodes["jug"]["pos"], gt["jug"])
    assert g.nodes["cup"]["stale"] is False
    assert g.get_edge_data("cup", "person:owner")


def test_permanence_marks_stale_not_deleted(ctx):
    model, data, gt = ctx
    g = init_perception_graph(model, data)
    update_from_detections(g, [_det("cup", 0.57, gt["cup"]),
                               _det("sponge", 0.63, gt["sponge"])], ts=1.0)
    stats = update_from_detections(
        g, [_det("cup", 0.60, gt["cup"] + (0.001, 0, 0))], ts=2.0)
    assert stats["stale"] == ["sponge"]
    assert "sponge" in g.nodes  # never deleted
    assert g.nodes["sponge"]["stale"] is True
    assert g.nodes["sponge"]["last_seen"] == 1.0
    assert g.nodes["cup"]["stale"] is False
    assert g.nodes["cup"]["last_seen"] == 2.0


def test_unknown_prompt_dropped(ctx):
    model, data, gt = ctx
    g = init_perception_graph(model, data)
    stats = update_from_detections(
        g, [_det("hand", 0.9, gt["cup"])], ts=1.0)
    assert stats["dropped"] == [("hand", "no-listing-object")]
    assert stats["assigned"] == []
