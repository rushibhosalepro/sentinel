"""L-07: live HALT monitor (person_in_path, evaluated during execution).

The static checker can't see the person move mid-motion, so the live
loop re-checks every ~100 ms against CURRENT sim state: person bodies
from the sim, the gripper + held object, and the arm's remaining
planned path. Thresholds come from rules/hard/person_in_path.json;
a sharp held object doubles them. Pure geometry in imminent();
check_halt() gathers live points around it.
"""

from __future__ import annotations

import numpy as np

from sentinel.check import load_rulebook
from sentinel.relations import (KNIFE_BODY, KNIFE_HANDLE_LOCAL,
                                KNIFE_TIP_LOCAL)
from sim.human import (FOREARM_BODY, HAND_BODY, TORSO_BODY,
                       UPPER_ARM_BODY)
from sim.ik import GRASP_OFFSET
from sim.play import ROBOT_HAND

PERSON_BODIES = (HAND_BODY, FOREARM_BODY, UPPER_ARM_BODY, TORSO_BODY)
MONITOR_DT_S = 0.1
CLEAR_S = 1.0


def rule_params(rules=None) -> dict | None:
    """person_in_path thresholds from the rulebook (None if absent)."""
    if rules is None:
        rules = load_rulebook()
    for r in rules:
        if r.get("id") == "person_in_path":
            return dict(r["when"]["person_in_path"])
    return None


def limits(params: dict, sharp: bool) -> tuple[float, float]:
    """(grip_m, path_m): sharp held doubles both (rule sharp_x2)."""
    m = 2.0 if sharp and params.get("sharp_x2", True) else 1.0
    return params["grip_cm"] / 100.0 * m, params["path_cm"] / 100.0 * m


def imminent(person_pts, near_pts, path_pts, near_lim: float,
             path_lim: float) -> tuple[bool, float, str]:
    """(fired, min_dist_m, what): person vs gripper/held + path sweep.

    near_pts/path_pts are (tag, xyz) lists. Fires when the closest
    approach violates its own limit (grip tags vs near_lim, path tags
    vs path_lim). Empty inputs never fire.
    """
    best = (float("inf"), "", float("inf"))
    for p in person_pts:
        p = np.asarray(p, dtype=float)
        for tag, q in near_pts:
            d = float(np.linalg.norm(
                p - np.asarray(q, dtype=float)))
            if d < best[0]:
                best = (d, tag, near_lim)
        for tag, q in path_pts:
            d = float(np.linalg.norm(
                p - np.asarray(q, dtype=float)))
            if d < best[0]:
                best = (d, tag, path_lim)
    d, tag, lim = best
    return (d <= lim), d, tag


def check_halt(model, data, motion: dict, tau: float, held: str | None,
               props: dict, params: dict) -> tuple[bool, float, str]:
    """Live person_in_path evaluation at execution time tau (sim seconds).

    Person bodies + gripper + held object from CURRENT sim state;
    remaining path = planned grasp poses after tau. `held` is the live
    held body (or None); sharpness from props.
    """
    person_pts = [data.xpos[model.body(b).id].copy()
                  for b in PERSON_BODIES]
    hid = model.body(ROBOT_HAND).id
    grip = data.xpos[hid] + data.xmat[hid].reshape(3, 3) @ np.array(
        [0.0, 0.0, GRASP_OFFSET])
    near = [("gripper", grip)]
    if held is not None:
        kid = model.body(held).id
        near.append((f"held {held}", data.xpos[kid].copy()))
        if held == KNIFE_BODY:
            rot = data.xmat[kid].reshape(3, 3)
            near.append(("blade tip",
                         data.xpos[kid] + rot @ KNIFE_TIP_LOCAL))
            near.append(("handle",
                         data.xpos[kid] + rot @ KNIFE_HANDLE_LOCAL))
    path = [("remaining path", np.asarray(p[:3], dtype=float))
            for p, t in zip(motion["path"], motion["t"]) if t > tau]
    sharp = (held is not None and "sharp" in props["objects"].get(
        held, {}).get("properties", []))
    near_lim, path_lim = limits(params, sharp)
    return imminent(person_pts, near, path, near_lim, path_lim)
