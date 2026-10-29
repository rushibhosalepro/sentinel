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


def test_hazard_tag():
    assert E.hazard_tag(["sharp"]) == "SHARP"
    assert E.hazard_tag(["fragile"]) == "FRAGILE"
    assert E.hazard_tag(["food"]) is None
    assert E.hazard_tag([]) is None
    assert E.hazard_tag(["hot"]) is None  # not a camera tag


def test_project_boxes_tags():
    from graph.scene_graph import load_props
    from sim.world import load_scene

    model, data = load_scene("kitchen")
    props = load_props()
    by_id = {b["id"]: b
             for b in E.project_boxes(model, data, props, "demo", 640, 480)}
    assert by_id["chef_knife"]["tag"] == "SHARP"
    assert by_id["laptop"]["tag"] == "ELECTRONIC"
    assert by_id["jug"]["tag"] == "LIQUID"
    assert by_id["pill_bottle"]["tag"] == "MEDICATION"
    assert by_id["wine_glass"]["tag"] == "FRAGILE"
    assert by_id["cup"]["tag"] is None
    assert by_id["apple"]["tag"] is None
    perceived = {"chef_knife": {"pos": [0.35, -0.18, 0.05],
                                "extent": [0.02, 0.02, 0.02], "conf": 0.7}}
    boxes = E.project_boxes(model, data, props, "demo", 640, 480, perceived)
    assert [(b["id"], b["tag"], b["conf"]) for b in boxes] == [
        ("chef_knife", "SHARP", 0.7)]


def test_dashboard_payload_carries_builder_edges():
    from graph.scene_graph import (DASHBOARD_EDGE_TYPES, build_ground_truth,
                                   dashboard_payload, load_props)
    from sim.world import load_scene

    model, data = load_scene("kitchen")
    props = load_props()
    payload = dashboard_payload(build_ground_truth(model, data, props),
                                props)
    assert set(DASHBOARD_EDGE_TYPES) == {"ON", "NEAR", "ABOVE", "INSIDE",
                                         "HAS"}
    got = {(e["rel"], e["subj"], e["obj"]) for e in payload["edges"]}
    assert ("ON", "apple", "plate") in got  # the visible hero edge
    assert ("HAS", "chef_knife", "prop:sharp") in got
    assert not [e for e in payload["edges"]
                if e["rel"] in ("OWNED_BY", "HOLDS")]
    near = [e for e in payload["edges"] if e["rel"] == "NEAR"]
    assert near and all(isinstance(e["dist_cm"], float) for e in near)
    assert all(e["dist_cm"] is None for e in payload["edges"]
               if e["rel"] == "HAS")
    assert [(n["id"], n["label"]) for n in payload["extra_nodes"]] == [
        ("counter", "counter")]
    pos = payload["extra_nodes"][0]["pos"]
    assert len(pos) == 3 and all(isinstance(v, float) for v in pos)
    json.dumps(payload)  # JSON-native, no numpy


def test_graph_event_edges_match_builders():
    from dashboard.server import _render_idle_frame
    from graph.scene_graph import (DASHBOARD_EDGE_TYPES, build_ground_truth,
                                   load_props)
    from sim.world import load_scene

    model, data = load_scene("kitchen")
    props = load_props()
    want = {(d["type"], a, b)
            for a, b, d in build_ground_truth(
                model, data, props).edges(data=True)
            if d["type"] in DASHBOARD_EDGE_TYPES}
    _, graph_ev = _render_idle_frame("default", {})
    got = {(e["rel"], e["subj"], e["obj"])
           for e in graph_ev["graph"]["edges"]}
    assert got == want
    assert ("ON", "apple", "plate") in got
    json.dumps(E.to_jsonable(graph_ev))


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


def test_second_post_queues_with_position_then_runs():
    gate = threading.Event()
    seen = []

    def _slow(instruction, sink, **kwargs):
        seen.append(instruction)
        gate.wait(timeout=10)
        sink(E.done_event("complete", {}))

    app = create_app(runner=_slow)
    with TestClient(app) as client:
        first = client.post("/instruction", json={"instruction": "one"})
        assert first.json()["status"] == "started"
        second = client.post("/instruction", json={"instruction": "two"})
        assert second.status_code == 202
        assert second.json()["status"] == "queued"
        assert second.json()["position"] == 1
        assert client.get("/health").json()["queued"] == 1
        gate.set()
        for _ in range(200):
            if seen == ["one", "two"]:
                break
            time.sleep(0.05)
        assert seen == ["one", "two"]


def _stub_naive(instruction, *, preset, attack, out_path, tag, sink,
                fps=30):
    sink(E.frame_event("AAA", [{"id": "x"}], "truth", 0.0))
    sink(E.done_event("complete", {"outcome": "stub naive did X"}))


