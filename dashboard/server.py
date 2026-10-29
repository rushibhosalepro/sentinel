"""D-01: dashboard server: POST /instruction + /ws event stream.

POST /instruction runs the loop.live orchestrator (_run_headless) in
a worker thread; the run streams frame (JPEG ~10fps) + graph + plan +
round verdicts (with why_path) + HALT/clear + done over /ws as JSON.
One run at a time (409 while busy). Pass runner=... to create_app to
inject a fake orchestrator (tests).

D-05: a final soft ASK waits for the owner: POST /ask/{ask_id}
{decision, token} with token = OWNER_TOKEN from .env.local.

Start: uv run uvicorn dashboard.server:app --port 8000
"""

from __future__ import annotations

import asyncio
import csv
import datetime
import hmac
import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.events import done_event
from learner import events as learner_events
from learner import versions as rule_versions_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


class Instruction(BaseModel):
    instruction: str
    perception: str = "truth"
    model: str = "spark"
    preset: str | None = None
    token: str | None = None  # public_mode /debug posting (?owner=)


class SplitRequest(BaseModel):
    preset: str | None = None  # knife | water | sticky (open to all)
    instruction: str | None = None  # free text (open to all, <=200 ch)
    model: str = "spark"
    token: str | None = None  # legacy: /split no longer needs it


FREE_TEXT_MAX_CHARS = 200


class AskDecision(BaseModel):
    decision: Literal["approve", "deny"]
    token: str


class Incident(BaseModel):
    text: str


class Rollback(BaseModel):
    version: str
    token: str


class AskRegistry:
    """Pending owner approvals: live.py pre-registers + waits, POST decides."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict = {}

    def pre_register(self, ask_id: str) -> None:
        with self._lock:
            self._pending[ask_id] = {"event": threading.Event(),
                                     "decision": None}

    def decide(self, ask_id: str, decision: str) -> bool:
        """Record the owner's decision; False when unknown/already decided."""
        with self._lock:
            slot = self._pending.get(ask_id)
            if slot is None or slot["decision"] is not None:
                return False
            slot["decision"] = decision
            slot["event"].set()
            return True

    def wait(self, ask_id: str, timeout: float) -> str | None:
        """Block for the decision; None on timeout or unknown id (deny)."""
        with self._lock:
            slot = self._pending.get(ask_id)
        if slot is None:
            return None
        ok = slot["event"].wait(timeout)
        with self._lock:
            self._pending.pop(ask_id, None)
        return slot["decision"] if ok else None


def _owner_token() -> str | None:
    load_dotenv(REPO_ROOT / ".env.local")
    return os.environ.get("OWNER_TOKEN") or None


_warned_no_token = False


def run_loop_live(instruction: str, sink, *, perception: str = "truth",
                  model: str = "spark", preset: str | None = None,
                  ask_handler=None,
                  out_path: str = "out/dashboard_run.mp4") -> None:
    """Real runner: the loop.live orchestrator with an event sink."""
    from loop.live import _run_headless

    _run_headless(instruction, out_path, preset=preset,
                  perception=perception, planner_model=model, sink=sink,
                  ask_handler=ask_handler)


def _envelope(run_id: int, event: dict) -> dict:
    return {"run_id": run_id,
            "ts": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
            **event}


def _render_demo_rgb(preset: str, idle: dict):
    """Demo-camera RGB for a preset; lazy-loads the shared idle sim."""
    import mujoco

    import loop.live as live
    from graph.scene_graph import load_props
    from sim.world import HEIGHT, WIDTH, load_scene

    if idle.get("model") is None:
        model, data = load_scene("kitchen")
        idle.update(model=model, data=data, props=load_props(),
                    home={"qpos": data.qpos.copy()})
    live._apply_preset(idle["model"], idle["data"], idle["home"], preset)
    from sim.world import RENDER_LOCK

    # Fresh context per render, same thread throughout: GLFW contexts are
    # thread-affine (cross-thread use is a C-level fatal), and concurrent
    # creation races, so create+close stay under RENDER_LOCK.
    with RENDER_LOCK:
        renderer = mujoco.Renderer(idle["model"], height=HEIGHT,
                                   width=WIDTH)
    try:
        renderer.update_scene(idle["data"], camera="demo")
        return renderer.render()
    finally:
        with RENDER_LOCK:
            renderer.close()


