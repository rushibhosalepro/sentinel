"""G-08/G-09 + wire-up: frames, matching, unknowns, low-conf ASK.

No network: the Spark + SAM-box replies are committed fixtures
(tests/fixtures/perception/*.json, recorded by
`bench/perception_compare.py --save-fixtures`); depth is a synthetic
constant plane, so these tests assert pipeline structure (11
detections, matches, unknowns, graph nodes), not geometry.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from graph.scene_graph import build_perception_graph, load_props
from perception.detect import (
    is_person_label,
    match_label,
    parse_detections,
)
from perception.detections import _box_iou, detections_from_spark
from perception.frames import WIDTH, HEIGHT, coverage
from perception.lift3d import Detection, camera_params
from perception.sam import parse_raw_output
from planner.planner import scene_facts
from sentinel.check import check
from sentinel.graph_view import graph_snapshot
from sim.world import load_scene

FIXTURES = Path(__file__).parent / "fixtures" / "perception"
DOWN = [0.0, 1.0, 0.0, 0.0]


def _motion(grips, held):
    n = len(grips)
    return {
        "body": "arm",
        "path": [np.array([*g[:3], *g[3]], dtype=float) for g in grips],
        "t": [round(i * 0.5, 2) for i in range(n)],
        "held": list(held), "tilt": [0.0] * n,
        "speed": ["normal"] * n,
        "sample_steps": [f"s{i}" for i in range(n)],
        "end_state": [], "derived_from": "test", "step_ids": ["s0"],
    }


def _graph():
    return {
        "objects": {
            "cup": {"pos": [0.15, 0.2, 0.04], "quat": list(DOWN),
                    "properties": [], "owner": "owner", "conf": 1.0},
        },
        "people": {
            "owner": {"hand": [1.0, 0.0, 0.5], "torso": [1.6, 0.4, 0.4],
                      "hand_vel": [0.0, 0.0, 0.0],
                      "authorised": ["all"], "role": "owner"},
        },
    }


def _fixture_dets():
    """Parse the committed Spark fixture (no network)."""
    content = json.loads((FIXTURES / "spark_default.json").read_text())[
        "content"]
    dets, err = parse_detections(content, WIDTH, HEIGHT)
    assert err is None
    return dets


def _fixture_result():
    raw = json.loads((FIXTURES / "sam_box_default.json").read_text())[
        "raw_output"]
    return parse_raw_output(raw)


def _lift_fixture(spark_dets):
    """detections_from_spark over a synthetic constant-depth plane."""
    model, data = load_scene("kitchen")
    cam = camera_params(model, data, "front", WIDTH, HEIGHT)
    depth = np.full((HEIGHT, WIDTH), 2.4, dtype=np.float32)
    return detections_from_spark(spark_dets, _fixture_result(), depth,
                                 cam, load_props())


# --- G-08: the front camera covers the counter ---

def test_front_camera_covers_counter():
    model, data = load_scene("kitchen")
    bad = coverage(model, data)
    assert bad["corners"] == [] and bad["objects"] == []


# --- G-09: label matching ---

@pytest.mark.parametrize("label,oid", [
    ("knife", "chef_knife"),
    ("chef's knife", "chef_knife"),
    ("jug", "jug"),
    ("water jug", "jug"),
    ("cup", "cup"),
    ("laptop", "laptop"),
    ("Pill Bottle", "pill_bottle"),
    ("pill bottle", "pill_bottle"),
    ("wine glass", "wine_glass"),
    ("white plate", "plate"),
    ("apple", "apple"),
    ("sponge", "sponge"),
    ("phone", "phone"),
    ("sticky note", "sticky_note"),
])
def test_match_label(label, oid):
    assert match_label(label, load_props()) == oid


def test_match_label_cup_not_stolen_by_jug():
    # The jug grounds via the "cup" prompt (G-02); the id/label pass
    # must still win for the cup itself.
    assert match_label("cup", load_props()) == "cup"


def test_match_label_unmatched_is_none():
    assert match_label("banana", load_props()) is None


@pytest.mark.parametrize("label", ["person", "human", "hand", "Human Hand"])
def test_person_labels_skipped(label):
    assert is_person_label(label)
    assert not is_person_label("banana")


# --- G-09: detector output parsing ---

def test_parse_detections_rejects_bad_boxes():
    ok, err = parse_detections('{"detections": [{"label": "cup", '
                               '"box": [0, 0, 10, 10]}]}', WIDTH, HEIGHT)
    assert err is None and len(ok) == 1
    for bad in ['nope', '{"detections": {}}',
                '{"detections": [{"label": "", "box": [0, 0, 1, 1]}]}',
                '{"detections": [{"label": "x", "box": [0, 0, 1]}]}',
                '{"detections": [{"label": "x", "box": [5, 5, 5, 9]}]}',
                '{"detections": [{"label": "x", "box": [-1, 0, 9, 9]}]}',
                f'{{"detections": [{{"label": "x", "box": [0, 0, '
                f'{WIDTH + 1}, 9]}}]}}']:
        dets, err = parse_detections(bad, WIDTH, HEIGHT)
        assert dets == [] and err is not None


def test_box_iou():
    assert _box_iou([0, 0, 10, 10], [0, 0, 10, 10]) == pytest.approx(1.0)
    assert _box_iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert 0.0 < _box_iou([0, 0, 10, 10], [5, 5, 15, 15]) < 1.0


# --- G-09: cached-fixture pipeline (no network, no render) ---

def test_fixture_lifts_all_eleven():
    dets = _lift_fixture(_fixture_dets())
    assert len(dets) == 11
    assert {d.match for d in dets} == set(load_props()["objects"])
    assert all(0.0 < d.conf <= 1.0 for d in dets)
    assert all(np.isfinite(d.centroid).all() for d in dets)


def test_fixture_graph_carries_properties():
    model, data = load_scene("kitchen")
    graph = build_perception_graph(model, data,
                                   _lift_fixture(_fixture_dets()))

    def has(node, prop):
        return any(d.get("type") == "HAS" and b == f"prop:{prop}"
                   for _, b, d in graph.edges(node, data=True))

    assert has("chef_knife", "sharp")
    assert has("jug", "liquid")
    assert has("laptop", "electronic")
    assert has("phone", "electronic")


def test_unmatched_label_becomes_unknown_object():
    spark_dets = _fixture_dets()
    spark_dets[0] = dict(spark_dets[0], label="banana")  # box unchanged
    dets = _lift_fixture(spark_dets)
    unknown = [d for d in dets if d.match is None]
    assert len(unknown) == 1
    assert unknown[0].label == "banana"
    assert unknown[0].prompt == "unknown_object"

    model, data = load_scene("kitchen")
    graph = build_perception_graph(model, data, dets)
    node = graph.nodes["unknown_object"]
    assert node["label"] == "banana" and node["owner"] is None
    assert [d for _, _, d in graph.edges("unknown_object", data=True)
            if d.get("type") == "HAS"] == []


def test_duplicate_match_demotes_lower_confidence():
    spark_dets = _fixture_dets()
    # Relabel the pill bottle (conf 0.94) as a second cup: the real
    # cup (0.89) loses the id and becomes unknown.
    idx = next(i for i, d in enumerate(spark_dets)
               if d["label"] == "pill bottle")
    spark_dets[idx] = dict(spark_dets[idx], label="cup")
    dets = _lift_fixture(spark_dets)
    assert sum(d.match == "cup" for d in dets) == 1
    assert sum(d.match is None for d in dets) == 1


def test_person_detection_skipped():
    spark_dets = _fixture_dets() + [{"label": "person",
                                     "box": [900, 100, 1100, 900]}]
    dets = _lift_fixture(spark_dets)  # person box has no SAM records
    assert len(dets) == 11
    assert all(d.match is not None for d in dets)


def test_spawn_unknown_node_shape():
    model, data = load_scene("kitchen")
    det = Detection(prompt="unknown_object", conf=0.8, box2d=(0, 0, 1, 1),
                    centroid=np.array([0.1, 0.2, 0.0]),
                    bbox_min=np.array([0.09, 0.19, 0.0]),
                    bbox_max=np.array([0.11, 0.21, 0.02]), n_points=9,
                    label="banana", match=None)
    graph = build_perception_graph(model, data, [det])
    assert graph.nodes["unknown_object"]["unknown"] is True


# --- wire-up: low confidence ASKs, never ALLOWs ---

def test_low_confidence_target_asks():
    graph = _graph()
    graph["objects"]["cup"]["conf"] = 0.4
    motion = _motion([(0.15, 0.2, 0.3, DOWN)] * 3, ["cup"] * 3)
    verdict = check(motion, graph)
    assert verdict["kind"] == "ASK"
    assert verdict["findings"][0]["rule"] == "unknown_object"


def test_missing_target_asks():
    motion = _motion([(0.15, 0.2, 0.3, DOWN)] * 3, ["banana"] * 3)
    verdict = check(motion, _graph())
    assert verdict["kind"] == "ASK"
    assert verdict["findings"][0]["rule"] == "unknown_object"


def test_confident_target_allows():
    motion = _motion([(0.15, 0.2, 0.3, DOWN)] * 3, ["cup"] * 3)
    assert check(motion, _graph())["kind"] == "ALLOW"


def test_graph_snapshot_uses_perceived_conf():
    model, data = load_scene("kitchen")
    props = load_props()
    truth = graph_snapshot(model, data, props)
    perceived = {}
    for oid, node in truth["objects"].items():
        perceived[oid] = {"pos": list(node["pos"]),
                          "extent": list(node["extent"]), "conf": 0.9}
    perceived["cup"]["conf"] = 0.3
    perceived["unknown_object"] = {"pos": [0.0, 0.0, 0.0],
                                   "extent": [0.01] * 3, "conf": 0.8}
    del perceived["jug"]  # the frame missed it
    graph = graph_snapshot(model, data, props, perceived=perceived)
    assert graph["objects"]["cup"]["conf"] == 0.3
    assert graph["objects"]["unknown_object"]["properties"] == []
    assert "jug" not in graph["objects"]


def test_scene_facts_use_perceived_positions():
    model, data = load_scene("kitchen")
    props = load_props()
    facts = scene_facts(model, data, props,
                        perceived={"cup": [0.15, 0.2, 0.01]})
    assert [o["id"] for o in facts["objects"]] == ["cup"]
    assert facts["objects"][0]["pos"] == [0.15, 0.2, 0.01]
