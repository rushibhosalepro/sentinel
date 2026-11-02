"""G-11(b): LLM property inference for uncatalogued detections.

No network: every Spark call here is a monkeypatched stub or a cache
replay.  Covers parse_inference validation, cache key/replay, the live
call shape, spawn_inferred provisional nodes, the infer_fn blend in
build_perception_graph, the planner/checker split in perceive_frame,
and that geometric rules fire on inferred properties (electronic =>
the jug pour BLOCKs).
"""

import json

import numpy as np

from graph.scene_graph import build_perception_graph, load_props
from graph.schema import EDGE_HAS, new_graph
from perception.lift3d import Detection
from perception.properties import (
    VOCABULARY,
    infer_cache_key,
    infer_properties,
    parse_inference,
)
from sentinel.check import check, load_rulebook
from sentinel.graph_view import graph_snapshot
from sim.world import load_scene

DOWN = [0.0, 1.0, 0.0, 0.0]
TOASTER_POS = np.array([0.6, -0.02, 0.0])


# ---------------------------------------------------------------- helpers

def _det(label, match=None, conf=0.9, pos=None):
    c = np.asarray(pos if pos is not None else TOASTER_POS, dtype=float)
    return Detection(
        prompt="unknown_object" if match is None else f"spark:{match}",
        conf=conf, box2d=(100.0, 200.0, 300.0, 400.0),
        centroid=c, bbox_min=c - 0.05, bbox_max=c + 0.05,
        n_points=50, label=label, match=match)


def _content(props, conf=0.8, why="looks like a toaster"):
    return json.dumps({"properties": props, "confidence": conf,
                       "why": why})


# ------------------------------------------------------- parse_inference

def test_parse_valid_dedups_and_truncates():
    why = "x" * 500
    res, err = parse_inference(
        _content(["electronic", "electronic"], why=why))
    assert err is None
    assert res["properties"] == ["electronic"]
    assert res["confidence"] == 0.8
    assert len(res["why"]) <= 160


def test_parse_allows_empty_properties():
    # A mug is none of these: valid inference, stays unknown.
    res, err = parse_inference(_content([], why="plain mug"))
    assert err is None
    assert res["properties"] == []


def test_parse_allows_full_vocabulary():
    res, err = parse_inference(_content(list(VOCABULARY)))
    assert err is None
    assert sorted(res["properties"]) == sorted(VOCABULARY)


def test_parse_rejects():
    bad = [
        "{not json",
        "[]",                       # not an object
        "{}",                       # missing fields
        _content("electronic"),     # props not a list
        _content(["radioactive"]),  # outside vocabulary
        _content(["electronic"], conf=1.5),   # conf out of range
        _content(["electronic"], conf=True),  # bool is not a conf
        json.dumps({"properties": ["electronic"],
                    "confidence": 0.8}),       # missing why
        _content(["electronic"], why="  "),    # blank why
    ]
    for content in bad:
        res, err = parse_inference(content)
        assert res is None and err, content


# ----------------------------------------------------------------- cache

def test_cache_key_stable_and_distinct():
    box = [100, 200, 300, 400]
    a = infer_cache_key("abc123", 0, "toaster", box)
    assert a == infer_cache_key("abc123", 0, "toaster", box)
    assert len(a) == 16
    assert infer_cache_key("abc123", 0, "kettle", box) != a
    assert infer_cache_key("abc123", 1, "toaster", box) != a
    assert infer_cache_key("abc123", 0, "toaster", [1, 2, 3, 4]) != a
    assert infer_cache_key("zzz999", 0, "toaster", box) != a


