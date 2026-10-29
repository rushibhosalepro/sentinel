"""R-02: Muse Wonder proposes ONE candidate rule from an incident.

Reads the incident + its run context + the current rulebook + the
predicate VOCABULARY and returns the parsed candidate (or a no_rule
refusal). Vocabulary-only: anything outside check.py's predicates is
a refusal, never a guess. Activation is always soft AND unfixable
(verdict ASK, hard false, fixable false): a learned rule asks the
owner until a human promotes it. Cost-logged via model_client.
"""

from __future__ import annotations

import json
from pathlib import Path

WONDER_MODEL = "muse-wonder-1.0"

SYSTEM = """You write ONE safety rule for a kitchen robot's checker.
Input: an owner incident ("that was unsafe"), the run's verdicts, the
current rulebook, and the predicate vocabulary.
Output: exactly one JSON object, no prose. Either the rule:
{"id": "snake_case", "when": {pred: params, ...}, "unless": {},
 "verdict": "ASK", "hard": false, "fixable": false,
 "constraint_hint": "short advice", "reason": "one plain sentence"}
or a refusal: {"no_rule": "why no vocabulary predicate fits"}.
Rules: use ONLY vocabulary predicates with their documented params;
every predicate in when/unless must share ONE scope (sample, event,
or motion); the "any" key holds a list of same-scope alternatives.
Property names are lowercase props.yaml values (see PROPERTIES).
New predicates are out of scope: refuse instead of inventing one.
Pick thresholds with margin: the gate replays the incident with the
object shifted +/-5 cm and the person +/-10 cm, and the rule must
still catch every variant. The checker activates your rule as a
soft ASK to the owner."""


def properties_text() -> str:
    """Sorted unique object properties from props.yaml."""
    from graph.scene_graph import load_props

    props = set()
    for node in load_props()["objects"].values():
        props.update(node.get("properties", []))
    return ", ".join(sorted(props))


def vocabulary_text() -> str:
    """Render check.py's VOCABULARY for the prompt (no live-only)."""
    from sentinel.check import VOCABULARY

    lines = []
    for name, spec in VOCABULARY.items():
        if spec["scope"] == "live":
            continue
        lines.append(f"- {name}({json.dumps(spec['params'])}) "
                     f"[{spec['scope']}]: {spec['desc']}")
    return "\n".join(lines)


def rulebook_text(rules: list[dict]) -> str:
    """One line per rule: id, predicates, verdict."""
    lines = []
    for r in rules:
        preds = sorted(set(r.get("when", {}))
                       | set(r.get("unless", {})))
        lines.append(f"- {r['id']}: when {preds} -> {r['verdict']}"
                     f"{' HARD' if r.get('hard') else ''}")
    return "\n".join(lines) or "(empty rulebook)"


def incident_context(incident: dict, run_verdicts: list[dict]) -> str:
    """Incident text + its run's verdict rounds, compact."""
    lines = [f"incident {incident['id']}: {incident.get('text', '')}",
             f"instruction: {incident.get('instruction', '')}"]
    for v in run_verdicts:
        rules = ",".join(f["rule"] for f in v.get("findings", []))
        lines.append(f"round {v.get('round')}: {v.get('outcome')}"
                     + (f" {rules}" if rules else ""))
        for f in v.get("findings", []):
            lines.append(f"  - {f['rule']}: {f.get('detail', '')}")
        if v.get("motion"):
            lines.append(f"  motion: {v['motion']}")
        c = v.get("closest") or {}
        if c.get("fragile_cm") is not None:
            lines.append(f"  closest: held object {c['fragile_cm']} cm "
                         f"from {c['fragile_obj']} (fragile)")
        if c.get("electronic_cm") is not None:
            lines.append(f"  closest: held object {c['electronic_cm']} cm "
                         f"from {c['electronic_obj']} (electronic)")
        if c.get("person_cm") is not None:
            lines.append(f"  closest: held object {c['person_cm']} cm "
                         f"from {c['person']} (person)")
    objs = (incident.get("graph") or {}).get("objects", {})
    if objs:
        lines.append("objects: " + ", ".join(
            f"{oid} [{','.join(n.get('properties', []))}]"
            for oid, n in sorted(objs.items())))
    return "\n".join(lines)


def propose_from_content(content: str, learned_from: list[str]) -> dict:
    """Parse Wonder's response; coerce to soft+unfixable. Raises ValueError."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Wonder response is not JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("Wonder response must be one JSON object")
    if "no_rule" in obj:
        return {"rule": None, "no_rule": str(obj["no_rule"])}
    if not isinstance(obj.get("when"), dict) or not obj["when"]:
        raise ValueError("candidate rule needs a non-empty 'when' object")
    if not isinstance(obj.get("id"), str) or not obj["id"]:
        raise ValueError("candidate rule needs a string 'id'")
    rule = {"id": obj["id"], "when": obj["when"],
            "unless": obj.get("unless", {}),
            "verdict": "ASK", "hard": False, "fixable": False,
            "constraint_hint": str(obj.get("constraint_hint", "")),
            "reason": str(obj.get("reason", "")),
            "origin": "learned", "version": 1,
            "learned_from": list(learned_from)}
    return {"rule": rule, "no_rule": None}


def propose(incident_id: str, *, events_path=None,
            model: str = WONDER_MODEL, log_path: Path | None = None,
            ) -> dict:
    """Ask Wonder for a rule; returns rule/no_rule + usage + raw."""
    from learner.events import read_events
    from planner.model_client import chat, get_client
    from sentinel.check import load_rulebook

    log = read_events(events_path)
    inc = next((e for e in log if e.get("id") == incident_id
                and e.get("kind") == "incident"), None)
    if inc is None:
        raise ValueError(f"no incident {incident_id} in the event log")
    run = [e for e in log if inc.get("run_id") is not None
           and e.get("run_id") == inc.get("run_id")
           and e.get("kind") == "verdict"]
    user = (incident_context(inc, run) + "\n\nCURRENT RULEBOOK:\n"
            + rulebook_text(load_rulebook()) + "\n\nVOCABULARY:\n"
            + vocabulary_text() + "\n\nPROPERTIES:\n"
            + properties_text())
    client, mid, spec, alias = get_client(model)
    content, usage, latency = chat(
        client, model=mid, spec=spec, alias=alias,
        purpose="propose_rule", log_path=log_path,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"})
    out = propose_from_content(
        content, [inc["id"]] + [e["id"] for e in run])
    out.update({"usage": usage, "latency_s": round(latency, 2),
                "model": mid, "raw": content})
    return out
