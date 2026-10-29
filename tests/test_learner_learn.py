"""R-05: learn CLI end-to-end (recorded Wonder, tmp rulebook)."""

from pathlib import Path

import pytest

from learner import learn as L
from learner import versions as V
from learner.events import append_event, set_log_path
from sentinel.check import load_rulebook

WONDER = Path(__file__).parent / "fixtures" / "wonder"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "LEARNED_DIR", tmp_path / "learned")
    monkeypatch.setattr(V, "JOURNAL", tmp_path / "VERSIONS.jsonl")
    log = tmp_path / "events.jsonl"
    set_log_path(log)
    append_event({"kind": "verdict", "run_id": "run-x",
                  "instruction": "move the plate", "round": 1,
                  "graph": {"objects": {}}, "motion": "Motion: 1",
                  "findings": [], "outcome": "ALLOW"})
    inc = append_event({"kind": "incident", "run_id": "run-x",
                        "instruction": "move the plate",
                        "text": "nearly knocked the glass off",
                        "graph": {"objects": {}}, "motion": "Motion: 1",
                        "findings": [], "outcome": "ALLOW"})
    return log, inc["id"]


def _base():
    return [r for r in load_rulebook() if r.get("origin") != "learned"]


def test_recorded_learn_activates(sandbox, tmp_path):
    log, inc_id = sandbox
    res = L.learn(inc_id, events_path=log,
                  recorded=WONDER / "fragile_near_edge.json",
                  base_rules=_base())
    assert res["outcome"] == "activated"
    assert res["rule"]["id"] == "fragile_near_edge_fast"
    assert res["rule"]["learned_from"][0] == inc_id
    assert res["report"]["accepted"] is True
    assert res["entry"]["seq"] == 1
    assert (tmp_path / "learned" / "fragile_near_edge_fast.json").exists()


def test_second_learn_collides(sandbox):
    log, inc_id = sandbox
    kw = {"events_path": log,
          "recorded": WONDER / "fragile_near_edge.json"}
    first = L.learn(inc_id, base_rules=_base(), **kw)
    assert first["outcome"] == "activated"
    res = L.learn(inc_id, base_rules=_base() + [first["rule"]], **kw)
    assert res["outcome"] == "rejected"
    assert "already exists" in res["report"]["reason"]


def test_no_rule_outcome(sandbox):
    log, inc_id = sandbox
    res = L.learn(inc_id, events_path=log,
                  recorded=WONDER / "no_rule.json",
                  base_rules=_base())
    assert res["outcome"] == "no_rule" and "spill" in res["no_rule"]


def test_dry_run_writes_nothing(sandbox, tmp_path):
    log, inc_id = sandbox
    res = L.learn(inc_id, events_path=log,
                  recorded=WONDER / "fragile_near_edge.json",
                  base_rules=_base(), activate=False)
    assert res["outcome"] == "accepted"
    assert not (tmp_path / "learned").exists()


def test_unknown_incident_raises(sandbox):
    with pytest.raises(ValueError, match="no incident"):
        L.learn("inc-999", events_path=sandbox[0],
                recorded=WONDER / "fragile_near_edge.json")
