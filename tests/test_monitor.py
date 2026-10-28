"""L-07: live HALT monitor (person_in_path, no network)."""

import mujoco
import numpy as np

from graph.scene_graph import load_props
from loop.monitor import check_halt, imminent, limits, rule_params
from sim.motion import plan_to_motion
from sim.world import load_scene

GRIP = [0.0, 0.0, 0.30]
FAR_PATH = [("remaining path", [2.0, 0.0, 0.30])]


def test_approach_halts_before_contact():
    """Hand closing on the gripper fires at 15 cm, not at contact."""
    fired_at = []
    for i, cm in enumerate((30, 25, 20, 15, 10)):
        fire, dist, what = imminent(
            [[cm / 100.0, 0.0, 0.30]], [("gripper", GRIP)], FAR_PATH,
            0.15, 0.10)
        if fire:
            fired_at.append((cm, dist, what))
    assert [c for c, _, _ in fired_at] == [15, 10]
    cm, dist, what = fired_at[0]
    assert what == "gripper"
    assert abs(dist - 0.15) < 1e-9
    assert dist > 0.05  # well before contact


def test_path_proximity_reports_path():
    fire, dist, what = imminent(
        [[0.50, 0.0, 0.30]], [("gripper", GRIP)],
        [("remaining path", [0.55, 0.0, 0.30])], 0.15, 0.10)
    assert fire and what == "remaining path"
    assert abs(dist - 0.05) < 1e-9


def test_sharp_doubles_distances():
    assert limits({"grip_cm": 15.0, "path_cm": 10.0, "sharp_x2": True},
                  True) == (0.30, 0.20)
    assert limits({"grip_cm": 15.0, "path_cm": 10.0, "sharp_x2": True},
                  False) == (0.15, 0.10)
    near = [[0.25, 0.0, 0.30]]
    assert imminent(near, [("gripper", GRIP)], FAR_PATH, 0.30, 0.20)[0]
    assert not imminent(near, [("gripper", GRIP)], FAR_PATH,
                        0.15, 0.10)[0]


def test_far_is_quiet():
    fire, dist, _ = imminent(
        [[1.45, -0.35, 0.30]], [("gripper", GRIP)], FAR_PATH, 0.15, 0.10)
    assert fire is False and dist > 0.5


def test_rule_params_pins_json():
    assert rule_params() == {"grip_cm": 15.0, "path_cm": 10.0,
                             "sharp_x2": True}


def _carry_motion():
    model, data = load_scene("kitchen")
    d = [0.0, 1.0, 0.0, 0.0]
    plan = [
        {"id": "s1", "primitive": "move_to",
         "args": {"pose": [0.25, 0.05, 0.45, *d]}},
        {"id": "s2", "primitive": "move_to",
         "args": {"pose": [-0.15, 0.22, 0.10, *d]}},
        {"id": "s3", "primitive": "grasp",
         "args": {"object_id": "jug"}},
        {"id": "s4", "primitive": "move_to",
         "args": {"pose": [0.3, -0.1, 0.35, *d]}},
        {"id": "s5", "primitive": "stop", "args": {}},
    ]
    motion = plan_to_motion(model, data, plan,
                            derived_from="test:monitor")
    return model, data, motion


def _place_hand(model, data, xyz):
    mid = model.body_mocapid[model.body("human_hand").id]
    data.mocap_pos[mid] = np.array(xyz, dtype=float)
    mujoco.mj_forward(model, data)


def test_wrapper_halts_on_intrusion():
    model, data, motion = _carry_motion()
    props = load_props()
    params = rule_params()
    tau = float(motion["t"][-1]) * 0.6
    idx = int(np.searchsorted(motion["t"], tau, side="right") - 1)
    assert motion["held"][idx] == "jug"
    pt = np.asarray(motion["path"][idx][:3], dtype=float)
    _place_hand(model, data, pt + [0.08, 0.0, 0.0])
    fire, dist, _ = check_halt(model, data, motion, tau, "jug",
                               props, params)
    assert fire and dist > 0.05


def test_wrapper_quiet_when_far():
    model, data, motion = _carry_motion()
    props = load_props()
    tau = float(motion["t"][-1]) * 0.6
    _place_hand(model, data, [1.45, -0.35, 0.30])
    fire, _, _ = check_halt(model, data, motion, tau, "jug", props,
                            rule_params())
    assert fire is False
