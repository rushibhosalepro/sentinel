"""Scene-graph schema: node/edge types and id conventions. (G-01, PLAN §4)

Node types: object, person, bodypart, property (scene_text and instruction
arrive with perception/episodic layers). Ids are unique across types:

- object:   the MuJoCo body name, e.g. ``chef_knife`` (matches planner ids)
- person:   ``person:<role>``, e.g. ``person:owner``
- bodypart: ``bp:<body name>``, e.g. ``bp:human_hand``, ``bp:hand`` (gripper)
- property: ``prop:<name>``, e.g. ``prop:sharp``

Relation thresholds live in sim.geometry (shared with sim/motion.py so the
Motion end_state and the graph compute the same numbers).
"""

from __future__ import annotations

import networkx as nx

NODE_OBJECT = "object"
NODE_PERSON = "person"
NODE_BODYPART = "bodypart"
NODE_PROPERTY = "property"

EDGE_HAS = "HAS"
EDGE_OWNED_BY = "OWNED_BY"
EDGE_ON = "ON"
EDGE_NEAR = "NEAR"
EDGE_ABOVE = "ABOVE"
EDGE_INSIDE = "INSIDE"
EDGE_HOLDS = "HOLDS"


def object_id(body_name: str) -> str:
    return body_name


def person_id(role: str) -> str:
    return f"person:{role}"


def bodypart_id(body_name: str) -> str:
    return f"bp:{body_name}"


def property_id(name: str) -> str:
    return f"prop:{name}"


def new_graph() -> nx.MultiDiGraph:
    # MultiDiGraph: a pair can hold several relations at once
    # (e.g. the knife is both ON and NEAR the counter).
    return nx.MultiDiGraph()
