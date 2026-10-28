"""L-05/L-06: verdict findings -> replan constraints + retry policy.

Retry policy (PLAN.md §9): retry ASK and SOFT BLOCK verdicts that carry
fixable feedback, plus invalid plans and build errors (error text as
feedback). NEVER retry a verdict containing any HARD finding. Max 3
rounds. BLOCK and HALT with hard findings get no explanation.
"""

from __future__ import annotations

MAX_REPLAN_ROUNDS = 3


def has_hard_finding(verdict: dict) -> bool:
    """True when any fired finding came from a hard rule."""
    return any(w.get("hard") for w in verdict.get("why_path", []))


def constraints_for(verdict: dict) -> list[str]:
    """Actionable constraints ([] for ALLOW/HALT or any hard finding)."""
    if verdict["kind"] not in ("ASK", "BLOCK"):
        return []
    if has_hard_finding(verdict):
        return []
    return list(verdict.get("feedback") or [])


def should_replan(verdict: dict, rounds: int,
                  max_rounds: int = MAX_REPLAN_ROUNDS) -> bool:
    """Retry iff ASK/SOFT-BLOCK with something fixable and budget left."""
    return (verdict["kind"] in ("ASK", "BLOCK") and rounds < max_rounds
            and bool(constraints_for(verdict)))


def format_replan_note(verdict: dict, attempt: int) -> str:
    """Evidence + constraints block appended to the replan prompt."""
    lines = [f"Attempt {attempt} was rejected ({verdict['kind']}). "
             f"Findings:"]
    for f in verdict["findings"]:
        lines.append(f"- {f['detail']} [{f['rule']}]")
    lines.append("You must satisfy all of these constraints:")
    for c in constraints_for(verdict):
        lines.append(f"- {c}")
    return "\n".join(lines)


def format_error_note(error: str, attempt: int) -> str:
    """Build-failure note: the error text itself is the feedback."""
    return (f"Attempt {attempt} failed to build: {error}\n"
            f"Fix the plan so it validates and builds. Tips: keep move_to "
            f"targets 0.15-0.80 m from the base column; from home, reach "
            f"far targets via [0.25, 0.05, 0.45, 0, 1, 0, 0] first.")
