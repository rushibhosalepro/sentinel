"""L-00: a recorded planner reply parses, validates, and builds a Motion."""

import json
from pathlib import Path

import pytest

from graph.scene_graph import load_props
from planner.planner import plan_from_content, scene_facts
from sim.motion import plan_to_motion
from sim.world import load_scene

FIXTURE = Path(__file__).parent / "fixtures" / "llm_knife_handover.json"


def _ids():
    return set(load_props()["objects"])


def test_recorded_plan_builds_motion():
    rec = json.loads(FIXTURE.read_text())
    assert rec["instruction"] == "give me the knife"
    steps, err = plan_from_content(rec["content"], _ids())
    assert err is None, err
    assert [s["id"] for s in steps][:3] == ["s1", "s2", "s3"]
    assert {s["primitive"] for s in steps} <= {
        "move_to", "grasp", "release", "tilt", "set_speed", "stop"}
    model, data = load_scene("kitchen")
    motion = plan_to_motion(model, data, steps,
                            derived_from="test:llm_fixture")
    assert len(motion["path"]) > 10
    assert motion["held"][-1] == "chef_knife"
    assert motion["step_ids"] == [s["id"] for s in steps]


def _plan(*steps):
    return json.dumps({"steps": list(steps)})


def _step(sid, prim, args=None, **kw):
    d = {"id": sid, "primitive": prim, "args": args or {},
         "serves_instruction": "do it", "why": "because"}
    d.update(kw)
    return d


DOWN = [0.0, 1.0, 0.0, 0.0]


@pytest.mark.parametrize("content,match", [
    ("not json", "not valid JSON"),
    ("[1, 2]", "no 'steps' list"),
    (_plan(), "non-empty list"),
    (_plan(_step("a", "fly")), "unknown primitive 'fly'"),
    (_plan(_step("a", "grasp", {"object_id": "toaster"})),
     "unknown object 'toaster'"),
    (_plan(_step("a", "move_to", {"pose": [0.3, 0.0, 0.2]})),
     "pose must have 7"),
    (_plan(_step("a", "move_to", {"pose": [0.3, 0, 0.2, 0, 0, 0, 0]})),
     "quat is zero"),
    (_plan(_step("a", "set_speed", {"speed": "fast"})),
     "speed must be one of"),
    (_plan(_step("a", "tilt", {"deg": "a lot"})),
     "tilt deg must be a number"),
    (_plan(_step("a", "stop", {}, why="")), "missing 'why'"),
    (_plan(_step("a", "stop"), _step("a", "stop")), "duplicate step id"),
])
def test_invalid_plans_rejected(content, match):
    steps, err = plan_from_content(content, {"cup"})
    assert steps is None
    assert match in err


def test_hand_to_validates_person():
    ok, err = plan_from_content(
        _plan(_step("h", "hand_to", {"person": "owner"})),
        {"cup"}, {"owner", "visitor"})
    assert err is None and ok[0]["primitive"] == "hand_to"
    bad, err = plan_from_content(
        _plan(_step("h", "hand_to", {"person": "stranger"})),
        {"cup"}, {"owner", "visitor"})
    assert bad is None and "unknown person 'stranger'" in err


def test_scene_facts_include_people():
    model, data = load_scene("kitchen")
    facts = scene_facts(model, data, load_props(), reaching=True)
    by_id = {p["id"]: p for p in facts["people"]}
    assert set(by_id) == {"owner", "visitor"}
    owner = by_id["owner"]
    assert owner["present"] is True and owner["reaching"] is True
    assert len(owner["hand_pos"]) == 3 and len(owner["torso_pos"]) == 3
    assert by_id["visitor"]["present"] is False
