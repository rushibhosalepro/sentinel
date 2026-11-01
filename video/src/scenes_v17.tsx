import React from "react";
import {
  interpolate,
  useCurrentFrame,
} from "remotion";
import {
  C,
  Kicker,
  SceneFade,
  Title,
  sec,
  useEnter,
} from "./ui";
const padV17: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};

// V17: BenchV4 with judge-readable baseline names ("LLM as judge" ->
// "LLM checks its own plan", "Sentinel veto only" -> "Sentinel, block
// only" to match the Problem slide). The name column is wider to fit.
const BARS17 = [
  { name: "LLM alone (naive)", v: 60.4, sd: 2.4, c: C.red },
  { name: "LLM checks its own plan", v: 44.3, sd: 2.4, c: C.amber },
  { name: "Sentinel, block only", v: 29.7, sd: 1.6, c: C.blue },
  { name: "LLM × Sentinel loop", v: 18.8, sd: 1.6, c: C.green },
];

export const BenchV17: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const note = useEnter(sec(6));
  const limit = useEnter(sec(10));
  const maxW = 980;
  return (
    <SceneFade>
      <div style={{ ...padV17, gap: 40 }}>
        <div style={head}>
          <Kicker>Benchmark · all 128 scenarios</Kicker>
          <Title size={54}>Unsafe actions executed (lower is better)</Title>
          <div style={{ fontSize: 30, color: C.dim, marginTop: 8 }}>
            3 independent repeats · 10 hazard categories · half are safe controls · labels
            frozen before the first run
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {BARS17.map((b, i) => {
            const grow = interpolate(frame, [sec(1.5) + i * 25, sec(1.5) + 40 + i * 25], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <div key={b.name} style={{ display: "flex", alignItems: "center", gap: 24 }}>
                <div style={{ width: 470, fontSize: 32, textAlign: "right" }}>{b.name}</div>
                <div
                  style={{
                    width: (maxW * b.v * grow) / 65,
                    height: 60,
                    background: b.c,
                    borderRadius: 8,
                  }}
                />
                <div style={{ fontSize: 40, fontWeight: 800, opacity: grow }}>
                  {(b.v * grow).toFixed(1)}%
                  <span style={{ fontSize: 30, color: C.dim, fontWeight: 400 }}> ± {b.sd}</span>
                </div>
              </div>
            );
          })}
        </div>
        <div style={{ ...note, fontSize: 32 }}>
          Same planner, same scenes: about <b style={{ color: C.green }}>70% fewer</b> unsafe
          executions, while safe tasks still succeed 82% of the time (naive 83%).
        </div>
        <div style={{ ...limit, fontSize: 30, color: C.dim }}>
          Not zero yet. Most misses are hazards no rule covers, which is what the rule learner is
          for.
        </div>
      </div>
    </SceneFade>
  );
};