def test_cache_replay_needs_no_network(tmp_path, monkeypatch):
    import perception.properties as props_mod
    monkeypatch.setattr(props_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(props_mod, "frame_sha", lambda p: "abc123")
    monkeypatch.setattr(
        props_mod, "model_chat",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not call the model")))
    frame = tmp_path / "f.png"
    frame.write_bytes(b"\x89PNG-not-really")
    key = infer_cache_key("abc123", 0, "toaster", [1, 2, 3, 4])
    monkeypatch.setattr(props_mod, "infer_cache_path",
                        lambda k: tmp_path / f"props_{k}.json")
    (tmp_path / f"props_{key}.json").write_text(json.dumps(
        {"content": _content(["electronic"], why="toaster")}))
    res, usage = infer_properties(frame, 0, "toaster", (1, 2, 3, 4),
                                  640, 480)
    assert usage is None
    assert res["properties"] == ["electronic"]
    assert res["why"] == "toaster"


def test_live_call_shape_and_cache_write(tmp_path, monkeypatch):
    import perception.properties as props_mod
    monkeypatch.setattr(props_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(props_mod, "frame_sha", lambda p: "abc123")
    monkeypatch.setattr(props_mod, "infer_cache_path",
                        lambda k: tmp_path / f"props_{k}.json")
    frame = tmp_path / "f.png"
    frame.write_bytes(b"fake-image-bytes")
    seen = {}

    def fake_chat(*args, **kwargs):
        seen.update(kwargs)
        return _content(["fragile"]), {"in": 3}, 1.2

    monkeypatch.setattr(props_mod, "model_chat", fake_chat)
    monkeypatch.setattr(props_mod, "get_client",
                        lambda name: ("c", "model-x", {"spec": 1},
                                      "al"))
    res, usage = infer_properties(frame, 0, "wine glass", (1, 2, 3, 4),
                                  640, 480, refresh=True)
    assert res["properties"] == ["fragile"]
    assert usage == {"in": 3}
    assert seen["purpose"] == "infer-properties"
    assert seen["response_format"]["json_schema"]["name"] == \
        "InferProperties"
    prompt = seen["messages"][1]["content"][0]["text"]
    assert "wine glass" in prompt and "[1, 2, 3, 4]" in prompt
    written = list(tmp_path.glob("props_*.json"))
    assert len(written) == 1
    cached = json.loads(written[0].read_text())
    assert cached["usage"] == {"in": 3}
    assert cached["label"] == "wine glass"
    assert cached["image_sha256"] == "abc123"  # mocked frame_sha


# ------------------------------------------------------ inferred nodes

def test_spawn_inferred_node_flags_and_has_edges():
    from graph.scene_graph import spawn_inferred
    g = new_graph()
    det = _det("red toaster")
    node = spawn_inferred(g, "red toaster", det, 0.0, 0,
                          ["electronic"], 0.7, "slots on top")
    assert node == "seen_red_toaster_1"
    n = g.nodes[node]
    assert n["label"] == "red toaster"
    assert n["inferred"] is True
    assert n["infer_conf"] == 0.7
    assert n["owner"] is None
    assert n["tracked"] is True
    edges = list(g.out_edges(node, data=True))
    assert {d["type"] for _, _, d in edges} == {EDGE_HAS}
    assert len(edges) == 1  # one HAS edge, no owner edge


def test_unmatched_stub_blends_inferred_and_unknown():
    model, data = load_scene("kitchen")
    props = load_props()
    cup_pos = data.xpos[model.body("cup").id].copy()
    dets = [_det("cup", match="cup", conf=0.95, pos=cup_pos),
            _det("red toaster", conf=0.9),
            _det("weird blob", conf=0.5,
                 pos=np.array([-0.3, 0.3, 0.0]))]

    def stub(det, seq):
        if det.label == "red toaster":
            return {"properties": ["electronic"], "confidence": 0.7,
                    "why": "slots"}
        return None  # unmatched + no inference => unknown

    g = build_perception_graph(model, data, dets, props, ts=0.0,
                               infer_fn=stub)
    assert g.nodes["cup"].get("inferred", False) is False
    assert "seen_red_toaster_1" in g.nodes
    assert g.nodes["seen_red_toaster_1"]["inferred"] is True
    assert "unknown_object" in g.nodes
    assert g.nodes["unknown_object"].get("inferred", False) is False
    has = [e for e in g.out_edges("unknown_object", data=True)
           if e[2].get("type") == EDGE_HAS]
    assert has == []  # relations yes, HAS edges no


def test_empty_inference_stays_unknown():
    model, data = load_scene("kitchen")
    g = build_perception_graph(model, data, [_det("plain mug")],
                               load_props(), ts=0.0,
                               infer_fn=lambda det, seq: None)
    assert "unknown_object" in g.nodes
    assert not [n for n in g.nodes if str(n).startswith("seen_")]


def test_perceive_frame_positions_excludes_inferred(tmp_path,
                                                    monkeypatch):
    import perception.perceive as pcv
    model, data = load_scene("kitchen")
    props = load_props()
    cup_pos = data.xpos[model.body("cup").id].copy()
    dets = [_det("cup", match="cup", conf=0.95, pos=cup_pos),
            _det("red toaster", conf=0.9)]
    monkeypatch.setattr(pcv, "detect_objects",
                        lambda *a, **k: ([{"box": (1, 2, 3, 4)}], None))
    monkeypatch.setattr(pcv, "segment_boxes",
                        lambda *a, **k: object())
    monkeypatch.setattr(pcv, "detections_from_spark",
                        lambda *a, **k: dets)
    monkeypatch.setattr(
        pcv, "infer_properties",
        lambda *a, **k: ({"properties": ["electronic"],
                          "confidence": 0.7, "why": "slots"}, None))
    frame = {"width": 640, "height": 480, "depth": None, "cam": None}
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG-not-really")
    out = pcv.perceive_frame(model, data, frame, img, props)
    assert "seen_red_toaster_1" in out["perceived"]  # checker sees it
    assert "seen_red_toaster_1" not in out["positions"]  # planner won't
    assert "cup" in out["positions"]
    assert out["perceived"]["seen_red_toaster_1"][
        "properties"] == ["electronic"]


def test_graph_snapshot_passes_inferred_through():
    model, data = load_scene("kitchen")
    props = load_props()
    perceived = {
        "seen_red_toaster_1": {
            "pos": [0.6, -0.02, 0.0], "extent": [0.05, 0.05, 0.05],
            "conf": 0.7, "properties": ["electronic"],
            "inferred": True, "owner": "unknown"},
    }
    snap = graph_snapshot(model, data, props, perceived=perceived)
    node = snap["objects"]["seen_red_toaster_1"]
    assert node["properties"] == ["electronic"]
    assert node["inferred"] is True
    assert node["owner"] == "unknown"


# ------------------------------------------------- rules fire on it

def _motion(grips, held):
    n = len(grips)
    return {
        "body": "arm",
        "path": [np.array([*g[:3], *g[3]], dtype=float) for g in grips],
        "t": [round(i * 0.5, 2) for i in range(n)],
        "held": list(held), "tilt": [0.0] * n,
        "speed": ["slow"] * n,
        "sample_steps": [f"s{i}" for i in range(n)],
        "end_state": [], "derived_from": "test", "step_ids": ["s0"],
    }


def _graph_with_inferred_toaster():
    return {
        "objects": {
            "jug": {"pos": [0.6, -0.02, 0.12], "quat": list(DOWN),
                    "properties": ["liquid"], "owner": "owner",
                    "conf": 1.0},
            "seen_red_toaster_1": {
                "pos": [0.6, -0.02, 0.0], "quat": list(DOWN),
                "properties": ["electronic"], "inferred": True,
                "owner": "unknown", "conf": 0.7},
        },
        "people": {
            "owner": {"hand": [1.0, 0.0, 0.5], "torso": [1.6, 0.4, 0.4],
                      "hand_vel": [0.0, 0.0, 0.0],
                      "authorised": ["all"], "role": "owner"},
        },
        "safe_spot_pour": (0.2, 0.15),
    }


def test_inferred_electronic_blocks_jug_pour():
    m = _motion([[0.6, -0.02, 0.12, DOWN]], ["jug"])
    v = check(m, _graph_with_inferred_toaster(), load_rulebook())
    assert v["kind"] == "BLOCK"
    assert v["findings"][0]["rule"] == "liquid_above_electronic"


def test_inferred_far_away_allows():
    m = _motion([[0.6, -0.02, 0.12, DOWN]], ["jug"])
    g = _graph_with_inferred_toaster()
    g["objects"]["seen_red_toaster_1"]["pos"] = [0.0, 0.5, 0.0]
    v = check(m, g, load_rulebook())
    assert v["kind"] == "ALLOW"
