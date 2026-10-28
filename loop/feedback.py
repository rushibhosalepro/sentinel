"""L-05/L-06: verdict findings -> replan constraints + retry policy.

constraints_for: hints the planner can act on ([] for BLOCK/HALT --
a hard BLOCK is never retried and never explained).
format_replan_note: evidence + constraints block for the replan prompt.
should_replan: ASK + fixable feedback + rounds left.
"""

from __future__ import annotations

MAX_REPLAN_ROUNDS = 3


def constraints_for(verdict: dict) -> list[str]:
    """Actionable constraints ([] for BLOCK/HALT)."""
    if verdict["kind"] in ("BLOCK", "HALT"):
        return []
    return list(verdict.get("feedback") or [])


def should_replan(verdict: dict, rounds: int,
                  max_rounds: int = MAX_REPLAN_ROUNDS) -> bool:
    """Retry iff ASK with something fixable and budget left."""
    return (verdict["kind"] == "ASK" and rounds < max_rounds
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
