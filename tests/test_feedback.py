"""L-05: findings -> constraints + retry policy (no network)."""

from loop.feedback import (MAX_REPLAN_ROUNDS, constraints_for,
                           format_replan_note, should_replan)


def _verdict(kind, rules=("sharp_fast_near_person",), feedback=None):
    return {"kind": kind,
            "findings": [{"rule": r, "node": "owner", "t": 1.0,
                          "detail": f"detail for {r}"} for r in rules],
            "why_path": [], "feedback": feedback}


def test_constraints_from_ask_feedback():
    v = _verdict("ASK", feedback=["slow within 30 cm of a person"])
    assert constraints_for(v) == ["slow within 30 cm of a person"]


def test_block_and_halt_have_no_constraints():
    v = _verdict("BLOCK", rules=("sharp_toward_person",),
                 feedback=["slow within 30 cm of a person"])
    assert constraints_for(v) == []
    v = _verdict("HALT", feedback=["x"])
    assert constraints_for(v) == []
    assert constraints_for(_verdict("ASK")) == []


def test_should_replan_policy():
    v = _verdict("ASK", feedback=["slow within 30 cm of a person"])
    assert should_replan(v, 0) is True
    assert should_replan(v, MAX_REPLAN_ROUNDS) is False
    assert should_replan(_verdict("ASK"), 0) is False
    assert should_replan(_verdict("BLOCK"), 0) is False
    assert should_replan(_verdict("ALLOW"), 0) is False
    assert MAX_REPLAN_ROUNDS == 3


def test_replan_note_carries_evidence_and_constraints():
    v = _verdict("ASK", feedback=["slow within 30 cm of a person"])
    note = format_replan_note(v, 1)
    assert "Attempt 1 was rejected (ASK)" in note
    assert "detail for sharp_fast_near_person" in note
    assert "[sharp_fast_near_person]" in note
    assert "slow within 30 cm of a person" in note
