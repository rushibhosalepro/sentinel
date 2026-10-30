"""D-12: plain-language step rows, live status, plain rules, shadow notes."""

import json
from pathlib import Path

from dashboard.split_steps import (
    describe_plan,
    finding_plain,
    lane_b_footer,
    parent_step_id,
    plain_rule,
    rejected_line,
    script_turned_hids,
    shadow_notes,
    step_statuses,
)

FIX = Path(__file__).parent / "fixtures"
DOWN = [0.0, 1.0, 0.0, 0.0]


def _props():
    return {"objects": {
        "chef_knife": {"label": "chef's knife",
                       "properties": ["sharp"]},
        "cup": {"label": "cup", "properties": []},
        "jug": {"label": "water jug", "properties": ["liquid"]},
        "laptop": {"label": "laptop", "properties": ["electronic"]},
        "pill_bottle": {"label": "pill bottle",
                        "properties": ["medication"]},
    }, "people": {"owner": {}, "visitor": {}}}


def _positions():
    return {"chef_knife": (0.35, -0.18, 0.05),
            "cup": (0.15, 0.20, 0.08),
            "jug": (-0.15, 0.22, 0.14),
            "laptop": (0.60, -0.02, 0.21),
            "pill_bottle": (0.28, 0.22, 0.09)}


def _people():
    return {"owner": (1.29, -0.14)}


def _step(i, prim, args):
    return {"id": i, "primitive": prim, "args": args,
            "serves_instruction": "test", "why": "test"}


def _move(i, x, y, z):
    return _step(i, "move_to", {"pose": [x, y, z, *DOWN]})


def _knife_plan():
    return [
        _move("s1", 0.25, 0.05, 0.45),
        _move("s2", 0.35, -0.18, 0.25),
        _move("s3", 0.35, -0.18, 0.10),
        _step("s4", "grasp", {"object_id": "chef_knife"}),
        _move("s5", 0.35, -0.18, 0.30),
        _step("s6", "set_speed", {"speed": "slow"}),
        _step("s7", "hand_to", {"person": "owner"}),
        _step("s8", "stop", {}),
    ]


def test_describe_knife_handover():
    rows = describe_plan(_knife_plan(), _props(), _positions(),
                         _people(), turned={"s7"})
    assert [r["id"] for r in rows] == ["s1", "s2", "s3", "s4", "s5",
                                       "s6", "s7"]  # stop skipped
    assert [r["text"] for r in rows] == [
        "Move to the start pose",
        "Reach above the chef's knife",
        "Lower to the knife",
        "Grasp the knife (by the handle)",
        "Lift it to carry height",
        "Slow down for the hand-over",
        "Hand it to the owner \u2014 handle first",
    ]
    assert rows[5]["note"] == \
        "Sentinel: slowed within 30 cm of the person"
    assert rows[6]["note"] == "Sentinel: turned handle-first"
    assert rows[0]["note"] is None
    assert rows[1]["raw"]["primitive"] == "move_to"  # tooltip source
    assert "0.35" not in rows[1]["text"]  # no coordinates


def test_describe_notes_cite_rejected_round():
    rows = describe_plan(_knife_plan(), _props(), _positions(),
                         _people(), turned={"s7"},
                         rejected=[(1, "BLOCK")])
    assert rows[5]["note"] == ("Sentinel: slowed within 30 cm of the "
                               "person after round 1 BLOCK")
    assert rows[6]["note"] == ("Sentinel: turned handle-first "
                               "after round 1 BLOCK")


