"""D-12: plain-language step rows, live status, plain rules, shadow notes.

describe_plan turns planner primitives into judge-readable rows
(no coordinates; the raw step rides along for tooltips). Statuses
are order-based over the plan ids with the frame's current step id.
plain_rule/finding_plain translate rule ids to short sentences for
rejected rounds, shadow notes, and the one-sentence lane footers.
shadow_notes runs the real check() over lane A's motion without
touching its execution.
"""

from __future__ import annotations

STAGING = (0.25, 0.05, 0.45)
NEAR_XY = 0.10
ABOVE_DZ = 0.12
PERSON_SIDE_X = 0.45


def _short(label: str) -> str:
    return label.split()[-1]


def _label(props: dict, oid: str) -> str:
    return props["objects"].get(oid, {}).get("label", oid)


def _near_oid(x: float, y: float, z: float,
              positions: dict) -> str | None:
    """Closest object below the pose (highest top wins ties)."""
    best = None
    for oid, (ox, oy, top) in positions.items():
        if abs(x - ox) > NEAR_XY or abs(y - oy) > NEAR_XY:
            continue
        if top > z + 0.02:
            continue
        if best is None or top > positions[best][2]:
            best = oid
    return best


def _near_staging(x: float, y: float, z: float) -> bool:
    sx, sy, sz = STAGING
    return abs(x - sx) <= 0.06 and abs(y - sy) <= 0.06 \
        and abs(z - sz) <= 0.06


def describe_plan(steps: list, props: dict, positions: dict,
                  people_xy: dict | None = None,
                  turned: set | frozenset = frozenset(),
                  rejected: list | None = None,
                  sentinel_notes: bool = True) -> list:
    """Planner steps -> [{id, text, note, raw, who}]. Skips stop.

    Green notes need sentinel_notes (lane B final plans only:
    rejected and lane-A plans never carry them).
    """
    people_xy = people_xy or {}
    suffix = ""
    if rejected:
        n, kind = rejected[-1]
        suffix = f" after round {n} {kind}"
    rows = []
    held = None
    mentioned: set[str] = set()
    last_z: float | None = None
    grasp_xy: tuple | None = None
    prev_grasp = False
    first_move = True
    moves = [s for s in steps if s["primitive"] == "move_to"]
    for k, s in enumerate(steps):
        prim = s["primitive"]
        args = s.get("args", {})
        if prim == "stop":
            continue
        note, who, text = None, None, ""
        if prim == "move_to":
            x, y, z = (float(v) for v in args["pose"][:3])
            oid = _near_oid(x, y, z, positions)
            if oid == held:
                oid = None
            if first_move:
                text = "Move to the start pose"
            elif prev_grasp and last_z is not None and grasp_xy is not None \
                    and z - last_z > 0.05 \
                    and abs(x - grasp_xy[0]) <= 0.06 \
                    and abs(y - grasp_xy[1]) <= 0.06:
                text = "Lift it to carry height"
            elif held is None and oid is not None:
                label = _label(props, oid)
                word = label if oid not in mentioned \
                    else f"the {_short(label)}"
                if oid not in mentioned:
                    word = f"the {label}"
                top = positions[oid][2]
                text = (f"Reach above {word}" if z >= top + ABOVE_DZ
                        else f"Lower to {word}")
                mentioned.add(oid)
            elif held is not None and oid is not None:
                label = _label(props, oid)
                word = label if oid not in mentioned \
                    else f"the {_short(label)}"
                if oid not in mentioned:
                    word = f"the {label}"
                text = f"Carry it over {word}"
                mentioned.add(oid)
            elif held is not None and x >= PERSON_SIDE_X \
                    and people_xy:
                name = min(people_xy,
                           key=lambda p: abs(people_xy[p][0] - x)
                           + abs(people_xy[p][1] - y))
                text = f"Carry it toward the {name}"
            elif _near_staging(x, y, z):
                last = s is moves[-1]
                if held is not None:
                    text = "Carry it back to the start pose" if last \
                        else "Carry it via the start pose"
                else:
                    text = "Move back to the start pose" if last \
                        else "Move via the start pose"
            else:
                text = "Move the arm"
            if prim == "move_to":
                first_move = False
            last_z = z
            prev_grasp = False
        elif prim == "grasp":
            oid = args["object_id"]
            label = _label(props, oid)
            sharp = "sharp" in props["objects"].get(
                oid, {}).get("properties", [])
            text = f"Grasp the {_short(label)}"
            if sharp:
                text += " (by the handle)"
            held = oid
            mentioned.add(oid)
            prev_grasp = True
            grasp_xy = None
            if oid in positions:
                grasp_xy = (positions[oid][0], positions[oid][1])
        elif prim == "release":
            if held is not None and held in mentioned:
                text = "Let go of it"
            elif held is not None:
                text = f"Let go of the {_short(_label(props, held))}"
            else:
                text = "Let go"
            held = None
            prev_grasp = False
        elif prim == "tilt":
            deg = args.get("deg", 0)
            if held is not None:
                what = f"the {_short(_label(props, held))} "
            else:
                what = ""
            text = f"Tilt {what}to pour" if deg else \
                f"Level {what}again".replace("  ", " ")
            prev_grasp = False
        elif prim == "set_speed":
            nxt = next((t for t in steps[k + 1:]
                        if t["primitive"] != "stop"), None)
            if args.get("speed") == "slow" and nxt is not None \
                    and nxt["primitive"] == "hand_to":
                text = "Slow down for the hand-over"
                who = nxt["args"]["person"]
                if sentinel_notes:
                    note = ("Sentinel: slowed within 30 cm of the "
                            "person" + suffix)
            elif args.get("speed") == "slow":
                text = "Slow down"
            else:
                text = "Resume normal speed"
            prev_grasp = False
        elif prim == "hand_to":
            person = args["person"]
            who = person
            text = f"Hand it to the {person}"
            if s["id"] in turned:
                text += " \u2014 handle first"
                if sentinel_notes:
                    note = "Sentinel: turned handle-first" + suffix
            held = None
            prev_grasp = False
        else:
            text = "Continue the plan"
            prev_grasp = False
        rows.append({"id": s["id"], "text": text, "note": note,
                     "raw": s, "who": who})
    return rows


