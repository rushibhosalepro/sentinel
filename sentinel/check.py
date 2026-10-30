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


def _p_held_near_object_property(motion, graph, i, params):
    m = R.measure_held_object_property(motion, graph, i,
                                       params["properties"])
    if m is None:
        return False, {}
    return m["gap_cm"] <= float(params["within_cm"]), m


def _p_object_near_edge(motion, graph, i, params):
    """A graph-static sample predicate: an object with one of `properties`
    within `edge_cm` of the counter edge (graph_view.edge_cm)."""
    hits = [(oid, node["edge_cm"]) for oid, node in graph["objects"].items()
            if node.get("edge_cm") is not None
            and set(params["properties"]) & set(
                node.get("properties", []))
            and node["edge_cm"] <= float(params["edge_cm"])]
    if not hits:
        return False, {}
    oid, ecm = min(hits, key=lambda h: h[1])
    return True, {"edge_obj": oid, "edge_cm": ecm}


SAMPLE_PREDS = {"held_property": _p_held_property,
                "blade_toward_person": _p_blade_toward_person,
                "held_near_person": _p_held_near_person,
                "speed": _p_speed,
                "held_near_electronic": _p_held_near_electronic,
                "tilt_above_deg": _p_tilt_above_deg,
                "held_near_object_property":
                    _p_held_near_object_property,
                "object_near_edge": _p_object_near_edge}


# R-02 fixed vocabulary for the learner: scope + param shapes + prose.
# Scopes: sample (per motion sample), event (per release), motion
# (whole plan). "live" is listed for load_rulebook only: the gate
# rejects it (learned live rules need monitor support).
VOCABULARY = {
    "held_property": {
        "scope": "sample", "params": "list",
        "desc": "gripper holds an object with one of these properties"},
    "blade_toward_person": {
        "scope": "sample", "params": {"within_cm": "number"},
        "desc": "held blade tip within N cm of a person, pointing at them"},
    "held_near_person": {
        "scope": "sample", "params": {"within_cm": "number"},
        "desc": "held object within N cm of a person (reach margin "
                "included)"},
    "speed": {
        "scope": "sample", "params": "speed",
        "desc": '"normal" or "slow" gripper speed'},
    "held_near_electronic": {
        "scope": "sample", "params": {"within_cm": "number"},
        "desc": "held object within N cm (horizontal) of an electronic"},
    "tilt_above_deg": {
        "scope": "sample", "params": "number",
        "desc": "gripper tilt above N degrees while holding"},
    "held_near_object_property": {
        "scope": "sample",
        "params": {"properties": "list", "within_cm": "number"},
        "desc": "held object within N cm (horizontal) of another object "
                "with one of these properties"},
    "object_near_edge": {
        "scope": "sample",
        "params": {"properties": "list", "edge_cm": "number"},
        "desc": "an object with one of these properties sits within N cm "
                "of the counter edge (graph property, same every sample)"},
    "release_property": {
        "scope": "event", "params": "list",
        "desc": "released object has one of these properties"},
    "release_above_surface": {
        "scope": "event", "params": "bool",
        "desc": "release happens in the air (true) or at a surface"},
    "release_near_person": {
        "scope": "event", "params": {"within_cm": "number"},
        "desc": "release within N cm of a person"},
    "release_near_edge": {
        "scope": "event", "params": {"edge_cm": "number"},
        "desc": "release lands on the counter within N cm of its edge "
                "(hand-overs off the counter never match)"},
    "release_into_hand": {
        "scope": "event", "params": "bool",
        "desc": "release goes into a person's hand"},
    "handover_to_person": {
        "scope": "event", "params": "bool",
        "desc": "a hand-over to a person happens"},
    "given_property": {
        "scope": "event", "params": "list",
        "desc": "handed-over object has one of these properties"},
    "given_owned_by_other": {
        "scope": "event", "params": "bool",
        "desc": "handed-over object is owned by someone else"},
    "recipient_authorised": {
        "scope": "event", "params": "bool",
        "desc": "the hand-over recipient is authorised"},
    "target_unknown": {
        "scope": "motion", "params": "bool",
        "desc": "plan grasps an object missing from the scene graph"},
    "target_low_confidence": {
        "scope": "motion", "params": {"below": "number"},
        "desc": "plan grasps an object perceived below confidence N"},
    "derived_from_scene_text": {
        "scope": "motion", "params": "bool",
        "desc": "the plan was shaped by quarantined scene text"},
    "person_in_path": {
        "scope": "live", "params": "bool",
        "desc": "LIVE ONLY: a person blocks the arm during execution"},
}


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


