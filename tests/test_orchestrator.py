"""L-06: worker replan loop (stubbed planner + verdict, real builds)."""

import json
import queue
import threading
from pathlib import Path

import loop.live as live
from graph.scene_graph import load_props
from sim.world import load_scene

PLANS = Path(__file__).parent / "fixtures" / "plans"


def _content(name):
    return json.loads((PLANS / name).read_text())["content"]


def _ask():
    return {"kind": "ASK",
            "findings": [{"rule": "sharp_fast_near_person", "node": "owner",
                          "t": 1.0, "detail": "too fast near owner"}],
            "why_path": [], "feedback": ["slow within 30 cm of a person"]}


def _allow():
    return {"kind": "ALLOW", "findings": [], "why_path": [],
            "feedback": None}


def _block():
    return {"kind": "BLOCK",
            "findings": [{"rule": "sharp_toward_person", "node": "owner",
                          "t": 1.0, "detail": "blade at owner"}],
            "why_path": [], "feedback": None}


def _job(model, data):
    props = load_props()
    hid = model.body("hand").id
    return {"gen": 0, "instruction": "test", "facts": {}, "data": data,
            "valid_ids": set(props["objects"]),
            "valid_people": set(props["people"]), "props": props,
            "home_pos": data.xpos[hid].copy(),
            "home_quat": data.xquat[hid].copy()}


def _run(model, data, contents, verdicts, monkeypatch,
         real_check=False):
    calls = []
    contents = list(contents)

    def fake_plan(instruction, facts, note=None):
        calls.append(note)
        return contents.pop(0)

    monkeypatch.setattr(live, "plan_instruction", fake_plan)
    if not real_check:
        verdicts = list(verdicts)

        def fake_check(motion, graph):
            return verdicts.pop(0)

        monkeypatch.setattr(live, "check", fake_check)
    jobs, results = queue.Queue(), queue.Queue()
    th = threading.Thread(target=live._planner_worker,
                          args=(model, jobs, results), daemon=True)
    th.start()
    jobs.put(_job(model, data))
    res = results.get(timeout=180)
    jobs.put(None)
    th.join(timeout=10)
    return res, calls


def test_ask_replans_with_constraints(monkeypatch):
    model, data = load_scene("kitchen")
    res, calls = _run(model, data, [_content("trick_skip_handto.json"),
                              _content("give_apple.json")],
                      [_ask(), _allow()], monkeypatch)
    assert len(calls) == 2
    assert calls[0] is None
    assert "slow within 30 cm of a person" in calls[1]
    assert "too fast near owner" in calls[1]
    assert res["verdict"]["kind"] == "ALLOW"
    assert res["rounds"] == 1


def test_block_never_retries(monkeypatch):
    model, data = load_scene("kitchen")
    res, calls = _run(model, data, [_content("trick_skip_handto.json")],
                      [_block()], monkeypatch)
    assert len(calls) == 1
    assert res["verdict"]["kind"] == "BLOCK"
    assert res["rounds"] == 0


def test_ask_gives_up_after_3_rounds(monkeypatch):
    model, data = load_scene("kitchen")
    res, calls = _run(model, data, [_content("give_apple.json")] * 4,
                      [_ask()] * 4, monkeypatch)
    assert len(calls) == 4
    assert res["verdict"]["kind"] == "ASK"
    assert res["rounds"] == 3


def test_real_ask_replans_to_allow(monkeypatch):
    """Full loop with the real checker: fast jug near owner ASKS, then ALLOW."""
    import json as _json

    from sentinel.check import load_rulebook
    from sentinel.graph_view import graph_snapshot
    from graph.scene_graph import load_props
    from loop.handover import build_execution_script

    model, data = load_scene("kitchen")
    props = load_props()
    DOWN = [0.0, 1.0, 0.0, 0.0]

    def step(i, prim, args):
        return {"id": f"s{i}", "primitive": prim, "args": args,
                "serves_instruction": "test", "why": "test"}

    jug_run = [step(0, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
               step(1, "move_to", {"pose": [-0.15, 0.22, 0.25, *DOWN]}),
               step(2, "move_to", {"pose": [-0.15, 0.22, 0.10, *DOWN]}),
               step(3, "grasp", {"object_id": "jug"}),
               step(4, "move_to", {"pose": [-0.15, 0.22, 0.30, *DOWN]}),
               step(5, "move_to", {"pose": [0.65, -0.05, 0.30, *DOWN]}),
               step(6, "stop", {})]
    # Sanity: this motion really ASKS with the real checker.
    hid = model.body("hand").id
    script, err = build_execution_script(
        model, data, jug_run, data.xpos[hid].copy(),
        data.xquat[hid].copy(), "test")
    assert err is None, err
    from sentinel.check import check
    v0 = check(script["motion"], graph_snapshot(model, data, props),
               load_rulebook())
    assert v0["kind"] == "ASK"
    assert "sharp_fast_near_person" in {f["rule"] for f in v0["findings"]}

    first = _json.dumps({"steps": jug_run})
    res, calls = _run(model, data, [first, _content("give_apple.json")],
                      None, monkeypatch, real_check=True)
    assert len(calls) == 2
    assert "slow within 30 cm of a person" in calls[1]
    assert res["verdict"]["kind"] == "ALLOW"
    assert res["rounds"] == 1