def parent_step_id(step_id: str) -> str:
    """handover sub-step -> its top-level hand_to id."""
    return step_id.split(":")[0]


def step_statuses(ids: list, current: str | None) -> dict:
    """Order-based statuses: done < running current < pending.

    Unknown current ids stay pending (never claim done unheard).
    """
    if current is None:
        return {i: "pending" for i in ids}
    cur = parent_step_id(current)
    if cur not in ids:
        return {i: "pending" for i in ids}
    k = ids.index(cur)
    return {i: ("done" if j < k else "running" if j == k
                else "pending")
            for j, i in enumerate(ids)}


def handover_step_id(hid: str, phase: str, last_id: str) -> str:
    """Current sub-step id for a live hand-over phase."""
    if phase == "offer":
        return f"{hid}:offer"
    if phase in ("wait", "holding"):
        return f"{hid}:release"
    return last_id


def plain_rule(rule_id: str, ev: dict | None = None,
               props: dict | None = None) -> str:
    """Rule id -> short judge-readable sentence (no verdict words)."""
    ev = ev or {}
    person = ev.get("person")
    who = f"the {person}" if person else "a person"
    if rule_id == "sharp_toward_person":
        return f"blade pointed at {who}"
    if rule_id == "hazard_fast_near_person":
        return f"moving fast near {who}"
    if rule_id == "liquid_above_electronic":
        eid = ev.get("electronic")
        if eid is None:
            return "liquid near electronics"
        label = _label(props or {}, eid)
        return f"liquid above the {label}"
    if rule_id == "restricted_item":
        return f"restricted item for {who}"
    if rule_id == "release_near_person_in_air":
        oid = ev.get("obj")
        if oid is None:
            return f"object released mid-air near {who}"
        return (f"{_short(_label(props or {}, oid))} released "
                f"mid-air near {who}")
    if rule_id == "scene_text_provenance":
        return "plan followed the sticky note, not the instruction"
    if rule_id == "unknown_object":
        return "target not in the scene"
    if rule_id.startswith("release_near_counter_edge"):
        return "released near the counter edge"
    return rule_id.replace("_", " ")


def finding_plain(finding: dict, props: dict | None) -> str:
    """Plain words for one finding (word-rules keep their detail)."""
    rule = finding.get("rule", "")
    if rule.startswith("instruction_") and finding.get("detail"):
        return finding["detail"]
    ev = finding.get("_predicates") or finding.get("predicates")
    return plain_rule(rule, ev, props)


