"""C-03: verdict assembly, severity, feedback policy, suppression."""

import json

import numpy as np
import pytest

from sentinel.check import check, load_rulebook

DOWN = [0.0, 1.0, 0.0, 0.0]
TURNED = [0.0, 0.0, -1.0, 0.0]  # Rz(180) * down


def _motion(grips, held, steps=None, speed="normal", tilt=None, t=None,
              derived_from="test"):
    n = len(grips)
    speeds = speed if isinstance(speed, list) else [speed] * n
    return {
        "body": "arm",
        "path": [np.array([*g[:3], *g[3]], dtype=float) for g in grips],
        "t": list(t) if t else [round(i * 0.5, 2) for i in range(n)],
        "held": list(held), "tilt": list(tilt) if tilt else [0.0] * n,
        "speed": speeds,
        "sample_steps": list(steps) if steps else [f"s{i}" for i in range(n)],
        "end_state": [], "derived_from": derived_from, "step_ids": ["s0"],
    }


def _graph(hand=(1.0, 0.0, 0.5)):
    return {
        "objects": {
            "chef_knife": {"pos": [0.35, -0.18, 0.05], "quat": list(DOWN),
                           "properties": ["sharp"], "owner": "owner",
                           "conf": 1.0},
            "apple": {"pos": [-0.16, -0.24, 0.04], "quat": list(DOWN),
                      "properties": ["food"], "owner": "owner", "conf": 1.0},
            "jug": {"pos": [0.6, -0.02, 0.12], "quat": list(DOWN),
                    "properties": ["liquid"], "owner": "owner", "conf": 1.0},
            "cup": {"pos": [0.15, 0.2, 0.04], "quat": list(DOWN),
                    "properties": [], "owner": "owner", "conf": 1.0},
            "laptop": {"pos": [0.6, -0.02, 0.0], "quat": list(DOWN),
                       "properties": ["electronic"], "owner": "owner",
                       "conf": 1.0},
            "pill_bottle": {"pos": [0.2, 0.3, 0.05], "quat": list(DOWN),
                            "properties": ["medication"], "owner": "owner",
                            "conf": 1.0},
        },
        "people": {
            # Torso parked far: the hand is the binding constraint below.
            "owner": {"hand": list(hand), "torso": [1.6, 0.4, 0.4],
                      "hand_vel": [0.0, 0.0, 0.0],
                      "authorised": ["all"], "role": "owner"},
        },
    }


def _rules():
    return load_rulebook()


def test_allow_when_nothing_fires():
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["apple"], speed="slow")
    v = check(m, _graph(), _rules())
    assert v["kind"] == "ALLOW"
    assert v["findings"] == [] and v["feedback"] is None
    assert v["why_path"] == [] and "stub" not in v


def test_why_carries_structured_evidence():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, DOWN]]
    m = _motion(grips, ["chef_knife", "chef_knife"], speed="slow")
    v = check(m, _graph(hand=(1.3, -0.18, 0.25)), _rules())
    (w,) = v["why_path"]
    assert (w["rule"], w["verdict"], w["hard"]) == (
        "sharp_toward_person", "BLOCK", True)
    assert w["origin"] == "seed"
    assert "blade" in w["reason"]
    assert w["params"]["blade_toward_person"]["within_cm"] == 25.0
    assert w["predicates"]["toward"] is True
    p = w["predicates"]
    assert p["tip_cm"] - p["margin_cm"] <= 25.0  # the firing condition
    assert w["steps"] == ["s1"]  # firing sample's plan step
    assert w["relations"] == [{"subj": "chef_knife", "rel": "POINTS_AT",
                               "obj": "owner"}]


def test_hard_findings_never_become_ask():
    for rule in load_rulebook():
        assert not (rule["verdict"] == "ASK" and rule["hard"]), rule["id"]
    g = _graph(hand=(0.2, 0.0, 0.3))
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["jug"], speed="normal")
    v = check(m, g, _rules())
    assert v["kind"] == "ASK"
    assert not any(w["hard"] for w in v["why_path"])


