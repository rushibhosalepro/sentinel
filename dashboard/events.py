"""D-01: shared dashboard event schema (server + tests).

Event types: frame, graph, plan, verdict, halt, clear, done. Builders
return plain dicts; to_jsonable() makes numpy-laden structures
(graphs, boxes) JSON-safe (drops _-private keys like _fixable).
"""

from __future__ import annotations

import base64
import io

import numpy as np

FRAME = "frame"
GRAPH = "graph"
PLAN = "plan"
VERDICT = "verdict"
HALT = "halt"
CLEAR = "clear"
DONE = "done"
PROPOSAL = "proposal"
FEEDBACK = "feedback"
ASK = "ask"
PATH = "path"
REJECTED = "rejected"

ALL_TYPES = (FRAME, GRAPH, PLAN, VERDICT, HALT, CLEAR, DONE,
             PROPOSAL, FEEDBACK, ASK, PATH, REJECTED)


def to_jsonable(obj):
    """Recursively convert numpy scalars/arrays (and friends) to JSON."""
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()
                if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, (str, type(None))):
        return obj
    return str(obj)


def frame_event(image_b64: str, boxes: list, source: str, t: float,
                step: str | None = None) -> dict:
    """A video frame: JPEG base64 + 2D boxes [{id,x0,y0,x1,y1,conf}].

    step is the executing plan step id (handover sub-steps read
    "<hand_to id>:<phase>"); None outside execution (idle clips).
    """
    return {"type": FRAME, "image": image_b64, "boxes": boxes,
            "source": source, "t": round(t, 2), "step": step}


def graph_event(graph: dict) -> dict:
    """A checker-graph snapshot (objects + people + safe spot)."""
    return {"type": GRAPH, "graph": to_jsonable(graph)}


def plan_event(steps: list, rounds: int, rows: list | None = None) -> dict:
    """The accepted plan steps (after any replans).

    rows (D-12) are the plain-language [{id, text, note, raw, who}]
    rows; None when the caller has no describer context.
    """
    return {"type": PLAN, "steps": to_jsonable(steps), "rounds": rounds,
            "rows": to_jsonable(rows if rows is not None else [])}


def verdict_event(round_no: int, kind: str, findings: list,
                  feedback: list | None, why_path: list,
                  live_run_id: str | None = None) -> dict:
    """One round's verdict: kind + findings + structured why from check().

    why_path entries are {rule, verdict, hard, t, origin, reason,
    predicates, steps, relations, params, learned_from};
    why_path_for(trace) stays as fallback. live_run_id (R-01) joins
    the dashboard to the event log (named apart from the envelope's
    server run_id).
    """
    ev = {"type": VERDICT, "round": round_no, "kind": kind,
          "findings": to_jsonable(findings), "feedback": feedback,
          "why_path": to_jsonable(why_path)}
    if live_run_id is not None:
        ev["live_run_id"] = live_run_id
    return ev


def proposal_event(round_no: int, model: str, latency_s: float,
                   n_steps: int) -> dict:
    """What the planner proposed this round (D-04 timeline)."""
    return {"type": PROPOSAL, "round": round_no, "model": model,
            "latency_s": round(float(latency_s), 1), "n_steps": n_steps}


def feedback_event(round_no: int, note: str) -> dict:
    """Constraints (or the build-error note) sent back to the planner."""
    return {"type": FEEDBACK, "round": round_no, "note": note}


def ask_event(ask_id: str, round_no: int, question: str,
              findings: list) -> dict:
    """Final ASK awaiting the owner's approve/deny (D-05)."""
    return {"type": ASK, "ask_id": ask_id, "round": round_no,
            "question": question, "findings": to_jsonable(findings)}


def path_event(round_no: int, points: list, fires: list) -> dict:
    """Planned gripper path, top-down [[x, y]]; fires = points near a
    finding's t (drawn red)."""
    return {"type": PATH, "round": round_no,
            "points": to_jsonable(points), "fires": to_jsonable(fires)}


def rejected_event(round_no: int, kind: str, plain: str,
                   rows: list) -> dict:
    """A non-ALLOW round's plan in plain rows (D-12, collapsed in UI).

    plain is "Round N rejected: <rule in plain words>" (BLOCK/ASK) or
    "Round N failed: <short error>" (ERROR).
    """
    return {"type": REJECTED, "round": round_no, "kind": kind,
            "plain": plain, "rows": to_jsonable(rows)}


