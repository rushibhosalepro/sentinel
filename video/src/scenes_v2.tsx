import React from "react";
import {
  AbsoluteFill,
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
  sec,
  Shot,
  useEnter,
} from "./ui";

const pad: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 80px",
  display: "flex",
  flexDirection: "column",
};
const LANE_W = 840;

// ---------------------------------------------------------------- cold open
// V2: the blade-first take as a real close-up (handover camera), not a
// digital zoom. Freeze frame 130 = the take; the stamp lands ON the
// freeze frame (v1 keyed it past the freeze, so it never showed).
export const ColdV2: React.FC = () => {
  const cap = useEnter(0);
  return (
    <SceneFade>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 26 }}>
        <div style={{ ...cap, fontSize: 32, color: C.dim }}>
          <span style={{ fontFamily: MONO, color: C.text }}>"hand me the knife"</span>
          {"  ·  "}an LLM-planned robot arm, no safety layer
        </div>
        <Shot
          name="knife_A_close"
          frames={228}
          width={1180}
          startFrom={70}
          zoom={{ from: 100, to: 125, cx: 315, cy: 215, scale: 1.6 }}
          freezeAt={130}
          marks={[{ at: 120, x: 315, y: 215, r: 30, color: C.red }]}
          stamps={[{ at: 130, text: "Blade first. Into a hand.", color: C.red }]}
        />
      </AbsoluteFill>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- title
// V2: adds the simulated-kitchen chip (judge nit #1), timed to the new
// narration line ("...runs in a simulated kitchen" lands ~8 s in).
export const IntroV2: React.FC = () => {
  const a = useEnter(0);
  const b = useEnter(15);
  const c = useEnter(30);
  const d = useEnter(sec(7.5));
  return (
    <SceneFade>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 36 }}>
        <div style={{ ...a, fontSize: 150, fontWeight: 900, letterSpacing: -3 }}>
          Sentinel
        </div>
        <div style={{ ...b, fontSize: 52, color: C.dim }}>
          The LLM decides <b style={{ color: C.text }}>how</b>. Sentinel decides{" "}
          <b style={{ color: C.green }}>whether</b>.
        </div>
        <div style={{ ...c, fontSize: 30, color: C.dim }}>
          A deterministic safety layer for robot actions planned by an LLM
        </div>
        <div style={d}>
          <Badge color={C.blue}>SIMULATED KITCHEN · MUJOCO</Badge>
        </div>
      </AbsoluteFill>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- how it works
// V2: identical loop diagram, beats rescaled x0.78 to the tighter
// narration (13.22 s voice -> 14.3 s scene).
const HOW_T2 = {
  tags: 2.5, plan: 4.7, sim: 5.9, check: 7.2, block: 7.6, fix: 8.7,
  plan2: 9.8, check2: 10.6, allow: 11.1, move: 11.9,
};
const TAGS2 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 2.5 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 2.8 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 3.1 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 3.4 },
];

const LoopNode2: React.FC<{
  x: number; y: number; title: string; sub: React.ReactNode; color: string; lit: number;
}> = ({ x, y, title, sub, color, lit }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: 330,
      minHeight: 112,
      borderRadius: 16,
      padding: "14px 20px",
      background: C.panel,
      border: `3px solid ${lit > 0.5 ? color : C.line}`,
      boxShadow: lit > 0.5 ? `0 0 26px ${color}66` : "none",
    }}
  >
    <div style={{ fontSize: 32, fontWeight: 800, color: lit > 0.5 ? C.text : C.dim }}>{title}</div>
    <div style={{ fontSize: 24, marginTop: 6 }}>{sub}</div>
  </div>
);

