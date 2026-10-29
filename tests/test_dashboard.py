"""D-01: dashboard event schema + server (injected runner, no network)."""

import json
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dashboard import events as E
from dashboard.server import create_app


def _sample_events():
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    frame[10:20, 10:20] = (0, 0, 255)
    findings = [{"rule": "R1", "severity": "hard", "verdict": "BLOCK",
                 "detail": "blade near hand"}]
    trace = ["Round 1: BLOCK R1", "feedback: keep the blade away"]
    graph = {"objects": [{"id": "cup", "label": "cup",
                          "position": np.array([0.1, 0.2, 0.3])}],
             "people": [], "safe_spot": [0.0, 0.0, 0.3]}
    return [
        E.frame_event(E.encode_jpeg_b64(frame), [{"id": "cup"}], "sam", 1.5),
        E.graph_event(graph),
        E.plan_event([{"action": "grasp", "args": {"object_id": "cup"}}], 1),
        E.verdict_event(1, "BLOCK", findings, "feedback text",
                        E.why_path_for(trace, 1)),
        E.halt_event(0.5, 1.2, "vel 30.0 > 25.0"),
        E.clear_event(2.0, 2),
        E.done_event("complete", {"takers": {}}),
    ]


def test_every_event_type_serializes():
    for ev in _sample_events():
        assert ev["type"] in {"frame", "graph", "plan", "verdict", "halt",
                              "clear", "done"}
        json.dumps(E.to_jsonable(ev))  # must not raise


def test_verdict_carries_why_path_and_feedback():
    ev = _sample_events()[3]
    assert ev["why_path"] == ["Round 1: BLOCK R1",
                              "feedback: keep the blade away"]
    assert ev["feedback"] == "feedback text"


def test_why_path_for_extracts_round_block():
    trace = ["quarantine: note quarantined", "Round 1: BLOCK R1",
             "feedback: keep away", "Round 2: ALLOW",
             "HALT t=1.0: person in path"]
    assert E.why_path_for(trace, 1) == trace[:3]
    assert E.why_path_for(trace, 2) == ["Round 2: ALLOW"]
    assert E.why_path_for(trace, 3) == []


def _run_plan_done(instruction, sink, **kwargs):
    sink(E.plan_event([{"action": "stop", "args": {}}], 1))
    sink(E.done_event("complete", {"instruction": instruction}))


def test_post_streams_plan_then_done_over_ws():
    app = create_app(runner=_run_plan_done)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        r = client.post("/instruction", json={"instruction": "wave"})
        assert r.status_code == 202
        first = ws.receive_json()
        second = ws.receive_json()
        assert (first["type"], second["type"]) == ("plan", "done")
        assert first["run_id"] == r.json()["run_id"]
        assert second["detail"]["instruction"] == "wave"


def test_second_post_while_busy_is_409_then_recovers():
    gate = threading.Event()

    def _slow(instruction, sink, **kwargs):
        gate.wait(timeout=10)
        sink(E.done_event("complete", {}))

    app = create_app(runner=_slow)
    with TestClient(app) as client:
        assert client.post("/instruction",
                           json={"instruction": "one"}).status_code == 202
        assert client.post("/instruction",
                           json={"instruction": "two"}).status_code == 409
        gate.set()
        for _ in range(200):
            r = client.post("/instruction", json={"instruction": "three"})
            if r.status_code == 202:
                break
            time.sleep(0.05)
        assert r.status_code == 202


def test_runner_crash_streams_done_error():
    def _boom(instruction, sink, **kwargs):
        raise ValueError("boom")

    app = create_app(runner=_boom)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        ev = ws.receive_json()
        assert ev["type"] == "done"
        assert ev["status"] == "error"
        assert "boom" in ev["detail"]["error"]


def test_runner_system_exit_keeps_server_alive():
    def _halted(instruction, sink, **kwargs):
        sink(E.done_event("stopped", {"reason": "BLOCK"}))
        raise SystemExit(1)

    app = create_app(runner=_halted)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        assert ws.receive_json()["status"] == "stopped"
        for _ in range(200):
            r = client.post("/instruction", json={"instruction": "y"})
            if r.status_code == 202:
                break
            time.sleep(0.05)
        assert r.status_code == 202


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
