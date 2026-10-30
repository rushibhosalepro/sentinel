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
VOICE = sys.argv[1] if len(sys.argv) > 1 else "en-US-AndrewMultilingualNeural"
RATE = "-5%"
# Spellings the SAPI voice needed that a neural voice reads better as-is.
SAY = {"L L M": "LLM"}


PAUSE = "[pause]"  # in narration.json: 0.6 s of silence between pieces
PAUSE_S = 0.6
SR = 24000


async def _tts_wav(text: str, out: Path) -> None:
    tmp = out.with_suffix(".tts.mp3")
    for attempt in range(4):  # the service sometimes returns no audio
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(tmp))
            break
        except edge_tts.exceptions.NoAudioReceived:
            if attempt == 3:
                raise
            await asyncio.sleep(2)
    subprocess.run(
        ["npx", "remotion", "ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
         "-ac", "1", "-ar", str(SR), str(out)],
        cwd=ROOT, check=True, shell=True)
    tmp.unlink()


async def speak(sid: str, text: str) -> None:
    import wave

    for a, b in SAY.items():
        text = text.replace(a, b)
    out = ROOT / "public" / "voice" / f"{sid}.wav"
    pieces = [t.strip() for t in text.split(PAUSE) if t.strip()]
    audio = b""
    for i, piece in enumerate(pieces):
        part = out.with_suffix(f".part{i}.wav")
        await _tts_wav(piece, part)
        with wave.open(str(part)) as w:
            audio += w.readframes(w.getnframes())
        part.unlink()
        if i < len(pieces) - 1:
            audio += b"\x00\x00" * int(PAUSE_S * SR)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio)
    print("wrote", out)


async def main() -> None:
    lines = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))
    for line in lines:
        await speak(line["id"], line["text"])


if __name__ == "__main__":
    asyncio.run(main())
