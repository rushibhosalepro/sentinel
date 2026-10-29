"""D-01: dashboard event schema + server (injected runner, no network)."""

import json
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dashboard import events as E
from dashboard.server import AskRegistry, create_app


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


def test_proposal_feedback_ask_events_serialize():
    why = [{"rule": "r1", "verdict": "ASK", "hard": False, "t": 0.5,
            "origin": "seed", "reason": "why", "predicates": {"gap_cm": 1.0},
            "steps": ["s1"], "relations": []}]
    evs = [
        E.proposal_event(2, "muse-spark-1.3", 12.34, 6),
        E.feedback_event(2, "Attempt 2 was rejected (BLOCK)."),
        E.ask_event("ask-1a2b", 2, "Allow the motion?",
                    [{"rule": "r1", "detail": "d"}]),
        E.verdict_event(2, "ASK", [{"rule": "r1"}], ["slow down"], why),
        E.path_event(2, [[0.1, 0.2], [0.3, 0.4]], [[0.3, 0.4]]),
    ]
    assert [e["type"] for e in evs] == ["proposal", "feedback", "ask",
                                        "verdict", "path"]
    for ev in evs:
        json.dumps(E.to_jsonable(ev))
    assert evs[0]["latency_s"] == 12.3 and evs[0]["n_steps"] == 6
    assert evs[2]["ask_id"] == "ask-1a2b"
    assert evs[3]["why_path"][0]["origin"] == "seed"


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


@pytest.mark.parametrize("origin", ["http://localhost:5173",
                                   "http://127.0.0.1:5173"])
def test_cors_preflight_allows_dev_server(origin):
    app = create_app(runner=_run_plan_done)
    with TestClient(app) as client:
        r = client.options("/instruction", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == origin


def test_two_sockets_both_receive_same_frame():
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    def _run(instruction, sink, **kwargs):
        sink(E.frame_event(E.encode_jpeg_b64(frame), [], "truth", 0.0))
        sink(E.done_event("complete", {}))

    app = create_app(runner=_run)
    with TestClient(app) as client, \
            client.websocket_connect("/ws") as ws1, \
            client.websocket_connect("/ws") as ws2:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        ev1, ev2 = ws1.receive_json(), ws2.receive_json()
        assert ev1["type"] == ev2["type"] == "frame"
        assert ev1["image"] == ev2["image"]
        assert ws1.receive_json()["type"] == "done"
        assert ws2.receive_json()["type"] == "done"


def test_late_socket_gets_latest_plan_and_graph():
    def _run(instruction, sink, **kwargs):
        sink(E.plan_event([{"action": "stop", "args": {}}], 1))
        sink(E.graph_event({"objects": [], "people": []}))
        sink(E.done_event("complete", {}))

    app = create_app(runner=_run)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws1:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        assert [ws1.receive_json()["type"] for _ in range(3)] == [
            "plan", "graph", "done"]
    with TestClient(app) as client, client.websocket_connect("/ws") as ws2:
        assert [ws2.receive_json()["type"] for _ in range(2)] == [
            "graph", "plan"]


def _asker(instruction, sink, ask_handler, **kwargs):
    ask_handler.pre_register("ask-1")
    sink(E.ask_event("ask-1", 1, "Allow the motion?", []))
    d = ask_handler.wait("ask-1", timeout=10)
    sink(E.done_event("complete", {"decision": d}))


@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_ask_decision_reaches_waiter(decision):
    app = create_app(runner=_asker, owner_token="test-token")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        assert ws.receive_json()["type"] == "ask"
        r = client.post("/ask/ask-1",
                        json={"decision": decision, "token": "test-token"})
        assert r.status_code == 200
        assert r.json() == {"ask_id": "ask-1", "decision": decision}
        done = ws.receive_json()
        assert done["detail"]["decision"] == decision


def test_ask_wrong_token_is_403_then_recover():
    app = create_app(runner=_asker, owner_token="test-token")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        assert ws.receive_json()["type"] == "ask"
        r = client.post("/ask/ask-1",
                        json={"decision": "approve", "token": "wrong"})
        assert r.status_code == 403
        assert client.post(
            "/ask/ask-1",
            json={"decision": "deny", "token": "test-token"}).status_code == 200
        assert ws.receive_json()["detail"]["decision"] == "deny"


def test_ask_unknown_id_is_404_and_no_token_is_403():
    app = create_app(runner=_asker, owner_token="test-token")
    with TestClient(app) as client:
        r = client.post("/ask/ask-nope",
                        json={"decision": "deny", "token": "test-token"})
        assert r.status_code == 404
    app = create_app(runner=_asker, owner_token="")
    with TestClient(app) as client:
        r = client.post("/ask/ask-1",
                        json={"decision": "approve", "token": "test-token"})
        assert r.status_code == 403


def _recv_two(app, timeout=10.0):
    """Read 2 ws events in a thread so a failure can't hang the suite."""
    out = []

    def _run():
        with TestClient(app) as client, \
                client.websocket_connect("/ws") as ws:
            out.append(ws.receive_json())
            out.append(ws.receive_json())

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout=timeout)
    assert not th.is_alive(), "no frame+graph within 10 s"
    return out


def test_idle_socket_gets_frame_and_graph():
    app = create_app(runner=_run_plan_done, idle_render=True)
    first, second = _recv_two(app)
    assert (first["type"], second["type"]) == ("frame", "graph")
    assert first["run_id"] == 0 and second["run_id"] == 0
    assert len(second["graph"]["objects"]) > 0


def test_scene_preset_republishes_and_unknown_404s():
    app = create_app(runner=_run_plan_done, idle_render=True)
    with TestClient(app) as client:
        assert client.get("/scene?preset=bogus").status_code == 404
    first, second = _recv_two(app)  # startup pair (either order source)
    assert {first["type"], second["type"]} == {"frame", "graph"}
    with TestClient(app) as client, \
            client.websocket_connect("/ws") as ws:
        # Drain the catch-up pair from latest, then switch presets.
        assert ws.receive_json()["type"] == "frame"
        assert ws.receive_json()["type"] == "graph"
        r = client.get("/scene?preset=cup_next_to_laptop")
        assert r.status_code == 200
        assert r.json() == {"preset": "cup_next_to_laptop"}
        assert ws.receive_json()["type"] == "frame"
        graph = ws.receive_json()
        assert graph["type"] == "graph"
        cup = graph["graph"]["objects"]["cup"]["pos"]
        assert abs(cup[0] - 0.35) < 0.01  # the F3 cup spot


def test_ask_registry_timeout_and_double_decide():
    reg = AskRegistry()
    reg.pre_register("ask-1")
    assert reg.wait("ask-1", timeout=0.05) is None  # timeout -> deny
    reg.pre_register("ask-2")
    assert reg.decide("ask-2", "approve") is True
    assert reg.decide("ask-2", "deny") is False  # single-shot
    assert reg.wait("ask-2", timeout=1.0) == "approve"
    assert reg.wait("ask-missing", timeout=0.01) is None


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
