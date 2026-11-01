import React from "react";
import {
  Audio,
  Composition,
  Sequence,
  Series,
  interpolate,
  staticFile,
} from "remotion";
import { LiveV15 } from "./scenes_v15";
import { ColdV12 } from "./scenes_v12";
import { HowV8, KnifeDemoV8 } from "./scenes_v8";
import { IntroV2 } from "./scenes_v2";
import {
  BenchV4,
  HaltV4,
  ProblemV4,
  StickyV4,
  WaterDemoV4,
} from "./scenes_v4";
import { StackV6 } from "./scenes_v6";
import { LearningV16, OutroV16 } from "./scenes_v16";
import timeline from "./timeline_v16.json";
import { FPS, sec } from "./ui";

// V16: v15 with the learner + Rules-tab scenes merged into one learning
// loop (LearningV16) and the outro link timing fixed (OutroV16).
// Music ducking is the untouched Root.tsx logic.
const SCENES: Record<string, React.FC> = {
  cold: ColdV12,
  intro: IntroV2,
  problem: ProblemV4,
  how: HowV8,
  knife: KnifeDemoV8,
  water: WaterDemoV4,
  sticky: StickyV4,
  halt: HaltV4,
  bench: BenchV4,
  learner: LearningV16,
  live: LiveV15,
  stack: StackV6,
  outro: OutroV16,
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

export const RemotionRootV16: React.FC = () => (
  <Composition
    id="SentinelV16"
    component={Video}
    durationInFrames={TOTAL}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
