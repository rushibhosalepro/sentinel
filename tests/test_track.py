"""G-03: association (label + nearest position) and permanence (stale).
G-04: relations on the SAM graph, same code path as GT."""

import numpy as np
import pytest

from graph.scene_graph import (RELATION_TYPES, init_perception_graph,
                               update_from_detections)
from perception.lift3d import Detection
from sim.geometry import body_aabb
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


def _det_at(model, data, prompt, conf, body):
    """Detection carrying the true AABB (a perfect SAM lift)."""
    lo, hi = body_aabb(model, data, model.body(body).id)
    return Detection(prompt=prompt, conf=conf, box2d=(0, 0, 10, 10),
                     centroid=(lo + hi) / 2, bbox_min=lo, bbox_max=hi,
                     n_points=500)


def _edge(g, a, rel, b):
    for u, v, d in g.edges(data=True):
        if u == a and v == b and d["type"] == rel:
            return d
    raise AssertionError(f"missing {rel} {a} {b}")


def _rels(g):
    return [(u, v, d) for u, v, d in g.edges(data=True)
            if d["type"] in RELATION_TYPES]


def test_relations_from_sam_boxes(ctx):
    model, data, _ = ctx
    g = init_perception_graph(model, data)
    stats = update_from_detections(g, [
        _det_at(model, data, "cup", 0.9, "cup"),
        _det_at(model, data, "pill bottle", 0.8, "pill_bottle"),
    ], ts=1.0)
    assert stats["relations"] > 0
    # Same relations GT reports, derived from SAM-side boxes only.
    assert _edge(g, "cup", "ON", "counter")["dist_cm"] == 0.0
    assert _edge(g, "pill_bottle", "ON", "counter")["dist_cm"] == 0.0
    assert _edge(g, "cup", "NEAR", "pill_bottle")["dist_cm"] == 6.9
    assert _edge(g, "bp:hand", "ABOVE", "counter")["dist_cm"] == 59.3


def test_relation_ts_refresh_no_accumulation(ctx):
    model, data, _ = ctx
    g = init_perception_graph(model, data)
    dets = [_det_at(model, data, "cup", 0.9, "cup")]
    update_from_detections(g, dets, ts=1.0)
    n1 = len(_rels(g))
    update_from_detections(g, dets, ts=2.0)
    rels = _rels(g)
    assert len(rels) == n1  # replaced, not accumulated
    assert all(d["ts"] == 2.0 for _, _, d in rels)


def test_stale_nodes_keep_relations(ctx):
    model, data, _ = ctx
    g = init_perception_graph(model, data)
    update_from_detections(g, [
        _det_at(model, data, "cup", 0.9, "cup"),
        _det_at(model, data, "sponge", 0.8, "sponge"),
    ], ts=1.0)
    stats = update_from_detections(
        g, [_det_at(model, data, "cup", 0.9, "cup")], ts=2.0)
    assert stats["stale"] == ["sponge"]
    # Best-known relations refresh even for the stale node.
    assert _edge(g, "sponge", "ON", "counter")["ts"] == 2.0
