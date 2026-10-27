"""L-00 hand_to: fixture plans execute headless; the person ends holding it."""

import json
from pathlib import Path

import mujoco
import numpy as np

from graph.scene_graph import load_props
from loop.handover import (STEP_DT, build_execution_script,
                           build_live_handover, step_handover)
from planner.planner import plan_from_content
from sim.world import load_scene

FIXTURE = Path(__file__).parent / "fixtures" / "llm_hand_to_apple.json"


def _home(model, data):
    hid = model.body("hand").id
    return data.xpos[hid].copy(), data.xquat[hid].copy()


def _fixture_steps():
    rec = json.loads(FIXTURE.read_text())
    props = load_props()
    steps, err = plan_from_content(rec["content"], set(props["objects"]),
                                   set(props["people"]))
    assert err is None, err
    return rec["instruction"], steps


def _run_script(model, data, script):
    """Execute a script headless; returns the taker LiveHandover (if any)."""
    lh_taken = None
    for kind, payload in script["segments"]:
        if kind == "prims":
            data.qpos[:] = payload["frames"][-1]
            mujoco.mj_forward(model, data)
        else:
            lh = payload["lh"]
            guard = 0
            while True:
                _, done = step_handover(lh, STEP_DT)
                guard += 1
                if done or guard > 5000:
                    break
            assert guard <= 5000
            if lh.transferred:
                lh_taken = lh
            else:
                break  # worker stops the script on "not taken" too
    return lh_taken


def test_fixture_handover_completes_headless():
    instruction, steps = _fixture_steps()
    assert steps[-1]["primitive"] == "hand_to"
    model, data = load_scene("kitchen")
    hp, hq = _home(model, data)
    script, err = build_execution_script(model, data, steps, hp, hq,
                                         instruction)
    assert err is None, err
    assert [k for k, _ in script["segments"]] == ["prims", "handover"]
    assert script["motion"]["held"][-1] is None
    aid = model.body("apple").id
    apple0 = data.xpos[aid].copy()
    lh = _run_script(model, data, script)
    assert lh is not None and lh.transferred
    assert lh.motion["held"][-1] is None  # release + retract baked in
    # The take point is the offer (carried there), not the plate it came from.
    assert float(np.linalg.norm(lh.aim - apple0)) > 0.3
    assert float(np.linalg.norm(lh.retreat_origin - lh.aim)) < 0.05
    # Rigid in the hand frame from the take to the end of the cycle.
    hid, aid = model.body("human_hand").id, model.body("apple").id
    R = data.xmat[hid].reshape(3, 3)
    end_offset = R.T @ (data.xpos[aid] - data.xpos[hid])
    assert np.allclose(end_offset, lh.transfer_offset[:3, 3], atol=1e-6)
    assert float(np.linalg.norm(data.xpos[aid] - data.xpos[hid])) < 0.15


def test_post_handover_segment_chains():
    instruction, steps = _fixture_steps()
    steps = list(steps) + [{
        "id": "s6", "primitive": "move_to",
        "args": {"pose": [0.3, -0.2, 0.4, 0.0, 1.0, 0.0, 0.0]},
        "serves_instruction": instruction, "why": "wave over the counter"}]
    model, data = load_scene("kitchen")
    hp, hq = _home(model, data)
    script, err = build_execution_script(model, data, steps, hp, hq,
                                         instruction)
    assert err is None, err
    assert [k for k, _ in script["segments"]] == ["prims", "handover",
                                                  "prims"]
    _run_script(model, data, script)
    grip = data.xpos[model.body("hand").id]
    assert float(np.linalg.norm(grip - np.array([0.3, -0.2, 0.4]))) < 0.01
    assert script["motion"]["held"][-1] is None


def test_hand_to_empty_gripper_rejected():
    model, data = load_scene("kitchen")
    hp, hq = _home(model, data)
    script, err = build_execution_script(
        model, data, [{"id": "h", "primitive": "hand_to",
                       "args": {"person": "owner"},
                       "serves_instruction": "x", "why": "y"}],
        hp, hq, "x")
    assert script is None and "empty gripper" in err


def test_hand_to_absent_person_rejected():
    instruction, steps = _fixture_steps()
    steps = [dict(s, args={"person": "visitor"})
             if s["primitive"] == "hand_to" else s for s in steps]
    model, data = load_scene("kitchen")
    hp, hq = _home(model, data)
    script, err = build_execution_script(model, data, steps, hp, hq,
                                         instruction)
    assert script is None and "not here" in err


def test_timeout_holds_and_reports(capsys):
    instruction, steps = _fixture_steps()
    model, data = load_scene("kitchen")
    hp, hq = _home(model, data)
    prims = [s for s in steps if s["primitive"] != "hand_to"]
    script, err = build_execution_script(model, data, prims, hp, hq,
                                         instruction)
    assert err is None, err
    data.qpos[:] = script["segments"][0][1]["frames"][-1]
    mujoco.mj_forward(model, data)
    hand_to = next(s for s in steps if s["primitive"] == "hand_to")
    lh = build_live_handover(model, data, hand_to, "apple", hp, hq,
                             instruction)
    # Simulate the no-show: the wait starts (and expires) while the hand is
    # still at park, before the reach can converge on the aim.
    lh.t_rel = 0.0
    lh.timeout = 0.0
    guard = 0
    while True:
        _, done = step_handover(lh, STEP_DT)
        guard += 1
        if done or guard > 5000:
            break
    assert not lh.transferred
    assert "not taken" in capsys.readouterr().out
    # Still held at the offer: apple travels with the gripper, not the hand.
    grip = data.xpos[model.body("hand").id]
    apple = data.xpos[model.body("apple").id]
    hand = data.xpos[model.body("human_hand").id]
    assert float(np.linalg.norm(apple - grip)) < 0.2
    assert float(np.linalg.norm(apple - hand)) > 0.1
