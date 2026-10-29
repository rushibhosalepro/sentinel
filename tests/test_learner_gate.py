"""R-04: admission gate (recorded candidate + mutations, no network)."""

import copy
from pathlib import Path

from learner import gate as G
from learner.propose import propose_from_content
from sentinel.check import check, load_rulebook

WONDER = Path(__file__).parent / "fixtures" / "wonder"


def _base():
    return [r for r in load_rulebook() if r.get("origin") != "learned"]


def _candidate():
    raw = (WONDER / "fragile_near_edge.json").read_text()
    return propose_from_content(raw, ["inc-001"])["rule"]


def test_cases_baseline_allow():
    cases = G.load_cases()
    assert len(cases) == 7  # plate incident + 3 controls + 3 safe edge
    base = _base()
    for case in cases:
        v = check(case["motion"], case["graph"], base)
        assert v["kind"] == "ALLOW", (case["id"], v["findings"])


def test_recorded_candidate_passes_gate():
    report = G.review(_candidate(), base_rules=_base())
    assert report["accepted"], report
    assert [s["name"] for s in report["stages"]] == [
        "schema", "replay", "ratchet", "preflight"]
    assert all(s["passed"] for s in report["stages"])
    inc = next(r for r in report["replay"]
               if r["case"] == "plate_near_glass")
    assert (inc["base"], inc["new"]) == ("ALLOW", "ASK")
    assert inc["candidate_fired"] is True
    for r in report["replay"]:
        if r["control"]:
            assert r["new"] == "ALLOW", r
    assert len(report["preflight"]) == 4
    assert all(p["candidate_fired"] for p in report["preflight"])


def test_too_tight_candidate_misses_incident():
    cand = _candidate()
    cand["when"]["held_near_object_property"]["within_cm"] = 0.5
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert report["reason"].startswith("replay: incident not caught")


def test_unknown_predicate_rejected():
    cand = _candidate()
    cand["when"] = {"teleport": True}
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert "unknown predicates" in report["reason"]


def test_mixed_scope_rejected():
    cand = _candidate()
    cand["when"] = {"speed": "normal", "target_unknown": True}
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert "mixed scopes" in report["reason"]


def test_hard_candidate_rejected():
    cand = _candidate()
    cand["hard"] = True
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert "soft" in report["reason"]


def test_id_collision_rejected():
    cand = _candidate()
    cand["id"] = "unknown_object"
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert "already exists" in report["reason"]


def test_ratchet_catches_control_regression():
    cand = _candidate()
    cand["id"] = "clingy"
    cand["when"] = {"held_near_person": {"within_cm": 500.0}}
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert report["reason"].startswith("ratchet: controls regressed")


def test_preflight_catches_escape():
    cand = _candidate()
    cand["when"]["held_near_object_property"]["within_cm"] = 5.0
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert report["reason"].startswith("preflight: incident escapes")


def test_checker_crash_rejects():
    cand = _candidate()
    cand["when"]["held_near_object_property"]["within_cm"] = "far"
    report = G.review(cand, base_rules=_base())
    assert report["accepted"] is False
    assert "checker crashed" in report["reason"]


def test_gate_ignores_learned_base_rules():
    learned = copy.deepcopy(_candidate())
    learned["origin"] = "learned"
    base = _base() + [learned]  # production base: already active
    report = G.review(_candidate(), base_rules=base)
    assert report["accepted"] is False  # same id collides
    assert "already exists" in report["reason"]
