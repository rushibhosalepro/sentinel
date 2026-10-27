"""S-05: scripted hand paths drive the mocap body on schedule."""

import mujoco
import numpy as np

from sim.human import HANDOVER_HOVER, reach_to_counter, retreat_to_park
from sim.world import load_scene


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
    assert np.allclose(data.mocap_quat[mid], (1, 0, 0, 0))


def test_retreat_returns_to_park():
    model, data = load_scene("kitchen")
    park = _hand_pos(model, data)
    reach_to_counter(model, data, t=5.0, start_t=0.0, duration=2.0)
    assert not np.allclose(_hand_pos(model, data), park)
    retreat_to_park(model, data, t=9.0, start_t=7.0, duration=2.0)
    assert np.allclose(_hand_pos(model, data), park, atol=1e-6)
