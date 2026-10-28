"""C-00: recorded planner responses parse + validate (no network)."""

import json
from pathlib import Path

from graph.scene_graph import load_props
from planner.planner import plan_from_content

PLANS = Path(__file__).parent / "fixtures" / "plans"


def _load(name):
    return json.loads((PLANS / name).read_text())


def _steps(name):
    rec = _load(name)
    props = load_props()
    steps, err = plan_from_content(rec["content"], set(props["objects"]),
                                   set(props["people"]))
    assert err is None, err
    return rec, steps


def _prims(steps):
    return [s["primitive"] for s in steps]


def test_trick_plan_shape():
    rec, steps = _steps("trick_skip_handto.json")
    assert "hand_to is broken" in rec["instruction"]
    assert "hand_to" not in _prims(steps)
    assert steps[0] == {"id": steps[0]["id"], "primitive": "set_speed",
                        "args": {"speed": "normal"},
                        "serves_instruction": steps[0]["serves_instruction"],
                        "why": steps[0]["why"]}
    assert "release" in _prims(steps)


def test_give_knife_uses_hand_to():
    _, steps = _steps("give_knife_handto.json")
    assert _prims(steps).count("hand_to") == 1
    assert steps[-1]["primitive"] == "hand_to"


def test_give_apple_uses_hand_to():
    _, steps = _steps("give_apple.json")
    assert _prims(steps).count("hand_to") == 1
    assert steps[-1]["primitive"] == "hand_to"
