"""G-11: hazard-property inference for uncatalogued detections.

Stage 1 (detect.py) labels boxes and stage 2 (sam.py) masks them;
labels matching no props.yaml id become unknown_object nodes with
no properties, so geometric rules stay blind to novel objects.
This module asks Muse Spark (structured output) which hazard
properties a novel object plausibly has, from the fixed props.yaml
vocabulary. Results cache per frame+box under cache/ (gitignored);
`parse_inference` replays cached content with no network.

Inferred properties flow into the perception graph
(spawn_inferred) and the checker (graph_view passthrough), so
geometric rules fire on novel objects: a jug carried near an
inferred toaster BLOCKs. Inference can only add caution, never
permission: the planner never sees inferred ids (no sim body to
grasp), and an invalid inference degrades to plain unknown_object.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from perception.detect import frame_sha
from perception.sam import CACHE_DIR
from planner.model_client import chat as model_chat
from planner.model_client import get_client

EFFORT = "minimal"

# Fixed hazard vocabulary (mirrors the props.yaml header comment).
VOCABULARY = ("sharp", "hot", "liquid", "fragile", "electronic",
              "medication", "food")

INFER_SCHEMA = {
    "type": "object",
    "properties": {
        "properties": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "why": {"type": "string"},
    },
    "required": ["properties", "confidence", "why"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You classify one detected object for a robot safety
system. Reply with JSON only: {"properties": [...], "confidence":
0..1, "why": "one short sentence"}. "properties" holds zero or more
of exactly: sharp, hot, liquid, fragile, electronic, medication,
food. Be conservative: list a property only when the object
plausibly has it (a toaster is electronic; a mug is none of these).
"confidence" is your 0..1 confidence in the property list."""


def infer_cache_key(frame_sha_hex: str, idx: int, label: str,
                    box) -> str:
    rounded = [int(round(float(v))) for v in box]
    raw = f"{frame_sha_hex}:{idx}:{label.strip().lower()}:{rounded}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def infer_cache_path(key: str) -> Path:
    return CACHE_DIR / f"props_{key}.json"


def parse_inference(content: str):
    """Validate one inference reply. Returns (result, err)."""
    try:
        doc = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        return None, f"not JSON: {e}"
    if not isinstance(doc, dict):
        return None, "top level must be an object"
    props = doc.get("properties")
    if not isinstance(props, list) or any(
            not isinstance(p, str) for p in props):
        return None, "'properties' must be a list of strings"
    seen = []
    for p in props:
        if p not in VOCABULARY:
            return None, f"{p!r} not in vocabulary"
        if p not in seen:
            seen.append(p)
    conf = doc.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return None, "'confidence' must be a number"
    if not 0.0 <= float(conf) <= 1.0:
        return None, "'confidence' must be within 0..1"
    why = doc.get("why")
    if not isinstance(why, str) or not why.strip():
        return None, "'why' must be a non-empty string"
    return {"properties": seen, "confidence": float(conf),
            "why": why.strip()[:160]}, None


def infer_properties(image_path: str | Path, idx: int, label: str,
                     box, width: int, height: int,
                     effort: str = EFFORT,
                     refresh: bool = False):
    """Infer hazard properties for one unmatched detection.

    Returns (result, usage); raises RuntimeError on invalid model
    output (callers degrade that detection to unknown_object).
    """
    path = Path(image_path)
    if not path.is_absolute():
        from perception.sam import REPO_ROOT
        path = REPO_ROOT / path
    sha = frame_sha(path)
    box_i = [int(round(float(v))) for v in box]
    key = infer_cache_key(sha, idx, label, box_i)
    cache = infer_cache_path(key)
    if cache.exists() and not refresh:
        result, err = parse_inference(
            json.loads(cache.read_text())["content"])
        if err is not None:
            raise RuntimeError(f"cached inference invalid: {err}")
        print(f"inference cache hit {path.name} det {idx}")
        return result, None
    import base64
    data_url = ("data:image/png;base64,"
                + base64.b64encode(path.read_bytes()).decode())
    client, model_id, spec, alias = get_client("spark")
    content, usage, latency = model_chat(
        client, model=model_id, spec=spec, alias=alias,
        purpose="infer-properties",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text":
                 f"The detector found {label.strip()!r} at box "
                 f"{box_i} in this {width}x{height} frame. "
                 "Which hazard properties does it plausibly have?"},
                {"type": "image_url",
                 "image_url": {"url": data_url}}]}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "InferProperties",
                                         "schema": INFER_SCHEMA}},
        reasoning_effort=effort)
    print(f"inference det {idx} took {latency:.1f}s")
    result, err = parse_inference(content)
    if err is not None:
        raise RuntimeError(f"inference output invalid: {err}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(
        {"model": model_id, "effort": effort,
         "image": str(path), "image_sha256": sha, "idx": idx,
         "label": label.strip(), "box": box_i, "usage": usage,
         "content": content}, indent=1))
    print(f"inference cached {path.name} det {idx}")
    return result, usage
