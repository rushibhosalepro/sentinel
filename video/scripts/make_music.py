"""Generate the demo video's soundtrack (original, synthesized, no samples).

The track follows the video's scenes: a tense minor opening for the
problem, a build through "how it works", a confident groove under the
demos, a breakdown for the ASK beat, a rebuild for the learner, the
fullest section under the benchmark, and a resolved ending.

    uv run python video/scripts/make_music.py   # -> public/music.wav
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 112.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
LENGTH_S = 178.0
OUT = Path(__file__).resolve().parent.parent / "public" / "music.wav"

# Scene starts in seconds (keep in sync with src/Root.tsx).
INTRO, PROBLEM, HOW, DEMOS, ASK, LEARN, BENCH, OUTRO, END = (
    0.0, 5.0, 16.0, 35.0, 109.0, 118.0, 140.0, 158.0, 176.0)

MINOR = [(50, 53, 57), (46, 50, 53), (53, 57, 60), (48, 52, 55)]  # Dm Bb F C
MAJOR = [(53, 57, 60), (48, 52, 55), (50, 53, 57), (46, 50, 53)]  # F C Dm Bb
HOOK = [12, 7, 9, 7, 12, 14, 12, 7]  # semitones above the chord root

N = int(LENGTH_S * SR)
L = np.zeros(N)
R = np.zeros(N)
rng = np.random.default_rng(11)


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def t_axis(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def osc(f: float, dur: float, harm: int = 6, tilt: float = 1.6,
        detune: float = 0.0) -> np.ndarray:
    t = t_axis(dur)
    out = np.zeros_like(t)
    for n in range(1, harm + 1):
        out += np.sin(2 * np.pi * f * n * (1 + detune) * t) / n ** tilt
    return out


def adsr(n: int, a: float, r: float) -> np.ndarray:
    env = np.ones(n)
    ai, ri = max(1, int(a * SR)), max(1, int(r * SR))
    env[:ai] = np.linspace(0, 1, ai)
    env[-ri:] = np.minimum(env[-ri:], np.linspace(1, 0, ri))
    return env


def put(sig: np.ndarray, start: float, pan: float = 0.5) -> None:
    i = int(start * SR)
    if i >= N:
        return
    j = min(N, i + len(sig))
    L[i:j] += sig[: j - i] * (1 - pan) * 2 ** 0.5
    R[i:j] += sig[: j - i] * pan * 2 ** 0.5


def lowpassed_noise(dur: float, cutoff: float) -> np.ndarray:
    x = rng.standard_normal(int(dur * SR))
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= 1 / (1 + (freqs / cutoff) ** 4)
    y = np.fft.irfft(spec, len(x))
    return y / (np.max(np.abs(y)) + 1e-9)


def highpassed_noise(dur: float, cutoff: float) -> np.ndarray:
    x = rng.standard_normal(int(dur * SR))
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= (freqs / cutoff) ** 4 / (1 + (freqs / cutoff) ** 4)
    y = np.fft.irfft(spec, len(x))
    return y / (np.max(np.abs(y)) + 1e-9)


# ------------------------------------------------------------- instruments
def pad(chord, start: float, dur: float, gain: float) -> None:
    env = adsr(int((dur + 1.0) * SR), 0.9, 1.3)
    for m in chord:
        for oct_, g in ((12, 1.0), (24, 0.45)):
            put(gain * g * env * osc(hz(m + oct_), dur + 1.0, detune=-0.004), start, 0.25)
            put(gain * g * env * osc(hz(m + oct_), dur + 1.0, detune=0.004), start, 0.75)


def bass(m: int, start: float, dur: float, gain: float) -> None:
    sig = gain * adsr(int(dur * SR), 0.005, 0.08) * osc(hz(m - 12), dur, 4, 1.8)
    put(sig, start)


def pluck(m: int, start: float, gain: float, pan: float = 0.5,
          decay: float = 0.22) -> None:
    d = 0.9
    t = t_axis(d)
    put(gain * np.exp(-t / decay) * osc(hz(m), d, 5, 2.0), start, pan)


def bell(m: int, start: float, gain: float) -> None:
    d = 2.5
    t = t_axis(d)
    sig = np.exp(-t / 0.7) * (np.sin(2 * np.pi * hz(m) * t)
                              + 0.4 * np.sin(2 * np.pi * hz(m) * 2.76 * t))
    put(gain * sig, start, 0.6)


def kick(start: float, gain: float) -> None:
    t = t_axis(0.35)
    f = 48 + 90 * np.exp(-t / 0.025)
    put(gain * np.exp(-t / 0.11) * np.sin(2 * np.pi * np.cumsum(f) / SR), start)


def clap(start: float, gain: float) -> None:
    d = 0.18
    env = np.exp(-t_axis(d) / 0.045)
    put(gain * env * highpassed_noise(d, 1200), start, 0.55)


def hat(start: float, gain: float, open_: bool = False) -> None:
    d = 0.25 if open_ else 0.05
    env = np.exp(-t_axis(d) / (0.08 if open_ else 0.012))
    put(gain * env * highpassed_noise(d, 7000), start, 0.62)


def riser(end: float, dur: float, gain: float) -> None:
    n = int(dur * SR)
    ramp = np.linspace(0, 1, n) ** 2.2
    sweep = np.concatenate([lowpassed_noise(dur / 4, c)[: n // 4]
                            for c in (600, 1500, 3500, 8000)])
    sweep = np.pad(sweep, (0, n - len(sweep)))
    put(gain * ramp * sweep, end - dur)


def impact(start: float, gain: float) -> None:
    t = t_axis(2.0)
    boom = np.exp(-t / 0.5) * np.sin(2 * np.pi * (40 + 30 * np.exp(-t / 0.1)) * t)
    put(gain * boom, start)
    put(0.35 * gain * np.exp(-t / 0.6) * highpassed_noise(2.0, 4000), start)


# ------------------------------------------------------------- arrangement
def bars(start: float, end: float):
    t = start
    k = 0
    while t < end - 0.05:
        yield k, t
        t += BAR
        k += 1


def groove(start: float, end: float, *, prog, drums: float, lead: float,
           arp: float, bass_g: float, pad_g: float) -> None:
    for k, t in bars(start, end):
        chord = prog[(k // 2) % len(prog)] if prog is MINOR else prog[k % len(prog)]
        root = chord[0]
        if k % (2 if prog is MINOR else 1) == 0:
            pad(chord, t, BAR * (2 if prog is MINOR else 1), pad_g)
        for b in range(8):  # eighth notes
            tb = t + b * BEAT / 2
            if tb >= end:
                break
            if bass_g:
                bass(root if b % 4 != 3 else root + 7, tb, BEAT / 2 * 0.9, bass_g)
            if arp:
                notes = [chord[0] + 24, chord[1] + 24, chord[2] + 24, chord[1] + 24]
                pluck(notes[b % 4], tb, arp, 0.3 if b % 2 else 0.7, 0.15)
            if drums:
                if b % 2 == 0:
                    kick(tb, 0.55 * drums)
                else:
                    hat(tb, 0.08 * drums, open_=(b == 7))
                if b in (2, 6):
                    clap(tb, 0.22 * drums)
        if lead and k % 2 == 0:
            for i, iv in enumerate(HOOK):
                tl = t + i * BEAT / 2
                if tl < end:
                    pluck(root + 12 + iv, tl, lead, 0.5, 0.3)


def main() -> None:
    # Intro: swell into the first hit.
    pad(MAJOR[0], INTRO, PROBLEM - INTRO, 0.030)
    riser(PROBLEM, 4.0, 0.10)
    impact(PROBLEM, 0.35)

    # Problem: tense minor, pulsing bass, ticking hats, no kick.
    groove(PROBLEM, HOW, prog=MINOR, drums=0.0, lead=0.0, arp=0.0,
           bass_g=0.10, pad_g=0.030)
    for k, t in bars(PROBLEM, HOW):
        for b in range(8):
            hat(t + b * BEAT / 2, 0.05)

    # How it works: brighter, building arpeggio.
    groove(HOW, DEMOS, prog=MAJOR, drums=0.0, lead=0.0, arp=0.035,
           bass_g=0.07, pad_g=0.034)
    riser(DEMOS, 6.0, 0.12)
    impact(DEMOS, 0.4)

    # Demos: confident groove with the hook.
    groove(DEMOS, ASK, prog=MAJOR, drums=1.0, lead=0.040, arp=0.025,
           bass_g=0.10, pad_g=0.028)

    # ASK: breakdown, pads + soft arp only.
    groove(ASK, LEARN, prog=MAJOR, drums=0.0, lead=0.0, arp=0.030,
           bass_g=0.0, pad_g=0.036)

    # Learner: rebuild (bass + half drums), riser into the results.
    groove(LEARN, BENCH, prog=MAJOR, drums=0.6, lead=0.0, arp=0.035,
           bass_g=0.09, pad_g=0.030)
    riser(BENCH, 5.0, 0.12)
    impact(BENCH, 0.45)

    # Benchmark: fullest section.
    groove(BENCH, OUTRO, prog=MAJOR, drums=1.0, lead=0.048, arp=0.030,
           bass_g=0.11, pad_g=0.032)

    # Outro: resolve on F with a bell motif.
    impact(OUTRO, 0.25)
    pad(MAJOR[1], OUTRO, BAR * 2, 0.034)
    pad(MAJOR[3], OUTRO + BAR * 2, BAR * 2, 0.034)
    pad(MAJOR[0], OUTRO + BAR * 4, END - OUTRO - BAR * 4 + 2, 0.036)
    for i, m in enumerate((77, 72, 74, 69, 72, 77)):
        bell(m, OUTRO + i * BEAT * 1.5, 0.05)

    # Echo, master fade-in/out, normalise to -1 dBFS.
    d = int(0.75 * BEAT * SR)
    for ch in (L, R):
        wet = np.zeros_like(ch)
        wet[d:] = ch[:-d] * 0.22
        ch += wet
    fade = np.ones(N)
    fi, fo = int(1.5 * SR), int(5.0 * SR)
    fade[:fi] = np.linspace(0, 1, fi)
    end_i = int(END * SR)
    fade[end_i - fo:end_i] = np.linspace(1, 0, fo)
    fade[end_i:] = 0
    stereo = np.stack([L * fade, R * fade], axis=1)
    stereo = np.tanh(stereo / np.max(np.abs(stereo)) * 1.4)  # gentle glue
    stereo *= 0.89 / np.max(np.abs(stereo))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
