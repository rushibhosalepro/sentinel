"""C-02: relations predicates on synthetic motions (no sim except pins)."""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from sentinel.relations import (
    KNIFE_HANDLE_LOCAL,
    KNIFE_TIP_LOCAL,
    carried_point,
    conf_of,
    grasp_offset,
    held_ids,
    knife_geometry,
    measure_blade,
    measure_held,
    measure_held_electronic,
    nearest_person_part,
    person_at,
    recipient_authorised,
    release_events,
    release_into_hand,
)

DOWN = [0.0, 1.0, 0.0, 0.0]
TURNED = (Rotation.from_euler("z", 180, degrees=True)
          * Rotation.from_quat([1.0, 0.0, 0.0, 0.0])).as_quat()[[3, 0, 1, 2]]


def _motion(grips, held, steps=None, t=None):
    n = len(grips)
    return {
        "body": "arm",
        "path": [np.array([*g[:3], *g[3]], dtype=float) for g in grips],
        "t": list(t) if t else [round(i * 0.5, 2) for i in range(n)],
        "held": list(held), "tilt": [0.0] * n,
        "speed": ["normal"] * n,
        "sample_steps": list(steps) if steps else [f"s{i}" for i in range(n)],
        "end_state": [], "derived_from": "test", "step_ids": ["s0"],
    }


def _graph(knife_pos=(0.35, -0.18, 0.05), hand=(1.0, 0.0, 0.5)):
    return {
        "objects": {
            "chef_knife": {"pos": list(knife_pos), "quat": list(DOWN),
                           "properties": ["sharp"], "owner": "owner",
                           "conf": 1.0},
            "apple": {"pos": [-0.16, -0.24, 0.04], "quat": list(DOWN),
                      "properties": ["food"], "owner": "owner", "conf": 1.0},
            "laptop": {"pos": [0.6, -0.02, 0.0], "quat": list(DOWN),
                       "properties": ["electronic"], "owner": "owner",
                       "conf": 1.0},
        },
        "people": {
            "owner": {"hand": list(hand), "torso": [1.1, 0.0, 0.4],
                      "hand_vel": [0.0, 0.0, 0.0],
                      "authorised": ["all"], "role": "owner"},
        },
    }


def test_quat_math_matches_scipy():
    from sentinel.relations import _quat_to_mat
    rng = np.random.default_rng(0)
    for _ in range(5):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        wxyz = [q[3], q[0], q[1], q[2]]
        assert np.allclose(_quat_to_mat(wxyz),
                           Rotation.from_quat(q).as_matrix(), atol=1e-9)


def test_knife_keypoints_pinned_to_model():
    from sim.world import load_scene
    model, data = load_scene("kitchen")
    kid = model.body("chef_knife").id
    Rb = data.xmat[kid].reshape(3, 3)
    pb = data.xpos[kid]
    bid = model.geom("chef_knife_blade").id
    tip_w = data.geom_xpos[bid] + Rb @ np.array(
        [model.geom_size[bid][0], 0, 0])
    hid = model.geom("chef_knife_handle").id
    assert np.allclose(Rb.T @ (tip_w - pb), KNIFE_TIP_LOCAL, atol=1e-6)
    assert np.allclose(Rb.T @ (data.geom_xpos[hid] - pb),
                       KNIFE_HANDLE_LOCAL, atol=1e-6)


def test_carry_follows_gripper_translation():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, DOWN]]
    m = _motion(grips, ["chef_knife", "chef_knife"])
    g = _graph()
    off = grasp_offset(m, g, "chef_knife")
    # Offset in the gripper frame (down = Rx180, so +z there is world -z).
    assert np.allclose(off[:3, 3], [0, 0, 0.05], atol=1e-9)
    pt = carried_point(m, g, "chef_knife", 1)
    assert np.allclose(pt, [0.5, -0.18, 0.25], atol=1e-9)
    assert carried_point(m, g, "apple", 1) is None


def test_carry_rotates_tip_with_gripper():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, DOWN],
             [0.5, -0.18, 0.30, TURNED]]
    held = ["chef_knife"] * 3
    m = _motion(grips, held)
    g = _graph()
    tip_down = knife_geometry(m, g, 1)["tip"]
    assert tip_down[0] == pytest.approx(0.5 + 0.175, abs=1e-6)
    tip_turned = knife_geometry(m, g, 2)["tip"]
    assert tip_turned[0] == pytest.approx(0.5 - 0.175, abs=1e-6)
    assert knife_geometry(_motion(grips, ["apple"] * 3), g, 1) is None