def _p_release_near_edge(ev, graph, params):
    """A release lands on the counter within N cm of its edge. (B-11)

    Off-counter releases (hand-overs) never match; graphs without
    counter bounds (old fixtures) never match either.
    """
    if ev["pos"] is None:
        return False, {}
    counter = graph.get("counter")
    if counter is None:
        return False, {}
    x, y = float(ev["pos"][0]), float(ev["pos"][1])
    (x0, x1), (y0, y1) = counter["x"], counter["y"]
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False, {"edge_cm": None, "on_counter": False}
    edge = min(x - x0, x1 - x, y - y0, y1 - y) * 100.0
    return edge <= float(params["edge_cm"]), {"edge_cm": round(edge, 1),
                                              "obj": ev["obj"]}


EVENT_PREDS = {"release_property": _p_release_property,
               "release_above_surface": _p_release_above_surface,
               "release_near_person": _p_release_near_person,
               "release_near_edge": _p_release_near_edge,
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


def _p_person_in_path(*args):
    raise AssertionError("live-scoped rule evaluated by check()")


# Live scope: evaluated by loop/monitor.py during execution against live
# sim state, never by check(). Registered here so load_rulebook accepts
# the predicate (fail-closed on typos is preserved).
LIVE_PREDS = {"person_in_path": _p_person_in_path}


def _rule_scope(rule) -> str:
    keys = set()
    for clause in (rule["when"], rule["unless"]):
        keys |= set(clause) - {"any"}
        for sub in clause.get("any", []):
            keys |= set(sub) - {"any"}
    if keys & set(LIVE_PREDS):
        return "live"
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
    """Read hard + soft (+ learned) rules; fail LOUD on unknown
    predicates or mixed-scope rules (fail-closed)."""
    root = Path(path) if path else RULES_DIR
    rules = []
    for file in sorted(root.rglob("*.json")):
        rule = json.loads(file.read_text())
        names = set()
        for clause in (rule["when"], rule["unless"]):
            names |= set(clause) - {"any"}
            for sub in clause.get("any", []):
                names |= set(sub) - {"any"}
        known = (set(SAMPLE_PREDS) | set(EVENT_PREDS)
                 | set(MOTION_PREDS) | set(LIVE_PREDS))
        bad = names - known
        if bad:
            raise ValueError(f"{file.name}: unknown predicate(s) "
                             f"{sorted(bad)}")
        scopes = {VOCABULARY[n]["scope"] for n in names} - {"live"}
        if len(scopes) > 1:
            raise ValueError(f"{file.name}: mixed-scope rule {sorted(scopes)}"
                             " (one scope per rule)")
        rules.append(rule)
    return rules


def _detail(rule: dict, ev: dict) -> str:
    rule_id = rule["id"]
    margin = (f" (clearance {ev['margin_cm']:.0f} cm)"
              if "margin_cm" in ev else "")
    if rule_id == "sharp_toward_person":
        return (f"knife blade {ev['tip_cm']:.0f} cm from "
                f"{ev['person']}'s {ev['part']}, pointing at them "
                f"(handle {ev['handle_cm']:.0f} cm){margin}")
    if rule_id == "release_near_person_in_air":
        return (f"released {ev['obj']} in mid-air {ev['gap_cm']:.0f} cm "
                f"from {ev['person']} (not into a hand){margin}")
    if rule_id == "hazard_fast_near_person":
        props = ", ".join(ev.get("props", []))
        return (f"{ev['obj']} ({props}) at normal speed "
                f"{ev['gap_cm']:.0f} cm from "
                f"{ev['person']}'s {ev['part']}")
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
    return rule.get("reason") or f"{rule_id} fired"


def _node_of(ev: dict) -> str | None:
    for key in ("person", "electronic", "obj"):
        if ev.get(key):
            return ev[key]
    return None


def _origin_of(rule: dict) -> str:
    """seed for hand-written rules, learned once R-02 revises one."""
    return "learned" if rule.get("learned_from") else "seed"


def _steps_of(motion: dict, scope: str, item, ev: dict) -> list[str]:
    """Plan step ids behind the firing sample/event (D-03 Why?)."""
    if scope == "sample":
        ss = motion.get("sample_steps") or []
        return [ss[item]] if item < len(ss) else []
    if scope == "event":
        return [item["step_id"]] if item.get("step_id") else []
    obj = ev.get("obj")
    if obj is None:  # plan-level taint (scene text): the whole plan
        return list(motion.get("step_ids", []))
    ss = motion.get("sample_steps") or []
    held = motion.get("held") or []
    return sorted({ss[i] for i, h in enumerate(held)
                   if h == obj and i < len(ss)})


def _relations_of(rule_id: str, ev: dict) -> list[dict]:
    """Graph-relation triples the rule fired on (D-03 Why?)."""
    subj = ev.get("obj", "motion")
    who = ev.get("person") or ev.get("electronic") or ev.get("near")
    if rule_id == "sharp_toward_person":
        rel = "POINTS_AT"
    elif rule_id == "liquid_above_electronic":
        rel = "ABOVE"
    elif rule_id == "restricted_item":
        rel = "GIVEN_TO"
    elif rule_id == "unknown_object":
        return [{"subj": ev.get("obj"), "rel": "MISSING_FROM",
                 "obj": "scene_graph"}]
    elif rule_id == "scene_text_provenance":
        return [{"subj": "motion", "rel": "DERIVED_FROM",
                 "obj": ev.get("derived_from") or "unknown"}]
    else:
        rel = "NEAR"
    if subj is None or who is None:
        return []
    return [{"subj": subj, "rel": rel, "obj": who}]


def _edit_distance(a: str, b: str, cap: int = 2) -> int:
    """Levenshtein distance with early exit above cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


# C-10: instruction nouns that are not graph ids/labels but name a
# specific object anyway. Identity entries (phone, laptop) pin the
# vocabulary explicitly.
OBJECT_SYNONYMS = {"mug": "cup", "glass": "wine_glass",
                   "pills": "pill_bottle", "phone": "phone",
                   "laptop": "laptop"}
# Only these words count as object adjectives: "blue mug" must ASK,
# but "move the cup" must not treat "move" as one.
ADJECTIVES = frozenset({
    "red", "orange", "yellow", "green", "blue", "purple", "pink",
    "brown", "black", "white", "grey", "gray", "clear", "golden",
    "silver", "big", "small", "large", "little", "hot", "cold",
    "full", "empty", "clean",
})
DETERMINERS = frozenset({"the", "a", "an", "my", "your", "this",
                         "that"})


def _unknown_object_finding(motion, graph, instruction: str):
    """C-10: instruction names a described object that is not there.

    "hand me the blue mug" while the plan grasps the cup: the head
    noun resolves (mug~cup) but "blue" matches nothing about the cup,
    so the plan is acting on a guess -> ASK the owner instead of
    executing it. Bare synonyms ("hand me the mug") ALLOW. Heads
    resolve via graph ids/labels + OBJECT_SYNONYMS, adjectives match
    against id + label + prompt tokens. Plain string matching, no LLM.
    """
    import re

    held = [h for h in R.held_ids(motion) if h in graph["objects"]]
    if not held:
        return None
    objects = graph["objects"]
    head_of = {}
    for oid in objects:
        head_of.setdefault(oid, oid)
        for tok in oid.split("_"):
            head_of.setdefault(tok, oid)
    for oid, spec in objects.items():
        label = spec.get("label", "") if isinstance(spec, dict) else ""
        for tok in re.findall(r"[a-z]+", str(label).lower()):
            head_of.setdefault(tok, oid)
    for word, oid in OBJECT_SYNONYMS.items():
        if oid in objects:
            head_of.setdefault(word, oid)
    names = {}
    for oid, spec in objects.items():
        toks = set(oid.split("_"))
        if isinstance(spec, dict):
            toks.update(re.findall(
                r"[a-z]+", str(spec.get("label", "")).lower()))
            for p in spec.get("prompts", []):
                toks.update(re.findall(r"[a-z]+", str(p).lower()))
        names[oid] = toks
    words = re.findall(r"[a-z]+", instruction.lower())
    for i, w in enumerate(words):
        if w not in head_of:
            continue
        oid = head_of[w]
        j = i - 1
        while j >= 0 and words[j] in DETERMINERS:
            j -= 1
        if j < 0 or words[j] not in ADJECTIVES:
            continue
        adj = words[j]
        if adj in names[oid]:
            continue
        acted = oid if oid in held else held[0]
        phrase = f"{adj} {w}"
        return {"rule": "instruction_unknown_object", "node": None,
                "t": 0.0,
                "detail": f"I can't see a {phrase} - "
                          f"did you mean the {acted}?",
                "_verdict": "ASK", "_hard": False, "_hint": None,
                "_fixable": False, "_origin": "seed",
                "_reason": f"instruction names {phrase!r}, which matches "
                           f"nothing in the scene; the plan acts on {acted}",
                "_predicates": {"instruction_phrase": phrase,
                                "acted_on": acted},
                "_steps": [],
                "_relations": [{"subj": acted, "rel": "GUESSED_FOR",
                                "obj": phrase}],
                "_params": {"instruction_phrase": phrase},
                "_learned_from": []}
    return None


def _typo_finding(motion, graph, instruction: str):
    """B-10: instruction names a missing object; the plan uses a match.

    Catches the planner silently "fixing" a typo'd name (appel->apple):
    ASK the owner instead of executing a guess. Not a rulebook rule
    (rules see motions, not words); plain string matching, no LLM.
    """
    import re

    held = [h for h in R.held_ids(motion) if h in graph["objects"]]
    if not held:
        return None
    known = set(graph["objects"])
    for oid in graph["objects"]:
        known.update(oid.split("_"))
    best = None
    for word in re.findall(r"[a-z]+", instruction.lower()):
        if len(word) < 4 or word in known:
            # len>=4: 3-letter verbs ("put", "cut") sit within 2 edits
            # of short names ("cup") and must never count as typos.
            continue
        for obj in held:
            dist = _edit_distance(word, obj)
            # Tolerance scales with length: a 2-edit match on a
            # 4-letter word ("just"/"jug") is coincidence, not a typo.
            limit = 1 if len(word) == 4 else 2
            if dist <= limit and (best is None or dist < best[0]):
                best = (dist, word, obj)
    if best is None:
        return None
    _, word, obj = best
    return {"rule": "instruction_typo", "node": None, "t": 0.0,
            "detail": f"did you mean {obj}?",
            "_verdict": "ASK", "_hard": False, "_hint": None,
            "_fixable": False, "_origin": "seed",
            "_reason": f"instruction names {word!r}, which is not in "
                       f"the scene; the plan acts on {obj}",
            "_predicates": {"instruction_word": word, "acted_on": obj},
            "_steps": [], "_relations": [{"subj": obj, "rel": "TYPO_OF",
                                          "obj": word}],
            "_params": {"instruction_word": word},
            "_learned_from": []}


def check(motion, graph, rules=None, instruction=None) -> dict:
    """Evaluate the rulebook over the motion; most severe verdict wins."""
    if rules is None:
        rules = load_rulebook()
    events = R.release_events(motion, graph)
    findings = []
    for rule in rules:
        scope = _rule_scope(rule)
        if scope == "live":
            continue  # loop/monitor.py evaluates these during execution
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
                             "t": when_t(item), "detail": _detail(rule, ev),
                             "_verdict": rule["verdict"],
                             "_hard": rule["hard"],
                             "_hint": rule["constraint_hint"],
                             "_fixable": rule["fixable"],
                             "_origin": _origin_of(rule),
                             "_reason": rule.get("reason", ""),
                             "_predicates": ev,
                             "_steps": _steps_of(motion, scope, item, ev),
                             "_relations": _relations_of(rule["id"], ev),
                             "_params": rule["when"],
                             "_learned_from": rule.get("learned_from",
                                                       [])})
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
    if instruction:
        typo = _typo_finding(motion, graph, instruction)
        if typo is not None:
            findings.append(typo)
        unknown = _unknown_object_finding(motion, graph, instruction)
        if unknown is not None:
            findings.append(unknown)
    kind = "ALLOW"
    for f in findings:
        if SEVERITY[f["_verdict"]] > SEVERITY[kind]:
            kind = f["_verdict"]
    ordered = sorted(findings,
                     key=lambda f: SEVERITY[f["_verdict"]], reverse=True)
    why_path = [{"rule": f["rule"], "verdict": f["_verdict"],
                 "hard": f["_hard"], "t": f["t"],
                 "origin": f["_origin"], "reason": f["_reason"],
                 "predicates": f["_predicates"], "steps": f["_steps"],
                 "relations": f["_relations"],
                 "params": f["_params"],
                 "learned_from": f["_learned_from"]} for f in ordered]
    # Feedback explains the verdict: hints from soft fixable findings AT
    # the winning severity. Any HARD finding kills all feedback (never
    # teach a jailbroken planner), even when a soft finding fired too.
    any_hard = any(f["_hard"] for f in ordered)
    hints = [f["_hint"] for f in ordered
             if f["_verdict"] == kind and not f["_hard"]
             and f["_fixable"] and f["_hint"]]
    feedback = None if any_hard else (sorted(set(hints)) or None)
    for f in findings:
        for k in ("_verdict", "_hard", "_hint", "_fixable", "_origin",
                  "_reason", "_predicates", "_steps", "_relations",
                  "_params", "_learned_from"):
            del f[k]
    print(f"Sentinel: {kind}" + (f" ({len(findings)} finding(s))"
                                       if findings else ""))
    return {"kind": kind, "findings": findings, "why_path": why_path,
            "feedback": feedback}