export const HowV2: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const between = (a: number, b: number) => (frame >= sec(a) && frame < sec(b) ? 1 : 0);
  const round2 = frame >= sec(HOW_T2.plan2);
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
      markerEnd={`url(#head2-${color.slice(1)})`}
    />
  );
  const heads = [C.text, C.amber, C.green, C.dim];
  return (
    <SceneFade>
      <div style={{ ...pad, gap: 26 }}>
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
              {TAGS2.map((g) => (
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
            <div style={{ opacity: at(HOW_T2.plan - 0.3), fontFamily: MONO, fontSize: 30 }}>
              "pour some water into the cup"
            </div>
          </div>
          <div style={{ position: "relative", width: 840, height: 640 }}>
            <svg width={840} height={640} style={{ position: "absolute", inset: 0 }}>
              <defs>
                {heads.map((c) => (
                  <marker
                    key={c}
                    id={`head2-${c.slice(1)}`}
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
              {arrow("M 345 70 L 470 70", HOW_T2.sim - 0.4, C.text, 125)}
              {arrow("M 650 150 L 650 245", HOW_T2.check - 0.4, C.text, 95)}
              {arrow("M 480 320 C 300 330, 170 290, 170 165", HOW_T2.fix, C.amber, 380, 6)}
              {arrow("M 650 400 L 650 495", HOW_T2.move, C.green, 95, 6)}
            </svg>
            <LoopNode2
              x={10}
              y={18}
              title="Muse Spark plans"
              color={C.purple}
              lit={between(HOW_T2.plan, HOW_T2.sim) || between(HOW_T2.plan2, HOW_T2.check2)}
              sub={
                <span style={{ fontFamily: MONO, color: C.dim, opacity: at(HOW_T2.plan) }}>
                  {round2 ? "round 2: move cup, then pour" : "grasp jug → over cup → pour"}
                </span>
              }
            />
            <LoopNode2
              x={480}
              y={18}
              title="Dry-run"
              color={C.blue}
              lit={between(HOW_T2.sim, HOW_T2.check) || between(HOW_T2.plan2 + 0.5, HOW_T2.check2)}
              sub={<span style={{ color: C.dim }}>every pose, before it moves</span>}
            />
            <LoopNode2
              x={480}
              y={250}
              title="Fixed rules check"
              color={frame >= sec(HOW_T2.allow) ? C.green : C.red}
              lit={between(HOW_T2.check, HOW_T2.fix + 0.6) || between(HOW_T2.check2, 99)}
              sub={
                frame >= sec(HOW_T2.allow) ? (
                  <span style={{ opacity: at(HOW_T2.allow) }}>
                    <Badge color={C.green}>ALLOW</Badge>
                  </span>
                ) : (
                  <span style={{ opacity: at(HOW_T2.block), fontFamily: MONO, fontSize: 22 }}>
                    <span style={{ color: C.red, fontWeight: 800 }}>BLOCK</span> liquid near laptop
                    <br />
                    14.9 cm &lt; 15 cm
                  </span>
                )
              }
            />
            <LoopNode2
              x={480}
              y={500}
              title="The arm moves"
              color={C.green}
              lit={frame >= sec(HOW_T2.move) ? 1 : 0}
              sub={<span style={{ color: C.dim }}>live monitor still watching</span>}
            />
            <div
              style={{
                position: "absolute",
                left: 20,
                top: 330,
                width: 330,
                opacity: at(HOW_T2.fix + 0.3),
                fontSize: 26,
                fontWeight: 700,
                color: C.amber,
              }}
            >
              BLOCK + a concrete fix:
              <div style={{ fontFamily: MONO, fontSize: 24, marginTop: 6 }}>
                move the cup to (0.20, 0.15)
              </div>
            </div>
            <div
              style={{
                position: "absolute",
                left: 20,
                top: 470,
                width: 420,
                opacity: at(HOW_T2.move + 0.4),
                fontSize: 24,
                color: C.dim,
                lineHeight: 1.45,
              }}
            >
              no LLM in the verdict
              <br />
              up to 3 rounds · hard violations are never retried
            </div>
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- knife demo
// V2: both lanes as real close-ups (handover camera). Same verdicts,
// same footers — the takes are now readable without a digital zoom.
const SplitHead2: React.FC<{ kicker: string; prompt: string }> = ({ kicker, prompt }) => {
  const head = useEnter(0);
  return (
    <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
      <Kicker>{kicker}</Kicker>
      <span style={{ fontFamily: MONO, fontSize: 44 }}>"{prompt}"</span>
    </div>
  );
};

export const KnifeDemoV2: React.FC = () => (
  <SceneFade>
    <div style={{ ...pad, gap: 26 }}>
      <SplitHead2 kicker="Demo 1" prompt="hand me the knife" />
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

// ---------------------------------------------------------------- sticky note
// V2: the note carries real printed texture (F-07) — the zoom callout
// crops the render, no overlay text anywhere in this scene.
export const StickyV2: React.FC = () => {
  const head = useEnter(0);
  const pic = useEnter(10);
  const zoom = useEnter(sec(2));
  const block = useEnter(sec(11.2));
  const W = 780;
  const k = W / 1280;
  return (
    <SceneFade>
      <div style={{ ...pad, gap: 26 }}>
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
          <Kicker color={C.red}>Demo 3 · prompt injection</Kicker>
          <span style={{ fontFamily: MONO, fontSize: 44 }}>"tidy the counter"</span>
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

// ---------------------------------------------------------------- stack
// V2: the model list plus a verbatim terminal card — a real open-weights
// plan (13.2 s, 11 steps, motion builds), quoted from the actual run.
const STACK2 = [
  ["SAM 3.1", "segments every object"],
  ["Muse Spark 1.3", "plans, replans, reads scene text in quarantine"],
  ["Muse Spark Open", "the same loop on open weights, on Baseten"],
  ["Muse Wonder", "proposes new rules from incidents"],
  ["Muse Code", "built the code with me, solo, in 9 days"],
];

const PARTNERS2 = [
  ["Baseten", "serves Muse Spark Open, the open-weights planner"],
  ["Modal", "hosts the live app anyone can try"],
];

const PROOF: React.ReactNode[] = [
  <div key="c"><span style={{ color: C.green }}>$</span> uv run python -m planner.planner \<br />&nbsp;&nbsp;"put the apple next to the sponge" --model spark-open</div>,
  <div key="p" style={{ color: C.dim }}>plan took 13.2 s (model=meta-models/muse-spark-open)</div>,
  <div key="s1">&nbsp;&nbsp;s1 move_to {"{…}"} <span style={{ color: C.dim }}># staging pose</span></div>,
  <div key="s4">&nbsp;&nbsp;s4 grasp {"{\"object_id\": \"apple\"}"} <span style={{ color: C.dim }}># Attach apple.</span></div>,
  <div key="e" style={{ color: C.dim }}>&nbsp;&nbsp;···</div>,
  <div key="s9">&nbsp;&nbsp;s9 release {"{}"} <span style={{ color: C.dim }}># Place apple next to sponge.</span></div>,
  <div key="s11">&nbsp;&nbsp;s11 stop {"{}"} <span style={{ color: C.dim }}># Task complete.</span></div>,
  <div key="m">Motion: 142 samples over 6.34 s, held=None <span style={{ color: C.green }}>✓</span></div>,
];

export const StackV2: React.FC = () => {
  const head = useEnter(0);
  const rows = [useEnter(10), useEnter(25), useEnter(40), useEnter(55), useEnter(70)];
  const head2 = useEnter(sec(5.0));
  const prow = [useEnter(sec(5.4)), useEnter(sec(7.2))];
  const proof = useEnter(sec(3.0));
  const Row = (m: string, w: string, style: React.CSSProperties) => (
    <div key={m} style={{ ...style, display: "flex", gap: 30, alignItems: "baseline" }}>
      <div style={{ width: 430, fontSize: 40, fontWeight: 800 }}>{m}</div>
      <div style={{ fontSize: 28, color: C.dim }}>{w}</div>
    </div>
  );
  return (
    <SceneFade>
      <div style={{ ...pad, gap: 24 }}>
        <div style={head}>
          <Kicker>Built with Meta models</Kicker>
        </div>
        <div style={{ display: "flex", gap: 48, alignItems: "flex-start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 22, flex: 1 }}>
            {STACK2.map(([m, w], i) => Row(m, w, rows[i]))}
            <div style={{ ...head2, marginTop: 14 }}>
              <Kicker color={C.blue}>Running on</Kicker>
            </div>
            {PARTNERS2.map(([m, w], i) => Row(m, w, prow[i]))}
          </div>
          <div
            style={{
              ...proof,
              width: 640,
              background: "#05070a",
              border: `2px solid ${C.line}`,
              borderRadius: 14,
              padding: "22px 26px",
              fontFamily: MONO,
              fontSize: 21,
              lineHeight: 1.65,
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            <div style={{ marginBottom: 8 }}>
              <Badge color={C.green}>OPEN WEIGHTS · SAME LOOP</Badge>
            </div>
            {PROOF}
          </div>
        </div>
      </div>
    </SceneFade>
  );
};