def halt_event(t: float, dist_cm: float, what: str,
               passive: bool = False) -> dict:
    """The HALT monitor froze the arm (person in path).

    passive=True (benchmark): the monitor would have fired but the
    condition kept executing.
    """
    ev = {"type": HALT, "t": round(t, 2),
          "dist_cm": round(dist_cm, 1), "what": what}
    if passive:
        ev["passive"] = True
    return ev


def clear_event(t: float, resumed_round: int) -> dict:
    """Path clear 1s: fresh replan, arm resumes."""
    return {"type": CLEAR, "t": round(t, 2), "resumed_round": resumed_round}


def done_event(status: str, detail: dict | None = None) -> dict:
    """Terminal run state: complete | BLOCK | ASK | refused | error."""
    return {"type": DONE, "status": status,
            "detail": to_jsonable(detail or {})}


def why_path_for(trace: list[str], round_no: int) -> list[str]:
    """Trace lines explaining round N: its "Round N:" block.

    Leading non-round lines (perception/quarantine context) attach to
    round 1; "Round N:" starts a block that runs to the next round
    header or a run-level line (clear/HALT).
    """
    cur, out, started = 0, [], False
    prefix = []
    for line in trace:
        if line.startswith("Round "):
            try:
                cur = int(line.split(" ", 2)[1].rstrip(":"))
            except (IndexError, ValueError):
                continue
            started = cur == round_no
            if started:
                out.append(line)
            elif cur > round_no:
                break
        elif line.startswith(("clear ", "HALT", "resumed ")):
            if started:
                break
        elif started:
            out.append(line)
        elif cur == 0:
            prefix.append(line)
    if round_no == 1:
        return prefix + out
    return out


def encode_jpeg_b64(rgb: np.ndarray, quality: int = 70) -> str:
    """Encode an RGB frame as base64 JPEG."""
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(np.asarray(rgb, dtype=np.uint8)).save(
        buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


HAZARD_TAGS = {"sharp": "SHARP", "fragile": "FRAGILE",
               "liquid": "LIQUID", "electronic": "ELECTRONIC",
               "medication": "MEDICATION"}


def hazard_tag(properties: list) -> str | None:
    """First hazard tag for a property list (None when untagged)."""
    for p in properties:
        if p in HAZARD_TAGS:
            return HAZARD_TAGS[p]
    return None


def project_boxes(model, data, props: dict, camera: str,
                  width: int, height: int,
                  perceived: dict | None = None) -> list:
    """2D boxes for every object: [{id,x0,y0,x1,y1,conf,source,tag}].

    Truth mode projects sim boxes; sam mode uses perceived
    pos/extent/conf (objects the frame missed are absent). tag is the
    hazard tag (SHARP/...) or None; properties always come from
    props.yaml (matched ids keep them in sam mode too).
    """
    from perception.lift3d import camera_params, project
    from sim.geometry import body_aabb

    cam = camera_params(model, data, camera, width, height)
    boxes = []
    for oid in props["objects"]:
        if perceived is not None:
            if oid not in perceived:
                continue
            p = perceived[oid]
            pos = np.asarray(p["pos"], dtype=float)
            ext = np.asarray(p["extent"], dtype=float)
            conf, source = float(p["conf"]), "sam"
        else:
            bid = model.body(oid).id
            pos = np.asarray(data.xpos[bid], dtype=float)
            try:
                lo, hi = body_aabb(model, data, bid)
                ext = (np.asarray(hi) - np.asarray(lo)) / 2.0
            except Exception:  # noqa: BLE001 - unbounded -> point
                ext = np.zeros(3)
            conf, source = 1.0, "truth"
        corners = np.array([[pos[0] + dx, pos[1] + dy, pos[2] + dz]
                            for dx in (-ext[0], ext[0])
                            for dy in (-ext[1], ext[1])
                            for dz in (-ext[2], ext[2])])
        u, v, d = project(corners, cam)
        if (d <= 0).any():
            continue
        x0, y0 = max(0, int(u.min())), max(0, int(v.min()))
        x1, y1 = min(width, int(u.max()) + 1), min(height, int(v.max()) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        tag = hazard_tag(
            props["objects"][oid].get("properties", []))
        boxes.append({"id": oid, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                      "conf": round(conf, 2), "source": source,
                      "tag": tag})
    boxes.sort(key=lambda b: b["id"])
    return boxes