def _stub_live(instruction, out_path, *, preset, attack, perception,
               planner_model, sink):
    sink(E.verdict_event(1, "BLOCK", [], None, []))
    sink(E.done_event("BLOCK", {}))


def test_split_runs_both_lanes_with_lane_tags():
    app = create_app(runner=_run_plan_done, split_naive=_stub_naive,
                     split_live=_stub_live)
    with TestClient(app) as client, \
            client.websocket_connect("/ws-split") as ws:
        r = client.post("/split", json={"preset": "knife"})
        assert r.status_code == 202
        assert r.json()["preset"] == "knife"
        got = []
        for _ in range(8):
            ev = ws.receive_json()
            got.append(ev)
            if sum(1 for e in got if e["type"] == "done") == 2:
                break
        by_lane = {}
        for e in got:
            by_lane.setdefault(e["lane"], []).append(e["type"])
        assert sorted(by_lane["A"]) == ["done", "frame"]
        assert sorted(by_lane["B"]) == ["done", "verdict"]
        frame = next(e for e in got if e["type"] == "frame")
        assert frame["boxes"] == []  # clean lane cameras
        done_a = next(e for e in got if e["lane"] == "A"
                      and e["type"] == "done")
        assert done_a["detail"]["outcome"] == "stub naive did X"
        assert {e["run_id"] for e in got} == {r.json()["run_id"]}


def test_split_validation_and_free_text_token():
    app = create_app(runner=_run_plan_done, split_naive=_stub_naive,
                     split_live=_stub_live, owner_token="test-token")
    with TestClient(app) as client:
        assert client.post("/split", json={"preset": "nope"}
                           ).status_code == 400
        both = client.post("/split", json={"preset": "knife",
                                           "instruction": "x"})
        assert both.status_code == 400
        assert client.post("/split", json={}).status_code == 400
        free = client.post("/split", json={"instruction": "wave"})
        assert free.status_code == 403
        owned = client.post("/split", json={"instruction": "wave",
                                            "token": "test-token"})
        assert owned.status_code == 202
        assert owned.json()["preset"] == "free"


def test_public_mode_gates_debug_posting():
    app = create_app(runner=_run_plan_done, public_mode=True,
                     owner_token="test-token")
    with TestClient(app) as client:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 403
        ok = client.post("/instruction", json={"instruction": "x",
                                               "token": "test-token"})
        assert ok.status_code == 202
    open_app = create_app(runner=_run_plan_done)
    with TestClient(open_app) as client:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202


def test_rate_limit_429s_when_over_limit():
    app = create_app(runner=_run_plan_done, rate_limit_per_hour=2)
    with TestClient(app) as client:
        assert client.post("/instruction",
                           json={"instruction": "a"}).status_code == 202
        assert client.post("/instruction",
                           json={"instruction": "b"}).status_code == 202
        third = client.post("/instruction", json={"instruction": "c"})
        assert third.status_code == 429


def test_daily_budget_stops_with_polite_message(tmp_path):
    import datetime

    costs = tmp_path / "costs.jsonl"
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    costs.write_text(json.dumps({"ts": f"{today}T00:00:01+00:00",
                                 "cost_usd": 9.99}) + "\n")
    broke = create_app(runner=_run_plan_done, daily_budget_usd=5.0,
                       costs_path=costs)
    with TestClient(broke) as client:
        r = client.post("/instruction", json={"instruction": "x"})
        assert r.status_code == 503
        assert "tomorrow" in r.json()["error"]
    rich = create_app(runner=_run_plan_done, daily_budget_usd=50.0,
                      costs_path=costs)
    with TestClient(rich) as client:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202


def test_bench_strip_from_results_csv(tmp_path):
    app = create_app(runner=_run_plan_done)
    with TestClient(app) as client:
        strip = client.get("/bench-strip").json()
        assert strip["naive_unsafe_pct"] == 62.0
        assert strip["sentinel_unsafe_pct"] == 23.4
        assert strip["n_scenarios"] == 128
    missing = create_app(runner=_run_plan_done,
                         bench_csv=tmp_path / "nope.csv")
    with TestClient(missing) as client:
        assert client.get("/bench-strip").status_code == 503


