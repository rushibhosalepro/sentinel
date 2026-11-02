"""G-09 pipeline: frame -> Spark labels -> SAM masks -> 3D graph. (G-09)

`perceive_frame` runs the full two-stage detection on one saved frame:
Muse Spark proposes {label, box} (cached per frame hash), one SAM call
masks every box, masks lift to base points with the depth frame, and
`build_perception_graph` assembles the networkx scene graph. Pure sim +
cache on replays; live API calls only on cache misses.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from graph.scene_graph import build_perception_graph
from graph.schema import EDGE_HAS, NODE_OBJECT
from perception.detect import detect_cache_path, detect_objects
from perception.detections import detections_from_spark
from perception.properties import infer_properties
from perception.sam import box_cache_path, segment_boxes


def _cache_usage(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text()).get("usage")
    except (OSError, ValueError):
        return None


def _add_usage(total: dict, usage: dict | None, calls: int = 1) -> None:
    total["calls"] = total.get("calls", 0) + calls
    if not usage:
        return
    for key in ("prompt_tokens", "input_tokens"):
        if usage.get(key) is not None:
            total["prompt_tokens"] = total.get("prompt_tokens", 0) \
                + usage[key]
    for key in ("completion_tokens", "output_tokens"):
        if usage.get(key) is not None:
            total["completion_tokens"] = total.get("completion_tokens", 0) \
                + usage[key]


def perceive_frame(model, data, frame: dict, image_path: Path,
                   props: dict, refresh: bool = False) -> dict:
    """Run G-09 on one frame; returns graph + planner/checker views.

    `frame` is perception_frame() output (depth + cam); `image_path`
    is the saved PNG Spark/SAM read. Returns {"graph", "detections",
    "spark", "perceived", "positions", "usage"} where `perceived` feeds
    graph_snapshot() and `positions` feeds scene_facts().
    """
    image_path = Path(image_path)
    width, height = frame["width"], frame["height"]
    usage: dict = {}
    spark_dets, spark_usage = detect_objects(
        image_path, width, height, refresh=refresh)
    _add_usage(usage, spark_usage or _cache_usage(
        detect_cache_path(image_path)))
    boxes = [d["box"] for d in spark_dets]
    sam_result = segment_boxes(image_path, boxes, refresh=refresh)
    _add_usage(usage, _cache_usage(box_cache_path(image_path, boxes)))
    dets = detections_from_spark(spark_dets, sam_result, frame["depth"],
                                 frame["cam"], props)
    # G-11: infer hazard properties for unmatched detections. One
    # failure degrades that box to plain unknown, never the frame.
    infer_map = {}
    seq = 0
    for det in dets:
        if det.match is not None:
            continue
        label = det.label or det.prompt
        try:
            res, one = infer_properties(
                image_path, seq, label, det.box2d, width, height,
                refresh=refresh)
        except Exception as e:  # noqa: BLE001 - degrade to unknown
            print(f"inference skipped for {label!r}: {e}")
            res, one = None, None
        _add_usage(usage, one)
        infer_map[id(det)] = res
        seq += 1
    graph = build_perception_graph(
        model, data, dets, props,
        infer_fn=lambda det, _s: infer_map.get(id(det)))
    perceived, positions = {}, {}
    for node, attrs in graph.nodes(data=True):
        if attrs.get("type") != NODE_OBJECT or not attrs.get("tracked"):
            continue
        lo = np.asarray(attrs["bbox3d"][:3], dtype=float)
        hi = np.asarray(attrs["bbox3d"][3:], dtype=float)
        perceived[node] = {
            "pos": [float(v) for v in attrs["pos"]],
            "extent": [float(v) for v in (hi - lo) / 2.0],
            "conf": float(attrs["conf"]),
            "properties": sorted(
                {b.split("prop:", 1)[1]
                 for _, b, d in graph.out_edges(node, data=True)
                 if d.get("type") == EDGE_HAS and "prop:" in b}),
            "inferred": bool(attrs.get("inferred", False)),
            "owner": attrs.get("owner"),
        }
        if not attrs.get("unknown") and not attrs.get("inferred"):
            # Planner sees catalog ids only (G-11): inferred nodes
            # have no sim body to grasp; the checker still guards
            # motion around them.
            positions[node] = perceived[node]["pos"]
    return {"graph": graph, "detections": dets, "spark": spark_dets,
            "perceived": perceived, "positions": positions,
            "usage": usage}
