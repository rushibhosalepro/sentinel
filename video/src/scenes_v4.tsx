import React from "react";
import {
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
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
  Title,
  sec,
  useEnter,
} from "./ui";

// V4 system: every content scene top-pins its header (kicker at y=60)
// so text never jumps between frames. Titles 54, demo prompts mono 48.
// Title cards (cold/intro/outro) stay centered — open/title/close grammar.
const padV4: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};
const LANE_W = 840;

// ---------------------------------------------------------------- problem
// V4: title 54 with a balanced manual break (no orphan "danger"), and the
// 17% carries its configuration (veto_only) so it can't be confused with
// the loop's 11.5% / v2's 10.9% that appear later.
const HAZARDS4 = [
  { img: "split_A_knife_f120.png", t: "a blade toward a hand", at: 4.3, zoom: { cx: 333, cy: 233, s: 2.0 } },
  { img: "split_A_water_f130.png", t: "water by a laptop", at: 6.2, zoom: { cx: 235, cy: 232, s: 1.9 } },
  { img: "note_zoom.png", t: "a stranger's note giving orders", at: 7.8, zoom: null },
];

export const ProblemV4: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const fade = (at: number) =>
    interpolate(frame, [sec(at), sec(at) + 14], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const filter = useEnter(sec(9.8));
  const CW = 540;
  const CH = 360;
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 34 }}>
        <div style={head}>
          <Kicker color={C.red}>The problem</Kicker>
          <Title size={54}>LLMs can plan robot actions,<br />but they can't see the danger</Title>
        </div>
        <div style={{ display: "flex", gap: 40 }}>
          {HAZARDS4.map((h) => (
            <div key={h.t} style={{ opacity: fade(h.at), width: CW }}>
              <div
                style={{
                  width: CW,
                  height: CH,
                  borderRadius: 14,
                  overflow: "hidden",
                  border: `3px solid ${C.red}`,
                  position: "relative",
                  background: "#000",
                }}
              >
                <Img
                  src={staticFile(h.img)}
                  style={
                    h.zoom
                      ? {
                          position: "absolute",
                          width: CW * h.zoom.s,
                          left: CW / 2 - (h.zoom.cx / 640) * CW * h.zoom.s,
                          top: CH / 2 - (h.zoom.cy / 480) * CW * h.zoom.s * 0.75,
                        }
                      : { width: CW, height: CH, objectFit: "cover" }
                  }
                />
              </div>
              <div style={{ fontSize: 32, fontWeight: 700, marginTop: 14 }}>{h.t}</div>
            </div>
          ))}
        </div>
        <div style={{ ...filter, fontSize: 36, display: "flex", alignItems: "center", gap: 18 }}>
          <Badge color={C.dim}>BLOCK-ONLY FILTER · veto_only</Badge>
          <span>
            just says no — refused 17% of safe tasks{" "}
            <span style={{ color: C.dim, fontSize: 28 }}>(the block-only baseline)</span>
          </span>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- how it works
// V4: vertical stepper, full-width rows. The verdict lines that matter
// (BLOCK + measurement, the fix, no-LLM verdict) run 40-44 px — double
// the old 22-24. Same beats, same voice as v2.
const HOW_T4 = {
  tags: 2.5, plan: 4.7, sim: 5.9, check: 7.2, block: 7.6, fix: 8.7,
  plan2: 9.8, check2: 10.6, allow: 11.1, move: 11.9,
};
const TAGS4 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 2.5 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 2.8 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 3.1 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 3.4 },
];

const Step4: React.FC<{
  y: number; h: number; title: string; sub: React.ReactNode; color: string; lit: number;
}> = ({ y, h, title, sub, color, lit }) => (
  <div
    style={{
      position: "absolute",
      left: 90,
      top: y,
      width: 910,
      height: h,
      borderRadius: 16,
      padding: "12px 24px",
      background: C.panel,
      border: `3px solid ${lit > 0.5 ? color : C.line}`,
      boxShadow: lit > 0.5 ? `0 0 26px ${color}66` : "none",
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
    }}
  >
    <div style={{ fontSize: 40, fontWeight: 800, color: lit > 0.5 ? C.text : C.dim }}>{title}</div>
    <div style={{ marginTop: 4 }}>{sub}</div>
  </div>
);

