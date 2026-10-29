"""R-05: learn CLI: incident -> Wonder -> gate -> activate.

uv run python -m learner.learn inc-001 [--recorded FILE] [--no-activate]
Exit 0 activated/accepted, 1 gate rejected, 2 Wonder refused (no_rule).
Prints the rule JSON, the gate stages, and the before/after verdicts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def learn(incident_id: str, *, events_path=None, recorded=None,
          base_rules=None, activate: bool = True,
          model: str | None = None) -> dict:
    """Propose + gate (+ activate). Pure except the model call + files."""
    from learner.events import read_events
    from learner.gate import review
    from learner.propose import (WONDER_MODEL, propose, propose_from_content)
    from learner.versions import add_rule

    log = read_events(events_path)
    inc = next((e for e in log if e.get("id") == incident_id
                and e.get("kind") == "incident"), None)
    if inc is None:
        raise ValueError(f"no incident {incident_id} in the event log")
    learned_from = [inc["id"]] + [
        e["id"] for e in log if inc.get("run_id") is not None
        and e.get("run_id") == inc.get("run_id")
        and e.get("kind") == "verdict"]
    if recorded is None:
        out = propose(incident_id, events_path=events_path,
                      model=model or WONDER_MODEL)
    else:
        out = propose_from_content(Path(recorded).read_text(), learned_from)
        out["model"] = f"recorded:{Path(recorded).name}"
    if out["rule"] is None:
        return {"outcome": "no_rule", "incident": incident_id,
                "no_rule": out["no_rule"]}
    report = review(out["rule"], base_rules=base_rules)
    result = {"outcome": "", "incident": incident_id, "rule": out["rule"],
              "report": report, "model": out.get("model"),
              "usage": out.get("usage")}
    if not report["accepted"]:
        result["outcome"] = "rejected"
        return result
    if activate:
        result["entry"] = add_rule(out["rule"], incident_id, report)
        result["outcome"] = "activated"
    else:
        result["outcome"] = "accepted"
    return result


def _before_after(report: dict) -> str:
    rows = [r for r in report.get("replay", []) if not r["control"]]
    if not rows:
        return "before ? -> after ?"
    r = rows[0]
    return f"before {r['base']} -> after {r['new']}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incident_id")
    parser.add_argument("--recorded", default=None,
                        help="recorded Wonder response (no network)")
    parser.add_argument("--events", default=None,
                        help="event log path (default out/events.jsonl)")
    parser.add_argument("--no-activate", action="store_true",
                        help="propose + gate only, do not write the rule")
    args = parser.parse_args(argv)
    try:
        res = learn(args.incident_id, events_path=args.events,
                    recorded=args.recorded,
                    activate=not args.no_activate)
    except ValueError as e:
        print(f"learn failed: {e}")
        return 1
    if res["outcome"] == "no_rule":
        print(f"Wonder refused: {res['no_rule']}")
        return 2
    print(json.dumps(res["rule"], indent=2))
    for s in res["report"]["stages"]:
        print(f"gate {s['name']}: "
              f"{'PASS' if s['passed'] else 'FAIL'} ({s['detail']})")
    print(_before_after(res["report"]))
    if res["outcome"] == "activated":
        print(f"activated as version {res['entry']['seq']}: "
              f"sentinel/rules/learned/{res['rule']['id']}.json")
        return 0
    if res["outcome"] == "accepted":
        print("accepted (dry run, not written)")
        return 0
    print(f"REJECTED: {res['report']['reason']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
