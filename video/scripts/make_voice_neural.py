"""Draft voiceover with a Microsoft Edge neural voice (needs internet).

Writes public/voice/<id>.wav for every line in narration.json, replacing
the SAPI draft. Then run voice_timing.py and re-render:

    uv run --with edge-tts python video/scripts/make_voice_neural.py
    uv run python video/scripts/voice_timing.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
VOICE = sys.argv[1] if len(sys.argv) > 1 else "en-US-AndrewNeural"
RATE = "+0%"
# Spellings the SAPI voice needed that a neural voice reads better as-is.
SAY = {"L L M": "LLM"}


async def speak(sid: str, text: str) -> None:
    for a, b in SAY.items():
        text = text.replace(a, b)
    out = ROOT / "public" / "voice" / f"{sid}.wav"
    tmp = out.with_suffix(".tts.mp3")
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(tmp))
    subprocess.run(
        ["npx", "remotion", "ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
         "-ac", "1", "-ar", "24000", str(out)],
        cwd=ROOT, check=True, shell=True)
    tmp.unlink()
    print("wrote", out)


async def main() -> None:
    lines = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))
    for line in lines:
        await speak(line["id"], line["text"])


if __name__ == "__main__":
    asyncio.run(main())
