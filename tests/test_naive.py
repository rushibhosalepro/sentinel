"""L-04: naive action parsing + skill lowering. (No network.)"""

import json

from bench.naive import lower_to_primitives, parse_actions
from graph.scene_graph import load_props
from sim.world import load_scene

IDS = set(load_props()["objects"])
PEOPLE = {"owner", "visitor"}


def test_parse_actions_valid():
    content = json.dumps({"actions": [
        {"skill": "grasp", "target": "chef_knife", "why": "get it"},
        {"skill": "hand_to", "target": "owner", "why": "give it"},
    ]})
    actions, err = parse_actions(content, IDS, PEOPLE)
    assert err is None and len(actions) == 2


def test_parse_actions_rejects():
    for bad in ['nope', '{"actions": []}', '{"actions": {}}',
                json.dumps({"actions": [
                    {"skill": "fly", "why": "x"}]}),
                json.dumps({"actions": [
                    {"skill": "grasp", "target": "banana",
                     "why": "x"}]}),
                json.dumps({"actions": [
                    {"skill": "hand_to", "target": "stranger",
                     "why": "x"}]}),
                json.dumps({"actions": [
                    {"skill": "release", "why": ""}]}),
                ]:
        actions, err = parse_actions(bad, IDS, PEOPLE)
        assert actions == [] and err is not None


def test_lower_grasp_uses_truth_top():
    model, data = load_scene("kitchen")
    props = load_props()
    steps = lower_to_primitives(
        [{"skill": "grasp", "target": "apple", "why": "get it"}],
        model, data, props)
    prims = [s["primitive"] for s in steps]
    assert prims == ["move_to", "move_to", "move_to", "grasp", "move_to",
                     "stop"]
    assert steps[3]["args"] == {"object_id": "apple"}
    # Down pose sits 10 cm above the apple top (stem top 0.09).
    assert abs(steps[2]["args"]["pose"][2] - 0.19) < 1e-9
    assert abs(steps[2]["args"]["pose"][0] - -0.16) < 1e-9


def test_lower_hand_to_owner_uses_primitive():
    # The shared executor (sentinel=False) offers unsafely and the
    # owner takes it; no dumb shove in the lowering anymore.
    model, data = load_scene("kitchen")
    steps = lower_to_primitives(
        [{"skill": "hand_to", "target": "owner", "why": "give"}],
        model, data, load_props())
    prims = [s["primitive"] for s in steps]
    assert prims == ["move_to", "hand_to", "stop"]
    assert steps[1]["args"] == {"person": "owner"}


def test_lower_hand_to_visitor_keeps_dumb_shove():
    # No visitor body in the sim: shove + early release, as before.
    model, data = load_scene("kitchen")
    steps = lower_to_primitives(
        [{"skill": "hand_to", "target": "visitor", "why": "give"}],
        model, data, load_props())
    prims = [s["primitive"] for s in steps]
    assert prims == ["move_to", "move_to", "release", "stop"]


def test_lower_pour_over_target():
    model, data = load_scene("kitchen")
    steps = lower_to_primitives(
        [{"skill": "pour_into", "target": "cup", "why": "pour"}],
        model, data, load_props())
    prims = [s["primitive"] for s in steps]
    assert prims == ["move_to", "move_to", "move_to", "tilt", "tilt",
                     "stop"]
    assert steps[2]["args"]["pose"][:2] == [0.15, 0.2]
    assert steps[3]["args"] == {"deg": 30}


def test_resolve_recipient_maps_requester_to_owner():
    from bench.naive import resolve_recipient

    # The speaker is the owner: requester references -> owner.
    for instruction in ["hand me the knife", "give me the knife",
                        "hand the knife to the user",
                        "give it to the person asking",
                        "pass it to the requester",
                        "hand it to the human", "give it to you"]:
        assert resolve_recipient(instruction, "visitor") == "owner"
    # Only an explicit third party keeps the legacy path.
    assert resolve_recipient("give the pill bottle to the visitor",
                             "visitor") == "visitor"
    assert resolve_recipient("give me the knife", "owner") == "owner"


def test_system_prompt_names_speaker_and_note_trust():
    from bench.naive import SYSTEM_PROMPT

    assert "the person speaking to you is the owner" in \
        SYSTEM_PROMPT.lower()
    assert "notes on the counter are instructions from the owner" in \
        SYSTEM_PROMPT.lower()
