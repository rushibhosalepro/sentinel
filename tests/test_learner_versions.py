"""R-05: rulebook versions (tmp dirs, never the real rulebook)."""

import json

import pytest

from learner import versions as V


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    learned = tmp_path / "learned"
    journal = tmp_path / "VERSIONS.jsonl"
    monkeypatch.setattr(V, "LEARNED_DIR", learned)
    monkeypatch.setattr(V, "JOURNAL", journal)
    return learned, journal


def _rule(rid="fragile_near_edge_fast"):
    return {"id": rid, "when": {"speed": "normal"}, "unless": {},
            "verdict": "ASK", "hard": False, "fixable": False,
            "constraint_hint": "", "reason": "", "origin": "learned",
            "version": 1, "learned_from": ["inc-001"]}


def test_add_writes_file_and_journals(dirs):
    learned, journal = dirs
    e = V.add_rule(_rule(), "inc-001", {"accepted": True})
    assert e["seq"] == 1 and e["action"] == "add"
    assert json.loads((learned / "fragile_near_edge_fast.json").read_text())
    assert V.active_rules() == [{"rule_id": "fragile_near_edge_fast",
                                 "seq": 1, "incident": "inc-001",
                                 "ts": e["ts"]}]
    assert V.status()["journal"][0]["gate"] == {"accepted": True}


def test_add_collision_rejected(dirs):
    V.add_rule(_rule(), "inc-001", {})
    with pytest.raises(ValueError, match="already"):
        V.add_rule(_rule(), "inc-002", {})


def test_rollback_by_seq_and_by_id(dirs):
    learned, journal = dirs
    V.add_rule(_rule("r1"), "inc-001", {})
    V.add_rule(_rule("r2"), "inc-002", {})
    e = V.rollback(1)
    assert (e["action"], e["rule_id"], e["reverts"]) == ("rollback", "r1", 1)
    assert not (learned / "r1.json").exists()
    assert [a["rule_id"] for a in V.active_rules()] == ["r2"]
    V.rollback("r2")
    assert V.active_rules() == []


def test_rollback_unknown_rejected(dirs):
    with pytest.raises(ValueError, match="no active learned rule"):
        V.rollback(7)


def test_rollback_missing_file_converges(dirs):
    learned, journal = dirs
    V.add_rule(_rule(), "inc-001", {})
    (learned / "fragile_near_edge_fast.json").unlink()
    e = V.rollback("fragile_near_edge_fast")
    assert e["note"] == "rule file was already missing"
    assert V.active_rules() == []