def test_describe_pour_and_release_and_park():
    steps = [
        _step("p0", "set_speed", {"speed": "slow"}),
        _move("p1", 0.25, 0.05, 0.45),
        _move("p2", -0.15, 0.22, 0.30),
        _move("p3", -0.15, 0.22, 0.16),
        _step("p4", "grasp", {"object_id": "jug"}),
        _move("p5", 0.15, 0.20, 0.30),
        _step("p6", "tilt", {"deg": 30}),
        _step("p7", "tilt", {"deg": 0}),
        _step("p8", "release", {}),
        _move("p9", 0.25, 0.05, 0.45),
        _step("p10", "stop", {}),
    ]
    rows = describe_plan(steps, _props(), _positions(), _people())
    assert [r["id"] for r in rows][0] == "p0"
    assert [r["text"] for r in rows] == [
        "Slow down",
        "Move to the start pose",
        "Reach above the water jug",
        "Lower to the jug",
        "Grasp the jug",
        "Carry it over the cup",
        "Tilt the jug to pour",
        "Level the jug again",
        "Let go of it",
        "Move back to the start pose",
    ]
    assert all(r["note"] is None for r in rows)  # planner's own moves


def test_describe_carry_toward_person_and_fallbacks():
    steps = [
        _move("n1", 0.25, 0.05, 0.45),
        _step("n2", "grasp", {"object_id": "cup"}),
        _move("n3", 0.55, -0.30, 0.35),
        _move("n4", 0.00, 0.00, 0.50),
        _step("n5", "set_speed", {"speed": "normal"}),
        _move("n5b", 0.25, 0.05, 0.45),
        _step("n6", "hand_to", {"person": "owner"}),
    ]
    rows = describe_plan(steps, _props(), _positions(), _people())
    assert [r["text"] for r in rows] == [
        "Move to the start pose",
        "Grasp the cup",
        "Carry it toward the owner",
        "Move the arm",
        "Resume normal speed",
        "Carry it back to the start pose",
        "Hand it to the owner",
    ]
    assert all(r["note"] is None for r in rows)  # no turn, no slow


def test_parent_step_id():
    assert parent_step_id("s7:offer") == "s7"
    assert parent_step_id("s7:release") == "s7"
    assert parent_step_id("n3") == "n3"


def test_step_status_progression():
    ids = ["s1", "s2", "s3"]
    assert step_statuses(ids, None) == {"s1": "pending", "s2": "pending",
                                        "s3": "pending"}
    # Walk the motion's sample_steps: done grows, current runs.
    assert step_statuses(ids, "s1") == {"s1": "running", "s2": "pending",
                                        "s3": "pending"}
    assert step_statuses(ids, "s2:offer") == {"s1": "done",
                                              "s2": "running",
                                              "s3": "pending"}
    assert step_statuses(ids, "s3") == {"s1": "done", "s2": "done",
                                        "s3": "running"}
    assert step_statuses(ids, "s9") == {"s1": "pending", "s2": "pending",
                                        "s3": "pending"}  # unknown: no claim


def test_plain_rule():
    props = _props()
    assert plain_rule("sharp_toward_person",
                      {"person": "owner"}) == \
        "blade pointed at the owner"
    assert plain_rule("sharp_toward_person") == \
        "blade pointed at a person"
    assert plain_rule("hazard_fast_near_person",
                      {"person": "visitor"}) == \
        "moving fast near the visitor"
    assert plain_rule("liquid_above_electronic",
                      {"electronic": "laptop"}, props) == \
        "liquid above the laptop"
    assert plain_rule("restricted_item",
                      {"person": "visitor"}) == \
        "restricted item for the visitor"
    assert plain_rule("release_near_person_in_air",
                      {"obj": "chef_knife", "person": "owner"},
                      props) == "knife released mid-air near the owner"
    assert plain_rule("scene_text_provenance") == \
        "plan followed the sticky note, not the instruction"
    assert plain_rule("unknown_object") == "target not in the scene"
    assert plain_rule("release_near_counter_edge") == \
        "released near the counter edge"
    assert plain_rule("some_future_learned_rule") == \
        "some future learned rule"  # never crashes


def test_finding_plain_prefers_detail_for_word_rules():
    assert finding_plain({"rule": "instruction_typo",
                          "detail": "did you mean apple?"}, None) == \
        "did you mean apple?"
    assert finding_plain({"rule": "sharp_toward_person",
                          "_predicates": {"person": "owner"}},
                         None) == "blade pointed at the owner"


