"""D-05: final-ASK owner approval (fake planner + checker, real headless)."""

import json
from pathlib import Path

import pytest

import loop.live as live

PLANS = Path(__file__).parent / "fixtures" / "plans"


def _content(name):
    return json.loads((PLANS / name).read_text())["content"]


def _final_ask(hard=False):
    return {"kind": "ASK",
            "findings": [{"rule": "hazard_fast_near_person", "node": "owner",
                          "t": 1.0, "detail": "too fast near owner"}],
            "why_path": [{"rule": "hazard_fast_near_person",
                          "verdict": "ASK", "hard": hard, "t": 1.0}],
            "feedback": None}  # unfixable: final, no replan


class _Handler:
    """Stand-in for the dashboard's ASK registry."""

    def __init__(self, decision):
        self.decision = decision
        self.registered = []
        self.waits = []

    def pre_register(self, ask_id):
        self.registered.append(ask_id)

    def wait(self, ask_id, timeout):
        self.waits.append((ask_id, timeout))
        return self.decision


def _stub(monkeypatch, verdict):
    monkeypatch.setattr(live, "plan_instruction",
                        lambda *a, **k: _content("give_apple.json"))
    monkeypatch.setattr(live, "check", lambda m, g: verdict)


def _log(tmp_path):
    with open(tmp_path / "events.jsonl") as f:
        return [json.loads(line) for line in f]


def test_ask_question():
    v = {"findings": [{"detail": "too fast"}, {"detail": "near owner"}]}
    assert live.ask_question(v) == "Allow the motion? (too fast; near owner)"
    assert live.ask_question({"findings": []}) == "Allow the motion?"


def test_decide_ask_approve_emits_event():
    events = []
    ask_id, decision = live.decide_ask(
        _final_ask(), 2, _Handler("approve"), events.append, timeout=5.0)
    assert decision == "approve"
    (ev,) = events
    assert ev["type"] == "ask" and ev["ask_id"] == ask_id
    assert ev["round"] == 2
    assert ev["question"].startswith("Allow the motion?")
    assert ev["findings"][0]["rule"] == "hazard_fast_near_person"


def test_decide_ask_deny_and_timeout():
    assert live.decide_ask(_final_ask(), 1, _Handler("deny"),
                           lambda e: None)[1] == "deny"
    assert live.decide_ask(_final_ask(), 1, _Handler(None),
                           lambda e: None, timeout=0.05)[1] == "deny"


def test_headless_approve_executes(monkeypatch, tmp_path):
    _stub(monkeypatch, _final_ask())
    events = []
    out = str(tmp_path / "ask_ok.mp4")
    live._run_headless("test", out, sink=events.append,
                       ask_handler=_Handler("approve"))
    kinds = [e["type"] for e in events]
    assert "ask" in kinds
    done = next(e for e in events if e["type"] == "done")
    assert done["status"] == "complete"
    assert done["detail"]["ask"]["decision"] == "approve"
    assert (tmp_path / "ask_ok.mp4").exists()
    log = _log(tmp_path)  # R-01: verdict + ask_answer entries
    assert [e["kind"] for e in log] == ["verdict", "ask_answer"]
    assert log[0]["outcome"] == "ASK" and log[0]["run_id"]
    assert log[1]["outcome"] == "approve" and log[1]["who"] == "owner"
    assert log[1]["ask_id"] == done["detail"]["ask"]["ask_id"]
    assert log[1]["run_id"] == log[0]["run_id"]


def test_headless_deny_stops(monkeypatch, tmp_path):
    _stub(monkeypatch, _final_ask())
    events = []
    with pytest.raises(SystemExit):
        live._run_headless("test", str(tmp_path / "ask_no.mp4"),
                           sink=events.append,
                           ask_handler=_Handler("deny"))
    done = next(e for e in events if e["type"] == "done")
    assert done["status"] == "ASK"
    assert done["detail"]["ask"]["decision"] == "deny"
    log = _log(tmp_path)
    assert [e["kind"] for e in log] == ["verdict", "ask_answer"]
    assert log[1]["outcome"] == "deny"


def test_headless_hard_ask_never_asks(monkeypatch, tmp_path):
    _stub(monkeypatch, _final_ask(hard=True))
    events = []
    handler = _Handler("approve")
    with pytest.raises(SystemExit):
        live._run_headless("test", str(tmp_path / "ask_hard.mp4"),
                           sink=events.append, ask_handler=handler)
    assert handler.registered == []  # gate refused before asking
    assert [e["type"] for e in events if e["type"] == "ask"] == []
    done = next(e for e in events if e["type"] == "done")
    assert done["status"] == "ASK" and done["detail"]["ask"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
