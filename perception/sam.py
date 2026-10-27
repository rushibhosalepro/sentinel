"""SAM 3.1 segmentation: streaming Responses call, parse, cache, overlay. (P0-06)

Sends an image + noun-phrase prompt to `sam-3.1` over the Responses API
(streaming, `include_confidence=true`), parses with `meta_sam_parser`,
caches the raw wire output by (image hash, prompt) under `cache/`, and
renders a box+mask overlay PNG.

Usage:
    uv run python -m perception.sam --demo                     # mug on day1
    uv run python -m perception.sam --image out/x.png --prompt knife
    uv run python -m perception.sam --demo --refresh            # skip cache
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
from collections.abc import AsyncIterable
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from meta_sam_parser import (
    ImageSegmentationResult,
    ResponsesEventLike,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)
from openai import OpenAI
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "cache"
OUT_DIR = REPO_ROOT / "out"

MODEL = "sam-3.1"
BASE_URL = "https://api.meta.ai/v1"

PALETTE = [
    (255, 64, 64), (64, 255, 64), (64, 128, 255), (255, 255, 64),
    (255, 64, 255), (64, 255, 255), (255, 160, 64), (160, 64, 255),
]


def _socketpair_works() -> bool:
    try:
        a, b = socket.socketpair()
    except OSError:
        return False
    a.close()
    b.close()
    return True


if hasattr(asyncio, "ProactorEventLoop"):  # Windows only

    class _NoWakeupProactor(asyncio.ProactorEventLoop):
        """Proactor loop without the self-pipe wakeup socket.

        Some locked-down Windows accounts (services, sandboxes) forbid the
        loopback listen() that socket.socketpair() needs, so a stock loop
        cannot even start. Single-threaded asyncio never touches the wakeup
        pipe (it only serves call_soon_threadsafe from other threads), so
        stub it out instead of failing. Cross-thread scheduling fails loudly.
        """

        def _make_self_pipe(self):
            # Dummy fds: fileno() == -1 disables the wakeup fd; any real
            # use (send/recv) fails loudly instead of hanging.
            class _DeadFD:
                def fileno(self):
                    return -1

                def close(self):
                    pass

                def send(self, *args):
                    raise RuntimeError("wakeup pipe is disabled")

                def recv(self, *args):
                    raise RuntimeError("wakeup pipe is disabled")

            self._ssock = _DeadFD()
            self._csock = _DeadFD()

        def _close_self_pipe(self):
            self._ssock.close()
            self._csock.close()

        def call_soon_threadsafe(self, *args, **kwargs):
            raise RuntimeError(
                "cross-thread scheduling needs the wakeup pipe")

        def _loop_self_reading(self, *args):
            # Nobody can write to the wakeup pipe (see above), so there is
            # nothing to read. Stub out the continuous self-pipe read cycle.
            pass


def _run(coro):
    """asyncio.run, with a fallback for Windows accounts without socketpair."""
    if os.name == "nt" and not _socketpair_works():
        return asyncio.run(coro, loop_factory=_NoWakeupProactor)
    return asyncio.run(coro)


def load_settings() -> tuple[str, str]:
    """Read API base URL + key from the environment (`.env.local` supported)."""
    load_dotenv(REPO_ROOT / ".env.local")
    base_url = os.environ.get("META_API_BASE_URL", BASE_URL)
    api_key = os.environ.get("MODEL_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "MODEL_API_KEY is not set. Copy .env.example to .env.local "
            "and add your key (never commit it)."
        )
    return base_url, api_key


def cache_path(image_path: Path, prompt: str) -> Path:
    digest = hashlib.sha256(image_path.read_bytes() + b"\0" + prompt.encode())
    return CACHE_DIR / f"sam_{digest.hexdigest()[:16]}.json"


async def _parse_events(
    events: AsyncIterable[ResponsesEventLike],
) -> ImageSegmentationResult:
    parsed = parse_responses_stream(events, image_segmentation_format())
    return await parsed.final_result()


def parse_raw_output(raw_output: str) -> ImageSegmentationResult:
    """Re-parse cached wire text through the real parser (no network).

    Synthesizes the minimal Responses event sequence (one delta, one
    output_text.done, one response.completed) so cache replay exercises
    the same code path as the live stream.
    """
    async def _replay():
        lane = {"item_id": "replay", "output_index": 0, "content_index": 0}
        yield {"type": "response.output_text.delta", "delta": raw_output, **lane}
        yield {"type": "response.output_text.done", "text": raw_output, **lane}
        yield {"type": "response.completed"}

    return _run(_parse_events(_replay()))


def _collect_events(
    image_path: Path, prompt: str
) -> list[ResponsesEventLike]:
    """Stream the Responses API (sync client) and buffer the events.

    Transport and parsing are deliberately split: the sync client owns the
    HTTP stream (no event loop involved), then the buffered events go
    through the async parser. This also works on locked-down Windows
    accounts where asyncio cannot use threads (see _NoWakeupProactor).
    """
    import base64

    base_url, api_key = load_settings()
    client = OpenAI(base_url=base_url, api_key=api_key,
                    timeout=300.0, max_retries=2)
    data_url = (
        "data:image/png;base64,"
        + base64.b64encode(image_path.read_bytes()).decode()
    )
    events: list[ResponsesEventLike] = []
    with client.responses.stream(
        model=MODEL,
        input=[{
            "type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url},
            ],
        }],
        metadata={"include_confidence": "true", "mask_encoding": "one_bit"},
    ) as stream:
        for event in stream:
            events.append(event)
    return events


def segment(
    image_path: Path, prompt: str, refresh: bool = False
) -> ImageSegmentationResult:
    cached = cache_path(image_path, prompt)
    if cached.exists() and not refresh:
        print(f"cache hit: {cached}")
        return parse_raw_output(json.loads(cached.read_text())["raw_output"])

    events = _collect_events(image_path, prompt)

    async def _buffered():
        for event in events:
            yield event

    result = _run(_parse_events(_buffered()))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "image": str(image_path),
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "outcome": str(result.outcome),
        "n_records": len(result.records),
        "raw_output": result.raw_output,
    }))
    print(f"cached: {cached}")
    return result


def confidences(result: ImageSegmentationResult) -> list[float]:
    """Box confidences (the mask of each record carries the same value)."""
    return [r.confidence for r in result.records
            if r.kind == "box" and r.confidence is not None]


def record_mask_full(record, height: int, width: int) -> np.ndarray:
    """Decode a mask record to a full-frame boolean array."""
    raster = np.frombuffer(
        decode_mask_to_raster(record.mask), dtype=np.uint8
    ).reshape(record.mask.height, record.mask.width)
    b = record.bounds
    x0, y0 = max(0, int(b.left)), max(0, int(b.top))
    x1, y1 = min(width, int(b.right)), min(height, int(b.bottom))
    if (y1 - y0, x1 - x0) != raster.shape:
        m = Image.fromarray((raster * 255).astype(np.uint8))
        raster = (np.asarray(m.resize((x1 - x0, y1 - y0),
                                      Image.NEAREST)) > 0).astype(np.uint8)
    full = np.zeros((height, width), dtype=bool)
    full[y0:y1, x0:x1] |= raster[: y1 - y0, : x1 - x0].astype(bool)
    return full


def draw_overlay(rgb: np.ndarray, result: ImageSegmentationResult) -> Image.Image:
    """Draw filled masks + boxes + labels on the RGB frame."""
    h, w, _ = rgb.shape
    img = Image.fromarray(rgb).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    ids = sorted({r.object_id for r in result.records})
    color = {oid: PALETTE[i % len(PALETTE)] for i, oid in enumerate(ids)}
    for record in result.records:
        c = color[record.object_id]
        if record.kind == "mask":
            ys, xs = np.nonzero(record_mask_full(record, h, w))
            if len(xs):
                fill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                px = fill.load()
                for x, y in zip(xs.tolist(), ys.tolist()):
                    px[x, y] = c + (110,)
                layer = Image.alpha_composite(layer, fill)
                draw = ImageDraw.Draw(layer)
    img = Image.alpha_composite(img, layer)
    draw = ImageDraw.Draw(img)
    for record in result.records:
        if record.kind != "box":
            continue
        c = color[record.object_id]
        draw.rectangle(
            [int(record.left), int(record.top),
             int(record.right), int(record.bottom)],
            outline=c + (255,), width=2,
        )
        label = f"{record.object_id} {record.confidence:.2f}" \
            if record.confidence is not None else str(record.object_id)
        draw.text((int(record.left) + 3, int(record.top) + 3), label,
                  fill=(255, 255, 255, 255))
    return img.convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Segment an image with SAM 3.1.")
    parser.add_argument("--demo", action="store_true",
                        help="segment the mug in out/day1_rgb.png")
    parser.add_argument("--image", default="out/day1_rgb.png")
    parser.add_argument("--prompt", default="mug")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cache and call the API")
    parser.add_argument("--out", default="out/day1_sam.png")
    args = parser.parse_args()
    if not args.demo and args.image == "out/day1_rgb.png" and args.prompt == "mug":
        pass  # defaults == demo; --demo is documentation

    image_path = REPO_ROOT / args.image
    result = segment(image_path, args.prompt, refresh=args.refresh)
    print(f"outcome={result.outcome} records={len(result.records)} "
          f"diagnostics={len(result.diagnostics)}")
    confs = confidences(result)
    boxes = [r for r in result.records if r.kind == "box"]
    masks = [r for r in result.records if r.kind == "mask"]
    print(f"matches: {len(boxes)} box(es), {len(masks)} mask(s)")
    for b in boxes:
        print(f"  id={b.object_id} box=({b.left:.0f},{b.top:.0f},"
              f"{b.right:.0f},{b.bottom:.0f}) confidence={b.confidence}")
    if not boxes:
        print("no matches (normal result when the concept is absent)")

    rgb = np.asarray(Image.open(image_path).convert("RGB"))
    overlay = draw_overlay(rgb, result)
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(out_path)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
