"""C-03: the real Sentinel. check(motion, graph, rules) -> Verdict.

No LLM inside (PLAN.md §9 rule 1). Rules are data (sentinel/rules/*.json);
this module only matches predicates from sentinel/relations.py against the
§4 Rule contract and assembles the verdict. Most severe wins
(BLOCK > HALT > ASK > ALLOW). Feedback carries constraint hints from SOFT
fixable findings only -- hard BLOCKs return NO feedback (don't teach a
jailbroken planner how to get around them).
"""

from __future__ import annotations

import json
from pathlib import Path

from sentinel import relations as R

RULES_DIR = Path(__file__).parent / "rules"

SEVERITY = {"ALLOW": 0, "ASK": 1, "HALT": 2, "BLOCK": 3}

# A release higher than this above the counter (top z = 0) is a drop, not
# a placement: placements release at ~5 cm, the trick releases at 20 cm.
RELEASE_AIR_Z_M = 0.15


def _props(graph, obj) -> list:
    node = graph["objects"].get(obj)
    return [] if node is None else list(node.get("properties", []))


# --- sample-scope predicates: (motion, graph, i, params) -> (match, evidence)

def _p_held_property(motion, graph, i, params):
    obj = motion["held"][i]
    hit = [p for p in params if p in _props(graph, obj)] if obj else []
    return bool(hit), {"obj": obj, "props": hit}


def _with_margin(m, graph, t, speed):
    m = dict(m)
    m["margin_cm"] = R.person_margin_cm(graph, m["person"], t, speed)
    return m


def _p_blade_toward_person(motion, graph, i, params):
    m = R.measure_blade(motion, graph, i)
    if m is None:
        return False, {}
    m = _with_margin(m, graph, motion["t"][i], motion["speed"][i])
    ok = m["toward"] and m["tip_cm"] - m["margin_cm"] <= float(
        params["within_cm"])
    return ok, m


def _p_held_near_person(motion, graph, i, params):
    m = R.measure_held(motion, graph, i)
    if m is None:
        return False, {}
    m = _with_margin(m, graph, motion["t"][i], motion["speed"][i])
    return m["gap_cm"] - m["margin_cm"] <= float(params["within_cm"]), m


def _p_speed(motion, graph, i, params):
    return motion["speed"][i] == params, {"speed": motion["speed"][i]}


def _p_held_near_electronic(motion, graph, i, params):
    m = R.measure_held_electronic(motion, graph, i)
    if m is None:
        return False, {}
    return m["gap_cm"] <= float(params["within_cm"]), m


def _p_tilt_above_deg(motion, graph, i, params):
    return float(motion["tilt"][i]) > float(params), \
        {"tilt_deg": float(motion["tilt"][i])}


SAMPLE_PREDS = {"held_property": _p_held_property,
                "blade_toward_person": _p_blade_toward_person,
                "held_near_person": _p_held_near_person,
                "speed": _p_speed,
                "held_near_electronic": _p_held_near_electronic,
                "tilt_above_deg": _p_tilt_above_deg}


# --- event-scope predicates: (ev, graph, params) -> (match, evidence)

def _p_release_property(ev, graph, params):
    hit = [p for p in params if p in _props(graph, ev["obj"])]
    return bool(hit), {"obj": ev["obj"], "props": hit}


def _p_release_above_surface(ev, graph, params):
    if ev["pos"] is None:
        return False, {}
    z = float(ev["pos"][2])
    return (z > RELEASE_AIR_Z_M) == bool(params), {"z_cm": z * 100.0}


def _p_release_near_person(ev, graph, params):
    if ev["pos"] is None:
        return False, {}
    pid, part, d = R.nearest_person_part(ev["pos"], graph, ev["t"])
    gap = d * 100.0
    m = _with_margin({"gap_cm": gap, "person": pid, "part": part},
                     graph, ev["t"], ev["speed"])
    return m["gap_cm"] - m["margin_cm"] <= float(params["within_cm"]), m


def _p_release_into_hand(ev, graph, params):
    into, who = R.release_into_hand(ev, graph)
    return into == bool(params), {"into_hand": into, "person": who}


def _p_handover_to_person(ev, graph, params):
    into, who = R.release_into_hand(ev, graph)
    return into == bool(params), {"person": who, "obj": ev["obj"]}


def _p_given_property(ev, graph, params):
    return _p_release_property(ev, graph, params)


def _p_given_owned_by_other(ev, graph, params):
    into, who = R.release_into_hand(ev, graph)
    owner = graph["objects"].get(ev["obj"], {}).get("owner")
    other = into and owner is not None and owner != who
    return other == bool(params), {"obj": ev["obj"], "owner": owner,
                                   "person": who}


