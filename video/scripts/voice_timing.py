"""Build src/timeline.json: each scene's start, duration and voice length.

A scene lasts max(its visual minimum from scenes.json, voice + 1.3 s), so
the narration always fits. Re-run after replacing any voice file:

    uv run python video/scripts/voice_timing.py
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE_LEAD_S = 0.4  # narration starts this far into its scene
VOICE_TAIL_S = 0.65
MAX_TOTAL_S = 180.0


def voice_len(sid: str) -> float:
    path = ROOT / "public" / "voice" / f"{sid}.wav"
    if not path.exists():
        return 0.0
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def normalise_to_mp3(sid: str) -> None:
    """public/voice/<id>.wav -> loudness-matched public/voice/<id>.mp3.

    Highpass, short fades at both ends, then a loudness pass; the mp3
    is 44.1 kHz / 192k. Duration is preserved so voice_len stays valid.
    """
    import subprocess

    src = ROOT / "public" / "voice" / f"{sid}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af",
         "highpass=f=80,afade=t=in:d=0.01,areverse,afade=t=in:d=0.03,"
         "areverse,loudnorm=I=-16:TP=-1.5:LRA=7",
         "-ar", "44100", "-b:a", "192k", str(src.with_suffix(".mp3"))],
        cwd=ROOT, check=True)


def main() -> None:
    scenes = json.loads((ROOT / "scenes.json").read_text(encoding="utf-8"))
    for sid, _ in scenes:
        if (ROOT / "public" / "voice" / f"{sid}.wav").exists():
            normalise_to_mp3(sid)
    timeline, t = [], 0.0
    for sid, minimum in scenes:
        v = voice_len(sid)
        dur = round(max(minimum, v + VOICE_LEAD_S + VOICE_TAIL_S if v else 0), 1)
        timeline.append({"id": sid, "start": round(t, 1), "dur": dur,
                         "voice": round(v, 2)})
        t += dur
    (ROOT / "src" / "timeline.json").write_text(json.dumps(timeline, indent=1))
    for s in timeline:
        print(f"{s['id']:8s} {s['start']:6.1f}s  {s['dur']:5.1f}s  voice {s['voice']:5.2f}s")
    print(f"total {t:.1f}s")
    if t > MAX_TOTAL_S:
        raise SystemExit(f"over {MAX_TOTAL_S:.0f} s: trim scenes.json or the narration")


if __name__ == "__main__":
    main()
