"""Generate the demo video's background track (original, no samples).

Calm A-minor ambient: pad + bass + plucked arpeggio with echo, a soft
pulse through the demo section, fade in/out. Writes public/music.wav.

    uv run python video/scripts/make_music.py
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
LENGTH_S = 180.0
BPM = 96.0
BEAT = 60.0 / BPM
OUT = Path(__file__).resolve().parent.parent / "public" / "music.wav"

# Am - F - C - G, two bars each (MIDI notes: root, third, fifth).
CHORDS = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]
CHORD_BEATS = 8


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def tone(f: float, dur: float, harmonics: int = 6, tilt: float = 1.6,
         detune: float = 0.0) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for n in range(1, harmonics + 1):
        out += np.sin(2 * np.pi * f * n * (1 + detune) * t) / n ** tilt
    return out


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    a, r = int(attack * SR), int(release * SR)
    env = np.ones(n)
    env[:a] = np.linspace(0, 1, a)
    env[-r:] = np.minimum(env[-r:], np.linspace(1, 0, r))
    return env


def add(buf: np.ndarray, sig: np.ndarray, start_s: float) -> None:
    i = int(start_s * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[: j - i]


def main() -> None:
    n = int(LENGTH_S * SR)
    left, right = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(7)
    chord_s = CHORD_BEATS * BEAT
    n_chords = int(np.ceil(LENGTH_S / chord_s))

    for k in range(n_chords):
        start = k * chord_s
        root, third, fifth = CHORDS[k % len(CHORDS)]
        dur = chord_s + 1.2  # overlap into the next chord
        env = envelope(int(dur * SR), 1.0, 1.4)
        # Pad: chord tones an octave up, detuned apart in stereo.
        for m in (root + 12, third + 12, fifth + 12, root + 24):
            add(left, 0.050 * env * tone(hz(m), dur, detune=-0.003), start)
            add(right, 0.050 * env * tone(hz(m), dur, detune=0.003), start)
        # Bass on beats 1 and 5 of the chord.
        for b in (0, 4):
            bd = 4 * BEAT
            bass = 0.11 * envelope(int(bd * SR), 0.02, 1.2) * tone(
                hz(root - 12), bd, harmonics=3, tilt=2.0)
            add(left, bass, start + b * BEAT)
            add(right, bass, start + b * BEAT)
        # Arpeggio (eighth notes) from 6 s, louder through the demos.
        if start >= 6.0:
            notes = [root + 12, third + 12, fifth + 12, root + 24,
                     fifth + 12, third + 12, root + 24, fifth + 24]
            gain = 0.045 if start < 30 else 0.06
            for e in range(CHORD_BEATS * 2):
                t0 = start + e * BEAT / 2
                m = notes[e % len(notes)]
                d = 0.6
                tt = np.arange(int(d * SR)) / SR
                pluck = gain * np.exp(-tt / 0.18) * tone(hz(m), d, 4, 2.2)
                pan = 0.3 if e % 2 else 0.7
                add(left, pluck * (1 - pan) * 2, t0)
                add(right, pluck * pan * 2, t0)
        # Soft pulse (kick + hat) through the demo and results section.
        if 36.0 <= start < 160.0:
            for b in range(CHORD_BEATS):
                t0 = start + b * BEAT
                kd = 0.25
                tt = np.arange(int(kd * SR)) / SR
                f = 50 + 70 * np.exp(-tt / 0.03)
                kick = 0.16 * np.exp(-tt / 0.08) * np.sin(
                    2 * np.pi * np.cumsum(f) / SR)
                add(left, kick, t0)
                add(right, kick, t0)
                hd = 0.05
                hat = 0.012 * np.exp(-np.arange(int(hd * SR)) / SR / 0.012) \
                    * rng.standard_normal(int(hd * SR))
                add(left, hat, t0 + BEAT / 2)
                add(right, hat, t0 + BEAT / 2)

    # Echo (dotted eighth), then master fades.
    delay = int(0.75 * BEAT * SR)
    for ch in (left, right):
        echo = np.zeros_like(ch)
        echo[delay:] = ch[:-delay] * 0.28
        ch += echo
    fade = np.ones(n)
    fi, fo = int(2.5 * SR), int(7.0 * SR)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.linspace(1, 0, fo)
    stereo = np.stack([left * fade, right * fade], axis=1)
    stereo *= 0.89 / np.max(np.abs(stereo))  # peak -1 dBFS

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(f"wrote {OUT} ({LENGTH_S:.0f} s)")


if __name__ == "__main__":
    main()