def _p_recipient_authorised(ev, graph, params):
    into, who = R.release_into_hand(ev, graph)
    auth = into and R.recipient_authorised(graph, who)
    return auth == bool(params), {"person": who, "authorised": auth}


EVENT_PREDS = {"release_property": _p_release_property,
               "release_above_surface": _p_release_above_surface,
               "release_near_person": _p_release_near_person,
               "release_into_hand": _p_release_into_hand,
               "handover_to_person": _p_handover_to_person,
               "given_property": _p_given_property,
               "given_owned_by_other": _p_given_owned_by_other,
               "recipient_authorised": _p_recipient_authorised}


# --- motion-scope predicates: (motion, graph, params) -> (match, evidence)

def _p_target_unknown(motion, graph, params):
    missing = [h for h in R.held_ids(motion)
               if h not in graph["objects"]]
    return (bool(missing)) == bool(params), {"obj": missing[0] if missing
                                              else None}


def _p_target_low_confidence(motion, graph, params):
    low = [(h, R.conf_of(graph, h)) for h in R.held_ids(motion)
           if h in graph["objects"]
           and R.conf_of(graph, h) < float(params["below"])]
    return bool(low), {"obj": low[0][0] if low else None,
                       "conf": low[0][1] if low else None}


def _p_derived_from_scene_text(motion, graph, params):
    src = motion.get("derived_from")
    hit = (not src) or str(src).startswith("scene_text:")
    return hit == bool(params), {"derived_from": src}


MOTION_PREDS = {"target_unknown": _p_target_unknown,
                "target_low_confidence": _p_target_low_confidence,
                "derived_from_scene_text": _p_derived_from_scene_text}


def _rule_scope(rule) -> str:
    keys = set()
    for clause in (rule["when"], rule["unless"]):
        keys |= set(clause) - {"any"}
        for sub in clause.get("any", []):
            keys |= set(sub) - {"any"}
    if keys & set(EVENT_PREDS):
        return "event"
    if keys & set(MOTION_PREDS):
        return "motion"
    return "sample"


def _eval_clause(clause: dict, table: dict, *args) -> tuple[bool, dict]:
    """All predicates must match; 'any' holds OR-ed sub-clauses."""
    ev = {}
    for name, params in clause.items():
        if name == "any":
            branch = None
            for sub in params:
                ok, sub_ev = _eval_clause(sub, table, *args)
                if ok:
                    branch = sub_ev
                    break
            if branch is None:
                return False, {}
            ev.update(branch)
            continue
        try:
            fn = table[name]
        except KeyError:
            raise ValueError(f"unknown predicate {name!r}") from None
        ok, sub_ev = fn(*args, params)
        if not ok:
            return False, {}
        ev.update(sub_ev)
    return True, ev


def load_rulebook(path=None) -> list[dict]:
    """Read hard + soft rules; fail LOUD on unknown predicates (fail-closed)."""
    root = Path(path) if path else RULES_DIR
    rules = []
    for file in sorted(root.rglob("*.json")):
        rule = json.loads(file.read_text())
        for clause in (rule["when"], rule["unless"]):
            names = set(clause) - {"any"}
            for sub in clause.get("any", []):
                names |= set(sub) - {"any"}
            known = set(SAMPLE_PREDS) | set(EVENT_PREDS) | set(MOTION_PREDS)
            bad = names - known
            if bad:
                raise ValueError(f"{file.name}: unknown predicate(s) "
                                 f"{sorted(bad)}")
        rules.append(rule)
    return rules