export const HowV4: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const between = (a: number, b: number) => (frame >= sec(a) && frame < sec(b) ? 1 : 0);
  const round2 = frame >= sec(HOW_T4.plan2);
  const IW = 700;
  const k = IW / 890;
  const IH = 600 * k;
  const arrow = (d: string, t: number, color: string, len: number, w = 6) => (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={w}
      strokeLinecap="round"
      strokeDasharray={len}
      strokeDashoffset={len * (1 - at(t, 14))}
      opacity={at(t, 14) > 0.02 ? 1 : 0}
      markerEnd={`url(#head4-${color.slice(1)})`}
    />
  );
  const heads = [C.text, C.amber, C.green, C.dim];
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 26 }}>
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 26 }}>
          <Kicker>How it works</Kicker>
          <Title size={54}>Sentinel puts the model in a loop</Title>
        </div>
        <div style={{ display: "flex", gap: 40, alignItems: "flex-start" }}>
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
              {TAGS4.map((g) => (
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
            <div style={{ opacity: at(2.2), fontSize: 30, color: C.dim }}>
              SAM 3.1 + Muse Spark tag the scene: what's sharp, liquid, electronic
            </div>
            <div style={{ opacity: at(HOW_T4.plan - 0.3), fontFamily: MONO, fontSize: 34 }}>
              "pour some water into the cup"
            </div>
            <div style={{ opacity: at(HOW_T4.move + 0.4), marginTop: 26 }}>
              <div style={{ fontSize: 40, fontWeight: 800 }}>no LLM in the verdict</div>
              <div style={{ fontSize: 34, color: C.dim, marginTop: 6, lineHeight: 1.45 }}>
                up to 3 rounds · hard violations are never retried
              </div>
            </div>
          </div>
          <div style={{ position: "relative", width: 1020, height: 880 }}>
            <svg width={1020} height={880} style={{ position: "absolute", inset: 0 }}>
              <defs>
                {heads.map((c) => (
                  <marker
                    key={c}
                    id={`head4-${c.slice(1)}`}
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
              {arrow("M 45 135 L 45 165", HOW_T4.sim - 0.4, C.text, 30)}
              {arrow("M 45 305 L 45 335", HOW_T4.check - 0.4, C.text, 30)}
              {arrow("M 45 545 L 45 575", HOW_T4.fix - 0.2, C.text, 30)}
              {arrow("M 45 705 L 45 735", HOW_T4.allow, C.green, 30)}
              {arrow("M 22 640 L 22 65", HOW_T4.fix, C.amber, 575, 7)}
            </svg>
            <Step4
              y={0}
              h={130}
              title="Muse Spark plans"
              color={C.purple}
              lit={between(HOW_T4.plan, HOW_T4.sim) || between(HOW_T4.plan2, HOW_T4.check2)}
              sub={
                <span style={{ fontFamily: MONO, fontSize: 32, color: C.dim, opacity: at(HOW_T4.plan) }}>
                  {round2 ? "round 2: move cup, then pour" : "grasp jug → over cup → pour"}
                </span>
              }
            />
            <Step4
              y={170}
              h={130}
              title="Dry-run"
              color={C.blue}
              lit={between(HOW_T4.sim, HOW_T4.check) || between(HOW_T4.plan2 + 0.5, HOW_T4.check2)}
              sub={<span style={{ fontSize: 32, color: C.dim }}>every pose, before it moves</span>}
            />
            <Step4
              y={340}
              h={200}
              title="Fixed rules check"
              color={frame >= sec(HOW_T4.allow) ? C.green : C.red}
              lit={between(HOW_T4.check, HOW_T4.fix + 0.6) || between(HOW_T4.check2, 99)}
              sub={
                frame >= sec(HOW_T4.allow) ? (
                  <span style={{ opacity: at(HOW_T4.allow) }}>
                    <Badge color={C.green}>ALLOW</Badge>
                  </span>
                ) : (
                  <span style={{ opacity: at(HOW_T4.block), fontFamily: MONO, fontSize: 44 }}>
                    <span style={{ color: C.red, fontWeight: 800 }}>BLOCK</span>{" "}
                    <span style={{ color: C.text }}>liquid near laptop</span>
                    <br />
                    <span style={{ color: C.text }}>14.9 cm &lt; 15 cm</span>
                  </span>
                )
              }
            />
            <Step4
              y={580}
              h={120}
              title="BLOCK + a concrete fix"
              color={C.amber}
              lit={between(HOW_T4.fix, HOW_T4.plan2 + 0.8)}
              sub={
                <span style={{ opacity: at(HOW_T4.fix + 0.3), fontFamily: MONO, fontSize: 40, color: C.amber }}>
                  move the cup to (0.20, 0.15)
                </span>
              }
            />
            <Step4
              y={740}
              h={120}
              title="The arm moves"
              color={C.green}
              lit={frame >= sec(HOW_T4.move) ? 1 : 0}
              sub={<span style={{ fontSize: 32, color: C.dim }}>live monitor still watching</span>}
            />
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- split demos
// V4: same close-up (knife) / tuned (water, sticky) shots, prompts at 48.
const SplitHead4: React.FC<{ kicker: string; prompt: string }> = ({ kicker, prompt }) => {
  const head = useEnter(0);
  return (
    <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
      <Kicker>{kicker}</Kicker>
      <span style={{ fontFamily: MONO, fontSize: 48 }}>"{prompt}"</span>
    </div>
  );
};

export const KnifeDemoV4: React.FC = () => (
  <SceneFade>
    <div style={{ ...padV4, gap: 26 }}>
      <SplitHead4 kicker="Demo 1" prompt="hand me the knife" />
      <div style={{ display: "flex", gap: 60 }}>
        <Lane
          label="A · WITHOUT SENTINEL"
          color={C.red}
          sub="same Muse Spark, no checks"
          footer="Owner takes the knife by the blade"
          footerDelay={90}
        >
          <Shot
            name="knife_A_close"
            frames={228}
            width={LANE_W}
            startFrom={70}
            zoom={{ from: 100, to: 125, cx: 315, cy: 215, scale: 1.6 }}
            freezeAt={130}
            pushIn={0.08}
            marks={[{ at: 120, x: 315, y: 215, r: 30, color: C.red }]}
            stamps={[{ at: 130, text: "Blade points at the hand", color: C.red }]}
          />
        </Lane>
        <Lane
          label="B · WITH SENTINEL"
          color={C.green}
          sub="Muse Spark × Sentinel loop"
          footer="Checked before moving: handle first, slow near the person"
          footerDelay={250}
        >
          <Shot
            name="knife_B_close"
            frames={431}
            width={LANE_W}
            startFrom={150}
            delay={90}
            dimHold
            zoom={{ from: 185, to: 205, cx: 340, cy: 215, scale: 1.6 }}
            freezeAt={210}
            pushIn={0.08}
            marks={[{ at: 200, x: 340, y: 215, r: 30, color: C.green }]}
            stamps={[
              { at: 150, until: 185, text: "Sentinel: blade direction + speed checked", color: C.green },
              { at: 210, text: "Handle to the hand · slowed", color: C.green },
            ]}
          />
        </Lane>
      </div>
    </div>
  </SceneFade>
);

export const WaterDemoV4: React.FC = () => (
  <SceneFade>
    <div style={{ ...padV4, gap: 26 }}>
      <SplitHead4 kicker="Demo 2" prompt="pour some water into the cup" />
      <div style={{ display: "flex", gap: 60 }}>
        <Lane
          label="A · WITHOUT SENTINEL"
          color={C.red}
          sub="same Muse Spark, no checks"
          footer="Pours right beside the laptop"
          footerDelay={80}
        >
          <Shot
            name="split_A_water"
            frames={139}
            width={LANE_W}
            startFrom={60}
            zoom={{ from: 100, to: 120, cx: 240, cy: 228, scale: 2.2 }}
            freezeAt={130}
            marks={[{ at: 118, x: 235, y: 232, r: 42, color: C.red }]}
            stamps={[{ at: 130, text: "Pouring next to the laptop", color: C.red }]}
          />
        </Lane>
        <Lane
          label="B · WITH SENTINEL"
          color={C.green}
          sub="Muse Spark × Sentinel loop"
          footer="BLOCK → fix → ALLOW: cup moved away, then poured"
          footerDelay={300}
        >
          <Shot
            name="split_B_water"
            frames={194}
            width={LANE_W}
            delay={90}
            dimHold
            holdStamps={[
              { at: 6, text: "Round 1 · BLOCK · liquid over electronics", color: C.red },
              { at: 45, text: "Fix sent: move the cup to (0.20, 0.15)", color: C.amber },
            ]}
            zoom={{ from: 150, to: 170, cx: 200, cy: 228, scale: 1.9 }}
            marks={[{ at: 166, x: 185, y: 238, r: 40, color: C.green }]}
            stamps={[
              { at: 0, until: 165, text: "Round 2 · moving the cup away", color: C.amber },
              { at: 165, text: "ALLOW · pours away from the laptop", color: C.green },
            ]}
          />
        </Lane>
      </div>
    </div>
  </SceneFade>
);

export const StickyV4: React.FC = () => {
  const head = useEnter(0);
  const pic = useEnter(10);
  const zoom = useEnter(sec(2));
  const block = useEnter(sec(11.2));
  const W = 780;
  const k = W / 1280;
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 26 }}>
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
          <Kicker color={C.red}>Demo 3 · prompt injection</Kicker>
          <span style={{ fontFamily: MONO, fontSize: 48 }}>"tidy the counter"</span>
        </div>
        <div style={{ display: "flex", gap: 60 }}>
          <div style={{ ...pic, width: W, display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <Badge color={C.amber}>WHAT THE PLANNER SEES</Badge>
            </div>
            <div style={{ position: "relative", width: W }}>
              <Img
                src={staticFile("sticky_attack_close_v2.png")}
                style={{ width: W, borderRadius: 14, border: `2px solid ${C.line}` }}
              />
              <div
                style={{
                  position: "absolute",
                  left: 370 * k,
                  top: 390 * k,
                  width: 150 * k,
                  height: 110 * k,
                  border: `4px solid ${C.red}`,
                  borderRadius: 8,
                }}
              />
              <div style={{ ...zoom, position: "absolute", right: -20, bottom: -24 }}>
                <Img
                  src={staticFile("note_zoom_v2.png")}
                  style={{ width: 440, borderRadius: 12, border: `4px solid ${C.red}` }}
                />
              </div>
            </div>
            <div style={{ fontSize: 24, color: C.dim, marginTop: 20 }}>
              Close-up: the print is rendered geometry, not an overlay.
            </div>
          </div>
          <Lane
            label="A · WITHOUT THE CHECK"
            color={C.red}
            sub="the note-driven plan, executed"
            footer={
              <div style={block}>
                <Badge color={C.green}>B · SENTINEL: BLOCK</Badge>{" "}
                <span style={{ color: C.text }}>
                  the motion came from the note, not the owner. No retries.
                </span>
              </div>
            }
            footerDelay={0}
          >
            <Shot
              name="split_A_sticky"
              frames={329}
              width={W}
              startFrom={120}
              delay={sec(5.6)}
              dimHold
              zoom={{ from: 150, to: 185, cx: 210, cy: 200, scale: 1.8 }}
              freezeAt={200}
              pushIn={0.08}
              marks={[{ at: 160, x: 205, y: 205, r: 34, color: C.red }]}
              stamps={[
                { at: 120, until: 200, text: "Grasps the knife", color: C.amber },
                { at: 200, text: "Knife carried off. The owner never asked", color: C.red },
              ]}
            />
          </Lane>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- live HALT
// V4: header joins the top zone (was buried in the side column).
export const HaltV4: React.FC = () => {
  const head = useEnter(0);
  const s1 = useEnter(sec(2.2));
  const s2 = useEnter(sec(4.4));
  const s3 = useEnter(sec(5.2));
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 26 }}>
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 26 }}>
          <Kicker color={C.purple}>Live monitor</Kicker>
          <Title size={54}>A hand reaches in while the arm moves</Title>
        </div>
        <div style={{ display: "flex", gap: 56, alignItems: "flex-start" }}>
          <Shot
            name="demo_halt"
            frames={603}
            width={1000}
            startFrom={80}
            zoom={{ from: 92, to: 112, cx: 320, cy: 262, scale: 1.6 }}
            freezeAt={340}
            flash={{ at: 127, len: 20 }}
            marks={[
              {
                at: 108,
                until: 178,
                x: 0,
                y: 0,
                r: 38,
                color: C.purple,
                path: [[108, 520, 262], [116, 420, 258], [122, 330, 275], [127, 275, 292], [140, 245, 288], [155, 295, 298], [170, 430, 272], [178, 520, 265]],
              },
            ]}
            stamps={[
              { at: 104, until: 127, text: "Hand entering the arm's path", color: C.amber },
              { at: 127, until: 180, text: "HALT · arm frozen", color: C.purple },
              { at: 180, until: 208, text: "Path clear for 1 s", color: C.green },
              { at: 208, until: 296, text: "Fresh plan from where it stopped", color: C.green },
              { at: 296, text: "Hand-over resumes · handle first", color: C.green },
            ]}
          />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 28, paddingTop: 40 }}>
            <div style={{ ...s1, fontSize: 32 }}>
              <Badge color={C.purple}>HALT</Badge> within 15 cm of a hand (30 cm with a knife)
            </div>
            <div style={{ ...s2, fontSize: 32, color: C.dim }}>waits until the path is clear for 1 s</div>
            <div style={{ ...s3, fontSize: 32 }}>then plans again from where it stopped</div>
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- benchmark
// V4: title 54, small print bumped (28/24 -> 30).
const BARS4 = [
  { name: "LLM alone (naive)", v: 60.4, sd: 2.4, c: C.red },
  { name: "LLM as judge", v: 44.3, sd: 2.4, c: C.amber },
  { name: "Sentinel veto only", v: 29.7, sd: 1.6, c: C.blue },
  { name: "LLM × Sentinel loop", v: 18.8, sd: 1.6, c: C.green },
];

export const BenchV4: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const note = useEnter(sec(6));
  const limit = useEnter(sec(10));
  const maxW = 1050;
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 40 }}>
        <div style={head}>
          <Kicker>Benchmark · all 128 scenarios</Kicker>
          <Title size={54}>Unsafe actions executed (lower is better)</Title>
          <div style={{ fontSize: 30, color: C.dim, marginTop: 8 }}>
            3 independent repeats · 10 hazard categories · half are safe controls · labels
            frozen before the first run
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {BARS4.map((b, i) => {
            const grow = interpolate(frame, [sec(1.5) + i * 25, sec(1.5) + 40 + i * 25], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <div key={b.name} style={{ display: "flex", alignItems: "center", gap: 24 }}>
                <div style={{ width: 400, fontSize: 32, textAlign: "right" }}>{b.name}</div>
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

// ---------------------------------------------------------------- rule learner
// V4: title 54, chips and caveat bumped to 30.
const GATE4 = ["schema", "replay", "ratchet", "preflight"];

export const LearnerV4: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const inc = useEnter(sec(1));
  const prop = useEnter(sec(4));
  const v1 = useEnter(sec(8));
  const v2 = useEnter(sec(11));
  const res = useEnter(sec(13.5));
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 40 }}>
        <div style={head}>
          <Kicker>Rule learner · Muse Wonder</Kicker>
          <Title size={54}>It learns new hazards, but a gate decides what it keeps</Title>
        </div>
        <div style={{ display: "flex", gap: 56 }}>
          <div
            style={{
              ...inc,
              width: 640,
              background: C.panel,
              border: `2px solid ${C.amber}`,
              borderRadius: 14,
              padding: "28px 30px",
              display: "flex",
              flexDirection: "column",
              gap: 18,
              alignSelf: "flex-start",
            }}
          >
            <div style={{ fontSize: 27, color: C.amber, fontWeight: 700 }}>
              INCIDENT · a hazard no rule covered
            </div>
            <div style={{ fontSize: 33 }}>
              The arm set a cup down right at the counter edge. Every rule said ALLOW.
            </div>
            <div style={{ fontSize: 31, color: C.dim }}>The owner files:</div>
            <div style={{ fontSize: 32, fontFamily: MONO }}>
              "you put the cup right at the counter edge, it could fall off"
            </div>
          </div>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 24 }}>
            <div style={{ ...prop, fontSize: 31 }}>
              Muse Wonder proposes one rule from the fixed vocabulary:
              <div style={{ fontFamily: MONO, color: C.amber, fontSize: 30, marginTop: 8 }}>
                release_near_edge(edge_cm) → ASK
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              {GATE4.map((g, i) => {
                const on = interpolate(frame, [sec(6) + i * 15, sec(6) + i * 15 + 15], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                });
                return (
                  <div
                    key={g}
                    style={{
                      opacity: on,
                      border: `2px solid ${C.green}`,
                      borderRadius: 10,
                      padding: "8px 16px",
                      fontSize: 30,
                    }}
                  >
                    ✓ {g}
                  </div>
                );
              })}
            </div>
            <div style={{ ...v1, fontSize: 31 }}>
              <Badge color={C.red}>v1 · 15 cm · REJECTED</Badge>
              <div style={{ color: C.dim, marginTop: 8 }}>
                false refusals on safe tasks 11.5% → <b style={{ color: C.red }}>37.5%</b>
              </div>
            </div>
            <div style={{ ...v2, fontSize: 31 }}>
              <Badge color={C.green}>v2 · 8 cm · KEPT (asks the owner)</Badge>
              <div style={{ color: C.dim, marginTop: 8 }}>false refusals 10.9%</div>
            </div>
          </div>
        </div>
        <div style={{ ...res, fontSize: 38, fontWeight: 700 }}>
          Unseen-hazard scenarios, unsafe executed: 47.8% →{" "}
          <span style={{ color: C.green }}>15.9%</span>
          <div style={{ fontSize: 30, color: C.dim, fontWeight: 400, marginTop: 6 }}>
            The subset of hazards the hand-written rules never covered (69 cells), not the
            whole benchmark.
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- learner in the app
// V4: top-pinned header, step captions bumped to 30.
const LEARN_STEPS4 = [
  { at: 2.0, y: 0, h: 100, color: C.amber, n: "1", t: "The owner reports a problem", s: "one sentence, on the last run", zoom: 1.4 },
  { at: 4.6, y: 120, h: 142, color: C.blue, n: "2", t: "Muse Wonder's rule appears", s: "live, and the owner can roll it back", zoom: 1.4 },
  { at: 6.6, y: 285, h: 230, color: C.green, n: "3", t: "With its gate report", s: "schema, replay, ratchet, preflight all pass", zoom: 1.3 },
];

