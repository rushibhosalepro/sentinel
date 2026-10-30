"""D-09: judge chips replay their recorded lane-B plans (no network)."""

import json
from pathlib import Path

from dashboard.split import PRESETS
from graph.scene_graph import load_props
from loop.handover import build_execution_script
from perception.reader import ATTACK_LINES
from sentinel.check import check, load_rulebook
from sentinel.graph_view import graph_snapshot
from sim.world import load_scene

FIX = Path(__file__).parent / "fixtures"

SCENE_PRESET = {"knife": None, "water": "cup_next_to_laptop",
                "sticky": None}


def _replay(example):
    from loop.live import _apply_preset

    kinds = []
    for rnd in example["rounds"]:
        model, data = load_scene("kitchen")
        props = load_props()
        scene = SCENE_PRESET[example["preset"]]
        if scene is not None:
            _apply_preset(model, data, {"qpos": data.qpos.copy()}, scene)
        graph = graph_snapshot(model, data, props)
        hid = model.body("hand").id
        hp, hq = data.xpos[hid].copy(), data.xquat[hid].copy()
        script, err = build_execution_script(
            model, data, rnd["steps"], hp, hq, example["prompt"])
        assert err is None, (example["id"], err)
        motion = script["motion"]
        if example["attack"] == "scene-text":
            from loop.quarantine import scan_steps

            q = {"sticky_note": [" ".join(ATTACK_LINES)]}
            hit = scan_steps(rnd["steps"], q, example["prompt"], props,
                             set(props["people"]))
            if hit is not None:
                motion["derived_from"] = f"scene_text:{sorted(q)[0]}"
        v = check(motion, graph, load_rulebook(),
                  instruction=example["prompt"])
        kinds.append(v["kind"])
    return kinds


def test_recorded_chip_plans_replay_expected_verdicts():
    doc = json.loads((FIX / "examples.json").read_text())
    assert len(doc["examples"]) == 15
    for ex in doc["examples"]:
        assert ex["preset"] in PRESETS, ex["id"]
        assert ex["prompt"], ex["id"]
        kinds = _replay(ex)
        # Each recorded plan replays its recorded verdict (only the
        # final plan is emitted, so multi-round chains pin the final).
        assert kinds == [r["verdict"] for r in ex["rounds"]], \
            (ex["id"], kinds)
        assert kinds[-1] == ex["expected_b"], (ex["id"], kinds)
