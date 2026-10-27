"""SAM sweep: segment every props.yaml label (+ extras) on one frame. (G-02)

Uses perception.sam.segment, so every (image hash, prompt) pair is cached
under cache/ and re-runs are free. Saves one overlay PNG per prompt plus a
labelled contact sheet for review.

Usage:
    uv run python -m perception.sweep --demo kitchen
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from graph.scene_graph import load_props
from perception.sam import confidences, draw_overlay, segment

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "out"


def slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_")


def sweep(image_path: Path, prompts: list[str],
          refresh: bool = False) -> dict[str, dict]:
    """Run SAM once per prompt; return {prompt: summary} (cached)."""
    rgb = np.asarray(Image.open(image_path).convert("RGB"))
    results = {}
    for prompt in prompts:
        result = segment(image_path, prompt, refresh=refresh)
        boxes = [r for r in result.records if r.kind == "box"]
        masks = [r for r in result.records if r.kind == "mask"]
        results[prompt] = {
            "result": result,
            "n_boxes": len(boxes),
            "n_masks": len(masks),
            "confidences": confidences(result),
            "boxes": [(round(b.left), round(b.top), round(b.right),
                       round(b.bottom)) for b in boxes],
            "overlay": draw_overlay(rgb, result),
        }
        conf = ", ".join(f"{c:.2f}" for c in results[prompt]["confidences"])
        print(f"  {prompt:12s} boxes={len(boxes)} masks={len(masks)} "
              f"conf=[{conf}]", flush=True)
    return results


def contact_sheet(results: dict[str, dict], cols: int = 4) -> Image.Image:
    """Tile overlay PNGs into one labelled sheet for review."""
    items = list(results.items())
    w, h = next(iter(results.values()))["overlay"].size
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 22)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (prompt, summary) in enumerate(items):
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        sheet.paste(summary["overlay"], (x, y + 22))
        conf = ", ".join(f"{c:.2f}" for c in summary["confidences"])
        draw.text((x + 4, y + 4), f"{prompt} [{conf}]", fill="black")
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep SAM over a frame.")
    parser.add_argument("--demo", choices=["kitchen"])
    parser.add_argument("--image", default="out/kitchen_front.png")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.demo != "kitchen":
        parser.print_help()
        return
    props = load_props()
    prompts = [spec["label"] for spec in props["objects"].values()] + ["hand"]
    print(f"sweeping {len(prompts)} prompts on {args.image}:")
    results = sweep(REPO_ROOT / args.image, prompts, refresh=args.refresh)
    for i, (prompt, summary) in enumerate(results.items()):
        summary["overlay"].save(OUT_DIR / f"sam_kitchen_{i:02d}_{slug(prompt)}.png")
    sheet_path = OUT_DIR / "sam_kitchen_sheet.png"
    contact_sheet(results).save(sheet_path)
    print(f"saved 12 overlays + {sheet_path}")


if __name__ == "__main__":
    main()
