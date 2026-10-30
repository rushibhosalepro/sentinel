import React from "react";
import { Composition, Series } from "remotion";
import {
  Ask,
  Bench,
  Halt,
  How,
  Intro,
  KnifeDemo,
  Learner,
  Outro,
  Problem,
  Stack,
  Sticky,
  WaterDemo,
  Why,
} from "./scenes";
import { FPS, sec } from "./ui";

const SCENES: [React.FC, number][] = [
  [Intro, 6],
  [Problem, 11],
  [How, 20],
  [KnifeDemo, 19],
  [WaterDemo, 12],
  [Why, 11],
  [Sticky, 12],
  [Halt, 18],
  [Ask, 9],
  [Learner, 22],
  [Bench, 19],
  [Stack, 11],
  [Outro, 8],
];

const TOTAL = SCENES.reduce((n, [, s]) => n + sec(s), 0);

const Video: React.FC = () => (
  <Series>
    {SCENES.map(([Scene, s], i) => (
      <Series.Sequence key={i} durationInFrames={sec(s)}>
        <Scene />
      </Series.Sequence>
    ))}
  </Series>
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