def test_lane_b_footer():
    props = _props()
    blocked = [{"rule": "liquid_above_electronic",
                "_predicates": {"electronic": "laptop"}}]
    assert lane_b_footer("BLOCK", [], blocked, props) == \
        "Blocked: liquid above the laptop"
    asked = [{"rule": "restricted_item",
              "_predicates": {"person": "visitor"}}]
    assert lane_b_footer("ASK", [], asked, props) == \
        "Asked the owner: restricted item for the visitor"
    rows = [{"id": "s6", "text": "Slow down for the hand-over",
             "note": "Sentinel: slowed within 30 cm of the person",
             "who": "owner"},
            {"id": "s7", "text": "Hand it to the owner",
             "note": "Sentinel: turned handle-first",
             "who": "owner"}]
    assert lane_b_footer("ALLOW", rows, [], props) == \
        ("Allowed after checking: blade away from the owner, "
         "slow near the person")
    assert lane_b_footer("ALLOW", [], [], props) == \
        "Allowed after checking"


def test_rejected_line():
    entry = {"round": 1, "kind": "BLOCK",
             "findings": [{"rule": "sharp_toward_person",
                           "detail": "blade near"}],
             "why": [{"rule": "sharp_toward_person",
                      "predicates": {"person": "owner"}}]}
    assert rejected_line(entry, None) == \
        "Round 1 rejected: blade pointed at the owner"
    assert rejected_line({"round": 2, "kind": "ERROR",
                          "error": "cannot build Motion: boom"},
                         None) == "Round 2 failed: cannot build Motion: boom"
    assert rejected_line({"round": 3, "kind": "ASK"}, None) == \
        "Round 3 rejected: ask"


def test_script_turned_hids():
    from types import SimpleNamespace

    def _seg(hid, turned):
        subs = ["slow", "offer", "release"]
        if turned:
            subs.insert(1, "turn")
        lh = SimpleNamespace(
            motion={"sample_steps": [f"{hid}:{s}" for s in subs]})
        return ("handover", {"lh": lh, "hid": hid})

    script = {"segments": [_seg("s7", True), _seg("s9", False),
                           ("prims", {})]}
    assert script_turned_hids(script) == {"s7"}


def test_describe_without_sentinel_notes():
    rows = describe_plan(_knife_plan(), _props(), _positions(),
                         _people(), turned={"s7"},
                         sentinel_notes=False)
    assert rows[6]["text"] == "Hand it to the owner \u2014 handle first"
    assert all(r["note"] is None for r in rows)


def test_shadow_notes_flag_blade_first():
    from bench.naive import lower_to_primitives
    from graph.scene_graph import load_props
    from loop.handover import build_execution_script
    from sentinel.graph_view import graph_snapshot
    from sim.world import load_scene

    actions = json.loads(
        (FIX / "naive_knife_actions.json").read_text())
    model, data = load_scene("kitchen")
    props = load_props()
    steps = lower_to_primitives(actions, model, data, props)
    hid = model.body("hand").id
    script, err = build_execution_script(
        model, data, steps, data.xpos[hid].copy(),
        data.xquat[hid].copy(), "give me the knife", sentinel=False)
    assert err is None
    notes = shadow_notes(script["motion"],
                         graph_snapshot(model, data, props),
                         props, "give me the knife")
    assert notes, "blade-first naive plan must cast a shadow"
    assert all(v.startswith("\u26a0 ") for v in notes.values())
    assert "\u26a0 blade pointed at the owner" in set(notes.values())
    top = {s["id"] for s in steps}
    assert set(notes) <= top  # mapped to top-level step ids


def test_shadow_notes_quiet_on_safe_pour():
    pour = json.loads((FIX / "replay" / "safe_pour.json").read_text())
    assert shadow_notes(pour["motion"], pour["graph"], _props(),
                        "pour water into the cup") == {}
