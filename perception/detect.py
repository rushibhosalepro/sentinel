"""G-09 stage 1: Muse Spark looks at the frame, returns {label, box}.

`detect_objects` sends the frame to muse-spark-1.3 with structured output
and validates every box locally (ints, in-frame, non-empty). Results are
cached per frame hash under cache/ (gitignored); `parse_detections`
replays cached content with no network. `match_label` maps a free-form
Spark label to a props.yaml id (else None -> unknown_object); person
labels are skipped (people come from sim state, not the frame).
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path

from openai import OpenAI

from perception.sam import CACHE_DIR, REPO_ROOT, load_settings

MODEL = "muse-spark-1.3"
EFFORT = "minimal"  # fastest valid setting (out/planner_latency.md)

DETECT_SCHEMA = {
    "type": "object",
    "properties": {
        "detections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "box": {"type": "array",
                            "items": {"type": "integer"},
                            "minItems": 4, "maxItems": 4},
                },
                "required": ["label", "box"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["detections"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are an object detector for a robot kitchen counter. Reply with JSON only (the response is schema-constrained).

List EVERY distinct object resting on the counter, each with a tight bounding box. Use short, plain labels (knife, jug, cup, laptop, pill bottle, wine glass, plate, apple, sponge, phone, sticky note). Boxes are [x0, y0, x1, y1] pixels with (0, 0) at the top-left; the image size is given with the frame. Report each object once. Skip the robot arm and any person."""

# Spark may report the visible person anyway; people are tracked from sim
# state (graph people nodes), never from the frame, so these never become
# unknown_object nodes.
PERSON_LABELS = frozenset({
    "person", "human", "hand", "human hand", "owner", "visitor",
    "man", "woman", "arm", "human arm",
})


def frame_sha(image_path: Path) -> str:
    return hashlib.sha256(image_path.read_bytes()).hexdigest()


def detect_cache_path(image_path: Path) -> Path:
    return CACHE_DIR / f"spark_{frame_sha(image_path)[:16]}.json"


def _normalise(label: str) -> str:
    return " ".join(str(label).lower().split())


def match_label(label: str, props: dict) -> str | None:
    """Map a Spark label to a props.yaml object id (None = no match).

    Two passes, case-insensitive: first the id (underscores as spaces)
    and display label, then the SAM prompts. The jug grounds via "cup"
    (G-02), so a single pass would steal the cup's label. Exact
    matches only: anything else is for the caller to route to
    unknown_object.
    """
    want = _normalise(label)
    for oid, spec in props["objects"].items():
        if want in {_normalise(oid.replace("_", " ")),
                    _normalise(spec.get("label", ""))}:
            return oid
    for oid, spec in props["objects"].items():
        if want in {_normalise(p) for p in spec.get("prompts", [])}:
            return oid
    return None


def is_person_label(label: str) -> bool:
    return _normalise(label) in PERSON_LABELS


def parse_detections(content: str, width: int, height: int):
    """Parse + validate raw detector content; (dets, None) or ([], why).

    Pure (no network): shared by the live call and cache replay.
    """
    try:
        obj = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return [], "detector response is not valid JSON"
    if not isinstance(obj, dict) or not isinstance(obj.get("detections"),
                                                   list):
        return [], "detector response has no 'detections' list"
    dets = []
    for i, d in enumerate(obj["detections"]):
        if not isinstance(d, dict) or not isinstance(d.get("label"), str) \
                or not d["label"].strip():
            return [], f"detection {i} has no label"
        box = d.get("box")
        if not isinstance(box, list) or len(box) != 4 \
                or not all(isinstance(v, int) and not isinstance(v, bool)
                           for v in box):
            return [], f"detection {i} box must be 4 ints"
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            return [], (f"detection {i} box {box} outside "
                        f"{width}x{height}")
        dets.append({"label": d["label"].strip(), "box": list(box)})
    return dets, None


def detect_objects(image_path: Path, width: int, height: int,
                   model: str = MODEL, effort: str = EFFORT,
                   refresh: bool = False) -> tuple[list, dict | None]:
    """Detect {label, box}[] on the frame (cached per frame hash).

    Returns (detections, usage); usage is None on cache hits. Raises on
    transport errors or invalid detector output (fail-closed: the caller
    reports "perception error" and never moves).
    """
    image_path = REPO_ROOT / image_path if not image_path.is_absolute() \
        else image_path
    cached = detect_cache_path(image_path)
    if cached.exists() and not refresh:
        print(f"cache hit: {cached}")
        dets, err = parse_detections(
            json.loads(cached.read_text())["content"], width, height)
        if err is not None:
            raise RuntimeError(f"cached detections invalid: {err}")
        return dets, None

    base_url, api_key = load_settings()
    client = OpenAI(base_url=base_url, api_key=api_key,
                    timeout=120.0, max_retries=2)
    data_url = ("data:image/png;base64," + base64.b64encode(
        image_path.read_bytes()).decode())
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text",
                 "text": f"Detect all objects on the counter. The image "
                         f"is {width}x{height} pixels."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "Detections", "schema": DETECT_SCHEMA},
        },
        reasoning_effort=effort,
    )
    print(f"detect took {time.perf_counter() - t0:.1f} s "
          f"(model={model}, effort={effort})")
    content = resp.choices[0].message.content
    dets, err = parse_detections(content, width, height)
    if err is not None:
        raise RuntimeError(f"detector output invalid: {err}")
    usage = None
    if resp.usage is not None:
        usage = {"prompt_tokens": resp.usage.prompt_tokens,
                 "completion_tokens": resp.usage.completion_tokens,
                 "total_tokens": resp.usage.total_tokens}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({
        "model": model, "effort": effort,
        "image": str(image_path), "image_sha256": frame_sha(image_path),
        "width": width, "height": height,
        "n_detections": len(dets), "usage": usage, "content": content,
    }))
    print(f"cached: {cached}")
    return dets, usage
