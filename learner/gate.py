"""R-04: admission gate for learned rules.

Stages, in order (first failure rejects):
1. schema + vocabulary + soft-only + id collision;
2. replay: every incident case must now be caught;
3. ratchet: controls stay ALLOW, BLOCK/HALT never weakens;
4. preflight: the incident stays caught when the object moves
   +/-5 cm or the person moves +/-10 cm.
Pure check() replays: deterministic, no network, no robot.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPLAY_DIR = REPO_ROOT / "tests" / "fixtures" / "replay"

OBJ_SHIFT_M = 0.05
PERSON_SHIFT_M = 0.10


def load_cases(replay_dir=None) -> list[dict]:
    """Read every replay case (motion + full graph, JSON-native)."""
    root = Path(replay_dir) if replay_dir else REPLAY_DIR
    cases = []
    for file in sorted(root.glob("*.json")):
        case = json.loads(file.read_text())
        cases.append(case)
    return cases


def _run_check(motion, graph, rules):
    """check() that returns (verdict, error) instead of raising."""
    from sentinel.check import check

    try:
        return check(motion, graph, rules), None
    except Exception as e:  # noqa: BLE001 - a crash rejects the candidate
        return None, f"{type(e).__name__}: {e}"


def _schema_check(candidate: dict, base_ids: set[str]):
    """Stage 1: shape, vocabulary, single scope, soft-only, no collision."""
    from sentinel.check import VOCABULARY

    if not isinstance(candidate.get("id"), str) or not candidate["id"]:
        return False, "candidate needs a string 'id'"
    if candidate["id"] in base_ids:
        return False, f"rule id '{candidate['id']}' already exists"
    when = candidate.get("when")
    unless = candidate.get("unless", {})
    if not isinstance(when, dict) or not when:
        return False, "candidate needs a non-empty 'when' object"
    if not isinstance(unless, dict):
        return False, "candidate 'unless' must be an object"
    names = set()
    for clause in (when, unless):
        names |= set(clause) - {"any"}
        for sub in clause.get("any", []):
            if not isinstance(sub, dict):
                return False, "'any' entries must be objects"
            names |= set(sub) - {"any"}
    usable = {n for n, s in VOCABULARY.items() if s["scope"] != "live"}
    unknown = names - usable
    if unknown:
        return False, f"unknown predicates: {sorted(unknown)}"
    scopes = {VOCABULARY[n]["scope"] for n in names}
    if len(scopes) > 1:
        return False, f"mixed scopes {sorted(scopes)} in one rule"
    if candidate.get("verdict") != "ASK" or candidate.get("hard"):
        return False, "learned rules activate soft (ASK, hard false)"
    if candidate.get("fixable"):
        return False, "learned rules ask the owner (fixable false)"
    return True, f"soft ASK, scope {next(iter(scopes))}"


def _preflight_variants(case: dict):
    """(name, graph) pairs: object +/-5 cm, person +/-10 cm in x."""
    spec = case.get("preflight") or {}
    obj, person = spec.get("object"), spec.get("person")
    if obj not in case["graph"]["objects"] or person not in (
            case["graph"].get("people", {})):
        return []
    out = []
    for sign, tag in ((1.0, "+"), (-1.0, "-")):
        g = copy.deepcopy(case["graph"])
        g["objects"][obj]["pos"][0] += sign * OBJ_SHIFT_M
        out.append((f"{obj} x{tag}5cm", g))
        g = copy.deepcopy(case["graph"])
        for part in ("hand", "torso"):
            g["people"][person][part][0] += sign * PERSON_SHIFT_M
        out.append((f"{person} x{tag}10cm", g))
    return out


def review(candidate: dict, *, replay_dir=None,
           base_rules: list[dict] | None = None) -> dict:
    """Run the gate; report carries per-stage pass/fail + details."""
    from sentinel.check import SEVERITY, load_rulebook

    base = base_rules if base_rules is not None else load_rulebook()
    rules = list(base) + [candidate]
    report: dict = {"rule_id": candidate.get("id"), "accepted": False,
                    "reason": "", "stages": [], "replay": [],
                    "preflight": []}

    def stage(name, passed, detail):
        report["stages"].append({"name": name, "passed": passed,
                                 "detail": detail})
        return passed

    ok, detail = _schema_check(candidate, {r["id"] for r in base})
    if not stage("schema", ok, detail):
        report["reason"] = f"schema: {detail}"
        return report

    cases = load_cases(replay_dir)
    incidents = [c for c in cases if not c.get("control")]
    for case in cases:
        bv, berr = _run_check(case["motion"], case["graph"], base)
        nv, nerr = _run_check(case["motion"], case["graph"], rules)
        if berr or nerr:
            detail = f"{case['id']}: checker crashed ({nerr or berr})"
            stage("replay", False, detail)
            report["reason"] = f"replay: {detail}"
            return report
        fired = any(f["rule"] == candidate["id"]
                    for f in nv["findings"])
        report["replay"].append({"case": case["id"],
                                 "control": bool(case.get("control")),
                                 "base": bv["kind"], "new": nv["kind"],
                                 "candidate_fired": fired})
    missed = [r["case"] for r in report["replay"]
              if not r["control"] and not r["candidate_fired"]]
    if not incidents:
        stage("replay", False, "no incident case in the replay set")
        report["reason"] = "replay: no incident case in the replay set"
        return report
    if missed:
        detail = f"incident not caught: {missed}"
        stage("replay", False, detail)
        report["reason"] = f"replay: {detail}"
        return report
    stage("replay", True,
          f"{len(incidents)} incident(s) caught, "
          f"{len(cases) - len(incidents)} control(s) replayed")

    regressions = [r["case"] for r in report["replay"]
                   if r["control"]
                   and (r["candidate_fired"] or r["new"] != r["base"])]
    weakened = [r["case"] for r in report["replay"]
                if r["base"] in ("BLOCK", "HALT")
                and SEVERITY[r["new"]] < SEVERITY[r["base"]]]
    if regressions or weakened:
        detail = f"controls regressed: {regressions}; weakened: {weakened}"
        stage("ratchet", False, detail)
        report["reason"] = f"ratchet: {detail}"
        return report
    stage("ratchet", True, "controls ALLOW, BLOCK/HALT never weaken")

    for case in incidents:
        variants = _preflight_variants(case)
        if not variants:
            detail = f"{case['id']}: no preflight object/person in graph"
            stage("preflight", False, detail)
            report["reason"] = f"preflight: {detail}"
            return report
        for name, graph in variants:
            nv, nerr = _run_check(case["motion"], graph, rules)
            if nerr:
                detail = f"{case['id']} {name}: checker crashed ({nerr})"
                stage("preflight", False, detail)
                report["reason"] = f"preflight: {detail}"
                return report
            fired = any(f["rule"] == candidate["id"]
                        for f in nv["findings"])
            report["preflight"].append({"case": case["id"], "variant": name,
                                        "verdict": nv["kind"],
                                        "candidate_fired": fired})
    escaped = [f"{p['case']} {p['variant']}" for p in report["preflight"]
               if not p["candidate_fired"]]
    if escaped:
        detail = f"incident escapes: {escaped}"
        stage("preflight", False, detail)
        report["reason"] = f"preflight: {detail}"
        return report
    stage("preflight", True,
          f"{len(report['preflight'])} variant(s) still caught")
    report["accepted"] = True
    report["reason"] = "all stages passed"
    return report
