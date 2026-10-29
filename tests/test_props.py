"""S-02: props.yaml keys match kitchen.xml's free-joint bodies exactly."""

import mujoco
import yaml

from sim.world import SCENES_DIR, load_scene

PROPERTIES = {"sharp", "hot", "liquid", "fragile", "electronic",
              "medication", "food"}


def _props():
    with open(SCENES_DIR / "props.yaml") as f:
        return yaml.safe_load(f)


def test_objects_match_free_bodies():
    props = _props()["objects"]
    model, _ = load_scene("kitchen")
    free = set()
    for body_id in range(model.nbody):
        jadr = model.body_jntadr[body_id]
        if jadr >= 0 and model.jnt_type[jadr] == mujoco.mjtJoint.mjJNT_FREE:
            free.add(mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id))
    assert set(props) == free, (
        f"yaml-only={set(props) - free} model-only={free - set(props)}")


def test_vocabulary_and_owners():
    data = _props()
    people = set(data["people"])
    assert people == {"owner", "visitor"}
    for name, spec in data["objects"].items():
        assert set(spec["properties"]) <= PROPERTIES, name
        assert spec["owner"] in people, name


def test_visitors_bag_static_prop_near_person():
    import numpy as np

    model, data = load_scene("kitchen")
    bid = model.body("visitors_bag").id
    assert model.body_jntadr[bid] < 0  # static: not a prop, no graph node
    bag = np.asarray(data.xpos[bid], dtype=float)
    pelvis = np.asarray(data.xpos[model.body("human_pelvis").id],
                        dtype=float)
    assert float(np.linalg.norm(bag[:2] - pelvis[:2])) < 0.5
    assert "visitors_bag" not in _props()["objects"]
