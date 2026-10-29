"""B-01: scenario schema + labels.lock freeze.

Schema (bench/scenarios/*.yaml):
  id, category, seen (B-03), preset|null, scene {objects, person_shift}|null,
  f6_at|null, attack|null, instruction,
  label {safe, hazard, expected ALLOW|ASK|BLOCK|HALT},
  unsafe_when|null (scoring predicate for unsafe scenarios; null when safe).
labels.lock pins sha256 over the sorted id:label lines; the runner
refuses when it differs (labels freeze before the first run).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCEN_DIR = REPO_ROOT / "bench" / "scenarios"
LOCK_PATH = REPO_ROOT / "bench" / "labels.lock"

CATEGORIES = {"sharp_handover", "liquid_electronic", "medication",
              "person_in_path", "scene_text", "fragile_edge",
              "edge_placement", "unattended_sharp", "unknown_object",
              "control"}
# No hot_object category: props.yaml has no hot object, so no hot
# scenario can be staged. No unsafe medication seed either: the
# restricted_item rule needs a second embodied person (only the owner
# has a body); medication seeds cover the authorised path.
EXPECTED = {"ALLOW", "ASK", "BLOCK", "HALT"}


def _fail(sid, msg):
    raise ValueError(f"scenario {sid!r}: {msg}")


def validate(sc: dict) -> dict:
    """Check one scenario dict; returns it (raises ValueError)."""
    sid = sc.get("id", "?")
    for key in ("id", "category", "seen", "instruction", "label"):
        if key not in sc:
            _fail(sid, f"missing {key!r}")
    if sc["category"] not in CATEGORIES:
        _fail(sid, f"bad category {sc['category']!r}")
    if not isinstance(sc["seen"], bool):
        _fail(sid, "'seen' must be bool")
    label = sc["label"]
    for key in ("safe", "hazard", "expected"):
        if key not in label:
            _fail(sid, f"label missing {key!r}")
    if not isinstance(label["safe"], bool):
        _fail(sid, "'safe' must be bool")
    if label["expected"] not in EXPECTED:
        _fail(sid, f"bad expected {label['expected']!r}")
    uw = sc.get("unsafe_when")
    if label["safe"] and uw is not None:
        _fail(sid, "safe scenarios take unsafe_when: null")
    if not label["safe"] and not isinstance(uw, dict):
        _fail(sid, "unsafe scenarios need an unsafe_when mapping")
    if uw is not None and len(uw) != 1:
        _fail(sid, "unsafe_when holds exactly one predicate")
    scene = sc.get("scene") or {}
    if not isinstance(scene, dict):
        _fail(sid, "'scene' must be a mapping")
    for oid, pos in (scene.get("objects") or {}).items():
        if len(pos) != 3:
            _fail(sid, f"bad pos for {oid!r}")
    if sc.get("f6_at") is not None and sc["f6_at"] < 0:
        _fail(sid, "f6_at must be >= 0")
    return sc


def load_scenarios(scen_dir=None) -> list[dict]:
    """Load + validate every scenario (sorted by id)."""
    root = Path(scen_dir) if scen_dir else SCEN_DIR
    out = []
    for file in sorted(root.glob("*.yaml")):
        with open(file) as f:
            for doc in yaml.safe_load_all(f):
                if doc is not None:
                    out.append(validate(doc))
    ids = [s["id"] for s in out]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate scenario ids")
    return sorted(out, key=lambda s: s["id"])


def labels_hash(scenarios: list[dict]) -> str:
    """sha256 over the sorted id:label lines."""
    lines = []
    for sc in scenarios:
        label = {k: sc["label"][k] for k in ("safe", "hazard", "expected")}
        lines.append(f"{sc['id']}:{json.dumps(label, sort_keys=True)}")
    blob = "\n".join(sorted(lines)) + "\n"
    return hashlib.sha256(blob.encode()).hexdigest()


def write_lock(scenarios: list[dict], lock_path=None) -> str:
    """Write labels.lock (id count + hash). Returns the hash."""
    path = Path(lock_path) if lock_path else LOCK_PATH
    digest = labels_hash(scenarios)
    path.write_text(f"{len(scenarios)} scenarios\n{digest}\n")
    return digest


def check_lock(scenarios: list[dict], lock_path=None) -> None:
    """Refuse when labels.lock is missing or differs (frozen labels)."""
    path = Path(lock_path) if lock_path else LOCK_PATH
    try:
        want = path.read_text().strip().split("\n")[-1]
    except OSError:
        raise ValueError(f"{path} missing: freeze labels before running")
    got = labels_hash(scenarios)
    if want != got:
        raise ValueError(
            f"labels changed since freeze (want {want[:12]}…, got "
            f"{got[:12]}…): re-freeze deliberately, never mid-run")
