"""D-01: dashboard server: POST /instruction + /ws event stream.

POST /instruction runs the loop.live orchestrator (_run_headless) in
a worker thread; the run streams frame (JPEG ~10fps) + graph + plan +
round verdicts (with why_path) + HALT/clear + done over /ws as JSON.
One run at a time (409 while busy). Pass runner=... to create_app to
inject a fake orchestrator (tests).

Start: uv run uvicorn dashboard.server:app --port 8000
"""

from __future__ import annotations

import asyncio
import datetime
import queue
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.events import done_event


class Instruction(BaseModel):
    instruction: str
    perception: str = "truth"
    model: str = "spark"
    preset: str | None = None


def run_loop_live(instruction: str, sink, *, perception: str = "truth",
                  model: str = "spark", preset: str | None = None,
                  out_path: str = "out/dashboard_run.mp4") -> None:
    """Real runner: the loop.live orchestrator with an event sink."""
    from loop.live import _run_headless

    _run_headless(instruction, out_path, preset=preset,
                  perception=perception, planner_model=model, sink=sink)


def _envelope(run_id: int, event: dict) -> dict:
    return {"run_id": run_id,
            "ts": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
            **event}


def create_app(runner=run_loop_live) -> FastAPI:
    app = FastAPI(title="Sentinel dashboard")
    state = {"busy": False, "run_id": 0, "lock": threading.Lock(),
             "events": queue.Queue()}

    @app.get("/health")
    def health():
        return {"status": "ok"}

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
                runner(body.instruction, state["events"].put, **kwargs)
            except SystemExit:
                pass  # _run_headless emits done before raising
            except Exception as e:  # noqa: BLE001 - never kill the server
                state["events"].put(done_event("error", {"error": str(e)}))
            finally:
                with state["lock"]:
                    state["busy"] = False

        threading.Thread(target=_run, daemon=True).start()
        return {"run_id": run_id, "status": "started"}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        loop = asyncio.get_running_loop()
        try:
            while True:
                try:
                    event = await loop.run_in_executor(
                        None, lambda: state["events"].get(timeout=1.0))
                except queue.Empty:
                    continue
                await websocket.send_json(_envelope(state["run_id"], event))
        except WebSocketDisconnect:
            pass

    return app


app = create_app()
