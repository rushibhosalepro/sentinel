import React from "react";
import {
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {
  Badge,
  C,
  Kicker,
  Lane,
  MONO,
  SceneFade,
  Shot,
  sec,
  useEnter,
} from "./ui";

// V8: How fixes — the plans box keeps the round-1 text while BLOCK is
// on screen (flips exactly when ALLOW lands); the check box shrinks to
// the ALLOW badge instead of keeping the BLOCK height, with a longer
// green arrow down to the moves box; the amber return arrow lands in
// the plans box's left edge so the loop reads connected. Beats frozen.
const HOW_T8 = {
  tags: 2.8, plan: 4.7, sim: 5.9, check: 7.2, block: 7.6, fix: 8.7,
  plan2: 9.8, check2: 10.6, allow: 11.1, move: 11.9,
};
const TAGS8 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 2.8 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 3.1 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 3.4 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 3.7 },
];
const COL8 = { x: 480, w: 330, cx: 645 };

const LoopNode8: React.FC<{
  x: number; y: number; w: number; title: string;
  sub: React.ReactNode; color: string; lit: number; show: number;
}> = ({ x, y, w, title, sub, color, lit, show }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: w,
      borderRadius: 16,
      padding: "14px 20px",
      background: C.panel,
      border: `3px solid ${lit > 0.5 ? color : C.line}`,
      boxShadow: lit > 0.5 ? `0 0 26px ${color}66` : "none",
      opacity: show,
    }}
  >
    <div style={{ fontSize: 32, fontWeight: 800, color: lit > 0.5 ? C.text : C.dim }}>{title}</div>
    <div style={{ fontSize: 24, marginTop: 6 }}>{sub}</div>
  </div>
);