def _render_idle_frame(preset: str, idle: dict) -> tuple[dict, dict]:
    """Render one demo-camera frame + graph for a preset (lazy imports)."""
    from dashboard.events import (encode_jpeg_b64, frame_event, graph_event,
                                  project_boxes)
    from graph.scene_graph import attach_dashboard_edges
    from sentinel.graph_view import graph_snapshot
    from sim.world import HEIGHT, WIDTH

    frame = _render_demo_rgb(preset, idle)
    graph = graph_snapshot(idle["model"], idle["data"], idle["props"])
    attach_dashboard_edges(graph, idle["model"], idle["data"],
                           idle["props"])
    boxes = project_boxes(idle["model"], idle["data"], idle["props"],
                          "demo", WIDTH, HEIGHT)
    return (frame_event(encode_jpeg_b64(frame), boxes, "truth", 0.0),
            graph_event(graph))


SPLIT_PRESETS = {"knife": "default", "water": "cup_next_to_laptop",
                 "sticky": "default"}


def render_split_idle(preset: str, idle: dict) -> dict:
    """Clean demo-camera frame event for a split preset (D-08).

    No boxes. Sticky draws the attack note text on the frame (same
    staging as the demo). Raises ValueError on unknown presets.
    """
    import numpy as np

    from dashboard.events import encode_jpeg_b64, frame_event

    if preset not in SPLIT_PRESETS:
        raise ValueError(f"unknown preset {preset!r}")
    rgb = np.asarray(_render_demo_rgb(SPLIT_PRESETS[preset], idle))
    if preset == "sticky":
        from perception.lift3d import camera_params, project
        from perception.reader import ATTACK_LINES, stage_note_text
        from sim.world import HEIGHT, WIDTH

        cam = camera_params(idle["model"], idle["data"], "demo",
                            WIDTH, HEIGHT)
        pos = np.asarray(idle["data"].xpos[
            idle["model"].body("sticky_note").id], dtype=float)
        u, v, _ = project(pos + np.array([0.0, 0.0, 0.01]), cam)
        corners = pos + np.array([[dx, dy, 0.0]
                                  for dx in (-0.025, 0.025)
                                  for dy in (-0.025, 0.025)])
        cu, _, _ = project(corners, cam)
        width_px = max(12, int(np.ptp(np.asarray(cu, dtype=float))))
        rgb = np.asarray(stage_note_text(rgb, (int(u), int(v)),
                                         ATTACK_LINES,
                                         max_width_px=width_px))
    return frame_event(encode_jpeg_b64(rgb), [], "truth", 0.0)


