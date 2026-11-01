import React from "react";
import {
  AbsoluteFill,
} from "remotion";
import {
  Badge,
  C,
  MONO,
  SceneFade,
  Shot,
  useEnter,
} from "./ui";

// V12: the simulation label sits in-flow below the caption (the absolute
// top badge overlapped the caption on some frames) and reads as a plain
// statement of what the footage is.
export const ColdV12: React.FC = () => {
  const cap = useEnter(0);
  return (
    <SceneFade>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 36 }}>
        <div style={{ ...cap, fontSize: 32, color: C.dim }}>
          <span style={{ fontFamily: MONO, color: C.text }}>"hand me the knife"</span>
          {"  ·  "}an LLM-planned robot arm, no safety layer
        </div>
        <div style={cap}>
          <Badge color={C.blue}>ROBOT SIMULATION IN MUJOCO</Badge>
        </div>
        <Shot
          name="knife_A_close_v7"
          frames={228}
          width={1180}
          startFrom={70}
          zoom={{ from: 100, to: 125, cx: 295, cy: 240, scale: 1.6 }}
          freezeAt={130}
          marks={[{ at: 120, x: 295, y: 240, r: 34, color: C.red }]}
          stamps={[{ at: 130, text: "Blade first. Into a hand.", color: C.red }]}
        />
      </AbsoluteFill>
    </SceneFade>
  );
};
