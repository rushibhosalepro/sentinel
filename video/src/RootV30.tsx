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
  ColdV27,
  IntroV27,
  KnifeDemoV27,
  LoopV27,
  MemoryV27,
  OutroV27,
  WaterDemoV27,
} from "./scenes_v27";
import { ProblemV28 } from "./scenes_v28";
import {
  StickyV23,
} from "./scenes_v23";
import {
  BenchV29,
  BridgeV29,
  HowV29,
} from "./scenes_v29";
import {
  LiveV30,
} from "./scenes_v30";
import timeline from "./timeline_v30.json";
import { FPS, sec } from "./ui";

// V30: v29 scenes, except live (loading cut, +2 s of robot action) and the
// outro voice (last line dropped; visual unchanged, it fits 6.3 s). Music
// ducking is the untouched RootV28 logic.
const SCENES: Record<string, React.FC> = {
  cold: ColdV27,
  intro: IntroV27,
  problem: ProblemV28,
  bridge: BridgeV29,
  how: HowV29,
  loop: LoopV27,
  memory: MemoryV27,
  knife: KnifeDemoV27,
  water: WaterDemoV27,
  sticky: StickyV23,
  bench: BenchV29,
  live: LiveV30,
  outro: OutroV27,
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

export const RemotionRootV30: React.FC = () => (
  <Composition
    id="SentinelV30"
    component={Video}
    durationInFrames={TOTAL}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
