"""S-07: the hand-over completes: wait, transfer to the hand, retract."""

import numpy as np
import pytest

from sim.human import park_pos
from sim.motion import KNIFE_HANDOVER_PLAN, plan_to_motion
from sim.play import (TAKE_DIST, apply_at, build_handover, handle_pos,
                      handover_dist, reset, resolve_take)
from sim.world import load_scene

VARIANTS = ["knife_handover_safe", "knife_handover_unsafe"]
STEP = 0.05  # scenario stepping grid (matches the take resolver)


def _blade_tip(model, data):
    gid = model.geom("chef_knife_blade").id
    tip_local = (model.geom_pos[gid]
                 + np.array([model.geom_size[gid][0], 0.0, 0.0]))
    kid = model.body("chef_knife").id
    return data.xpos[kid] + data.xmat[kid].reshape(3, 3) @ tip_local


def _play(hb):
    """Step the whole cycle on the resolver's grid; returns (hb, took_at)."""
    took_at = None
    t = 0.0
    while t < hb.cycle_t:
        phase = apply_at(hb, t)
        if phase == "retreat" and took_at is None:
            took_at = handover_dist(hb.model, hb.data)
        t += STEP
    apply_at(hb, hb.cycle_t)
    return hb, took_at


def test_unknown_scenario():
    with pytest.raises(KeyError):
        build_handover("knife_handover")


@pytest.mark.parametrize("variant", VARIANTS)
def test_build_resolves_take(variant):
    hb = build_handover(variant)
    assert hb.take_tau is not None
    assert hb.t_arrive < hb.take_tau < hb.t_arrive + hb.timeout
    assert hb.cycle_t > hb.take_tau
    assert hb.handle_end.shape == (3,)


@pytest.mark.parametrize("variant", VARIANTS)
def test_knife_ends_attached_to_human_hand(variant):
    hb = build_handover(variant)
    model, data = hb.model, hb.data
    hid, kid = model.body("human_hand").id, model.body("chef_knife").id
    offsets, took_at = [], None
    t = 0.0
    while t < hb.cycle_t:
        phase = apply_at(hb, t)
        if phase == "retreat":
            if took_at is None:
                took_at = handover_dist(model, data)
            R = data.xmat[hid].reshape(3, 3)
            offsets.append(R.T @ (data.xpos[kid] - data.xpos[hid]))
        t += STEP
    apply_at(hb, hb.cycle_t)
    R = data.xmat[hid].reshape(3, 3)
    offsets.append(R.T @ (data.xpos[kid] - data.xpos[hid]))
    assert hb.transferred
    assert took_at < TAKE_DIST + 1e-6  # transfer right at the handle
    assert (np.abs(np.stack(offsets) - offsets[0]).max() < 1e-6)  # rigid
    assert float(np.linalg.norm(data.xpos[kid] - data.xpos[hid])) < 0.15


def test_safe_blade_away_at_offer():
    hb = build_handover("knife_handover_safe")
    apply_at(hb, hb.t_arrive)
    hand = hb.data.xpos[hb.model.body("human_hand").id]
    tip = _blade_tip(hb.model, hb.data)
    handle = handle_pos(hb.model, hb.data)
    assert float(np.linalg.norm(tip - hand)) > float(
        np.linalg.norm(handle - hand))


def test_unsafe_blade_leads_at_offer():
    hb = build_handover("knife_handover_unsafe")
    apply_at(hb, hb.t_arrive)
    hand = hb.data.xpos[hb.model.body("human_hand").id]
    tip = _blade_tip(hb.model, hb.data)
    handle = handle_pos(hb.model, hb.data)
    assert float(np.linalg.norm(tip - hand)) < float(
        np.linalg.norm(handle - hand))


def test_timeout_keeps_holding(capsys):
    model, data = load_scene("kitchen")
    frames = []
    motion = plan_to_motion(
        model, data, KNIFE_HANDOVER_PLAN, derived_from="test",
        on_sample=lambda m, s, st, ts: frames.append(s.qpos.copy()))
    t_arrive = motion["t"][-1]
    take = resolve_take(model, data, frames[-1], t_arrive,
                        park_pos(model), t_arrive - 1.0, park_pos(model),
                        timeout=1.0)
    assert take is None
    assert "hand-over not taken" in capsys.readouterr().out


def test_timeout_timeline_holds_knife():
    hb = build_handover("knife_handover_unsafe")
    hb.take_tau = None  # as if the wait had resolved to a timeout
    apply_at(hb, hb.t_arrive)
    knife_at_offer = hb.data.xpos[hb.model.body("chef_knife").id].copy()
    _play(hb)
    assert not hb.transferred
    assert np.allclose(
        hb.data.xpos[hb.model.body("chef_knife").id], knife_at_offer,
        atol=1e-9)
    grip = hb.data.xpos[hb.model.body("hand").id]
    assert float(np.linalg.norm(knife_at_offer - grip)) < 0.2


@pytest.mark.parametrize("variant", VARIANTS)
def test_reset_restores_home(variant):
    hb, _ = _play(build_handover(variant))
    assert hb.transferred
    assert reset(hb) == "approach"
    assert not hb.transferred and hb.transfer_offset is None
    assert np.array_equal(hb.data.qpos, hb.qpos_home)
    assert np.array_equal(hb.data.mocap_pos, hb.mocap_pos_home)
    assert np.array_equal(hb.data.mocap_quat, hb.mocap_quat_home)
