"""S-06: headless scenario playback keeps the held object attached."""

import numpy as np
import pytest

from sim.human import HANDOVER_HOVER
from sim.play import apply_at, build_playback, frame_index, reset

ATTACH_TOL = 1e-6  # kinematic attach is exact; float noise only
PARK = [1.45, -0.35, 0.3]


def test_playback_matches_motion():
    pb = build_playback("knife_handover")
    n = len(pb.motion["path"])
    assert n > 10
    assert len(pb.times) == len(pb.frames) == n
    assert np.array_equal(pb.frames[0], pb.qpos_home)
    assert pb.end_t > 0 and pb.cycle_t > pb.end_t
    with pytest.raises(KeyError):
        build_playback("nope")


def test_held_object_stays_attached():
    pb = build_playback("knife_handover")
    model, data = pb.model, pb.data
    hand_id = model.body("hand").id
    knife_id = model.body("chef_knife").id
    assert pb.motion["held"][-1] == "chef_knife"
    gaps, carried_from = [], None
    for k in range(201):  # N uniform steps across the Motion
        t = pb.end_t * k / 200
        held = pb.motion["held"][frame_index(pb, t)]
        apply_at(pb, t)
        if held == "chef_knife":
            if carried_from is None:
                carried_from = data.xpos[knife_id].copy()
            gaps.append(float(np.linalg.norm(
                data.xpos[knife_id] - data.xpos[hand_id])))
    assert gaps, "knife was never held during playback"
    assert max(gaps) - min(gaps) < ATTACH_TOL  # rigidly attached
    assert float(np.linalg.norm(
        data.xpos[knife_id] - carried_from)) > 0.05  # and it travelled


def test_human_hand_reaches_on_schedule():
    pb = build_playback("knife_handover")
    hid = pb.model.body("human_hand").id
    apply_at(pb, 0.0)
    assert pb.data.xpos[hid].tolist() == pytest.approx(PARK)
    apply_at(pb, pb.cycle_t)  # hold past the end lets the hand arrive
    assert np.allclose(pb.data.xpos[hid], HANDOVER_HOVER, atol=1e-6)


def test_reset_restores_home():
    pb = build_playback("knife_handover")
    apply_at(pb, pb.cycle_t)
    reset(pb)
    assert np.array_equal(pb.data.qpos, pb.qpos_home)
    assert np.allclose(pb.data.mocap_pos, pb.mocap_home)