def _detail(rule_id: str, ev: dict) -> str:
    margin = (f" (clearance {ev['margin_cm']:.0f} cm)"
              if "margin_cm" in ev else "")
    if rule_id == "sharp_toward_person":
        return (f"knife blade {ev['tip_cm']:.0f} cm from "
                f"{ev['person']}'s {ev['part']}, pointing at them "
                f"(handle {ev['handle_cm']:.0f} cm){margin}")
    if rule_id == "release_near_person_in_air":
        return (f"released {ev['obj']} in mid-air {ev['gap_cm']:.0f} cm "
                f"from {ev['person']} (not into a hand){margin}")
    if rule_id == "sharp_fast_near_person":
        return (f"held {ev['obj']} at normal speed {ev['gap_cm']:.0f} cm "
                f"from {ev['person']}'s {ev['part']}{margin}")
    if rule_id == "liquid_above_electronic":
        what = f"tilted {ev['tilt_deg']:.0f}°" if "tilt_deg" in ev \
            else f"held {ev['obj']}"
        where = "above" if ev.get("above") else "from"
        return (f"{what} {ev['gap_cm']:.0f} cm {where} electronic "
                f"{ev['electronic']}")
    if rule_id == "restricted_item":
        why = ("medication" if "medication" in ev.get("props", [])
               else f"owned by {ev.get('owner')}")
        return (f"handing {ev['obj']} ({why}) to {ev['person']}, who is "
                f"not authorised")
    if rule_id == "unknown_object":
        if ev.get("conf") is None:
            return f"target {ev['obj']} is not in the scene graph"
        return (f"target {ev['obj']} confidence {ev['conf']:.2f} "
                f"below threshold")
    if rule_id == "scene_text_provenance":
        src = ev.get("derived_from")
        if not src:
            return "motion has no provenance"
        return f"motion derived from scene text ({src}), not the owner"
    return f"{rule_id} fired"


def _node_of(ev: dict) -> str | None:
    for key in ("person", "electronic", "obj"):
        if ev.get(key):
            return ev[key]
    return None


def check(motion, graph, rules=None) -> dict:
    """Evaluate the rulebook over the motion; most severe verdict wins."""
    if rules is None:
        rules = load_rulebook()
    events = R.release_events(motion, graph)
    findings = []
    for rule in rules:
        scope = _rule_scope(rule)
        if scope == "sample":
            table, items = SAMPLE_PREDS, range(len(motion["t"]))
            stamp = lambda i: (motion, graph, i)  # noqa: E731
            when_t = lambda i: motion["t"][i]  # noqa: E731
        elif scope == "event":
            table, items = EVENT_PREDS, events
            stamp = lambda ev: (ev, graph)  # noqa: E731
            when_t = lambda ev: ev["t"]  # noqa: E731
        else:
            table, items = MOTION_PREDS, [None]
            stamp = lambda _: (motion, graph)  # noqa: E731
            when_t = lambda _: 0.0  # noqa: E731
        for item in items:
            ok, ev = _eval_clause(rule["when"], table, *stamp(item))
            if not ok:
                continue
            # An empty unless means "no exceptions" (vacuous match would
            # suppress everything).
            if rule["unless"]:
                blocked, _ = _eval_clause(rule["unless"], table,
                                           *stamp(item))
                if blocked:
                    continue
            findings.append({"rule": rule["id"], "node": _node_of(ev),
                             "t": when_t(item), "detail": _detail(rule["id"],
                                                                  ev),
                             "_verdict": rule["verdict"],
                             "_hard": rule["hard"],
                             "_hint": rule["constraint_hint"],
                             "_fixable": rule["fixable"]})
            break  # first firing per rule
    # C-09: fill the liquid hint's {safe_spot} from the graph. No spot
    # (crowded counter, or a graph that never computed one) downgrades
    # the finding to an unfixable ASK: straight to the owner, no replan.
    spot = graph.get("safe_spot_pour")
    for f in findings:
        if f["rule"] != "liquid_above_electronic":
            continue
        if spot is None:
            f["_verdict"] = "ASK"
            f["_fixable"] = False
        else:
            f["_hint"] = f["_hint"].replace(
                "{safe_spot}", f"({spot[0]:.2f}, {spot[1]:.2f})")
    kind = "ALLOW"
    for f in findings:
        if SEVERITY[f["_verdict"]] > SEVERITY[kind]:
            kind = f["_verdict"]
    ordered = sorted(findings,
                     key=lambda f: SEVERITY[f["_verdict"]], reverse=True)
    why_path = [{"rule": f["rule"], "verdict": f["_verdict"],
                 "hard": f["_hard"], "t": f["t"]} for f in ordered]
    # Feedback explains the verdict: hints from soft fixable findings AT
    # the winning severity. Any HARD finding kills all feedback (never
    # teach a jailbroken planner), even when a soft finding fired too.
    any_hard = any(f["_hard"] for f in ordered)
    hints = [f["_hint"] for f in ordered
             if f["_verdict"] == kind and not f["_hard"]
             and f["_fixable"] and f["_hint"]]
    feedback = None if any_hard else (sorted(set(hints)) or None)
    for f in findings:
        for k in ("_verdict", "_hard", "_hint", "_fixable"):
            del f[k]
    print(f"Sentinel: {kind}" + (f" ({len(findings)} finding(s))"
                                       if findings else ""))
    return {"kind": kind, "findings": findings, "why_path": why_path,
            "feedback": feedback}