def test_blade_toward_person_blocks_without_feedback():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, DOWN]]
    m = _motion(grips, ["chef_knife", "chef_knife"], speed="slow")
    v = check(m, _graph(hand=(1.3, -0.18, 0.25)), _rules())
    assert v["kind"] == "BLOCK"
    assert len(v["findings"]) == 1
    f = v["findings"][0]
    assert (f["rule"], f["node"], f["t"]) == (
        "sharp_toward_person", "owner", 0.5)
    assert "pointing at them" in f["detail"]
    assert "owner's hand" in f["detail"]
    assert v["feedback"] is None  # hard BLOCK: no feedback
    (w,) = v["why_path"]
    assert {k: w[k] for k in ("rule", "verdict", "hard", "t")} == {
        "rule": "sharp_toward_person", "verdict": "BLOCK", "hard": True,
        "t": 0.5}
    assert w["origin"] == "seed" and "blade" in w["reason"]


def test_blade_away_allows():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, TURNED]]
    m = _motion(grips, ["chef_knife", "chef_knife"], speed="slow")
    v = check(m, _graph(hand=(1.3, -0.18, 0.25)), _rules())
    assert v["kind"] == "ALLOW"


def test_sharp_fast_asks_with_feedback():
    g = _graph(hand=(0.2, 0.0, 0.3))
    g["objects"]["jug"]["pos"] = [0.0, 0.0, 0.3]
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["jug"], speed="normal")
    v = check(m, g, _rules())
    assert v["kind"] == "ASK"
    assert v["findings"][0]["rule"] == "sharp_fast_near_person"
    assert "normal speed" in v["findings"][0]["detail"]
    assert v["feedback"] == ["slow within 30 cm of a person"]


def test_release_in_air_blocks_and_beats_ask():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, TURNED],
             [0.5, -0.18, 0.30, TURNED]]
    m = _motion(grips, ["chef_knife", "chef_knife", None],
                steps=["s1", "s2", "s3"], speed="normal")
    v = check(m, _graph(hand=(0.5, 0.10, 0.25)), _rules())
    assert v["kind"] == "BLOCK"
    assert v["why_path"][0]["rule"] == "release_near_person_in_air"
    assert v["why_path"][1]["rule"] == "sharp_toward_person"
    assert v["why_path"][2]["rule"] == "sharp_fast_near_person"
    assert "mid-air" in v["findings"][0]["detail"]
    # Hard BLOCK verdict: no feedback, despite the soft ASK alongside.
    assert v["feedback"] is None


def test_tagged_handover_release_is_suppressed():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, TURNED],
             [0.5, -0.18, 0.30, TURNED]]
    m = _motion(grips, ["chef_knife", "chef_knife", None],
                steps=["s1", "s2", "s6:release"], speed="slow")
    v = check(m, _graph(hand=(1.3, -0.18, 0.25)), _rules())
    assert v["kind"] == "ALLOW"


def test_liquid_near_electronic_blocks_with_filled_hint():
    m = _motion([[0.6, -0.02, 0.12, DOWN]], ["jug"], speed="slow")
    g = _graph()
    g["safe_spot_pour"] = (0.2, 0.15)
    v = check(m, g, _rules())
    assert v["kind"] == "BLOCK"
    assert v["findings"][0]["rule"] == "liquid_above_electronic"
    assert v["feedback"] == ["move the cup to (0.20, 0.15) exactly, "
                             "away from electronics, then pour into it"]


def test_liquid_without_spot_asks_owner():
    m = _motion([[0.6, -0.02, 0.12, DOWN]], ["jug"], speed="slow")
    g = _graph()
    g["safe_spot_pour"] = None  # crowded counter: search found nothing
    v = check(m, g, _rules())
    assert v["kind"] == "ASK"
    assert v["findings"][0]["rule"] == "liquid_above_electronic"
    assert v["why_path"][0]["verdict"] == "ASK"
    assert v["feedback"] is None  # unfixable: straight to the owner


def test_crowded_counter_ask_is_terminal():
    from loop.feedback import should_replan

    m = _motion([[0.6, -0.02, 0.12, DOWN]], ["jug"], speed="slow")
    g = _graph()
    g["safe_spot_pour"] = None
    v = check(m, g, _rules())
    assert v["kind"] == "ASK"
    assert should_replan(v, 1) is False


def test_live_scope_rule_skipped_by_check():
    hand = (0.35, -0.18, 0.30)
    m = _motion([[*hand, DOWN]], ["apple"], speed="slow")
    v = check(m, _graph(hand=hand), _rules())
    assert "person_in_path" not in {f["rule"] for f in v["findings"]}
    assert "person_in_path" not in {w["rule"] for w in v["why_path"]}
    assert v["kind"] != "HALT"


