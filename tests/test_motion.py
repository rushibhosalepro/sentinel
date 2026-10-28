"""S-04: Motion matches the §4 contract; dry runs never touch the real sim."""

import mujoco
import numpy as np
import pytest

from sim.motion import KNIFE_HANDOVER_PLAN, plan_to_motion
from sim.play import rollout_frames
from sim.primitives import PrimitiveError
from sim.world import load_scene


@pytest.fixture(scope="module")
def rollout():
    model, data = load_scene("kitchen")
    before = {k: getattr(data, k).copy()
              for k in ("qpos", "qvel", "xpos", "xquat", "ctrl",
                        "mocap_pos", "mocap_quat")}
    motion = plan_to_motion(model, data, KNIFE_HANDOVER_PLAN,
                            derived_from="test:handover")
    return model, data, before, motion


def test_contract(rollout):
    model, _, _, motion = rollout
    assert set(motion) == {"body", "path", "t", "held", "tilt", "speed",
                           "sample_steps", "end_state", "derived_from",
                           "step_ids"}
    assert motion["body"] == "arm"
    n = len(motion["path"])
    assert n > 10
    assert len(motion["t"]) == len(motion["held"]) == len(motion["tilt"]) \
        == len(motion["speed"]) == len(motion["sample_steps"]) == n
    assert set(motion["sample_steps"]) <= set(motion["step_ids"])
    assert motion["sample_steps"][0] == motion["step_ids"][0]
    assert motion["sample_steps"][-1] == motion["step_ids"][-1]
    for pose in motion["path"]:
        assert len(pose) == 7
        assert abs(np.linalg.norm(pose[3:]) - 1.0) < 1e-6
    t = motion["t"]
    assert t[0] == 0.0 and all(b >= a for a, b in zip(t, t[1:]))
    free = set()
    for i in range(model.nbody):
        jadr = model.body_jntadr[i]
        if jadr >= 0 and model.jnt_type[jadr] == mujoco.mjtJoint.mjJNT_FREE:
            free.add(mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, i))
    assert set(h for h in motion["held"] if h) <= free
    assert set(motion["speed"]) <= {"slow", "normal"}
    assert all(isinstance(v, float) for v in motion["tilt"])
    for rel in motion["end_state"]:
        assert set(rel) == {"rel", "a", "b", "dist_cm"}
        assert rel["rel"] in {"on", "near", "above", "inside"}
        assert rel["dist_cm"] >= 0.0
    assert motion["derived_from"] == "test:handover"
    assert motion["step_ids"] == [s["id"] for s in KNIFE_HANDOVER_PLAN]


def test_real_sim_unchanged(rollout):
    _, data, before, _ = rollout
    for k, old in before.items():
        assert np.array_equal(getattr(data, k), old), k


def test_held_and_moved(rollout):
    _, _, _, motion = rollout
    assert motion["held"][0] is None
    assert motion["held"][-1] == "chef_knife"
    assert "chef_knife" in {r["a"] for r in motion["end_state"]}


def test_bad_plans_rejected():
    model, data = load_scene("kitchen")
    with pytest.raises(PrimitiveError):
        plan_to_motion(model, data, [{"id": "x", "primitive": "fly",
                                      "args": {}}])
    with pytest.raises(PrimitiveError):
        plan_to_motion(model, data, [{"id": "x", "primitive": "grasp",
                                      "args": {}}])


_DOWN = [0.0, 1.0, 0.0, 0.0]


def _tstep(i, prim, args):
    return {"id": f"s{i}", "primitive": prim, "args": args,
            "serves_instruction": "test", "why": "test"}


def _tilt_plan(sx, sy, extra=()):
    seq = [_tstep(1, "move_to",
                  {"pose": [0.25, 0.05, 0.45, *_DOWN]}),
           _tstep(2, "move_to", {"pose": [sx, sy, 0.45, *_DOWN]}),
           _tstep(3, "move_to", {"pose": [sx, sy, 0.25, *_DOWN]}),
           _tstep(4, "tilt", {"deg": 30})]
    seq += list(extra)
    seq.append(_tstep(5 + len(extra), "tilt", {"deg": 0}))
    return seq


def test_tilt_round_trip_restores_config():
    """tilt 30 -> tilt 0 replays: end config == pre-tilt config, exactly."""
    model, data = load_scene("kitchen")
    motion, frames, _ = rollout_frames(model, data, _tilt_plan(0.2, 0.15),
                                       derived_from="test:tilt")
    steps = motion["sample_steps"]
    pre = frames[[i for i, s in enumerate(steps) if s == "s3"][-1]]
    post = frames[[i for i, s in enumerate(steps) if s == "s5"][-1]]
    assert np.array_equal(pre, post)


def test_tilt_after_move_solves_fresh():
    """A move between tilts disables replay (no teleport to stale q)."""
    model, data = load_scene("kitchen")
    extra = (_tstep(5, "move_to",
                     {"pose": [0.35, 0.06, 0.35, *_DOWN]}),)
    motion, _, _ = rollout_frames(model, data, _tilt_plan(0.35, 0.06,
                                                          extra),
                                  derived_from="test:tilt")
    assert abs(motion["tilt"][-1]) < 0.6
    end = np.asarray(motion["path"][-1][:3], dtype=float)
    assert float(np.linalg.norm(end - [0.35, 0.06, 0.25])) < 0.02
