"""L-05/L-06: constraints + retry policy (no network)."""

from loop.feedback import (MAX_REPLAN_ROUNDS, constraints_for,
                           format_error_note, format_replan_note,
                           has_hard_finding, should_replan)


def _verdict(kind, rules=(("sharp_fast_near_person", False),),
             feedback=None):
    return {"kind": kind,
            "findings": [{"rule": r, "node": "owner", "t": 1.0,
                          "detail": f"detail for {r}"} for r, _ in rules],
            "why_path": [{"rule": r, "verdict": kind, "hard": h, "t": 1.0}
                         for r, h in rules],
            "feedback": feedback}


def test_constraints_from_ask_feedback():
    v = _verdict("ASK", feedback=["slow within 30 cm of a person"])
    assert constraints_for(v) == ["slow within 30 cm of a person"]


def test_soft_block_has_constraints():
    v = _verdict("BLOCK", rules=(("liquid_above_electronic", False),),
                 feedback=["keep liquids away"])
    assert constraints_for(v) == ["keep liquids away"]


def test_hard_finding_kills_constraints():
    v = _verdict("BLOCK",
                 rules=(("sharp_toward_person", True),
                        ("liquid_above_electronic", False)),
                 feedback=["keep liquids away"])
    assert has_hard_finding(v) is True
    assert constraints_for(v) == []
    assert constraints_for(_verdict("HALT", feedback=["x"])) == []
    assert constraints_for(_verdict("ALLOW")) == []
    assert constraints_for(_verdict("ASK")) == []


def test_should_replan_policy():
    v = _verdict("ASK", feedback=["slow within 30 cm of a person"])
    assert should_replan(v, 0) is True
    assert should_replan(v, MAX_REPLAN_ROUNDS) is False
    soft_block = _verdict("BLOCK",
                           rules=(("liquid_above_electronic", False),),
                           feedback=["keep liquids away"])
    assert should_replan(soft_block, 0) is True
    hard_block = _verdict("BLOCK",
                           rules=(("sharp_toward_person", True),))
    assert should_replan(hard_block, 0) is False
    assert should_replan(_verdict("ASK"), 0) is False
    assert should_replan(_verdict("ALLOW"), 0) is False
    assert MAX_REPLAN_ROUNDS == 3


def test_replan_note_carries_evidence_and_constraints():
    v = _verdict("ASK", feedback=["slow within 30 cm of a person"])
    note = format_replan_note(v, 1)
    assert "Attempt 1 was rejected (ASK)" in note
    assert "detail for sharp_fast_near_person" in note
    assert "[sharp_fast_near_person]" in note
    assert "slow within 30 cm of a person" in note


def test_error_note_carries_error_text():
    note = format_error_note("step s2: unknown object 'spatula'", 1)
    assert "Attempt 1 failed to build" in note
    assert "unknown object 'spatula'" in note
    assert "0.25, 0.05, 0.45" in note
