"""V30 voice surgery: drop the outro's last line ("Go try to break it.").

Cut [5.234, end] (the [pause] + last line, per silencedetect -35dB).
Original snapshotted to voice_backup_v29/, then re-normalised to mp3
exactly like voice_timing.py does.

Usage: uv run python video/scripts/cut_voice_v30.py
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE = ROOT / "public" / "voice"
BACKUP = ROOT / "voice_backup_v29"
CUT_FROM = 5.234


def main() -> None:
    BACKUP.mkdir(exist_ok=True)
    for ext in (".wav", ".mp3"):
        p = VOICE / f"outro{ext}"
        if p.exists() and not (BACKUP / p.name).exists():
            shutil.copy2(p, BACKUP / p.name)
    print("backup: outro.wav/.mp3 -> voice_backup_v29/")
    src = VOICE / "outro.wav"
    with wave.open(str(src), "rb") as w:
        params = w.getparams()
        n = w.getnframes()
        raw = w.readframes(n)
    rate = params.framerate
    width = params.sampwidth * params.nchannels
    j = int(CUT_FROM * rate) * width
    before = n / rate
    with wave.open(str(src), "wb") as w:
        w.setparams(params)
        w.writeframes(raw[:j])
    after = j / width / rate
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af",
         "highpass=f=80,afade=t=in:d=0.01,areverse,afade=t=in:d=0.03,"
         "areverse,loudnorm=I=-16:TP=-1.5:LRA=7",
         "-ar", "44100", "-b:a", "192k", str(src.with_suffix(".mp3"))],
        cwd=ROOT, check=True)
    print(f"outro: {before:.2f}s -> {after:.2f}s "
          f"(saved {before - after:.2f}s)")


if __name__ == "__main__":
    main()
