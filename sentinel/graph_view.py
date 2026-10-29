"""Graph snapshot for the checker: props + live sim state -> graph dict.

The relations/check contract (see sentinel/relations.py). People present
in the sim come from their bodies; absent people (e.g. the visitor) are
added by the caller when the scenario stages them.
"""

from __future__ import annotations

import numpy as np

from sentinel.safe_spot import find_safe_spot
from sim.geometry import body_aabb


def graph_snapshot(model, data, props: dict,
                   perceived: dict | None = None) -> dict:
    """Build the checker's graph from props + current sim state.

    `perceived` (G-09 sam mode) maps object id -> {pos, extent, conf}
    from the perception graph; matched ids keep their props.yaml
    properties/owner, unknown_object entries get none. Objects the
    frame missed are absent (check() treats missing targets as
    unknown); people always come from sim state.
    """
    objects = {}
    if perceived is None:
        for oid, spec in props["objects"].items():
            bid = model.body(oid).id
            try:
                lo, hi = body_aabb(model, data, bid)
                extent = ((np.asarray(hi) - np.asarray(lo)) / 2.0).tolist()
            except Exception:  # noqa: BLE001 - unbounded geometry -> point
                extent = [0.0, 0.0, 0.0]
            objects[oid] = {"pos": data.xpos[bid].copy(),
                            "quat": data.xquat[bid].copy(),
                            "extent": extent,
                            "properties": list(spec.get("properties", [])),
                            "owner": spec.get("owner"), "conf": 1.0}
    else:
        for oid, p in perceived.items():
            spec = props["objects"].get(oid, {})
            objects[oid] = {"pos": np.asarray(p["pos"], dtype=float),
                            "quat": np.array([1.0, 0.0, 0.0, 0.0]),
                            "extent": list(p["extent"]),
                            "properties": list(
                                spec.get("properties", [])),
                            "owner": spec.get("owner"),
                            "conf": float(p["conf"])}
    counter = None
    try:
        gid = model.geom("counter_top").id
        cx, cy = (float(v) for v in data.geom_xpos[gid][:2])
        sx, sy = (float(v) for v in model.geom_size[gid][:2])
        counter = {"x": [cx - sx, cx + sx], "y": [cy - sy, cy + sy]}
        for node in objects.values():
            x, y = float(node["pos"][0]), float(node["pos"][1])
            node["edge_cm"] = round(max(0.0, min(x - (cx - sx),
                                                 (cx + sx) - x,
                                                 y - (cy - sy),
                                                 (cy + sy) - y)) * 100.0, 1)
    except Exception:  # noqa: BLE001 - scene without a counter: no edges
        pass
    hid = model.body("human_hand").id
    tid = model.body("human_torso").id
    scopes = props.get("people", {}).get("owner", {}).get("authorised", [])
    graph = {
        "objects": objects,
        "people": {"owner": {"hand": data.xpos[hid].copy(),
                             "torso": data.xpos[tid].copy(),
                             "hand_vel": [0.0, 0.0, 0.0],
                             "authorised": list(scopes), "role": "owner",
                             "conf": 1.0}},
    }
    try:
        gid = model.body("hand").id
        graph["gripper"] = data.xpos[gid].tolist()
    except Exception:  # noqa: BLE001 - scene without a robot hand
        pass
    if counter is not None:
        graph["counter"] = counter
    graph["safe_spot_pour"] = find_safe_spot(model, data, graph)
    return graph
