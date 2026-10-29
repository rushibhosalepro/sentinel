"""D-07: record out/split_<preset>.mp4 (both lane cameras + footers).

uv run python -m dashboard.split_record [knife|water|sticky|all]
Runs lane A (naive) + lane B (Sentinel) headless in parallel, saves
per-lane mp4s, and stacks them with tags + the two footer lines.
Prints the outcome lines and the run cost (costs.jsonl delta).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "out"
COSTS_PATH = OUT_DIR / "costs.jsonl"

FOOTER_H = 64


def b_chain(events: list[dict]) -> str:
    """Lane B footer: verdict chain from its verdict/feedback/done events."""
    rounds: dict[int, dict] = {}
    for e in events:
        if e["type"] == "verdict":
            rounds.setdefault(e["round"], {})["verdict"] = e
        elif e["type"] == "feedback":
            rounds.setdefault(e["round"], {})["note"] = e["note"]
    dones = [e for e in events if e["type"] == "done"]
    nums = sorted(r for r, v in rounds.items() if "verdict" in v)
    if not nums:
        return dones[0]["status"] if dones else "..."
    parts = []
    for i, r in enumerate(nums):
        parts.append(rounds[r]["verdict"]["kind"])
        if "note" in rounds[r] and i < len(nums) - 1:
            parts.append("replan")
    s = " -> ".join(parts)
    last = rounds[nums[-1]]["verdict"]
    fb = [rounds[r]["verdict"].get("feedback") or [] for r in nums]
    fb = [f for f in fb if f]
    if last["kind"] == "ALLOW" and fb:
        s += f": {'; '.join(fb[-1])[:90]}"
    if last["kind"] in ("BLOCK", "ASK") and dones:
        findings = last.get("findings") or []
        rule = findings[0].get("rule") if findings else None
        s += f": not moving ({rule or last['kind'].lower()})"
    return s


def _truncate(draw, text: str, max_w: int) -> str:
    while draw.textlength(text) > max_w and len(text) > 4:
        text = text[:-5] + "..."
    return text


def compose_split(left: Path, right: Path, out: Path, footer_a: str,
                  footer_b: str, fps: int = 30) -> None:
    """Stack two lane mp4s + tags; footer bar carries both outcome lines."""
    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image, ImageDraw

    out.parent.mkdir(parents=True, exist_ok=True)
    with imageio.get_writer(out, fps=fps, codec="libx264",
                            quality=8) as writer:
        rl, rr = imageio.get_reader(left), imageio.get_reader(right)
        try:
            fl = fr = None
            done_l = done_r = False
            itl, itr = iter(rl), iter(rr)
            while not (done_l and done_r):
                if not done_l:
                    try:
                        fl = next(itl)[:, :, :3]
                    except (StopIteration, IndexError):
                        done_l = True
                if not done_r:
                    try:
                        fr = next(itr)[:, :, :3]
                    except (StopIteration, IndexError):
                        done_r = True
                if fl is None or fr is None:
                    break
                h = min(fl.shape[0], fr.shape[0])
                both = np.concatenate([fl[:h], fr[:h]], axis=1)
                canvas = np.zeros((h + FOOTER_H, both.shape[1], 3),
                                  dtype=np.uint8)
                canvas[:h] = both
                img = Image.fromarray(canvas)
                draw = ImageDraw.Draw(img)
                draw.text((10, 10), "A: WITHOUT SENTINEL",
                          fill=(255, 80, 80))
                draw.text((fl.shape[1] + 10, 10), "B: WITH SENTINEL",
                          fill=(80, 255, 80))
                half = both.shape[1] // 2 - 12
                draw.text((10, h + 8),
                          _truncate(draw, footer_a, half),
                          fill=(255, 80, 80))
                draw.text((both.shape[1] // 2 + 10, h + 8),
                          _truncate(draw, footer_b, half),
                          fill=(80, 255, 80))
                writer.append_data(np.asarray(img))
        finally:
            rl.close()
            rr.close()
    print(f"saved {out}")


def _costs_size() -> int:
    try:
        return COSTS_PATH.stat().st_size
    except OSError:
        return 0


def _new_spend(since: int) -> float:
    try:
        with open(COSTS_PATH, "rb") as f:
            f.seek(since)
            blob = f.read().decode()
    except OSError:
        return 0.0
    total = 0.0
    for line in blob.splitlines():
        try:
            total += json.loads(line).get("cost_usd") or 0.0
        except ValueError:
            continue
    return round(total, 4)


def record(name: str) -> dict:
    """Record one preset; returns {footers, cost_usd, video}."""
    from dashboard.split import resolve_split, run_naive_lane
    from loop.live import _run_headless

    spec = resolve_split(preset=name)
    cost_mark = _costs_size()
    events_a: list = []
    events_b: list = []

    def _lane_a():
        try:
            run_naive_lane(
                spec["instruction"], preset=spec["preset"],
                attack=spec["attack"],
                out_path=OUT_DIR / f"split_A_{name}.mp4", tag=name,
                sink=events_a.append)
        except Exception as e:  # noqa: BLE001 - recorded, never raised
            events_a.append({"type": "done", "status": "error",
                             "detail": {"outcome": f"lane A error: {e}"}})

    def _lane_b():
        try:
            _run_headless(
                spec["instruction"], str(OUT_DIR / f"split_B_{name}.mp4"),
                preset=spec["preset"], attack=spec["attack"],
                perception="truth", planner_model="spark",
                sink=events_b.append)
        except SystemExit:
            pass  # done already emitted
        except Exception as e:  # noqa: BLE001 - recorded, never raised
            events_b.append({"type": "done", "status": "error",
                             "detail": {"error": str(e)}})

    threads = [threading.Thread(target=f, daemon=True)
               for f in (_lane_a, _lane_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    dones_a = [e for e in events_a if e["type"] == "done"]
    footer_a = (dones_a[-1].get("detail") or {}).get("outcome",
                                                    "lane A: no outcome")
    footer_b = b_chain(events_b)
    print(f"A: {footer_a}")
    print(f"B: {footer_b}")
    video = OUT_DIR / f"split_{name}.mp4"
    compose_split(OUT_DIR / f"split_A_{name}.mp4",
                  OUT_DIR / f"split_B_{name}.mp4", video,
                  footer_a, footer_b)
    cost = _new_spend(cost_mark)
    print(f"cost: ${cost}")
    return {"footer_a": footer_a, "footer_b": footer_b,
            "cost_usd": cost, "video": str(video)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset", nargs="?", default="all",
                        choices=["knife", "water", "sticky", "all"])
    args = parser.parse_args(argv)
    names = ["knife", "water", "sticky"] if args.preset == "all" \
        else [args.preset]
    total = 0.0
    for name in names:
        print(f"=== split {name} ===")
        total += record(name)["cost_usd"]
    print(f"total spend: ${round(total, 4)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
