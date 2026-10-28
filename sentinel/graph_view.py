"""Graph snapshot for the checker: props + live sim state -> graph dict.

The relations/check contract (see sentinel/relations.py). People present
in the sim come from their bodies; absent people (e.g. the visitor) are
added by the caller when the scenario stages them.
"""

from __future__ import annotations


def graph_snapshot(model, data, props: dict) -> dict:
    """Build the checker's graph from props + current sim state."""
    objects = {}
    for oid, spec in props["objects"].items():
        bid = model.body(oid).id
        objects[oid] = {"pos": data.xpos[bid].copy(),
                        "quat": data.xquat[bid].copy(),
                        "properties": list(spec.get("properties", [])),
                        "owner": spec.get("owner"), "conf": 1.0}
    hid = model.body("human_hand").id
    tid = model.body("human_torso").id
    scopes = props.get("people", {}).get("owner", {}).get("authorised", [])
    return {
        "objects": objects,
        "people": {"owner": {"hand": data.xpos[hid].copy(),
                             "torso": data.xpos[tid].copy(),
                             "hand_vel": [0.0, 0.0, 0.0],
                             "authorised": list(scopes), "role": "owner",
                             "conf": 1.0}},
    }