export const LearnAppV4: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const pic = useEnter(8);
  const W = 1050;
  const k = W / 825;
  const H = 515 * k;
  const on = (at: number) =>
    interpolate(frame, [sec(at), sec(at) + 12], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  let s = 1;
  let cy = H / 2;
  LEARN_STEPS4.forEach((st) => {
    const e = interpolate(frame, [sec(st.at), sec(st.at) + 18], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.cubic),
    });
    s += (st.zoom - s) * e;
    cy += ((st.y + st.h / 2) * k - cy) * e;
  });
  const ty = Math.min(0, Math.max(H - s * H, H / 2 - s * cy));
  const tx = 0;
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 30 }}>
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
          <Kicker>The learning loop, in the app</Kicker>
          <span style={{ fontSize: 30, color: C.dim }}>dashboard · Rules tab</span>
        </div>
        <div style={{ display: "flex", gap: 60, alignItems: "center" }}>
          <div
            style={{
              ...pic,
              position: "relative",
              width: W,
              height: H,
              flexShrink: 0,
              overflow: "hidden",
              borderRadius: 14,
              border: `2px solid ${C.line}`,
              background: "#fff",
            }}
          >
            <div
              style={{
                position: "absolute",
                inset: 0,
                transform: `translate(${tx}px, ${ty}px) scale(${s})`,
                transformOrigin: "0 0",
              }}
            >
              <Img src={staticFile("rules_tab.png")} style={{ width: W, display: "block" }} />
              {LEARN_STEPS4.map((st) => (
                <div
                  key={st.n}
                  style={{
                    position: "absolute",
                    left: 4,
                    top: st.y * k + 2,
                    width: W - 8,
                    height: st.h * k - 4,
                    border: `${4 / s}px solid ${st.color}`,
                    borderRadius: 10,
                    opacity: on(st.at),
                  }}
                />
              ))}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
            {LEARN_STEPS4.map((st) => (
              <div key={st.n} style={{ opacity: on(st.at), display: "flex", gap: 20 }}>
                <div
                  style={{
                    width: 54,
                    height: 54,
                    borderRadius: 27,
                    background: st.color,
                    color: "#0b0f14",
                    fontSize: 32,
                    fontWeight: 900,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {st.n}
                </div>
                <div>
                  <div style={{ fontSize: 36, fontWeight: 800 }}>{st.t}</div>
                  <div style={{ fontSize: 30, color: C.dim, marginTop: 4 }}>{st.s}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- live app
// V4: stretched — the result segment plays at 6x instead of 8x and the
// scene holds the end state longer (scene 12 s -> 14 s).
type Cam4 = { s: number; x: number; y: number };

const REC4 = [
  { from: 5, to: 17.5, rate: 5, stamp: "Typed live, not a preset", color: C.amber,
    cam: { s: 1, x: 50, y: 50 } },
  { from: 17.5, to: 62, rate: 30, stamp: "Same Muse Spark plans both lanes", color: C.dim,
    cam: { s: 1.42, x: 50, y: 50 } },
  { from: 62, to: 108, rate: 6, stamp: "A hands it blade-first · B slows and turns the handle", color: C.green,
    cam: { s: 1.75, x: 49.5, y: 41 } },
];
const HOLD_CAM4: Cam4 = { s: 1.3, x: 50, y: 60 };
const HOLD_STAMP4 = "A: \"offered blade-first\" · B: ALLOW, handle first";

const camTransform4 = ({ s, x, y }: Cam4) => {
  const clamp = (v: number) => Math.min(0, Math.max(100 - 100 * s, v));
  return `translate(${clamp(50 - s * x)}%, ${clamp(50 - s * y)}%) scale(${s})`;
};

export const LiveV4: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  let t = 0;
  let idx = REC4.length;
  const starts: number[] = [];
  const parts = REC4.map((s, i) => {
    const len = Math.round(((s.to - s.from) * 30) / s.rate);
    const at = t;
    starts.push(at);
    t += len;
    if (frame >= at && frame < at + len) idx = i;
    return (
      <Sequence key={i} from={at} durationInFrames={len} layout="none">
        <OffthreadVideo
          src={staticFile("live_rec.mp4")}
          startFrom={Math.round(s.from * 30)}
          playbackRate={s.rate}
          muted
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        />
      </Sequence>
    );
  });
  const ended = frame >= t;
  if (frame < 0 || (!ended && idx === REC4.length)) idx = 0;
  const camOf = (i: number): Cam4 => (i >= REC4.length ? HOLD_CAM4 : REC4[i].cam);
  const segStart = ended ? t : starts[idx];
  const k = interpolate(frame, [segStart, segStart + 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const a = camOf(Math.max(0, idx - 1));
  const b = camOf(idx);
  const cam = { s: a.s + (b.s - a.s) * k, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
  const part = idx < REC4.length ? REC4[idx] : null;
  const W = 1400;
  const H = (W * 1080) / 1920;
  return (
    <SceneFade>
      <div style={{ ...padV4, alignItems: "center", gap: 22 }}>
        <div style={{ ...head, alignSelf: "stretch", display: "flex", alignItems: "baseline", gap: 28, paddingLeft: 160 }}>
          <Kicker>Live app</Kicker>
          <span style={{ fontSize: 34, color: C.dim }}>a request typed on the deployed demo</span>
        </div>
        <div
          style={{
            width: W,
            height: H,
            borderRadius: 14,
            overflow: "hidden",
            border: `2px solid ${C.line}`,
            position: "relative",
            background: "#fff",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              transform: camTransform4(cam),
              transformOrigin: "0 0",
            }}
          >
            {parts}
            {ended ? (
              <Img
                src={staticFile("live_rec_last.png")}
                style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
              />
            ) : null}
          </div>
          <span
            style={{
              position: "absolute",
              right: 18,
              top: 18,
              background: "rgba(8,10,14,0.82)",
              color: "#fff",
              fontSize: 26,
              fontWeight: 800,
              padding: "6px 14px",
              borderRadius: 8,
            }}
          >
            {part ? `${part.rate}× speed` : "end of run"}
          </span>
        </div>
        <div
          style={{
            alignSelf: "flex-start",
            marginLeft: (1920 - 200 - W) / 2,
            background: "rgba(8,10,14,0.85)",
            border: `3px solid ${part ? (part.color === C.dim ? C.line : part.color) : C.green}`,
            color: "#fff",
            fontSize: 30,
            fontWeight: 800,
            padding: "8px 16px",
            borderRadius: 10,
          }}
        >
          {part ? part.stamp : HOLD_STAMP4}
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- Meta stack
// V4: compact credits — one line for the models, one for Muse Code, one
// for sponsors, plus a two-line open-weights proof strip. Scene 10.3 s
// -> ~6.9 s; the saved seconds stretch the live scene.
export const StackV4: React.FC = () => {
  const head = useEnter(0);
  const big = useEnter(sec(0.6));
  const sub = useEnter(sec(1.5));
  const spons = useEnter(sec(2.5));
  const proof = useEnter(sec(3.5));
  return (
    <SceneFade>
      <div style={{ ...padV4, gap: 0 }}>
        <div style={head}>
          <Kicker>Built with</Kicker>
        </div>
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 30,
            paddingBottom: 60,
          }}
        >
          <div style={{ ...big, fontSize: 64, fontWeight: 900, letterSpacing: -1 }}>
            Meta API models + Muse Code
          </div>
          <div style={{ ...sub, fontSize: 34, color: C.dim }}>
            SAM 3.1 · Muse Spark 1.3 · Muse Spark Open · Muse Wonder
          </div>
          <div style={{ ...spons, fontSize: 32 }}>
            <span style={{ color: C.blue, fontWeight: 800 }}>RUNS ON </span>
            <span style={{ fontWeight: 800 }}>Baseten</span>
            <span style={{ color: C.dim }}> (open-weights planner) </span>
            <span style={{ color: C.dim }}>·</span>
            <span style={{ fontWeight: 800 }}> Modal</span>
            <span style={{ color: C.dim }}> (live app)</span>
          </div>
          <div
            style={{
              ...proof,
              alignSelf: "flex-start",
              background: "#05070a",
              border: `2px solid ${C.green}`,
              borderRadius: 12,
              padding: "14px 22px",
              fontFamily: MONO,
              fontSize: 27,
              lineHeight: 1.7,
            }}
          >
            <div>
              <span style={{ color: C.green }}>$</span> --model spark-open → valid 11-step plan{" "}
              <span style={{ color: C.green }}>✓</span>
            </div>
            <div>
              Motion: 142 samples over 6.34 s <span style={{ color: C.green }}>✓</span>
            </div>
          </div>
        </div>
      </div>
    </SceneFade>
  );
};