def test_web_dir_serves_index_for_root_and_debug(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<p>split</p>")
    (web / "assets" / "a.txt").write_text("x")
    app = create_app(runner=_run_plan_done, web_dir=web)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/debug").status_code == 200
        assert client.get("/assets/a.txt").text == "x"
        assert client.get("/health").json()["status"] == "ok"


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


def _two_rounds(instruction, sink, **kwargs):
    sink(E.plan_event([{"action": "stop", "args": {}}], 1))
    sink(E.proposal_event(1, "spark", 1.0, 3))
    sink(E.verdict_event(1, "BLOCK", [], ["slow down"], []))
    sink(E.feedback_event(1, "Attempt 1 was rejected (BLOCK)."))
    sink(E.proposal_event(2, "spark", 2.0, 3))
    sink(E.verdict_event(2, "ALLOW", [], None, []))
    sink(E.done_event("complete", {}))


def test_late_socket_replays_full_run_then_clears():
    kinds = ["plan", "proposal", "verdict", "feedback", "proposal",
             "verdict", "done"]
    app = create_app(runner=_two_rounds)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws1:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        assert [ws1.receive_json()["type"] for _ in range(7)] == kinds
    with TestClient(app) as client, client.websocket_connect("/ws") as ws2:
        got = [ws2.receive_json() for _ in range(7)]
        assert [e["type"] for e in got] == kinds
        assert {e["run_id"] for e in got} == {1}
    with TestClient(app) as client, client.websocket_connect("/ws") as ws3:
        assert [ws3.receive_json()["type"] for _ in range(7)] == kinds
        assert client.post("/instruction",
                           json={"instruction": "y"}).status_code == 202
        live = [ws3.receive_json() for _ in range(7)]
        assert [e["type"] for e in live] == kinds
        assert {e["run_id"] for e in live} == {2}
    with TestClient(app) as client, client.websocket_connect("/ws") as ws4:
        got = [ws4.receive_json() for _ in range(7)]
        assert [e["type"] for e in got] == kinds
        assert {e["run_id"] for e in got} == {2}  # run 1 cleared


def test_concurrent_scene_renders_stay_up():
    import concurrent.futures as futures

    app = create_app(runner=_run_plan_done, idle_render=True)

    def _get(_):
        with TestClient(app) as client:
            return client.get("/scene?preset=default").status_code

    with futures.ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(_get, range(3))) == [200, 200, 200]
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def _slow_stream(instruction, sink, **kwargs):
    import time as _time

    for i in range(10):
        sink(E.frame_event("e30=", [], "truth", float(i)))
        _time.sleep(0.2)


def test_live_disconnect_is_quiet():
    """Real sockets: a mid-stream drop leaves no traceback behind."""
    import logging
    import socket
    import time as _time

    import httpx
    import uvicorn
    import websockets.sync.client as ws_client

    records = []

    class _Sink(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("uvicorn.error")
    sink_handler = _Sink(level=logging.ERROR)
    logger.addHandler(sink_handler)
    try:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        server = uvicorn.Server(uvicorn.Config(
            create_app(runner=_slow_stream), port=port,
            log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/health",
                                 timeout=2).status_code == 200:
                        break
                except Exception:  # noqa: BLE001 - not up yet
                    _time.sleep(0.1)
            httpx.post(f"http://127.0.0.1:{port}/instruction",
                       json={"instruction": "x"}, timeout=10)
            with ws_client.connect(f"ws://127.0.0.1:{port}/ws",
                                      max_size=10_000_000) as ws:
                ws.recv(timeout=10)
            # Socket closed mid-stream; the send-only handler finds out
            # on its next send.
            _time.sleep(2.5)  # let several sends hit the dead socket
        finally:
            server.should_exit = True
            thread.join(timeout=15)
    finally:
        logger.removeHandler(sink_handler)
    assert [r for r in records
            if "Traceback" in r.getMessage() or r.exc_info] == []


def test_abrupt_disconnect_leaves_server_healthy():
    app = create_app(runner=_two_rounds)
    with TestClient(app) as client:
        with client.websocket_connect("/ws"):
            pass  # connect and drop immediately
        with client.websocket_connect("/ws") as ws:
            assert client.post("/instruction",
                               json={"instruction": "x"}).status_code == 202
            kinds = ["plan", "proposal", "verdict", "feedback", "proposal",
                     "verdict", "done"]
            assert [ws.receive_json()["type"] for _ in range(7)] == kinds


def test_ask_registry_timeout_and_double_decide():
    reg = AskRegistry()
    reg.pre_register("ask-1")
    assert reg.wait("ask-1", timeout=0.05) is None  # timeout -> deny
    reg.pre_register("ask-2")
    assert reg.decide("ask-2", "approve") is True
    assert reg.decide("ask-2", "deny") is False  # single-shot
    assert reg.wait("ask-2", timeout=1.0) == "approve"
    assert reg.wait("ask-missing", timeout=0.01) is None


def _incident_run(instruction, sink, **kwargs):
    sink(E.graph_event({"objects": {"wine_glass": {
        "properties": ["fragile"], "owner": "owner", "conf": 1.0}},
        "people": {}}))
    sink(E.verdict_event(1, "ALLOW", [], None, [],
                         live_run_id="run-live-1"))
    sink(E.done_event("complete", {"motion": "Motion: 10 samples"}))


def test_incident_files_on_last_run(tmp_path):
    app = create_app(runner=_incident_run)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "move plate"}
                           ).status_code == 202
        assert [ws.receive_json()["type"] for _ in range(3)] == [
            "graph", "verdict", "done"]
        r = client.post("/incident",
                        json={"text": "nearly knocked it off"})
        assert r.status_code == 200
        assert r.json()["incident_n"] == 1
    with open(tmp_path / "events.jsonl") as f:
        log = [json.loads(line) for line in f]
    (inc,) = [e for e in log if e["kind"] == "incident"]
    assert inc["id"] == "inc-001"
    assert inc["run_id"] == "run-live-1"  # joins worker verdicts
    assert inc["closest"] is None  # fake runner logged no verdicts
    assert inc["outcome"] == "complete"
    assert inc["motion"] == "Motion: 10 samples"
    assert inc["graph"]["objects"]["wine_glass"]["properties"] == ["fragile"]


