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
  CreditsV23,
  HowV23,
  IntroV23,
  KnifeDemoV23,
  LearnerV23,
  OutroV23,
  ProblemV23,
  StickyV23,
} from "./scenes_v23";
import { BenchV17 } from "./scenes_v17";
import { LiveV15 } from "./scenes_v15";
import { ColdV12 } from "./scenes_v12";
import {
  WaterDemoV4,
} from "./scenes_v4";
import timeline from "./timeline_v23.json";
import { FPS, sec } from "./ui";

// V23: accuracy + credits cut — knife hand-over without the false
// BLOCK, Meta models named in the first 50 s, verdict badges + Why?
// chip + core-rule footer in How, credits scene, honest-limits line,
// no black gap at the sticky->bench cut. Music ducking is the
// untouched Root.tsx logic.
const SCENES: Record<string, React.FC> = {
  cold: ColdV12,
  intro: IntroV23,
  problem: ProblemV23,
  how: HowV23,
  knife: KnifeDemoV23,
  water: WaterDemoV4,
  sticky: StickyV23,
  bench: BenchV17,
  learner: LearnerV23,
  live: LiveV15,
  credits: CreditsV23,
  outro: OutroV23,
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

export const RemotionRootV23: React.FC = () => (
  <Composition
    id="SentinelV23"
    component={Video}
    durationInFrames={TOTAL}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