def test_blade_toward_discriminator():
    grips = [[0.35, -0.18, 0.10, DOWN], [0.5, -0.18, 0.30, DOWN]]
    m = _motion(grips, ["chef_knife", "chef_knife"])
    near_tip = _graph(hand=(0.70, -0.18, 0.25))
    r = measure_blade(m, near_tip, 1)
    assert r["toward"] is True
    assert r["tip_cm"] == pytest.approx(2.5, abs=0.5)
    assert r["handle_cm"] > 20.0
    assert (r["person"], r["part"]) == ("owner", "hand")
    near_handle = _graph(hand=(0.40, -0.18, 0.25))
    r2 = measure_blade(m, near_handle, 1)
    assert r2["toward"] is False


def test_person_velocity_extrapolation_capped():
    g = _graph()
    g["people"]["owner"]["hand_vel"] = [-0.2, 0.0, 0.0]
    assert np.allclose(person_at(g, "owner", 1.0)["hand"],
                       [0.8, 0.0, 0.5])
    assert np.allclose(person_at(g, "owner", 10.0)["hand"],
                       [0.4, 0.0, 0.5])  # capped at PREDICT_CAP_S
    assert np.allclose(person_at(g, "owner", 0.0)["torso"],
                       [1.1, 0.0, 0.4])


def test_release_events_and_into_hand():
    grips = [[0.0, 0.0, 0.3, DOWN]] * 4
    held = [None, "apple", "apple", None]
    m = _motion(grips, held, steps=["s1", "s2", "s3", "s4"],
                t=[0.0, 0.5, 1.0, 1.5])
    g = _graph()
    evs = release_events(m, g)
    assert len(evs) == 1
    assert (evs[0]["step_id"], evs[0]["obj"]) == ("s4", "apple")
    assert np.allclose(evs[0]["pos"], [-0.16, -0.24, 0.04], atol=1e-6)
    into, _ = release_into_hand(evs[0], g)
    assert into is False  # hand a metre away
    mt = _motion(grips, held, steps=["s1", "s2", "s3", "s6:release"],
                 t=[0.0, 0.5, 1.0, 1.5])
    evt = release_events(mt, g)[0]
    into, who = release_into_hand(evt, g)
    assert (into, who) == (True, "owner")  # hand_to construction guarantee
    near = _graph(hand=(-0.12, -0.20, 0.04))
    into, who = release_into_hand(evs[0], near)
    assert (into, who) == (True, "owner")  # live hand within 10 cm


def test_nearest_person_part_and_held_gaps():
    g = _graph(hand=(0.0, 0.0, 0.5))
    pid, part, d = nearest_person_part(np.array([0.0, 0.0, 0.44]), g, 0.0)
    assert (pid, part) == ("owner", "hand") and d == pytest.approx(0.06)
    g2 = _graph(hand=(-0.16, -0.24, 0.5))
    grips = [[0.0, 0.0, 0.3, DOWN]]
    m = _motion(grips, ["apple"])
    r = measure_held(m, g2, 0)
    assert r["gap_cm"] == pytest.approx(46.0, abs=0.5)
    assert measure_held(_motion(grips, [None]), g2, 0) is None
    e = measure_held_electronic(m, g2, 0)
    assert e["electronic"] == "laptop" and e["gap_cm"] > 50.0


def test_ids_conf_and_authorisation():
    m = _motion([[0, 0, 0.3, DOWN]] * 3, ["apple", None, "chef_knife"])
    assert held_ids(m) == ["apple", "chef_knife"]
    g = _graph()
    assert conf_of(g, "apple") == 1.0
    assert conf_of(g, "nope") is None
    assert recipient_authorised(g, "owner") is True
    g["people"]["visitor"] = {"hand": [0, 0, 0.5], "torso": [0, 0, 0.4],
                              "hand_vel": [0, 0, 0],
                              "authorised": [], "role": "visitor"}
    assert recipient_authorised(g, "visitor") is False