def lane_b_footer(kind: str, rows: list, findings: list,
                  props: dict | None) -> str:
    """One plain sentence for lane B's done state."""
    if kind == "BLOCK":
        what = finding_plain(findings[0], props) if findings \
            else "blocked"
        return f"Blocked: {what}"
    if kind == "ASK":
        what = finding_plain(findings[0], props) if findings \
            else "the owner"
        return f"Asked the owner: {what}"
    if kind == "ALLOW":
        blades, slows = [], []
        for r in (rows or []):
            note = r.get("note") or ""
            who = r.get("who") or "the person"
            who = who if who.startswith("the ") else f"the {who}"
            if "turned handle-first" in note:
                blades.append(f"blade away from {who}")
            elif "slowed within 30 cm" in note:
                slows.append("slow near the person")
        facts = sorted(set(blades)) + sorted(set(slows))
        if facts:
            return "Allowed after checking: " + ", ".join(facts)
        return "Allowed after checking"
    return kind


def join_details(findings: list, why_path: list) -> list:
    """Why entries + their finding detail (check strips _-keys)."""
    details = {f.get("rule"): f.get("detail")
               for f in findings or []}
    return [{**w, "detail": details.get(w.get("rule"))}
            for w in why_path or []]


def rejected_line(entry: dict, props: dict | None) -> str:
    """'Round N rejected: <rule in plain words>' for a rounds_log entry."""
    n, kind = entry.get("round"), entry.get("kind")
    if kind == "ERROR":
        err = (entry.get("error") or "error")[:80]
        return f"Round {n} failed: {err}"
    joined = join_details(entry.get("findings"), entry.get("why"))
    if not joined:
        return f"Round {n} rejected: {str(kind).lower()}"
    return f"Round {n} rejected: {finding_plain(joined[0], props)}"


def script_turned_hids(script: dict) -> set:
    """hand_to ids whose expansion turned the blade away (":turn")."""
    out = set()
    for kind, payload in (script or {}).get("segments", []):
        if kind != "handover":
            continue
        motion = payload.get("lh").motion
        if any(str(s).endswith(":turn")
               for s in motion.get("sample_steps", [])):
            out.add(payload.get("hid"))
    return out


def shadow_notes(motion: dict, graph: dict, props: dict,
                 instruction: str, end: dict | None = None,
                 steps: list | None = None) -> dict:
    """check() over lane A's motion -> {top-level step id: red note}.

    Read-only: findings never touch lane A's execution. When end +
    steps are given, notes match what happened: if the owner was
    never involved (no take, no hand_to to the owner),
    person-directed findings are clearance artifacts and are
    dropped, except a mid-air release, kept without the person
    claim.
    """
    from sentinel.check import check, load_rulebook

    verdict = check(motion, graph, load_rulebook(),
                    instruction=instruction)
    involved = end is None or bool(end.get("takes")) or any(
        s.get("primitive") == "hand_to"
        and (s.get("args") or {}).get("person") == "owner"
        for s in steps or [])
    first = (motion.get("step_ids") or [None])[0]
    joined = join_details(verdict.get("findings"),
                          verdict.get("why_path"))
    notes = {}
    for f in joined:
        rule = f.get("rule", "")
        if not involved and rule in ("sharp_toward_person",
                                     "hazard_fast_near_person"):
            continue
        if not involved and rule == "release_near_person_in_air":
            ev = f.get("_predicates") or f.get("predicates") or {}
            oid = ev.get("obj")
            if oid is None:
                text = "\u26a0 object released in mid-air"
            else:
                text = (f"\u26a0 {_short(_label(props or {}, oid))} "
                        "released in mid-air")
        else:
            text = f"\u26a0 {finding_plain(f, props)}"
        sids = f.get("steps") or ([first] if first else [])
        for sid in sids:
            notes.setdefault(parent_step_id(sid), text)
    return notes


def object_tops(model, data, props: dict) -> dict:
    """{object id: (x, y, top z)} for the step describer."""
    from sim.geometry import body_aabb

    out = {}
    for oid in props["objects"]:
        bid = model.body(oid).id
        try:
            _, hi = body_aabb(model, data, bid)
            top = float(hi[2])
        except Exception:  # noqa: BLE001 - unbounded -> body height
            top = float(data.xpos[bid][2])
        out[oid] = (float(data.xpos[bid][0]),
                    float(data.xpos[bid][1]), top)
    return out


def people_xy(model, data) -> dict:
    """{person: (x, y)} for carry-toward lines (owner has the body)."""
    return {"owner": (float(data.xpos[model.body("human_torso").id][0]),
                     float(data.xpos[model.body("human_torso").id][1]))}
