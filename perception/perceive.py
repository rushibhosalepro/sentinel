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
from graph.schema import NODE_OBJECT
from perception.detect import detect_cache_path, detect_objects
from perception.detections import detections_from_spark
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
    graph = build_perception_graph(model, data, dets, props)
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
        }
        if not attrs.get("unknown"):
            positions[node] = perceived[node]["pos"]
    return {"graph": graph, "detections": dets, "spark": spark_dets,
            "perceived": perceived, "positions": positions,
            "usage": usage}