def create_app(runner=run_loop_live, owner_token: str | None = None,
               idle_render: bool = False, split_naive=None,
               split_live=None, rate_limit_per_hour: int | None = 10,
               daily_budget_usd: float | None = None, costs_path=None,
               public_mode: bool = False, web_dir=None,
               bench_csv=None) -> FastAPI:
    global _warned_no_token
    app = FastAPI(title="Sentinel dashboard")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    token = _owner_token() if owner_token is None else (owner_token or None)
    if token is None and not _warned_no_token:
        _warned_no_token = True
        print("OWNER_TOKEN not set in .env.local: ASK approvals disabled "
              "(all /ask -> 403)")
    if split_naive is None:
        from dashboard.split import run_naive_lane as split_naive
    if split_live is None:
        from loop.live import _run_headless as split_live
    registry = AskRegistry()
    state = {"busy": False, "run_id": 0, "lock": threading.Lock(),
             "subs": set(), "latest": {}, "history": [], "idle": {},
             "render_lock": threading.Lock(), "instruction": None,
             "live_run_id": None, "incident_idx": None,
             "pending": deque(), "hits": deque(),
             "split_subs": set(), "split_latest": {},
             "split_history": [], "split_run_id": 0,
             "split_preset": "knife", "split_idle_frames": {}}

    def _incident_index():
        """{event id: (incident_n, ts)} from the event log (cached)."""
        if state["incident_idx"] is None:
            state["incident_idx"] = {
                e["id"]: (e["incident_n"], e["ts"])
                for e in learner_events.read_events()
                if e.get("kind") == "incident"}
        return state["incident_idx"]

    def _enrich(event: dict):
        """Attach learned-rule incident refs to a verdict (both lanes)."""
        for w in event.get("why_path") or []:
            if not isinstance(w, dict):
                continue
            if w.get("origin") != "learned":
                continue
            for lid in w.get("learned_from") or []:
                hit = _incident_index().get(lid)
                if hit is not None:
                    w["incident_ref"] = {"n": hit[0], "ts": hit[1]}
                    break

    def _publish(event: dict):
        with state["lock"]:
            if event["type"] in ("frame", "graph", "plan"):
                state["latest"][event["type"]] = (state["run_id"], event)
            if event["type"] in ("proposal", "verdict", "feedback", "ask",
                                 "halt", "clear", "done"):
                state["history"].append((state["run_id"], event))
            if event["type"] == "verdict":
                if event.get("live_run_id"):
                    state["live_run_id"] = event["live_run_id"]
                _enrich(event)
            subs = list(state["subs"])
        for q in subs:
            q.put(event)

    def _publish_split(lane: str, run_id: int, event: dict):
        """Lane-tagged split event -> split catchup + /ws-split sockets."""
        if event["type"] == "verdict":
            with state["lock"]:
                _enrich(event)
        with state["lock"]:
            if event["type"] in ("frame", "graph", "plan"):
                state["split_latest"][(event["type"], lane)] = (
                    run_id, event)
            if event["type"] in ("proposal", "verdict", "feedback", "ask",
                                 "halt", "clear", "done"):
                state["split_history"].append((run_id, lane, event))
            subs = list(state["split_subs"])
        for q in subs:
            q.put((run_id, lane, event))

    def _serve(job):
        try:
            job()
        finally:
            with state["lock"]:
                if state["pending"]:
                    nxt = state["pending"].popleft()
                    threading.Thread(target=_serve, args=(nxt,),
                                     daemon=True).start()
                else:
                    state["busy"] = False

    def _submit(job) -> tuple[bool, int | None]:
        """Run now or enqueue on the single slot; (started, position)."""
        with state["lock"]:
            if not state["busy"]:
                state["busy"] = True
                threading.Thread(target=_serve, args=(job,),
                                 daemon=True).start()
                return True, None
            state["pending"].append(job)
            return False, len(state["pending"])

    def _rate_ok(ip: str) -> bool:
        """At most rate_limit_per_hour run-posts per IP (None disables)."""
        if rate_limit_per_hour is None:
            return True
        now = time.time()
        with state["lock"]:
            while state["hits"] and \
                    state["hits"][0][1] < now - 3600.0:
                state["hits"].popleft()
            if sum(1 for h in state["hits"] if h[0] == ip) >= \
                    rate_limit_per_hour:
                return False
            state["hits"].append((ip, now))
            return True

    def _budget_left():
        """Daily $ left from costs.jsonl (None when unbudgeted)."""
        if daily_budget_usd is None:
            return None
        try:
            lines = Path(costs_path
                         if costs_path is not None
                         else REPO_ROOT / "out" / "costs.jsonl"
                         ).read_text().splitlines()
        except OSError:
            return round(daily_budget_usd, 4)
        today = datetime.datetime.now(datetime.timezone.utc).date()
        spent = 0.0
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            ts = entry.get("ts", "")
            if ts[:10] == today.isoformat():
                spent += entry.get("cost_usd") or 0.0
        return round(daily_budget_usd - spent, 4)

    def _token_ok(given: str | None) -> bool:
        return token is not None and bool(given) and \
            hmac.compare_digest(given, token)

    def _publish_idle(preset: str):
        with state["render_lock"]:
            frame, graph = _render_idle_frame(preset, state["idle"])
        _publish(frame)
        _publish(graph)

    def _publish_split_idle(preset: str, clear: bool = True):
        """Render once (cached per preset), send to both lanes (D-08).

        Idle always carries run 0: it belongs to no run. clear=True
        (explicit /split-scene) replaces old run frames/history with
        the fresh setup; clear=False (connect-time seeding) only
        fills lanes that have no frame yet, so a run that published
        while the render was in flight is never clobbered.
        """
        with state["render_lock"]:
            if preset not in state["split_idle_frames"]:
                state["split_idle_frames"][preset] = render_split_idle(
                    preset, state["idle"])
            frame = state["split_idle_frames"][preset]
        with state["lock"]:
            state["split_preset"] = preset
            if clear:
                state["split_latest"] = {}
                state["split_history"] = []
            lanes = [lane for lane in ("A", "B")
                     if clear or ("frame", lane)
                     not in state["split_latest"]]
        for lane in lanes:
            _publish_split(lane, 0, frame)

    if idle_render:
        def _startup_render():
            try:
                _publish_idle("default")
                _publish_split_idle("knife")
            except Exception as e:  # noqa: BLE001 - page stays in loading
                print(f"idle scene render failed: {e}")

        threading.Thread(target=_startup_render, daemon=True).start()

    @app.get("/health")
    def health():
        with state["lock"]:
            queued = len(state["pending"])
        return {"status": "ok", "queued": queued,
                "budget_left": _budget_left()}

    @app.get("/scene")
    def scene(preset: str = "default"):
        try:
            _publish_idle(preset)
        except ValueError:
            return JSONResponse({"error": f"unknown preset {preset!r}"},
                                status_code=404)
        except Exception as e:  # noqa: BLE001 - render failed, stay loading
            print(f"idle scene render failed: {e}")
            return JSONResponse({"error": "scene render failed"},
                                status_code=500)
        return {"preset": preset}

    @app.get("/split-scene")
    def split_scene(preset: str = "knife"):
        try:
            _publish_split_idle(preset)
        except ValueError:
            return JSONResponse({"error": f"unknown preset {preset!r}"},
                                status_code=404)
        except Exception as e:  # noqa: BLE001 - render failed, stay loading
            print(f"split idle render failed: {e}")
            return JSONResponse({"error": "scene render failed"},
                                status_code=500)
        return {"preset": preset}

    def _client_ip(request: Request) -> str:
        return request.client.host if request.client is not None \
            else "unknown"

    def _guarded(request: Request):
        """429/503 guardrail responses, or None when the post may proceed."""
        if not _rate_ok(_client_ip(request)):
            return JSONResponse(
                {"error": "too many runs: at most "
                 f"{rate_limit_per_hour} per hour per IP"},
                status_code=429)
        left = _budget_left()
        if left is not None and left <= 0:
            return JSONResponse(
                {"error": "the demo's daily budget is spent: "
                 "please try again tomorrow"},
                status_code=503)
        return None

    @app.post("/instruction", status_code=202)
    def instruct(body: Instruction, request: Request):
        if public_mode and not _token_ok(body.token):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        denied = _guarded(request)
        if denied is not None:
            return denied
        with state["lock"]:
            state["run_id"] += 1
            run_id = state["run_id"]
        kwargs = {"perception": body.perception, "model": body.model,
                  "preset": body.preset}

        def _run():
            with state["lock"]:
                state["history"] = []
                state["instruction"] = body.instruction
                state["live_run_id"] = None
            try:
                runner(body.instruction, _publish, ask_handler=registry,
                       **kwargs)
            except SystemExit:
                pass  # _run_headless emits done before raising
            except Exception as e:  # noqa: BLE001 - never kill the server
                _publish(done_event("error", {"error": str(e)}))

        started, position = _submit(_run)
        out = {"run_id": run_id,
               "status": "started" if started else "queued"}
        if position is not None:
            out["position"] = position
        return out

    @app.post("/split", status_code=202)
    def split(body: SplitRequest, request: Request):
        from dashboard.split import resolve_split

        try:
            spec = resolve_split(preset=body.preset,
                                 instruction=body.instruction)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if body.instruction is not None:
            # D-09: free text for everyone. Guardrails are the 200-char
            # cap plus the shared rate limit, budget, and queue below.
            # The text travels only as the owner's instruction (user
            # role) in both lanes, never as system text.
            if len(body.instruction) > FREE_TEXT_MAX_CHARS:
                return JSONResponse(
                    {"error": f"instruction too long: at most "
                              f"{FREE_TEXT_MAX_CHARS} characters"},
                    status_code=400)
            if not body.instruction.strip():
                return JSONResponse({"error": "instruction is empty"},
                                    status_code=400)
        denied = _guarded(request)
        if denied is not None:
            return denied
        with state["lock"]:
            state["split_run_id"] += 1
            run_id = state["split_run_id"]

        def _run():
            with state["lock"]:
                state["split_history"] = []
            _run_split_lanes(spec, run_id, body.model)

        started, position = _submit(_run)
        out = {"run_id": run_id, "preset": spec["name"],
               "status": "started" if started else "queued"}
        if position is not None:
            out["position"] = position
        return out

    def _run_split_lanes(spec: dict, run_id: int, model: str):
        """Lane A (naive) + lane B (Sentinel) in parallel; slot held."""
        tag = f"{spec['name']}_r{run_id}"
        out = REPO_ROOT / "out"
        lanes = (
            ("A", split_naive,
             {"preset": spec["preset"], "attack": spec["attack"],
              "out_path": str(out / f"split_A_{tag}.mp4"), "tag": tag,
              "fps": 30}),
            ("B", split_live,
             {"preset": spec["preset"], "attack": spec["attack"],
              "perception": "truth", "planner_model": model}),
        )

        def _lane(lane, fn, kwargs):
            def go():
                def sink(ev):
                    if ev["type"] == "frame":
                        ev = {**ev, "boxes": []}  # clean lane cameras
                    _publish_split(lane, run_id, ev)

                try:
                    if lane == "A":
                        fn(spec["instruction"], sink=sink, **kwargs)
                    else:
                        fn(spec["instruction"],
                           str(out / f"split_B_{tag}.mp4"), sink=sink,
                           **kwargs)
                except SystemExit:
                    pass  # _run_headless emits done before raising
                except Exception as e:  # noqa: BLE001 - one lane survives
                    _publish_split(
                        lane, run_id,
                        done_event("error", {"error": str(e)}))

            return go

        threads = [threading.Thread(target=_lane(lane, fn, kwargs),
                                    daemon=True)
                   for lane, fn, kwargs in lanes]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    @app.get("/bench-strip")
    def bench_strip():
        from bench.scenarios import load_scenarios

        path = Path(bench_csv) if bench_csv is not None else \
            REPO_ROOT / "bench" / "results.csv"
        try:
            rows = list(csv.DictReader(
                path.read_text().splitlines()))
        except OSError:
            return JSONResponse(
                {"error": "bench/results.csv missing "
                 "(run bench/report.py --csv)"},
                status_code=503)
        if not rows:
            return JSONResponse({"error": "bench/results.csv is empty"},
                                status_code=503)
        unsafe = {s["id"] for s in load_scenarios()
                  if not s["label"]["safe"]}

        def _rate(cond: str) -> float:
            sub = [r for r in rows if r["condition"] == cond
                   and r["scenario"] in unsafe]
            if not sub:
                return 0.0
            return round(100.0 * sum(int(r["unsafe_executed"])
                                     for r in sub) / len(sub), 1)

        return {"naive_unsafe_pct": _rate("naive"),
                "sentinel_unsafe_pct": _rate("loop"),
                "n_scenarios": len({r["scenario"] for r in rows})}

    @app.get("/examples")
    def examples():
        """D-09 example chips (single source: tests/fixtures file)."""
        path = REPO_ROOT / "tests" / "fixtures" / "examples.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"examples": []}
        if not isinstance(doc, dict) or \
                not isinstance(doc.get("examples"), list):
            return {"examples": []}
        return {"examples": doc["examples"]}

    @app.post("/incident")
    def file_incident(body: Incident):
        """File "that was unsafe" on the last run (R-01 incident entry)."""
        with state["lock"]:
            if state["instruction"] is None:
                return JSONResponse({"error": "no run yet"},
                                    status_code=404)
            history = list(state["history"])
            instruction = state["instruction"]
            live_id = state["live_run_id"]
            srv_run = state["run_id"]
            latest_graph = state["latest"].get("graph")
        verdicts = [e for _, e in history if e["type"] == "verdict"]
        dones = [e for _, e in history if e["type"] == "done"]
        findings = verdicts[-1]["findings"] if verdicts else []
        if dones:
            outcome = dones[-1]["status"]
            motion = dones[-1]["detail"].get("motion")
        elif verdicts:
            outcome = verdicts[-1]["kind"]
            motion = None
        else:
            outcome, motion = "unknown", None
        graph = None
        if latest_graph is not None:
            graph = learner_events.compact_graph(latest_graph[1]["graph"])
        closest = None
        if live_id is not None:
            logged = [e for e in learner_events.read_events()
                      if e.get("run_id") == live_id
                      and e.get("kind") == "verdict"]
            if logged:
                closest = logged[-1].get("closest")
        entry = learner_events.append_event({
            "kind": "incident", "run_id": live_id,
            "instruction": instruction, "text": body.text,
            "graph": graph, "motion": motion, "closest": closest,
            "findings": findings, "outcome": outcome})
        with state["lock"]:
            state["incident_idx"] = None
        return {"id": entry["id"], "incident_n": entry["incident_n"],
                "run_id": srv_run}

    @app.get("/rules/versions")
    def rule_versions():
        """Journal + active learned rules for the Rules tab."""
        return rule_versions_mod.status()

    @app.get("/rules/gate-report")
    def gate_report(version: int | None = None):
        """Gate report of the latest (or Nth) learned rule."""
        adds = [e for e in rule_versions_mod.journal()
                if e.get("action") == "add"]
        pick = None
        if version is None:
            pick = adds[-1] if adds else None
        else:
            pick = next((e for e in adds if e["seq"] == version), None)
        if pick is None:
            return JSONResponse({"error": "no such learned rule"},
                                status_code=404)
        return {"version": pick["seq"], "rule_id": pick["rule_id"],
                "rule": pick["rule"], "gate": pick["gate"],
                "incident": pick.get("incident")}

    @app.post("/rules/rollback")
    def rollback_rule(body: Rollback):
        """Roll back a learned rule (owner only, like ASK approvals)."""
        if token is None or not hmac.compare_digest(body.token, token):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        try:
            entry = rule_versions_mod.rollback(body.version)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        return {"rule_id": entry["rule_id"],
                "reverts": entry["reverts"], "seq": entry["seq"]}

    @app.post("/ask/{ask_id}")
    def decide_ask_endpoint(ask_id: str, body: AskDecision):
        if token is None or not hmac.compare_digest(body.token, token):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        if not registry.decide(ask_id, body.decision):
            return JSONResponse({"error": "no pending ask with that id"},
                                status_code=404)
        return {"ask_id": ask_id, "decision": body.decision}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        mine: queue.Queue = queue.Queue()
        with state["lock"]:
            state["subs"].add(mine)
            catchup = [state["latest"][t]
                       for t in ("frame", "graph", "plan")
                       if t in state["latest"]]
            catchup += list(state["history"])
        loop = asyncio.get_running_loop()
        try:
            for rid, event in catchup:
                await websocket.send_json(_envelope(rid, event))
            while True:
                try:
                    event = await loop.run_in_executor(
                        None, lambda: mine.get(timeout=1.0))
                except queue.Empty:
                    continue
                await websocket.send_json(_envelope(state["run_id"], event))
        except WebSocketDisconnect:
            pass
        finally:
            with state["lock"]:
                state["subs"].discard(mine)

    @app.websocket("/ws-split")
    async def ws_split(websocket: WebSocket):
        await websocket.accept()
        mine: queue.Queue = queue.Queue()
        loop = asyncio.get_running_loop()
        with state["lock"]:
            # Subscribe first: anything published from here on lands
            # in latest/history AND our queue, so the catchup below
            # cannot miss it.
            state["split_subs"].add(mine)
            preset = state["split_preset"]
            need_idle = not state["split_latest"] \
                and not state["split_history"]
        if need_idle:
            # Nothing published yet: seed both lanes with the preset
            # idle (no clearing), off the event loop.
            try:
                await loop.run_in_executor(
                    None,
                    lambda: _publish_split_idle(preset, clear=False))
            except Exception as e:  # noqa: BLE001 - stay in loading
                print(f"split idle render failed: {e}")
        # Drop anything queued during the render: it is all in
        # latest/history too, which is what the catchup reads (a
        # publish landing between drain and re-read may arrive
        # twice; every consumer here is idempotent).
        try:
            while True:
                mine.get_nowait()
        except queue.Empty:
            pass
        with state["lock"]:
            replay = dict(state["split_latest"])
            history = list(state["split_history"])
        catchup = [(rid, key[1], ev)
                   for key, (rid, ev) in replay.items()]
        catchup += history
        try:
            for rid, lane, event in catchup:
                await websocket.send_json(
                    {"run_id": rid, "lane": lane, **_envelope(rid, event)})
            while True:
                try:
                    rid, lane, event = await loop.run_in_executor(
                        None, lambda: mine.get(timeout=1.0))
                except queue.Empty:
                    continue
                await websocket.send_json(
                    {"run_id": rid, "lane": lane, **_envelope(rid, event)})
        except WebSocketDisconnect:
            pass
        finally:
            with state["lock"]:
                state["split_subs"].discard(mine)

    if web_dir is not None:
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        root = Path(web_dir)

        @app.get("/")
        def _index():
            return FileResponse(root / "index.html")

        @app.get("/debug")
        def _debug():
            return FileResponse(root / "index.html")

        app.mount("/assets", StaticFiles(directory=root / "assets"),
                  name="assets")

    return app


app = create_app(idle_render=True)
