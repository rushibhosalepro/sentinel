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
# "SAM" -> "Sam": caps acronyms get spelled out (S-A-M); the name reads
# as intended. TTS text only -- on-screen text is untouched.
SAY = {"L L M": "LLM", "SAM": "Sam"}


PAUSE = "[pause]"  # in narration.json: 0.5 s of silence between pieces
PAUSE_S = 0.5
SR = 24000


async def _tts_wav(text: str, out: Path, rate: str) -> None:
    tmp = out.with_suffix(".tts.mp3")
    for attempt in range(4):  # the service sometimes returns no audio
        try:
            await edge_tts.Communicate(text, VOICE, rate=rate).save(str(tmp))
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


async def speak(sid: str, text: str, rate: str = RATE) -> None:
    import wave

    for a, b in SAY.items():
        text = text.replace(a, b)
    out = ROOT / "public" / "voice" / f"{sid}.wav"
    pieces = [t.strip() for t in text.split(PAUSE) if t.strip()]
    audio = b""
    for i, piece in enumerate(pieces):
        part = out.with_suffix(f".part{i}.wav")
        await _tts_wav(piece, part, rate)
        # Trim TTS edge silence per piece, before joining, so the
        # inserted [pause] gaps survive untouched and the line starts
        # clean on the VOICE_LEAD.
        trimmed = out.with_suffix(f".part{i}.trim.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(part), "-af",
             "silenceremove=start_periods=1:start_threshold=-45dB,"
             "areverse,"
             "silenceremove=start_periods=1:start_threshold=-45dB,"
             "areverse",
             str(trimmed)],
            cwd=ROOT, check=True)
        part.unlink()
        with wave.open(str(trimmed)) as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2, trimmed
            audio += w.readframes(w.getnframes())
        trimmed.unlink()
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
    print("pronunciation check: lines containing SAM (voiced as 'Sam'):")
    for line in lines:
        if "SAM" in line["text"]:
            print(f"  {line['id']}: {line['text']}")
    for line in lines:
        await speak(line["id"], line["text"], line.get("rate", RATE))


if __name__ == "__main__":
    asyncio.run(main())
