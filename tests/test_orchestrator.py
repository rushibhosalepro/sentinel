"""L-06: worker replan loop (stubbed planner + verdict, real builds)."""

import json
import queue
import threading
from pathlib import Path

import mujoco
import numpy as np

import loop.live as live
from graph.scene_graph import load_props
from loop.handover import build_execution_script
from sentinel.check import check
from sentinel.graph_view import graph_snapshot
from sentinel.relations import aabb_xz_gap
from sim.primitives import free_qposadr
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
    assert res["trace"] == ["Round 1: ASK sharp_fast_near_person",
                            "feedback: slow within 30 cm of a person",
                            "Round 2: ALLOW"]


def test_block_never_retries(monkeypatch):
    model, data = load_scene("kitchen")
    res, calls = _run(model, data, [_content("trick_skip_handto.json")],
                      [_block()], monkeypatch)
    assert len(calls) == 1
    assert res["verdict"]["kind"] == "BLOCK"
    assert res["rounds"] == 0
    assert res["trace"] == ["Round 1: BLOCK sharp_toward_person"]


def test_ask_gives_up_after_3_rounds(monkeypatch):
    model, data = load_scene("kitchen")
    res, calls = _run(model, data, [_content("give_apple.json")] * 4,
                      [_ask()] * 4, monkeypatch)
    assert len(calls) == 4
    assert res["verdict"]["kind"] == "ASK"
    assert res["rounds"] == 3
    assert len(res["trace"]) == 7
    assert res["trace"][0] == "Round 1: ASK sharp_fast_near_person"
    assert res["trace"][-1] == "Round 4: ASK sharp_fast_near_person"


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

    # South corridor: joint-space bows cut ~5 cm inside straight legs,
    # so the jug reaches the owner around (not over) the laptop AABB zone.
    jug_run = [step(0, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
               step(1, "move_to", {"pose": [-0.15, 0.22, 0.25, *DOWN]}),
               step(2, "move_to", {"pose": [-0.15, 0.22, 0.10, *DOWN]}),
               step(3, "grasp", {"object_id": "jug"}),
               step(4, "move_to", {"pose": [-0.15, 0.22, 0.30, *DOWN]}),
               step(5, "move_to", {"pose": [0.25, 0.05, 0.45, *DOWN]}),
               step(6, "move_to", {"pose": [0.20, -0.15, 0.35, *DOWN]}),
               step(7, "move_to", {"pose": [0.20, -0.35, 0.30, *DOWN]}),
               step(8, "move_to", {"pose": [0.45, -0.35, 0.30, *DOWN]}),
               step(9, "move_to", {"pose": [0.70, -0.35, 0.30, *DOWN]}),
               step(10, "stop", {})]
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
    assert res["trace"][0].startswith("Round 1: ASK")
    assert res["trace"][-1] == "Round 2: ALLOW"


STAGING = [0.25, 0.05, 0.45]
JUG_HOME = (-0.15, 0.22)


def _mv(x, y, z):
    return ("move_to", {"pose": [x, y, z, 0.0, 1.0, 0.0, 0.0]})


def _plan(seq):
    return [{"id": f"s{i}", "primitive": prim, "args": args,
             "serves_instruction": "test", "why": "test"}
            for i, (prim, args) in enumerate(seq, 1)]


def _f3_verdict(plan):
    """Real live build + real check with the cup at the F3 preset."""
    model, data = load_scene("kitchen")
    props = load_props()
    live._apply_preset(model, data, None, "cup_next_to_laptop")
    hid = model.body("hand").id
    script, err = build_execution_script(
        model, data, plan, data.xpos[hid].copy(),
        data.xquat[hid].copy(), "test")
    assert err is None, err
    graph = graph_snapshot(model, data, props)
    return check(script["motion"], graph), graph


def _pour_at(cx, cy):
    jx, jy = JUG_HOME
    return _plan([
        _mv(*STAGING), _mv(jx, jy, 0.30), _mv(jx, jy, 0.10),
        ("grasp", {"object_id": "jug"}), _mv(jx, jy, 0.30), _mv(*STAGING),
        _mv(cx, cy, 0.45), _mv(cx, cy, 0.25),
        ("tilt", {"deg": 30}), ("tilt", {"deg": 0}),
        _mv(cx, cy, 0.45), _mv(*STAGING),
        _mv(jx, jy, 0.30), _mv(jx, jy, 0.10),
        ("release", {}), ("stop", {}),
    ])


def test_f3_pour_blocks_soft_with_computed_hint():
    """Round-1 trigger: F3 pour soft-BLOCKs; hint names computed spot."""
    cx, cy, _ = live.CUP_NEAR_LAPTOP
    v, graph = _f3_verdict(_pour_at(cx, cy))
    assert v["kind"] == "BLOCK"
    assert {f["rule"] for f in v["findings"]} == {
        "liquid_above_electronic"}
    assert v["why_path"] and v["why_path"][0]["hard"] is False
    assert graph["safe_spot_pour"] == (0.2, 0.15)
    assert v["feedback"] == ["move the cup to (0.20, 0.15) exactly, "
                             "away from electronics, then pour into it"]


def _f3_spot():
    """Computed safe spot for the F3 scene (no motion build)."""
    model, data = load_scene("kitchen")
    props = load_props()
    live._apply_preset(model, data, None, "cup_next_to_laptop")
    return graph_snapshot(model, data, props)["safe_spot_pour"]


def test_cup_move_recovery_allows():
    """Round-2 shape: cup to the computed spot, pour there -> ALLOW."""
    cx, cy, _ = live.CUP_NEAR_LAPTOP
    jx, jy = JUG_HOME
    sx, sy = _f3_spot()
    v, _ = _f3_verdict(_plan([
        _mv(*STAGING), _mv(cx, cy, 0.30), _mv(cx, cy, 0.10),
        ("grasp", {"object_id": "cup"}), _mv(cx, cy, 0.30), _mv(*STAGING),
        _mv(sx, sy, 0.45), _mv(sx, sy, 0.12), ("release", {}),
        _mv(*STAGING), _mv(jx, jy, 0.30), _mv(jx, jy, 0.10),
        ("grasp", {"object_id": "jug"}), _mv(jx, jy, 0.30), _mv(*STAGING),
        _mv(sx, sy, 0.45), _mv(sx, sy, 0.25),
        ("tilt", {"deg": 30}), ("tilt", {"deg": 0}),
        _mv(sx, sy, 0.45), _mv(*STAGING),
        _mv(jx, jy, 0.30), _mv(jx, jy, 0.10),
        ("release", {}), ("stop", {}),
    ]))
    assert v["kind"] == "ALLOW"


def test_spot_moves_with_laptop():
    """Shift the laptop 10 cm west; the spot follows and stays valid."""
    before = _f3_spot()
    model, data = load_scene("kitchen")
    props = load_props()
    live._apply_preset(model, data, None, "cup_next_to_laptop")
    data.qpos[free_qposadr(model, "laptop")] -= 0.10
    mujoco.mj_forward(model, data)
    graph = graph_snapshot(model, data, props)
    after = graph["safe_spot_pour"]
    assert after is not None and tuple(after) != tuple(before)
    pt = np.array(after, dtype=float)
    for node in graph["objects"].values():
        if "electronic" not in node.get("properties", []):
            continue
        gap = aabb_xz_gap(pt, np.asarray(node["pos"], dtype=float),
                           node.get("extent") or [0.0, 0.0, 0.0])
        assert gap >= 0.19 - 1e-9


def test_invalid_plan_retries_with_error_text(monkeypatch):
    model, data = load_scene("kitchen")
    res, calls = _run(model, data, ["not json", _content("give_apple.json")],
                      [_allow()], monkeypatch)
    assert len(calls) == 2
    assert "failed to build" in calls[1]
    assert "not valid JSON" in calls[1]
    assert res["verdict"]["kind"] == "ALLOW"
    assert res["rounds"] == 1
    assert res["trace"][0].startswith("Round 1: ERROR")
    assert res["trace"][-1] == "Round 2: ALLOW"
