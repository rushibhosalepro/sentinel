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

ALL_TYPES = (FRAME, GRAPH, PLAN, VERDICT, HALT, CLEAR, DONE)


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


def frame_event(image_b64: str, boxes: list, source: str, t: float) -> dict:
    """A video frame: JPEG base64 + 2D boxes [{id,x0,y0,x1,y1,conf}]."""
    return {"type": FRAME, "image": image_b64, "boxes": boxes,
            "source": source, "t": round(t, 2)}


def graph_event(graph: dict) -> dict:
    """A checker-graph snapshot (objects + people + safe spot)."""
    return {"type": GRAPH, "graph": to_jsonable(graph)}


def plan_event(steps: list, rounds: int) -> dict:
    """The accepted plan steps (after any replans)."""
    return {"type": PLAN, "steps": to_jsonable(steps), "rounds": rounds}


def verdict_event(round_no: int, kind: str, findings: list,
                  feedback: str | None, why_path: list[str]) -> dict:
    """One round's verdict: kind + findings + the why path (trace)."""
    return {"type": VERDICT, "round": round_no, "kind": kind,
            "findings": to_jsonable(findings), "feedback": feedback,
            "why_path": list(why_path)}


def halt_event(t: float, dist_cm: float, what: str) -> dict:
    """The HALT monitor froze the arm (person in path)."""
    return {"type": HALT, "t": round(t, 2),
            "dist_cm": round(dist_cm, 1), "what": what}


def clear_event(t: float, resumed_round: int) -> dict:
    """Path clear 1s: fresh replan, arm resumes."""
    return {"type": CLEAR, "t": round(t, 2), "resumed_round": resumed_round}


def done_event(status: str, detail: dict | None = None) -> dict:
    """Terminal run state: complete | BLOCK | ASK | error."""
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


def project_boxes(model, data, props: dict, camera: str,
                  width: int, height: int,
                  perceived: dict | None = None) -> list:
    """2D boxes for every object: [{id,x0,y0,x1,y1,conf,source}].

    Truth mode projects sim boxes; sam mode uses perceived
    pos/extent/conf (objects the frame missed are absent).
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
        boxes.append({"id": oid, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                      "conf": round(conf, 2), "source": source})
    boxes.sort(key=lambda b: b["id"])
    return boxes
