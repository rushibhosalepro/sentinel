"""S-04: Motion matches the §4 contract; dry runs never touch the real sim."""

import mujoco
import numpy as np
import pytest

from sim.motion import KNIFE_HANDOVER_PLAN, plan_to_motion
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
                           "end_state", "derived_from", "step_ids"}
    assert motion["body"] == "arm"
    n = len(motion["path"])
    assert n > 10
    assert len(motion["t"]) == len(motion["held"]) == len(motion["tilt"]) \
        == len(motion["speed"]) == n
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
