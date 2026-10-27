"""Load the day-1 scene, step it, and render RGB/depth/segmentation. (P0-04)

Usage:
    uv run python -m sim.world --demo   # renders sim/scenes/day1.xml to out/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENES_DIR = REPO_ROOT / "sim" / "scenes"
OUT_DIR = REPO_ROOT / "out"

WIDTH, HEIGHT = 640, 480
HOME_KEY = "home"


def load_scene(name: str = "day1") -> tuple[mujoco.MjModel, mujoco.MjData]:
    """Load a scene XML, reset to its `home` keyframe, and forward dynamics."""
    model = mujoco.MjModel.from_xml_path(str(SCENES_DIR / f"{name}.xml"))
    data = mujoco.MjData(model)
    key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, HOME_KEY)
    if key_id >= 0:
        data.qpos[:] = model.key_qpos[key_id]
        if model.nu > 0:
            data.ctrl[:] = model.key_ctrl[key_id]
    mujoco.mj_forward(model, data)
    return model, data


def render(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    camera: str = "front",
    width: int = WIDTH,
    height: int = HEIGHT,
) -> dict[str, np.ndarray]:
    """Render RGB (H,W,3 uint8), depth (H,W float32 meters), seg (H,W,2 int32).

    The seg channels are (object id, object type); background is (-1, -1).
    """
    try:
        renderer = mujoco.Renderer(model, height=height, width=width)
    except Exception as e:
        raise RuntimeError(
            f"Could not create a MuJoCo renderer ({e}). If this is a headless "
            "machine, try MUJOCO_GL=egl (Linux) or osmesa."
        ) from e
    try:
        renderer.update_scene(data, camera=camera)
        rgb = renderer.render()
        renderer.enable_depth_rendering()
        renderer.update_scene(data, camera=camera)
        depth = renderer.render()
        renderer.enable_segmentation_rendering()
        renderer.update_scene(data, camera=camera)
        seg = renderer.render()
    finally:
        renderer.close()
    return {"rgb": rgb, "depth": depth, "seg": seg}


def colorize_seg(seg: np.ndarray) -> np.ndarray:
    """Map each unique (objid, objtype) pair to a deterministic bright color."""
    out = np.zeros(seg.shape[:2] + (3,), dtype=np.uint8)
    for objid, objtype in np.unique(seg.reshape(-1, 2), axis=0):
        if objid < 0:
            continue
        rng = np.random.default_rng(int(objid) * 7919 + int(objtype) * 104729)
        color = rng.integers(40, 256, size=3, dtype=np.uint8)
        out[(seg[:, :, 0] == objid) & (seg[:, :, 1] == objtype)] = color
    return out


def save_pngs(
    rgb: np.ndarray,
    depth: np.ndarray,
    seg: np.ndarray,
    out_dir: Path = OUT_DIR,
    stem: str = "day1",
) -> dict[str, Path]:
    """Save RGB, 16-bit-mm depth, and colorized-seg PNGs. Returns paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "rgb": out_dir / f"{stem}_rgb.png",
        "depth": out_dir / f"{stem}_depth.png",
        "seg": out_dir / f"{stem}_seg.png",
    }
    Image.fromarray(rgb).save(paths["rgb"])
    depth_mm = np.clip(depth * 1000.0, 0, 65535).astype(np.uint16)
    Image.fromarray(depth_mm).save(paths["depth"])
    Image.fromarray(colorize_seg(seg)).save(paths["seg"])
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a scene to out/.")
    parser.add_argument("--demo", action="store_true",
                        help="render the day-1 scene and save PNGs")
    parser.add_argument("--scene", default="day1")
    parser.add_argument("--camera", default="front")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return
    model, data = load_scene(args.scene)
    frames = render(model, data, camera=args.camera)
    paths = save_pngs(frames["rgb"], frames["depth"], frames["seg"],
                      stem=args.scene)
    for kind, path in paths.items():
        print(f"{kind}: {path} {frames[kind].shape} {frames[kind].dtype}")


if __name__ == "__main__":
    main()
