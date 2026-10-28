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

import numpy as np

from graph.scene_graph import load_props
from perception.detect import is_person_label, match_label
from perception.lift3d import Detection, lift_mask

# Props rest on the counter (top z = 0); lifted points below this are
# mask bleed onto the floor/backdrop, not the object (G-09 base points).
LIFT_Z_FLOOR_M = -0.02

# Min box IoU to trust a SAM reply for its prompt box (G-09). Below this
# the reply is re-paired by best IoU, else dropped: a silently swapped
# mask would plant an object at another's position.
PAIR_MIN_IOU = 0.2


def _box_iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    if inter <= 0:
        return 0.0
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area - inter)


def _pair_records(spark_dets: list, by_id: dict) -> dict:
    """Pair each Spark box with its SAM record group (G-09).

    Trusts the echoed object_id first, verified by box IoU; on a
    mismatch re-pairs by best IoU, else drops the detection. Returns
    {spark_index: kinds}.
    """
    groups = {}  # id -> (kinds, reply box or None)
    for oid, kinds in by_id.items():
        try:
            key = int(oid)
        except (TypeError, ValueError):
            continue
        box = kinds.get("box")
        reply = None
        if box is not None:
            reply = (box.left, box.top, box.right, box.bottom)
        groups[key] = (kinds, reply)
    paired, used = {}, set()
    for i, sdet in enumerate(spark_dets):
        prompt = sdet["box"]
        kinds, reply = groups.get(i, ({}, None))
        if reply is not None and _box_iou(prompt, reply) >= PAIR_MIN_IOU:
            paired[i] = kinds
            used.add(i)
            continue
        best, best_iou = None, PAIR_MIN_IOU
        for j, (k2, r2) in groups.items():
            if j in used or r2 is None:
                continue
            iou = _box_iou(prompt, r2)
            if iou > best_iou:
                best, best_iou = j, iou
        if best is None:
            print(f"warning: no SAM records pair with Spark box {i} "
                  f"({sdet['label']}); dropping it")
            continue
        if best != i:
            print(f"warning: Spark box {i} ({sdet['label']}) re-paired "
                  f"to SAM id {best} (IoU {best_iou:.2f})")
        paired[i] = groups[best][0]
        used.add(best)
    return paired
from perception.sam import (
    cache_path,
    parse_raw_output,
    record_mask_full,
    records_by_id,
)


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
                centroid=centroid, bbox_min=lo, bbox_max=hi, n_points=n,
                label=prompt))
    return detections


def detections_from_spark(spark_dets: list, sam_result, depth, cam,
                          props: dict | None = None) -> list[Detection]:
    """Match Spark labels and lift the SAM box-mask reply. (G-09)

    Person labels are skipped (people come from sim state). Each other
    label matches a props id or becomes unknown_object (match=None);
    when two detections match the same id, the lower-confidence one is
    demoted to unknown. Boxes with no SAM records, or masks too small
    to lift, are dropped. Pure (no network).
    """
    props = props if props is not None else load_props()
    h, w = depth.shape
    # Pair over the FULL Spark list: SAM ids index every prompted box,
    # including person boxes. Person labels are skipped after pairing.
    paired = _pair_records(spark_dets, records_by_id(sam_result))
    scored = []
    for i, sdet in enumerate(spark_dets):
        if is_person_label(sdet["label"]):
            continue
        kinds = paired.get(i, {})
        if "mask" not in kinds or "box" not in kinds:
            continue
        lifted = lift_mask(record_mask_full(kinds["mask"], h, w),
                           depth, cam, z_floor=LIFT_Z_FLOOR_M)
        if lifted is None:
            continue
        centroid, lo, hi, n = lifted
        box = kinds["box"]
        scored.append((float(box.confidence), i, sdet, box,
                       centroid, lo, hi, n))
    taken: set[str] = set()
    detections = []
    for conf, i, sdet, box, centroid, lo, hi, n in sorted(
            scored, key=lambda s: -s[0]):
        oid = match_label(sdet["label"], props)
        if oid in taken:
            oid = None  # duplicate match -> unknown_object
        if oid is not None:
            taken.add(oid)
        base = np.array([float(centroid[0]), float(centroid[1]),
                         float(np.asarray(lo)[2])])
        detections.append(Detection(
            prompt=f"spark:{oid}" if oid else "unknown_object",
            conf=conf,
            box2d=(box.left, box.top, box.right, box.bottom),
            centroid=base, bbox_min=np.asarray(lo), bbox_max=np.asarray(hi),
            n_points=n, label=sdet["label"], match=oid))
    return detections
