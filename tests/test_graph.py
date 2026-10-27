"""G-01: ground-truth graph relations are correct for known poses."""

import pytest

from graph.scene_graph import build_ground_truth, load_props
from sim.world import load_scene


@pytest.fixture(scope="module")
def gt():
    model, data = load_scene("kitchen")
    return model, data, build_ground_truth(model, data)


def _edge(gt, a, rel, b):
    _, _, g = gt
    for u, v, d in g.edges(data=True):
        if u == a and v == b and d["type"] == rel:
            return d
    raise AssertionError(f"missing {rel} {a} {b}")


def test_resting_contacts(gt):
    assert _edge(gt, "chef_knife", "ON", "counter")["dist_cm"] == 0.0
    assert _edge(gt, "apple", "ON", "plate")["dist_cm"] == 0.0
    assert _edge(gt, "plate", "ON", "counter")["dist_cm"] == 0.0


def test_near_distances(gt):
    assert _edge(gt, "cup", "NEAR", "pill_bottle")["dist_cm"] == 6.9
    assert _edge(gt, "pill_bottle", "NEAR", "cup")["dist_cm"] == 6.9
    _, _, g = gt
    near_sponge = {v for _, v, d in g.out_edges("sponge", data=True)
                   if d["type"] == "NEAR"}
    assert "wine_glass" not in near_sponge


def test_semantics(gt):
    _, _, g = gt
    assert g.nodes["person:owner"]["authorised"] == ["all"]
    assert g.nodes["person:visitor"]["authorised"] == []
    assert _edge(gt, "phone", "OWNED_BY", "person:visitor")
    assert _edge(gt, "chef_knife", "HAS", "prop:sharp")
    assert _edge(gt, "person:owner", "HAS", "bp:human_hand")
    assert g.nodes["bp:hand"]["kind"] == "gripper"
    assert g.nodes["chef_knife"]["conf"] == 1.0


def test_every_edge_has_ts(gt):
    _, data, g = gt
    assert g.number_of_edges() > 0
    for _, _, d in g.edges(data=True):
        assert d["ts"] == data.time


def test_holds_mapping():
    model, data = load_scene("kitchen")
    g = build_ground_truth(model, data, held={"bp:hand": "chef_knife"})
    parallel = g.get_edge_data("bp:hand", "chef_knife").values()
    assert any(d["type"] == "HOLDS" for d in parallel)
    assert g.nodes["chef_knife"]["held"] is True
    assert g.nodes["cup"]["held"] is False