def test_incident_without_run_is_404():
    app = create_app(runner=_run_plan_done)
    with TestClient(app) as client:
        assert client.post("/incident",
                           json={"text": "x"}).status_code == 404


def test_rules_versions_and_gate_report(monkeypatch, tmp_path):
    from learner import versions as V

    monkeypatch.setattr(V, "LEARNED_DIR", tmp_path / "learned")
    monkeypatch.setattr(V, "JOURNAL", tmp_path / "VERSIONS.jsonl")
    app = create_app(runner=_run_plan_done)
    with TestClient(app) as client:
        assert client.get("/rules/versions").json() == {"journal": [],
                                                        "active": []}
        assert client.get("/rules/gate-report").status_code == 404
        V.add_rule({"id": "r1", "when": {"speed": "normal"}}, "inc-001",
                   {"accepted": True})
        got = client.get("/rules/versions").json()
        assert [a["rule_id"] for a in got["active"]] == ["r1"]
        assert got["journal"][0]["incident"] == "inc-001"
        g = client.get("/rules/gate-report").json()
        assert g["version"] == 1 and g["gate"] == {"accepted": True}
        assert g["rule"]["id"] == "r1"
        assert client.get("/rules/gate-report?version=9").status_code == 404


def test_rollback_needs_token_and_reverts(monkeypatch, tmp_path):
    from learner import versions as V

    monkeypatch.setattr(V, "LEARNED_DIR", tmp_path / "learned")
    monkeypatch.setattr(V, "JOURNAL", tmp_path / "VERSIONS.jsonl")
    V.add_rule({"id": "r1", "when": {"speed": "normal"}}, "inc-001",
               {"accepted": True})
    app = create_app(runner=_run_plan_done, owner_token="test-token")
    with TestClient(app) as client:
        r = client.post("/rules/rollback",
                        json={"version": "1", "token": "wrong"})
        assert r.status_code == 403
        r = client.post("/rules/rollback",
                        json={"version": "9", "token": "test-token"})
        assert r.status_code == 404
        r = client.post("/rules/rollback",
                        json={"version": "1", "token": "test-token"})
        assert r.status_code == 200
        assert r.json()["rule_id"] == "r1"
        assert client.get("/rules/versions").json()["active"] == []
        assert not (tmp_path / "learned" / "r1.json").exists()


def test_verdict_live_run_id_published_to_ws():
    seen = []

    def _run(instruction, sink, **kwargs):
        sink(E.verdict_event(1, "ALLOW", [], None, [],
                             live_run_id="run-x"))

    app = create_app(runner=_run)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        seen.append(ws.receive_json())
    assert seen[0]["live_run_id"] == "run-x"
    assert seen[0]["run_id"] == 1  # envelope keeps the server id


def test_learned_why_gets_incident_ref(tmp_path):
    from learner.events import append_event

    inc = append_event({"kind": "incident", "run_id": "run-x",
                        "instruction": "x", "text": "t"})
    why = [{"rule": "r1", "verdict": "ASK", "hard": False, "t": 0.5,
            "origin": "learned", "reason": "r", "predicates": {},
            "steps": [], "relations": [],
            "learned_from": [inc["id"], "ev-nope"]}]

    def _run(instruction, sink, **kwargs):
        sink(E.verdict_event(1, "ASK", [], None, why))

    app = create_app(runner=_run)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert client.post("/instruction",
                           json={"instruction": "x"}).status_code == 202
        (w,) = ws.receive_json()["why_path"]
    assert w["incident_ref"] == {"n": 1, "ts": inc["ts"]}


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
