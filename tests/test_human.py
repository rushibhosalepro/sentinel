"""S-05: scripted hand paths drive the mocap person on schedule."""

import mujoco
import numpy as np

from sim.human import (FORE_LEN, HANDOVER_HOVER, UPPER_LEN, reach_to_counter,
                       retreat_to_park)
from sim.world import load_scene, render


def _hand_pos(model, data):
    return data.xpos[model.body("human_hand").id].copy()


def test_parked_before_start():
    model, data = load_scene("kitchen")
    park = _hand_pos(model, data)
    assert park.tolist() == [1.45, -0.35, 0.3]
    reach_to_counter(model, data, t=1.0, start_t=2.0)
    assert np.allclose(_hand_pos(model, data), park)


def test_reach_and_hold():
    model, data = load_scene("kitchen")
    mid = model.body_mocapid[model.body("human_hand").id]
    assert mid >= 0  # driven body really is a mocap body
    reach_to_counter(model, data, t=0.0, start_t=2.0, duration=2.0)
    p0 = _hand_pos(model, data)
    reach_to_counter(model, data, t=3.0, start_t=2.0, duration=2.0)
    p1 = _hand_pos(model, data)
    reach_to_counter(model, data, t=4.0, start_t=2.0, duration=2.0)
    p2 = _hand_pos(model, data)
    reach_to_counter(model, data, t=9.0, start_t=2.0, duration=2.0)
    p3 = _hand_pos(model, data)
    target = np.array(HANDOVER_HOVER)
    assert np.allclose(p2, target, atol=1e-6)
    assert np.allclose(p3, target, atol=1e-6)  # holds after arrival
    d0 = np.linalg.norm(p0 - target)
    d1 = np.linalg.norm(p1 - target)
    assert d1 < 0.6 * d0  # mid-reach is well past halfway in distance
    # Hand yawed onto the forearm: fingers (+y) along elbow -> wrist,
    # palm (-z) down.
    mat = data.xmat[model.body("human_hand").id].reshape(3, 3)
    along = _hand_pos(model, data) \
        - data.xpos[model.body("human_forearm").id]
    along = along / np.linalg.norm(along)
    assert np.allclose(mat[:, 1], along, atol=1e-6)
    assert mat[2, 2] > 0.9


def test_retreat_returns_to_park():
    model, data = load_scene("kitchen")
    park = _hand_pos(model, data)
    reach_to_counter(model, data, t=5.0, start_t=0.0, duration=2.0)
    assert not np.allclose(_hand_pos(model, data), park)
    retreat_to_park(model, data, t=9.0, start_t=7.0, duration=2.0)
    assert np.allclose(_hand_pos(model, data), park, atol=1e-6)


def _arm_lengths(model, data):
    s = data.xpos[model.body("human_upper_arm").id]
    e = data.xpos[model.body("human_forearm").id]
    w = data.xpos[model.body("human_hand").id]
    return float(np.linalg.norm(e - s)), float(np.linalg.norm(w - e))


def test_arm_segments_hold_exact_lengths():
    model, data = load_scene("kitchen")
    for t in (0.0, 2.5, 3.0, 4.0, 9.0):
        reach_to_counter(model, data, t=t, start_t=2.0, duration=2.0)
        l1, l2 = _arm_lengths(model, data)
        assert abs(l1 - UPPER_LEN) < 1e-6, (t, l1)
        assert abs(l2 - FORE_LEN) < 1e-6, (t, l2)
    assert np.isfinite(data.mocap_pos).all()
    assert np.isfinite(data.mocap_quat).all()


def test_torso_leans_into_reach():
    model, data = load_scene("kitchen")
    head = model.geom("person_head").id
    torso_mid = model.body_mocapid[model.body("human_torso").id]
    assert torso_mid >= 0
    reach_to_counter(model, data, t=0.0, start_t=2.0, duration=2.0)
    assert np.allclose(data.mocap_quat[torso_mid], (1, 0, 0, 0))
    x0 = data.geom_xpos[head][0]
    reach_to_counter(model, data, t=9.0, start_t=2.0, duration=2.0)
    assert data.geom_xpos[head][0] < x0 - 0.15  # leans toward the counter


def test_demo_camera_frames_person_and_counter():
    model, data = load_scene("kitchen")
    reach_to_counter(model, data, t=9.0, start_t=2.0, duration=2.0)
    seg = render(model, data, camera="demo")["seg"][:, :, 0]
    seen = set(np.unique(seg)) - {-1}
    for geom in ("person_head", "person_foot_L", "person_foot_R",
                 "counter_top", "chef_knife_blade", "hand_palm"):
        assert model.geom(geom).id in seen, geom
