"""G-08: perception frames (1280x960, tight counter-covering front cam).

Renders RGB + metric depth plus the CamParams lift3d needs, and checks
that the counter (and every prop) projects inside the frame.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from graph.scene_graph import load_props
from perception.lift3d import CamParams, camera_params, project
from sim.world import load_scene, render

WIDTH, HEIGHT = 1280, 960
CAMERA = "front"
COUNTER_XY = [(-0.25, -0.35), (0.85, -0.35), (0.85, 0.35), (-0.25, 0.35)]


def perception_frame(model, data, camera: str = CAMERA,
                     width: int = WIDTH, height: int = HEIGHT) -> dict:
    """Render a perception frame: rgb, metric depth, camera params."""
    out = render(model, data, camera=camera, width=width, height=height)
    out["cam"] = camera_params(model, data, camera, width, height)
    out["width"], out["height"] = width, height
    return out


def save_frame(frame: dict, path) -> Path:
    """Save a frame's RGB (the PNG Spark/SAM read) and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame["rgb"]).save(path)
    return path


def coverage(model, data, camera: str = CAMERA, width: int = WIDTH,
             height: int = HEIGHT, margin: int = 8) -> dict:
    """Which counter corners / prop centroids fall outside the frame."""
    cam = camera_params(model, data, camera, width, height)
    bad = {"corners": [], "objects": []}
    for x, y in COUNTER_XY:
        u, v, _ = project(np.array([x, y, 0.0]), cam)
        if not margin <= u < width - margin \
                or not margin <= v < height - margin:
            bad["corners"].append((x, y, round(u), round(v)))
    props = load_props()
    for oid in props["objects"]:
        bid = model.body(oid).id
        u, v, _ = project(np.asarray(data.xpos[bid], dtype=float), cam)
        if not 0 <= u < width or not 0 <= v < height:
            bad["objects"].append(oid)
    return bad


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a perception frame.")
    parser.add_argument("--out", default="out/perception_default.png")
    parser.add_argument("--scene", default="kitchen")
    args = parser.parse_args()
    model, data = load_scene(args.scene)
    frame = perception_frame(model, data)
    out = save_frame(frame, args.out)
    bad = coverage(model, data)
    print(f"saved {out} ({WIDTH}x{HEIGHT})")
    print(f"outside: corners={bad['corners']} objects={bad['objects']}")


if __name__ == "__main__":
    main()
