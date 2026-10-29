"""R-05: rulebook versions: learned files + VERSIONS.jsonl journal.

learned/<id>.json holds active learned rules (load_rulebook rglobs
them in). VERSIONS.jsonl is append-only: {"seq", "action": add or
rollback, "rule_id", "ts", ...}. Active = added minus rolled back.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEARNED_DIR = REPO_ROOT / "sentinel" / "rules" / "learned"
JOURNAL = REPO_ROOT / "sentinel" / "rules" / "VERSIONS.jsonl"


def journal(path=None) -> list[dict]:
    """All journal entries (oldest first)."""
    path = Path(path) if path else JOURNAL
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []


def active_rules(path=None) -> list[dict]:
    """Adds not undone by a later rollback: rule_id, seq, incident, ts."""
    adds: dict[str, dict] = {}
    for e in journal(path):
        if e.get("action") == "add":
            adds[e["rule_id"]] = e
        elif e.get("action") == "rollback":
            adds.pop(e["rule_id"], None)
    return [{"rule_id": rid, "seq": e["seq"], "incident": e.get("incident"),
             "ts": e["ts"]}
            for rid, e in sorted(adds.items(), key=lambda kv: kv[1]["seq"])]


def status() -> dict:
    """Journal + active list for the dashboard Rules tab."""
    return {"journal": journal(), "active": active_rules()}


def _append(entry: dict, journal_path: Path) -> dict:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def add_rule(rule: dict, incident_id: str, gate_report: dict,
             *, learned_dir=None, journal_path=None) -> dict:
    """Write learned/<id>.json + journal the add. Raises on collision."""
    learned_dir = Path(learned_dir) if learned_dir else LEARNED_DIR
    journal_path = Path(journal_path) if journal_path else JOURNAL
    target = learned_dir / f"{rule['id']}.json"
    if target.exists():
        raise ValueError(f"rule file {target.name} already exists")
    if any(a["rule_id"] == rule["id"]
           for a in active_rules(journal_path)):
        raise ValueError(f"rule '{rule['id']}' is already active")
    learned_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rule) + "\n")
    seq = len(journal(journal_path)) + 1
    return _append({
        "seq": seq, "action": "add", "rule_id": rule["id"],
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "incident": incident_id, "rule": rule, "gate": gate_report,
    }, journal_path)


def rollback(version, *, learned_dir=None, journal_path=None) -> dict:
    """Remove a learned rule by journal seq or rule id; journal it."""
    learned_dir = Path(learned_dir) if learned_dir else LEARNED_DIR
    journal_path = Path(journal_path) if journal_path else JOURNAL
    active = {a["rule_id"]: a for a in active_rules(journal_path)}
    rule_id, reverts = None, None
    try:
        seq = int(version)
    except (TypeError, ValueError):
        seq = None
    if seq is not None:
        for a in active.values():
            if a["seq"] == seq:
                rule_id, reverts = a["rule_id"], seq
    elif isinstance(version, str) and version in active:
        rule_id, reverts = version, active[version]["seq"]
    if rule_id is None:
        raise ValueError(f"no active learned rule at version {version!r}")
    target = learned_dir / f"{rule_id}.json"
    missing = not target.exists()
    if not missing:
        target.unlink()
    entry = {
        "seq": len(journal(journal_path)) + 1, "action": "rollback",
        "rule_id": rule_id,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reverts": reverts,
    }
    if missing:
        entry["note"] = "rule file was already missing"
    return _append(entry, journal_path)