def test_tilt_branch_fires_without_liquid():
    grips = [[0.15, 0.2, 0.10, DOWN], [0.6, -0.02, 0.18, DOWN]]
    m = _motion(grips, ["cup", "cup"], speed="slow", tilt=[0.0, 70.0])
    g = _graph()
    g["safe_spot_pour"] = (0.2, 0.15)
    v = check(m, g, _rules())
    assert v["kind"] == "BLOCK"
    assert "tilted 70" in v["findings"][0]["detail"]


def test_restricted_item_to_visitor_asks():
    g = _graph()
    g["people"]["visitor"] = {"hand": [0.5, 0.3, 0.25],
                              "torso": [0.6, 0.4, 0.4],
                              "hand_vel": [0.0, 0.0, 0.0],
                              "authorised": [], "role": "visitor"}
    grips = [[0.2, 0.3, 0.10, DOWN], [0.5, 0.3, 0.30, DOWN],
             [0.5, 0.3, 0.30, DOWN]]
    m = _motion(grips, ["pill_bottle"] * 2 + [None],
                steps=["s1", "s2", "h:release"], speed="slow")
    v = check(m, g, _rules())
    assert v["kind"] == "ASK"
    assert v["findings"][0]["rule"] == "restricted_item"
    assert "visitor" in v["findings"][0]["detail"]
    assert v["feedback"] is None


def test_restricted_item_to_owner_allowed():
    grips = [[0.2, 0.3, 0.10, DOWN], [1.0, 0.0, 0.55, DOWN],
             [1.0, 0.0, 0.55, DOWN]]
    m = _motion(grips, ["pill_bottle"] * 2 + [None],
                steps=["s1", "s2", "h:release"], speed="slow")
    v = check(m, _graph(), _rules())
    assert v["kind"] == "ALLOW"


def test_unknown_and_low_conf_targets_ask():
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["mystery_box"], speed="slow")
    v = check(m, _graph(), _rules())
    assert v["kind"] == "ASK"
    assert v["findings"][0]["rule"] == "unknown_object"
    assert "not in the scene graph" in v["findings"][0]["detail"]
    assert v["feedback"] == ["use an object from the scene graph"]
    g = _graph()
    g["objects"]["apple"]["conf"] = 0.3
    m2 = _motion([[0.0, 0.0, 0.3, DOWN]], ["apple"], speed="slow")
    v2 = check(m2, g, _rules())
    assert v2["kind"] == "ASK"
    assert "0.30" in v2["findings"][0]["detail"]


def test_rulebook_rejects_unknown_predicates(tmp_path):
    bad = {"id": "bad", "when": {"nonsense": True}, "unless": {},
           "verdict": "ASK", "hard": False, "fixable": False,
           "constraint_hint": "", "reason": "x", "origin": "handwritten",
           "learned_from": [], "version": 1}
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="unknown predicate"):
        load_rulebook(tmp_path)


def test_far_blade_fires_through_reach_margin():
    # Trick-like: tip 53 cm from the parked hand at t=8, normal speed.
    # Margin 66 cm (40 reach + 16 stale + 10 speed) -> effective < 0.
    grips = [[0.35, -0.18, 0.10, DOWN], [0.77, -0.19, 0.30, DOWN]]
    m = _motion(grips, ["chef_knife", "chef_knife"], speed="normal",
                t=[0.0, 8.0])
    g = _graph(hand=(1.45, -0.35, 0.3))
    g["people"]["owner"]["torso"] = [1.6, 0.3, 0.4]
    v = check(m, g, _rules())
    assert v["kind"] == "BLOCK"
    assert v["findings"][0]["rule"] == "sharp_toward_person"
    assert "clearance 66 cm" in v["findings"][0]["detail"]


def test_scene_text_provenance_blocks():
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["apple"], speed="slow",
                derived_from="scene_text:sticky_1")
    v = check(m, _graph(), _rules())
    assert v["kind"] == "BLOCK"
    assert v["findings"][0]["rule"] == "scene_text_provenance"
    assert "scene text" in v["findings"][0]["detail"]
    assert v["feedback"] is None


def test_missing_provenance_blocks():
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["apple"], speed="slow",
                derived_from=None)
    v = check(m, _graph(), _rules())
    assert v["kind"] == "BLOCK"
    assert "no provenance" in v["findings"][0]["detail"]


def test_owner_instruction_provenance_passes():
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["apple"], speed="slow",
                derived_from="live:give me the knife")
    v = check(m, _graph(), _rules())
    assert v["kind"] == "ALLOW"


def test_graph_is_required():
    m = _motion([[0.0, 0.0, 0.3, DOWN]], ["apple"])
    with pytest.raises(TypeError):
        check(m)
