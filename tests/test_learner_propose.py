"""R-02: Wonder proposal parsing (recorded fixtures, no network)."""

from pathlib import Path

import pytest

from learner import propose as P

WONDER = Path(__file__).parent / "fixtures" / "wonder"


def test_vocabulary_text_lists_non_live_predicates():
    text = P.vocabulary_text()
    assert "held_near_object_property" in text
    assert "object_near_edge" in text
    assert "person_in_path" not in text  # live-only, not checkable
    assert text.count("\n") == 18  # 19 usable of 20


def test_recorded_rule_parses_and_softens():
    raw = (WONDER / "fragile_near_edge.json").read_text()
    out = P.propose_from_content(raw, ["inc-001", "ev-1"])
    assert out["no_rule"] is None
    rule = out["rule"]
    assert rule["id"] == "fragile_near_edge_fast"
    assert rule["verdict"] == "ASK" and rule["hard"] is False
    assert rule["fixable"] is False  # coerced: learned rules ask
    assert rule["origin"] == "learned" and rule["version"] == 1
    assert rule["learned_from"] == ["inc-001", "ev-1"]
    assert set(rule["when"]) == {"held_near_object_property",
                                 "object_near_edge", "speed"}
    assert "fragile" in rule["constraint_hint"]


def test_no_rule_refusal():
    out = P.propose_from_content(
        (WONDER / "no_rule.json").read_text(), ["inc-002"])
    assert out == {"rule": None, "no_rule": out["no_rule"]}
    assert "spill" in out["no_rule"]


def test_fenced_response_parses():
    out = P.propose_from_content(
        "```json\n" + (WONDER / "no_rule.json").read_text() + "\n```",
        ["inc-002"])
    assert out["rule"] is None


def test_bad_responses_raise():
    with pytest.raises(ValueError, match="not JSON"):
        P.propose_from_content("not json", [])
    with pytest.raises(ValueError, match="non-empty 'when'"):
        P.propose_from_content('{"id": "x", "when": {}}', [])
    with pytest.raises(ValueError, match="string 'id'"):
        P.propose_from_content('{"when": {"speed": "slow"}}', [])


def test_properties_text_lists_props_yaml_values():
    assert "fragile" in P.properties_text().split(", ")


def test_rulebook_and_context_render():
    rules = [{"id": "a", "when": {"speed": "slow"}, "unless": {},
              "verdict": "ASK", "hard": False}]
    assert "a: when ['speed'] -> ASK" in P.rulebook_text(rules)
    inc = {"id": "inc-001", "text": "nearly hit it",
           "instruction": "move it",
           "graph": {"objects": {"cup": {"properties": ["fragile"]}}}}
    ctx = P.incident_context(inc, [{"round": 1, "outcome": "ALLOW",
                                    "findings": [], "motion": "Motion: 1",
                                    "closest": {"fragile_cm": 8.5,
                                                "fragile_obj": "wine_glass",
                                                "electronic_cm": None,
                                                "electronic_obj": None,
                                                "person_cm": 120.0,
                                                "person": "owner"}}])
    assert "inc-001" in ctx and "round 1: ALLOW" in ctx
    assert "cup [fragile]" in ctx
    assert "8.5 cm from wine_glass (fragile)" in ctx
    assert "120.0 cm from owner (person)" in ctx
