"""Sentinel verdict stub (L-00): always ALLOW; the real checker is C-03."""


def check(motion, graph=None, rules=None):
    """Return an ALLOW verdict (stub)."""
    print("Sentinel: ALLOW (stub)")
    return {"kind": "ALLOW", "findings": [], "why_path": [],
            "feedback": None}
