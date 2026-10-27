"""Privileged planner: instruction + scene-graph facts -> PlanStep[]. (L-00)

Sends the owner instruction plus ground-truth facts (object ids, labels,
positions, properties; NO image) to muse-spark-1.3 with structured output,
then validates every step locally: only the 6 PLAN §4 primitives, only
object ids from props.yaml, correct arg shapes. Anything else is rejected
with a reason and never moves the robot.

Usage:
    uv run python -m planner.planner "give me the knife"   # live API call
"""

from __future__ import annotations

import argparse
import json
import math
import os

from openai import OpenAI

from perception.sam import load_settings

DEFAULT_MODEL = "muse-spark-1.3"
MAX_STEPS = 20

# The 6 PLAN §4 primitives (hardcoded so this module stays sim-free).
PRIMITIVES = ("move_to", "grasp", "release", "tilt", "set_speed", "stop")
SPEEDS = ("slow", "normal")

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_STEPS,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "primitive": {"type": "string", "enum": list(PRIMITIVES)},
                    "args": {"type": "object"},
                    "serves_instruction": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["id", "primitive", "args",
                             "serves_instruction", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["steps"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the planner for a Franka Panda robot arm on a kitchen counter. Reply with a JSON plan only (the response is schema-constrained).

Coordinate frame: metres; x points right, y points toward the back (negative y = front edge), z is up with the counter top at z=0. A gripper pose is [x, y, z, qw, qx, qy, qz]; the gripper-down orientation is [0, 1, 0, 0]. Object positions below are body origins near the counter surface.

Primitives (the ONLY allowed actions):
- move_to {"pose": [x, y, z, qw, qx, qy, qz]}: move the gripper to a hand pose.
- grasp {"object_id": id}: attach the object; FAILS unless the gripper is already within 6 cm of it. Always move above the object first, then down to it.
- release {}: detach the held object (it stays where it is).
- tilt {"deg": number}: pour angle in degrees from straight-down.
- set_speed {"speed": "slow" | "normal"}: speed for subsequent moves; use slow near people or fragile, hot, or liquid-carrying objects.
- stop {}: end the plan (no steps after this run).

Rules:
- Use ONLY object ids listed in the scene facts. Never invent ids.
- Every move_to pose must be a reachable point in free space above the counter (z >= 0.02); approach objects from above.
- Workspace: keep move_to targets 0.15-0.80 m horizontally from the robot base column at (0, 0), z between 0.06 and 0.80. Never plan a target inside the base column.
- The grasp point sits 10 cm below the move_to pose: with the gripper down, to grasp an object whose top is at height z, move to z + 0.10 (a counter object: z = 0.10). Never send the hand itself below z = 0.06.
- To move an object: move above it, move down near it, grasp it, lift to z >= 0.25, carry, then release or stop.
- Keep plans short (at most 12 steps). Each step needs a unique string id, serves_instruction (which part of the instruction it serves), and why (one line)."""


def scene_facts(model, data, props: dict) -> dict:
    """Ground-truth facts for the planner (ids, labels, positions, ...)."""
    objects = []
    for name, spec in props["objects"].items():
        pos = data.xpos[model.body(name).id]
        objects.append({
            "id": name,
            "label": spec["label"],
            "pos": [round(float(v), 3) for v in pos],
            "properties": list(spec["properties"]),
            "owner": spec["owner"],
        })
    return {"objects": objects}


def build_user_message(instruction: str, facts: dict) -> str:
    return (f"Instruction: {instruction}\n\n"
            f"Scene facts (ground truth, no image):\n{json.dumps(facts)}")


def plan_instruction(instruction: str, facts: dict,
                     model: str | None = None) -> str:
    """Call the planner model; returns the raw JSON content string."""
    base_url, api_key = load_settings()
    model = model or os.environ.get("PLANNER_MODEL", DEFAULT_MODEL)
    client = OpenAI(base_url=base_url, api_key=api_key,
                    timeout=120.0, max_retries=2)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": build_user_message(instruction, facts)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "Plan", "schema": PLAN_SCHEMA},
        },
    )
    return resp.choices[0].message.content


def parse_plan_content(content: str) -> tuple[list | None, str | None]:
    """Parse raw LLM content into a step list (no network)."""
    try:
        obj = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None, "LLM response is not valid JSON"
    if not isinstance(obj, dict) or not isinstance(obj.get("steps"), list):
        return None, "LLM response has no 'steps' list"
    return obj["steps"], None


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(float(v))


def validate_steps(steps: list, valid_ids: set[str]):
    """Reject anything out of schema; returns (steps, None) or (None, why)."""
    if not isinstance(steps, list) or not steps:
        return None, "plan must be a non-empty list of steps"
    if len(steps) > MAX_STEPS:
        return None, f"plan has {len(steps)} steps (max {MAX_STEPS})"
    seen = set()
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            return None, f"step {i} is not an object"
        sid = s.get("id")
        if not isinstance(sid, str) or not sid:
            return None, f"step {i} has no string id"
        if sid in seen:
            return None, f"duplicate step id {sid!r}"
        seen.add(sid)
        prim = s.get("primitive")
        if prim not in PRIMITIVES:
            return None, (f"step {sid}: unknown primitive {prim!r} "
                          f"(allowed: {', '.join(PRIMITIVES)})")
        args = s.get("args", {})
        if not isinstance(args, dict):
            return None, f"step {sid}: args must be an object"
        for key in ("serves_instruction", "why"):
            if not isinstance(s.get(key), str) or not s[key].strip():
                return None, f"step {sid}: missing {key!r}"
        if prim == "move_to":
            pose = args.get("pose")
            if not isinstance(pose, list) or len(pose) != 7 \
                    or not all(_is_num(v) for v in pose):
                return None, (f"step {sid}: move_to pose must have 7 "
                              f"finite numbers")
            if float(sum(v * v for v in pose[3:])) < 1e-12:
                return None, f"step {sid}: move_to quat is zero"
        elif prim == "grasp":
            oid = args.get("object_id")
            if oid not in valid_ids:
                return None, f"step {sid}: unknown object {oid!r}"
        elif prim == "tilt":
            if not _is_num(args.get("deg")):
                return None, f"step {sid}: tilt deg must be a number"
        elif prim == "set_speed":
            if args.get("speed") not in SPEEDS:
                return None, (f"step {sid}: speed must be one of "
                              f"{list(SPEEDS)}")
    return steps, None


def plan_from_content(content: str, valid_ids: set[str]):
    """Parse + validate raw LLM content; (steps, None) or (None, why)."""
    steps, err = parse_plan_content(content)
    if err is not None:
        return None, err
    return validate_steps(steps, valid_ids)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan one instruction with Muse Spark (live API call).")
    parser.add_argument("instruction")
    args = parser.parse_args()
    from graph.scene_graph import load_props  # lazy: keep this module light
    from sim.world import load_scene

    model, data = load_scene("kitchen")
    props = load_props()
    facts = scene_facts(model, data, props)
    try:
        content = plan_instruction(args.instruction, facts)
    except Exception as e:
        print(f"planner error: {e}")
        raise SystemExit(1)
    steps, err = plan_from_content(content, set(props["objects"]))
    if err is not None:
        print(f"invalid plan: {err}")
        raise SystemExit(1)
    for s in steps:
        print(f"  {s['id']} {s['primitive']} {json.dumps(s['args'])}"
              f"  # {s['why']}")
    from sim.play import rollout_frames  # lazy: keep this module light
    from sim.primitives import PrimitiveError
    try:
        motion, _, _ = rollout_frames(
            model, data, steps, derived_from="planner:cli")
    except PrimitiveError as e:
        print(f"cannot build Motion: {e}")
        raise SystemExit(1)
    print(f"Motion: {len(motion['t'])} samples over "
          f"{motion['t'][-1]:.2f} s, held={motion['held'][-1]}")


if __name__ == "__main__":
    main()
