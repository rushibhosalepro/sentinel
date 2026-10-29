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
import datetime
import hmac
import os
import queue
import threading
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.events import done_event

REPO_ROOT = Path(__file__).resolve().parent.parent


class Instruction(BaseModel):
    instruction: str
    perception: str = "truth"
    model: str = "spark"
    preset: str | None = None


class AskDecision(BaseModel):
    decision: Literal["approve", "deny"]
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


def _render_idle_frame(preset: str, idle: dict) -> tuple[dict, dict]:
    """Render one front frame + graph for a preset (lazy heavy imports)."""
    import mujoco

    import loop.live as live
    from dashboard.events import (encode_jpeg_b64, frame_event, graph_event,
                                  project_boxes)
    from graph.scene_graph import load_props
    from sentinel.graph_view import graph_snapshot
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
        renderer.update_scene(idle["data"], camera="front")
        frame = renderer.render()
    finally:
        with RENDER_LOCK:
            renderer.close()
    graph = graph_snapshot(idle["model"], idle["data"], idle["props"])
    boxes = project_boxes(idle["model"], idle["data"], idle["props"],
                          "front", WIDTH, HEIGHT)
    return (frame_event(encode_jpeg_b64(frame), boxes, "truth", 0.0),
            graph_event(graph))


def create_app(runner=run_loop_live, owner_token: str | None = None,
               idle_render: bool = False) -> FastAPI:
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
    registry = AskRegistry()
    state = {"busy": False, "run_id": 0, "lock": threading.Lock(),
             "subs": set(), "latest": {}, "idle": {},
             "render_lock": threading.Lock()}

    def _publish(event: dict):
        with state["lock"]:
            if event["type"] in ("frame", "graph", "plan"):
                state["latest"][event["type"]] = (state["run_id"], event)
            subs = list(state["subs"])
        for q in subs:
            q.put(event)

    def _publish_idle(preset: str):
        with state["render_lock"]:
            frame, graph = _render_idle_frame(preset, state["idle"])
        _publish(frame)
        _publish(graph)

    if idle_render:
        def _startup_render():
            try:
                _publish_idle("default")
            except Exception as e:  # noqa: BLE001 - page stays in loading
                print(f"idle scene render failed: {e}")

        threading.Thread(target=_startup_render, daemon=True).start()

    @app.get("/health")
    def health():
        return {"status": "ok"}

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

    @app.post("/instruction", status_code=202)
    def instruct(body: Instruction):
        with state["lock"]:
            if state["busy"]:
                return JSONResponse(
                    {"error": "a run is already in progress"},
                    status_code=409)
            state["busy"] = True
            state["run_id"] += 1
            run_id = state["run_id"]
        kwargs = {"perception": body.perception, "model": body.model,
                  "preset": body.preset}

        def _run():
            try:
                runner(body.instruction, _publish, ask_handler=registry,
                       **kwargs)
            except SystemExit:
                pass  # _run_headless emits done before raising
            except Exception as e:  # noqa: BLE001 - never kill the server
                _publish(done_event("error", {"error": str(e)}))
            finally:
                with state["lock"]:
                    state["busy"] = False

        threading.Thread(target=_run, daemon=True).start()
        return {"run_id": run_id, "status": "started"}

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

    return app


app = create_app(idle_render=True)
