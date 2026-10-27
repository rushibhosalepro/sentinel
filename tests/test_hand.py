"""G-05: hand velocity + short-horizon prediction."""

import numpy as np
import pytest

from graph.scene_graph import (init_perception_graph, update_hand_track)
from perception.hand import HandTrack
from sim.human import reach_to_counter
from sim.world import load_scene


def test_steady_motion_exact():
    track = HandTrack()
    for k in range(10):
        est = track.update(k * 0.1, (0.5 * k * 0.1, 0.0, 0.3))
    assert np.allclose(est["velocity"], (0.5, 0.0, 0.0))
    assert len(est["predicted"]) == 4  # one per PREDICT_HORIZON
    assert np.allclose(est["predicted"][3], (0.45 + 0.5, 0.0, 0.3))


def test_single_sample_assumes_static():
    est = HandTrack().update(1.0, (1.0, 2.0, 3.0))
    assert est["velocity"] == [0.0, 0.0, 0.0]
    assert all(p == [1.0, 2.0, 3.0] for p in est["predicted"])


def test_stale_timestamp_ignored():
    track = HandTrack()
    track.update(1.0, (0.0, 0.0, 0.0))
    track.update(0.5, (9.0, 9.0, 9.0))  # out of order: dropped
    est = track.update(2.0, (1.0, 0.0, 0.0))
    assert len(track.samples) == 2
    assert np.allclose(est["velocity"], (1.0, 0.0, 0.0))


def test_predictions_improve_as_hand_settles():
    # Cosine-eased 1 m stop over 2 s: linear extrapolation overshoots
    # mid-reach, then converges as the hand settles.
    track = HandTrack()
    traj = {}
    for k in range(41):
        t = k * 0.05
        x = 0.5 - 0.5 * np.cos(np.pi * min(1.0, t / 2.0))
        traj[t] = np.array([x, 0.0, 0.0])
        est = track.update(t, traj[t])
        if k == 20:
            mid_pred = np.array(est["predicted"][3])  # +1.0 s from t=1
        if k == 38:
            late_pred = np.array(est["predicted"][0])  # +0.25 s to t=2.15
    # Late forecast lands past the stop; compare against the held target.
    err_mid = float(np.linalg.norm(mid_pred - traj[2.0]))
    err_late = float(np.linalg.norm(late_pred - traj[2.0]))
    assert err_mid > 0.15  # peak-velocity overshoot (conservative side)
    assert err_late < err_mid / 2  # converges strongly as it settles
    assert err_late < 0.10


@pytest.fixture(scope="module")
def ctx():
    model, data = load_scene("kitchen")
    return model, data


def test_graph_wiring(ctx):
    model, data = ctx
    g = init_perception_graph(model, data)
    hand = g.nodes["bp:human_hand"]
    assert hand["stale"] is True  # pre-created, never observed
    assert hand["person_predicted"] == []
    assert g.get_edge_data("person:owner", "bp:human_hand")

    track = HandTrack()
    hid = model.body("human_hand").id
    park = np.array(hand["pos"])
    park_box = np.array(hand["bbox3d"])
    for k in range(5):
        t = k * 0.1
        reach_to_counter(model, data, t, start_t=0.0, duration=2.0)
        update_hand_track(g, track, t, data.xpos[hid].copy())
    hand = g.nodes["bp:human_hand"]
    assert hand["stale"] is False
    assert hand["last_seen"] == 0.4
    assert len(hand["person_predicted"]) == 4
    assert np.linalg.norm(hand["velocity"]) > 0  # mid-reach, moving
    # Rigid box: parked AABB translated by the travelled delta.
    assert np.allclose(hand["bbox3d"],
                       park_box + np.tile(np.array(hand["pos"]) - park, 2))
