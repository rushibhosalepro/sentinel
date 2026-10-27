"""Cached sweep -> 3D detections (never touches the network). (G-04)

detections_from_cache() replays one cached SAM response per prompt, lifts
each mask with the given depth frame, and returns Detection objects ready
for graph association. Missing cache entries raise FileNotFoundError with
a "run the sweep first" hint: demos and reports must be reproducible
without API access.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph.scene_graph import load_props
from perception.lift3d import Detection, lift_mask
from perception.sam import cache_path, parse_raw_output, record_mask_full


def sweep_prompts(props: dict | None = None) -> list[str]:
    """Ordered dedup union of props.yaml prompts (plus hand last)."""
    props = props if props is not None else load_props()
    prompts: list[str] = []
    for spec in props["objects"].values():
        for p in spec.get("prompts", [spec["label"]]):
            if p not in prompts:
                prompts.append(p)
    prompts.append("hand")
    return prompts


def detections_from_cache(image_path: Path, depth, cam,
                          prompts: list[str] | None = None,
                          ) -> list[Detection]:
    if prompts is None:
        prompts = sweep_prompts()
    h, w = depth.shape
    detections = []
    for prompt in prompts:
        cached = cache_path(image_path, prompt)
        if not cached.exists():
            raise FileNotFoundError(
                f"no cached SAM response for {prompt!r} on {image_path}; "
                "run `uv run python -m perception.sweep --demo kitchen` "
                "first (demos never hit the network)")
        result = parse_raw_output(json.loads(cached.read_text())["raw_output"])
        by_id: dict = {}
        for record in result.records:
            by_id.setdefault(record.object_id, {})[record.kind] = record
        for kinds in by_id.values():
            if "mask" not in kinds or "box" not in kinds:
                continue
            lifted = lift_mask(record_mask_full(kinds["mask"], h, w),
                               depth, cam)
            if lifted is None:
                continue
            centroid, lo, hi, n = lifted
            box = kinds["box"]
            detections.append(Detection(
                prompt=prompt, conf=box.confidence,
                box2d=(box.left, box.top, box.right, box.bottom),
                centroid=centroid, bbox_min=lo, bbox_max=hi, n_points=n))
    return detections
