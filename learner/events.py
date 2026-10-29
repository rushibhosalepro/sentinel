"""R-01: append-only event log for the rule learner (out/events.jsonl).

Every verdict round, ASK answer, HALT, build surprise, and unknown
object lands here; the owner can also file incident entries from the
dashboard. Propose (R-02) reads incidents + their run context; the
gate (R-04) replays saved motions. Appends never raise: logging must
not break the robot.
"""

from __future__ import annotations

import datetime
import json
import threading
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "out" / "events.jsonl"

_lock = threading.Lock()
_path = DEFAULT_PATH


def set_log_path(p) -> None:
    """Redirect the log (tests)."""
    global _path
    _path = Path(p)


def get_log_path() -> Path:
    return _path


def compact_graph(graph) -> dict | None:
    """Graph snapshot reduced to ids + props (+ owner/conf)."""
    if graph is None:
        return None
    from dashboard.events import to_jsonable

    return to_jsonable({
        "objects": {
            oid: {"properties": node.get("properties", []),
                  "owner": node.get("owner"), "conf": node.get("conf")}
            for oid, node in graph.get("objects", {}).items()},
        "people": sorted(graph.get("people", {})),
    })


def _next_incident_n(path: Path) -> int:
    try:
        with open(path) as f:
            n = sum(1 for line in f if '"kind": "incident"' in line)
    except OSError:
        return 1
    return n + 1


def append_event(entry: dict) -> dict:
    """Stamp ts/id, append as one JSONL line, return the stamped entry."""
    from dashboard.events import to_jsonable

    entry = dict(entry)
    entry.setdefault("ts", datetime.datetime.now(
        datetime.timezone.utc).isoformat())
    with _lock:
        if "id" not in entry:
            if entry.get("kind") == "incident":
                n = _next_incident_n(_path)
                entry["id"] = f"inc-{n:03d}"
                entry["incident_n"] = n
            else:
                entry["id"] = f"ev-{uuid.uuid4().hex[:8]}"
        try:
            _path.parent.mkdir(parents=True, exist_ok=True)
            with open(_path, "a") as f:
                f.write(json.dumps(to_jsonable(entry)) + "\n")
        except OSError as e:
            print(f"event log write failed: {e}")
    return entry


def read_events(path=None) -> list[dict]:
    """Read the whole log (propose/gate/rollback tooling)."""
    path = Path(path) if path else get_log_path()
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []
