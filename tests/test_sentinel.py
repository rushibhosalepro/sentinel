"""C-07: headline verdicts on real motions (fixtures + scripted, no network)."""

import json
import time
from pathlib import Path

from graph.scene_graph import load_props
from loop.handover import build_execution_script
from planner.planner import plan_from_content
from sentinel.check import check, load_rulebook
from sentinel.graph_view import graph_snapshot
from sim.play import SCENARIOS, rollout_frames
from sim.world import load_scene

PLANS = Path(__file__).parent / "fixtures" / "plans"
DOWN = [0.0, 1.0, 0.0, 0.0]


def _fresh():
    model, data = load_scene("kitchen")
    props = load_props()
    return model, data, props, graph_snapshot(model, data, props)


def _home(model, data):
    hid = model.body("hand").id
    return data.xpos[hid].copy(), data.xquat[hid].copy()


def _fixture_motion(name):
    rec = json.loads((PLANS / name).read_text())
    model, data, props, graph = _fresh()
    steps, err = plan_from_content(rec["content"], set(props["objects"]),
                                   set(props["people"]))
    assert err is None, err
    hp, hq = _home(model, data)
    script, err = build_execution_script(model, data, steps, hp, hq,
                                         rec["instruction"])
    assert err is None, err
    return script["motion"], graph


def _scripted_motion(scenario):
    model, data, _, graph = _fresh()
    motion, _, _ = rollout_frames(model, data,
                                  SCENARIOS[scenario]["plan"],
                                  derived_from="test:sentinel")
    return motion, graph


def _step(i, prim, args):
    return {"id": f"s{i}", "primitive": prim, "args": args,
            "serves_instruction": "test", "why": "test"}


def _plan_motion(plan):
    model, data, _, graph = _fresh()
    motion, _, _ = rollout_frames(model, data, plan,
                                  derived_from="test:sentinel")
    return motion, graph


def _fired(v):
    return {f["rule"] for f in v["findings"]}


def test_trick_blocks_without_feedback():
    motion, graph = _fixture_motion("trick_skip_handto.json")
    v = check(motion, graph, load_rulebook())
    assert v["kind"] == "BLOCK"
    assert {"sharp_toward_person", "release_near_person_in_air"} <= _fired(v)
    assert v["feedback"] is None


def test_unsafe_handover_asks_or_blocks():
    motion, graph = _scripted_motion("knife_handover_unsafe")
    v = check(motion, graph, load_rulebook())
    assert v["kind"] in ("ASK", "BLOCK")


def test_safe_handover_allows():
    motion, graph = _scripted_motion("knife_handover_safe")
    v = check(motion, graph, load_rulebook())
    assert v["kind"] == "ALLOW"
    assert v["findings"] == []


def test_give_knife_handto_allows():
    motion, graph = _fixture_motion("give_knife_handto.json")
    v = check(motion, graph, load_rulebook())
    assert v["kind"] == "ALLOW"
    assert v["findings"] == []


def test_give_apple_allows():
    motion, graph = _fixture_motion("give_apple.json")
    v = check(motion, graph, load_rulebook())
    assert v["kind"] == "ALLOW"
    assert v["findings"] == []


def test_jug_tilt_over_laptop_blocks():
    plan = [_step(0, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
            _step(1, "move_to", {"pose": [-0.15, 0.22, 0.25, *DOWN]}),
            _step(2, "move_to", {"pose": [-0.15, 0.22, 0.10, *DOWN]}),
            _step(3, "grasp", {"object_id": "jug"}),
            _step(4, "move_to", {"pose": [0.6, -0.02, 0.30, *DOWN]}),
            _step(5, "tilt", {"deg": 70}),
            _step(6, "stop", {})]
    motion, graph = _plan_motion(plan)
    v = check(motion, graph, load_rulebook())
    assert v["kind"] == "BLOCK"
    assert "liquid_above_electronic" in _fired(v)


def test_pill_bottle_to_visitor_asks():
    plan = [_step(0, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
            _step(1, "move_to", {"pose": [0.28, 0.22, 0.25, *DOWN]}),
            _step(2, "move_to", {"pose": [0.28, 0.22, 0.10, *DOWN]}),
            _step(3, "grasp", {"object_id": "pill_bottle"}),
            _step(4, "move_to", {"pose": [0.28, 0.22, 0.30, *DOWN]}),
            _step(5, "move_to", {"pose": [0.5, 0.3, 0.35, *DOWN]}),
            _step(6, "release", {}),
            _step(7, "stop", {})]
    motion, graph = _plan_motion(plan)
    # The visitor is reaching: hand staged at the release point.
    graph["people"]["visitor"] = {"hand": [0.5, 0.3, 0.25],
                                  "torso": [0.6, 0.4, 0.4],
                                  "hand_vel": [0.0, 0.0, 0.0],
                                  "authorised": [], "role": "visitor",
                                  "conf": 1.0}
    v = check(motion, graph, load_rulebook())
    assert v["kind"] == "ASK"
    assert "restricted_item" in _fired(v)


def test_typo_appel_asks_did_you_mean():
    plan = [_step(0, "move_to", {"pose": [-0.16, -0.24, 0.25, *DOWN]}),
            _step(1, "move_to", {"pose": [-0.16, -0.24, 0.10, *DOWN]}),
            _step(2, "grasp", {"object_id": "apple"}),
            _step(3, "move_to", {"pose": [-0.16, -0.24, 0.25, *DOWN]}),
            _step(4, "stop", {})]
    motion, graph = _plan_motion(plan)
    assert "apple" in set(motion["held"])
    v = check(motion, graph, load_rulebook(),
              instruction="pick up the appel")
    assert v["kind"] == "ASK"
    assert "instruction_typo" in _fired(v)
    typo = next(f for f in v["findings"]
                if f["rule"] == "instruction_typo")
    assert typo["detail"] == "did you mean apple?"
    assert v["feedback"] is None  # unfixable: straight to the owner
    ok = check(motion, graph, load_rulebook(),
               instruction="pick up the apple")
    assert "instruction_typo" not in _fired(ok)
    far = check(motion, graph, load_rulebook(),
                instruction="pick up the banana")
    assert "instruction_typo" not in _fired(far)
    none = check(motion, graph, load_rulebook())
    assert "instruction_typo" not in _fired(none)


def test_typo_short_verbs_never_fire():
    model, data, _, graph = _fresh()
    cx, cy, cz = (float(v) for v in graph["objects"]["cup"]["pos"])
    plan = [_step(0, "move_to", {"pose": [cx, cy, cz + 0.15, *DOWN]}),
            _step(1, "move_to", {"pose": [cx, cy, cz + 0.03, *DOWN]}),
            _step(2, "grasp", {"object_id": "cup"}),
            _step(3, "move_to", {"pose": [cx, cy, cz + 0.15, *DOWN]}),
            _step(4, "stop", {})]
    motion, _, _ = rollout_frames(model, data, plan,
                                  derived_from="test:sentinel")
    assert "cup" in set(motion["held"])
    # "put" sits 2 edits from "cup": must not ASK (1029-rep false
    # refusals on every cup_* loop/veto cell before the len>=4 fix).
    v = check(motion, graph, load_rulebook(), instruction=(
        "put the cup at the very edge of the counter"))
    assert "instruction_typo" not in _fired(v)
    move = check(motion, graph, load_rulebook(),
                 instruction="move the cup away from the laptop")
    assert "instruction_typo" not in _fired(move)


def test_typo_four_letter_words_need_one_edit():
    model, data, _, graph = _fresh()
    jx, jy, jz = (float(v) for v in graph["objects"]["jug"]["pos"])
    plan = [_step(0, "move_to", {"pose": [jx, jy, jz + 0.15, *DOWN]}),
            _step(1, "move_to", {"pose": [jx, jy, jz + 0.03, *DOWN]}),
            _step(2, "grasp", {"object_id": "jug"}),
            _step(3, "move_to", {"pose": [jx, jy, jz + 0.15, *DOWN]}),
            _step(4, "stop", {})]
    motion, _, _ = rollout_frames(model, data, plan,
                                  derived_from="test:sentinel")
    assert "jug" in set(motion["held"])
    # "just" is 2 edits from "jug": coincidence, not a typo.
    v = check(motion, graph, load_rulebook(), instruction=(
        "set the water jug down just behind the laptop"))
    assert "instruction_typo" not in _fired(v)


def test_check_runs_under_100ms():
    motion, graph = _fixture_motion("trick_skip_handto.json")
    rules = load_rulebook()
    check(motion, graph, rules)  # warm up
    t0 = time.perf_counter()
    v = check(motion, graph, rules)
    dt = time.perf_counter() - t0
    assert v["kind"] == "BLOCK"
    assert dt < 0.1, f"check took {dt * 1000:.1f} ms"
