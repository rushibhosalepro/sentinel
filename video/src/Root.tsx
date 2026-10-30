import React from "react";
import {
  Audio,
  Composition,
  Sequence,
  Series,
  interpolate,
  staticFile,
} from "remotion";
import {
  Bench,
  Cold,
  Halt,
  How,
  Intro,
  KnifeDemo,
  Learner,
  Live,
  Outro,
  Problem,
  Stack,
  Sticky,
  WaterDemo,
  Why,
} from "./scenes";
import timeline from "./timeline.json";
import { FPS, sec } from "./ui";

// Scene order and lengths come from timeline.json (scripts/voice_timing.py):
// each scene is long enough for its visuals and its narration.
const SCENES: Record<string, React.FC> = {
  cold: Cold,
  intro: Intro,
  problem: Problem,
  how: How,
  knife: KnifeDemo,
  water: WaterDemo,
  why: Why,
  sticky: Sticky,
  halt: Halt,
  bench: Bench,
  learner: Learner,
  live: Live,
  stack: Stack,
  outro: Outro,
};

const VOICE_LEAD = sec(0.4);
const TOTAL = timeline.reduce((n, s) => n + sec(s.dur), 0);

// Narration windows in global frames, for ducking the music under speech.
const VOICE_WINDOWS = timeline
  .filter((s) => s.voice > 0)
  .map((s) => [sec(s.start) + VOICE_LEAD, sec(s.start) + VOICE_LEAD + sec(s.voice)]);

const musicVolume = (f: number) => {
  const inVoice = VOICE_WINDOWS.some(([a, b]) => f >= a - 8 && f <= b + 8);
  const near = VOICE_WINDOWS.reduce((d, [a, b]) => {
    if (f >= a && f <= b) return 0;
    return Math.min(d, f < a ? a - f : f - b);
  }, 999);
  const duck = inVoice ? 0.32 : interpolate(near, [8, 20], [0.32, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(f, [TOTAL - sec(3), TOTAL], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return 0.5 * duck * fadeOut;
};

const Video: React.FC = () => (
  <>
    <Audio src={staticFile("music.mp3")} volume={musicVolume} />
    <Series>
      {timeline.map((s) => {
        const Scene = SCENES[s.id];
        return (
          <Series.Sequence key={s.id} durationInFrames={sec(s.dur)}>
            <Scene />
            {s.voice > 0 ? (
              <Sequence from={VOICE_LEAD} layout="none">
                <Audio src={staticFile(`voice/${s.id}.mp3`)} volume={1} />
              </Sequence>
            ) : null}
          </Series.Sequence>
        );
      })}
    </Series>
  </>
);

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Sentinel"
    component={Video}
    durationInFrames={TOTAL}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