export const HowV8: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const between = (a: number, b: number) => (frame >= sec(a) && frame < sec(b) ? 1 : 0);
  const allowed = frame >= sec(HOW_T8.allow);
  const IW = 760;
  const k = IW / 890;
  const IH = 600 * k;
  const arrow = (d: string, t: number, color: string, len: number, w = 5) => (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={w}
      strokeLinecap="round"
      strokeDasharray={len}
      strokeDashoffset={len * (1 - at(t, 14))}
      opacity={at(t, 14) > 0.02 ? 1 : 0}
      markerEnd={`url(#head8-${color.slice(1)})`}
    />
  );
  const heads = [C.text, C.amber, C.green, C.dim];
  const dimFix = interpolate(frame, [sec(HOW_T8.allow), sec(HOW_T8.allow) + 9], [1, 0.3], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          padding: "60px 100px",
          display: "flex",
          flexDirection: "column",
          gap: 26,
        }}
      >
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 26 }}>
          <Kicker>How it works</Kicker>
          <span style={{ fontSize: 40, fontWeight: 800 }}>Sentinel puts the model in a loop</span>
        </div>
        <div style={{ display: "flex", gap: 46, alignItems: "flex-start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div
              style={{
                position: "relative",
                width: IW,
                height: IH,
                borderRadius: 14,
                overflow: "hidden",
                border: `2px solid ${C.line}`,
              }}
            >
              <Img src={staticFile("how_frame.png")} style={{ position: "absolute", width: IW, height: IH }} />
              <Img
                src={staticFile("how_masks.png")}
                style={{ position: "absolute", width: IW, height: IH, opacity: at(2.2, 20) }}
              />
              {TAGS8.map((g) => (
                <span
                  key={g.t}
                  style={{
                    position: "absolute",
                    left: g.x * k,
                    top: g.y * k,
                    transform: "translate(-50%, -100%)",
                    opacity: at(g.at, 8),
                    background: "rgba(8,10,14,0.88)",
                    border: `3px solid ${g.c}`,
                    color: "#fff",
                    fontSize: 24,
                    fontWeight: 800,
                    padding: "4px 10px",
                    borderRadius: 8,
                    whiteSpace: "nowrap",
                  }}
                >
                  {g.t}
                </span>
              ))}
            </div>
            <div style={{ opacity: at(2.2), fontSize: 24, color: C.dim }}>
              SAM 3.1 + Muse Spark tag the scene: what's sharp, liquid, electronic
            </div>
            <div style={{ opacity: at(1.2), fontFamily: MONO, fontSize: 30 }}>
              "pour some water into the cup"
            </div>
            <div style={{ opacity: at(HOW_T8.move + 0.4), marginTop: 26 }}>
              <div style={{ fontSize: 40, fontWeight: 800 }}>no LLM in the verdict</div>
              <div style={{ fontSize: 38, color: C.dim, marginTop: 6, lineHeight: 1.45 }}>
                up to 3 rounds · hard violations are never retried
              </div>
            </div>
          </div>
          <div style={{ position: "relative", width: 840, height: 700 }}>
            <svg width={840} height={700} style={{ position: "absolute", inset: 0 }}>
              <defs>
                {heads.map((c) => (
                  <marker
                    key={c}
                    id={`head8-${c.slice(1)}`}
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="5"
                    markerHeight="5"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
                  </marker>
                ))}
              </defs>
              {arrow("M 345 70 L 470 70", HOW_T8.sim - 0.4, C.text, 125)}
              {arrow(`M ${COL8.cx} 152 L ${COL8.cx} 244`, HOW_T8.check - 0.4, C.text, 92)}
              {arrow(`M ${COL8.cx} 378 L ${COL8.cx} 584`, HOW_T8.move, C.green, 206, 6)}
              {arrow("M 4 472 C 2 380, 2 200, 4 120 C 4 95, 2 82, 14 78", HOW_T8.fix, C.amber, 410, 7)}
            </svg>
            <LoopNode8
              x={10}
              y={18}
              w={330}
              title="Muse Spark plans"
              color={C.purple}
              lit={between(HOW_T8.plan, HOW_T8.sim) || between(HOW_T8.plan2, HOW_T8.check2)}
              show={at(HOW_T8.plan)}
              sub={
                <span style={{ fontFamily: MONO, color: C.dim, opacity: at(HOW_T8.plan) }}>
                  {allowed ? "round 2: move cup, then pour" : "grasp jug → over cup → pour"}
                </span>
              }
            />
            <LoopNode8
              x={COL8.x}
              y={18}
              w={COL8.w}
              title="Dry-run"
              color={C.blue}
              lit={between(HOW_T8.sim, HOW_T8.check) || between(HOW_T8.plan2 + 0.5, HOW_T8.check2)}
              show={at(HOW_T8.sim)}
              sub={<span style={{ color: C.dim }}>every pose, before it moves</span>}
            />
            <LoopNode8
              x={COL8.x}
              y={250}
              w={COL8.w}
              title="Fixed rules check"
              color={allowed ? C.green : C.red}
              lit={between(HOW_T8.check, HOW_T8.fix + 0.6) || between(HOW_T8.check2, 99)}
              show={at(HOW_T8.check)}
              sub={
                allowed ? (
                  <span style={{ opacity: at(HOW_T8.allow) }}>
                    <Badge color={C.green}>ALLOW</Badge>
                  </span>
                ) : (
                  <span style={{ opacity: at(HOW_T8.block), fontFamily: MONO, fontSize: 40 }}>
                    <span style={{ color: C.red, fontWeight: 800 }}>BLOCK</span>
                    <br />
                    <span style={{ color: C.text }}>liquid near</span>
                    <br />
                    <span style={{ color: C.text }}>laptop</span>
                    <br />
                    <span style={{ color: C.text }}>14.9 cm</span>
                    <br />
                    <span style={{ color: C.text }}>&lt; 15 cm</span>
                  </span>
                )
              }
            />
            <div
              style={{
                position: "absolute",
                left: 10,
                top: 330,
                width: 450,
                opacity: at(HOW_T8.fix) * dimFix,
              }}
            >
              <div style={{ fontSize: 36, fontWeight: 700, color: C.amber }}>
                BLOCK + a concrete fix:
              </div>
              <div style={{ fontFamily: MONO, fontSize: 44, color: C.amber, marginTop: 6 }}>
                move the cup to
                <br />
                (0.20, 0.15)
              </div>
            </div>
            <LoopNode8
              x={COL8.x}
              y={590}
              w={COL8.w}
              title="The arm moves"
              color={C.green}
              lit={frame >= sec(HOW_T8.move) ? 1 : 0}
              show={at(HOW_T8.move)}
              sub={<span style={{ color: C.dim }}>live monitor still watching</span>}
            />
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- knife demo
// V8: lane B holds (dimmed) until the narration reaches "On the right"
// (~9.5 s in), then plays the rotation + handover; the footer lands
// with the freeze. Lane A untouched.
const LANE_W8 = 840;
const KNIFE_B_DELAY8 = 285;

export const KnifeDemoV8: React.FC = () => {
  const head = useEnter(0);
  return (
  <SceneFade>
    <div
      style={{
        position: "absolute",
        inset: 0,
        padding: "60px 100px",
        display: "flex",
        flexDirection: "column",
        gap: 26,
      }}
    >
      <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
        <Kicker>Demo 1</Kicker>
        <span style={{ fontFamily: MONO, fontSize: 48 }}>"hand me the knife"</span>
      </div>
      <div style={{ display: "flex", gap: 60 }}>
        <Lane
          label="A · WITHOUT SENTINEL"
          color={C.red}
          sub="same Muse Spark, no checks"
          footer="Owner takes the knife by the blade"
          footerDelay={90}
        >
          <Shot
            name="knife_A_close_v7"
            frames={228}
            width={LANE_W8}
            startFrom={70}
            zoom={{ from: 100, to: 125, cx: 295, cy: 240, scale: 1.6 }}
            freezeAt={130}
            pushIn={0.08}
            marks={[{ at: 120, x: 295, y: 240, r: 34, color: C.red }]}
            stamps={[{ at: 130, text: "Blade points at the hand", color: C.red }]}
          />
        </Lane>
        <Lane
          label="B · WITH SENTINEL"
          color={C.green}
          sub="Muse Spark × Sentinel loop"
          footer="Checked before moving: handle first, slow near the person"
          footerDelay={400}
        >
          <Shot
            name="knife_B_close"
            frames={431}
            width={LANE_W8}
            startFrom={100}
            delay={KNIFE_B_DELAY8}
            dimHold
            zoom={{ from: 185, to: 205, cx: 292, cy: 245, scale: 1.6 }}
            freezeAt={210}
            pushIn={0.08}
            marks={[{ at: 200, x: 292, y: 245, r: 34, color: C.green }]}
            stamps={[
              { at: 100, until: 140, text: "Rotates handle-first", color: C.green },
              { at: 150, until: 185, text: "Sentinel: blade direction + speed checked", color: C.green },
              { at: 210, text: "Handle to the hand · slowed", color: C.green },
            ]}
          />
        </Lane>
      </div>
    </div>
  </SceneFade>
  );
};
