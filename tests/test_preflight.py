"""C-06: preflight replays real plans on a sim copy (no network)."""

import mujoco
import numpy as np

from sentinel.graph_view import graph_snapshot
from sentinel.preflight import preflight
from sim.world import load_scene

DOWN = [0.0, 1.0, 0.0, 0.0]


def _step(i, prim, args, serves="test"):
    return {"id": f"s{i}", "primitive": prim, "args": args,
            "serves_instruction": serves, "why": "test"}


def _scene():
    from graph.scene_graph import load_props
    model, data = load_scene("kitchen")
    return model, data, load_props()


def _graph(model, data, props, hand=(1.45, -0.35, 0.3)):
    g = graph_snapshot(model, data, props)
    g["people"]["owner"]["hand"] = list(hand)
    return g


def _pick_place(obj, at, to, rel_z, tag="s6"):
    return [_step(1, "move_to", {"pose": [at[0], at[1], 0.25, *DOWN]}),
            _step(2, "move_to", {"pose": [at[0], at[1], 0.10, *DOWN]}),
            _step(3, "grasp", {"object_id": obj}),
            _step(4, "move_to", {"pose": [at[0], at[1], 0.30, *DOWN]}),
            _step(5, "move_to", {"pose": [to[0], to[1], 0.40, *DOWN]}),
            {"id": tag, "primitive": "move_to",
             "args": {"pose": [to[0], to[1], rel_z, *DOWN]},
             "serves_instruction": "test", "why": "test"},
            _step(7, "release", {}),
            _step(8, "stop", {})]


def test_drop_knife_blocks():
    model, data, props = _scene()
    plan = _pick_place("chef_knife", (0.35, -0.18), (0.5, 0.0), 0.40)
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out["kind"] == "BLOCK"
    assert out["findings"][0]["rule"] == "preflight_drop"
    assert "will fall" in out["findings"][0]["detail"]


def test_drop_apple_asks():
    model, data, props = _scene()
    plan = _pick_place("apple", (-0.16, -0.24), (0.3, 0.0), 0.40)
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out["kind"] == "ASK"
    assert "will fall" in out["findings"][0]["detail"]


def test_low_placement_is_quiet():
    model, data, props = _scene()
    plan = _pick_place("apple", (-0.16, -0.24), (-0.16, -0.24), 0.12)
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out == {"kind": "ALLOW", "findings": []}


def test_spill_over_laptop_blocks():
    model, data, props = _scene()
    plan = [_step(0, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
            _step(1, "move_to",
                  {"pose": [-0.15, 0.22, 0.25, *DOWN]}),
            _step(2, "move_to",
                  {"pose": [-0.15, 0.22, 0.10, *DOWN]}),
            _step(3, "grasp", {"object_id": "jug"}),
            _step(4, "move_to", {"pose": [0.6, -0.02, 0.30, *DOWN]}),
            _step(5, "tilt", {"deg": 70}),
            _step(6, "stop", {})]
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out["kind"] == "BLOCK"
    assert out["findings"][0]["rule"] == "preflight_spill"


def test_pour_over_cup_is_quiet():
    model, data, props = _scene()
    plan = [_step(0, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
            _step(1, "move_to",
                  {"pose": [-0.15, 0.22, 0.25, *DOWN]}),
            _step(2, "move_to",
                  {"pose": [-0.15, 0.22, 0.10, *DOWN]}),
            _step(3, "grasp", {"object_id": "jug"}),
            _step(4, "move_to", {"pose": [0.15, 0.2, 0.30, *DOWN]}),
            _step(5, "tilt", {"deg": 70}),
            _step(6, "tilt", {"deg": 0}),
            _step(7, "move_to",
                  {"pose": [-0.15, 0.22, 0.30, *DOWN]}),
            _step(8, "move_to",
                  {"pose": [-0.15, 0.22, 0.10, *DOWN]}),
            _step(9, "release", {}),
            _step(10, "stop", {})]
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out == {"kind": "ALLOW", "findings": []}


def test_fragile_edge_asks():
    model, data, props = _scene()
    # Stage the glass reachable (it starts outside the arm ring).
    from sim.primitives import free_qposadr
    adr = free_qposadr(model, "wine_glass")
    data.qpos[adr:adr + 3] = [0.3, 0.2, 0.0]
    mujoco.mj_forward(model, data)
    plan = _pick_place("wine_glass", (0.3, 0.2), (0.3, 0.33), 0.12)
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out["kind"] == "ASK"
    assert out["findings"][0]["rule"] == "preflight_edge"
    assert "2 cm" in out["findings"][0]["detail"]


def test_arm_contact_blocks():
    model, data, props = _scene()
    g = _graph(model, data, props, hand=(0.4, 0.0, 0.4))
    plan = [_step(1, "move_to", {"pose": [0.4, 0.0, 0.35, *DOWN]}),
            _step(2, "stop", {})]
    out = preflight(plan, model, data, g)
    assert out["kind"] == "BLOCK"
    assert out["findings"][0]["rule"] == "preflight_contact"


def test_wave_is_quiet():
    model, data, props = _scene()
    plan = [_step(1, "move_to", {"pose": [0.3, 0.0, 0.45, *DOWN]}),
            _step(2, "stop", {})]
    out = preflight(plan, model, data, _graph(model, data, props))
    assert out == {"kind": "ALLOW", "findings": []}
