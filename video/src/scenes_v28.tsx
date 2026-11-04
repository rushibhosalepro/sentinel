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
  Title,
  sec,
  useEnter,
} from "./ui";

const padV27: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};

// V27: ColdV26 unchanged — the freeze stamp reads "Unsafe action".
export const ColdV27: React.FC = () => {
  const cap = useEnter(0);
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          gap: 36,
        }}
      >
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
          stamps={[{ at: 130, text: "Unsafe action", color: C.red }]}
        />
      </div>
    </SceneFade>
  );
};

// V27: IntroV26 with every beat ~0.7 s earlier so the boxes lead the
// words instead of landing after them. Same voice.
const INTRO_T27 = {
  title: 0, sub: 1.2, plan: 3.9, arrow1: 4.5, sentinel: 5.1,
  blocked: 6.1, arrow2: 6.9, arm: 7.5, tag: 8.9,
};

const BOX_W27 = 440;
const BOX_H27 = 170;
const BOX_Y27 = 100;

const DiaBox27: React.FC<{
  x: number; title: string; sub: string; color: string; show: number;
}> = ({ x, title, sub, color, show }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: BOX_Y27,
      width: BOX_W27,
      height: BOX_H27,
      borderRadius: 18,
      padding: "20px 24px",
      background: C.panel,
      border: `3px solid ${color}`,
      boxShadow: `0 0 26px ${color}55`,
      opacity: show,
    }}
  >
    <div style={{ fontSize: 38, fontWeight: 800 }}>{title}</div>
    <div style={{ fontSize: 27, color: C.dim, marginTop: 8 }}>{sub}</div>
  </div>
);

export const IntroV27: React.FC = () => {
  const frame = useCurrentFrame();
  const at = (t: number, len = 12) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const X1 = 40;
  const X2 = 640;
  const X3 = 1240;
  const MID = BOX_Y27 + BOX_H27 / 2;
  const arrow = (d: string, t: number, color: string, len: number, dashed = false) => (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={6}
      strokeLinecap="round"
      strokeDasharray={dashed ? "14 10" : len}
      strokeDashoffset={dashed ? 0 : len * (1 - at(t, 14))}
      opacity={at(t, 14) > 0.02 ? 1 : 0}
      markerEnd={`url(#ih27-${color.slice(1)}${dashed ? "-d" : ""})`}
    />
  );
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          padding: "60px 100px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 30,
        }}
      >
        <div style={{ opacity: at(INTRO_T27.title), fontSize: 64, fontWeight: 900, textAlign: "center" }}>
          So I built Sentinel.
        </div>
        <div
          style={{
            opacity: at(INTRO_T27.sub),
            fontSize: 36,
            color: C.dim,
            textAlign: "center",
          }}
        >
          A rule-based safety layer between action planner (Muse Spark LLM) and robot arm.
        </div>
        <div style={{ position: "relative", width: 1720, height: 300 }}>
          <svg width={1720} height={300} style={{ position: "absolute", inset: 0 }}>
            <defs>
              {[C.text, C.red].map((c) => (
                <marker
                  key={c}
                  id={`ih27-${c.slice(1)}`}
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
              <marker
                id={`ih27-${C.red.slice(1)}-d`}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill={C.red} />
              </marker>
            </defs>
            {arrow(`M ${X1 + BOX_W27 + 4} ${MID} L ${X2 - 10} ${MID}`, INTRO_T27.arrow1, C.text, 150)}
            {arrow(`M ${X2 + BOX_W27 + 4} ${MID} L ${X3 - 10} ${MID}`, INTRO_T27.arrow2, C.text, 150)}
            {arrow(
              `M ${X2 + BOX_W27 / 2} 78 L ${X2 + BOX_W27 / 2} ${BOX_Y27 - 6}`,
              INTRO_T27.blocked,
              C.red,
              0,
              true
            )}
          </svg>
          <DiaBox27
            x={X1}
            title="Action planner"
            sub="Muse Spark LLM · figures out how"
            color={C.purple}
            show={at(INTRO_T27.plan)}
          />
          <DiaBox27
            x={X2}
            title="Sentinel"
            sub="allow · ask · block · halt"
            color={C.green}
            show={at(INTRO_T27.sentinel)}
          />
          <DiaBox27
            x={X3}
            title="Robot arm"
            sub="moves only checked plans"
            color={C.blue}
            show={at(INTRO_T27.arm)}
          />
          <div
            style={{
              position: "absolute",
              left: X2,
              top: 8,
              width: BOX_W27,
              display: "flex",
              justifyContent: "center",
              opacity: at(INTRO_T27.blocked),
            }}
          >
            <Badge color={C.red}>UNSAFE PLAN · BLOCKED</Badge>
          </div>
        </div>
        <div
          style={{
            opacity: at(INTRO_T27.tag),
            fontSize: 40,
            fontWeight: 800,
            textAlign: "center",
          }}
        >
          The model decides <span style={{ color: C.text }}>how</span>. Sentinel decides{" "}
          <span style={{ color: C.green }}>whether</span>.
        </div>
      </div>
    </SceneFade>
  );
};

// V27: ProblemV26 with the cards moved earlier still — each image now
// lands before its name is spoken, for all three. Same voice.
const HAZARDS27 = [
  { img: "split_A_knife_f120.png", t: "a blade toward a hand", at: 4.2, zoom: { cx: 333, cy: 233, s: 2.0 } },
  { img: "split_A_water_f130.png", t: "water poured near a laptop", at: 5.7, zoom: { cx: 235, cy: 232, s: 1.9 } },
  { img: "note_zoom_v2.png", t: "a random note instructing the robot", at: 8.2, zoom: null },
];

export const ProblemV27: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const fade = (at: number) =>
    interpolate(frame, [sec(at), sec(at) + 14], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const CW = 540;
  const CH = 360;
  return (
    <SceneFade>
      <div style={{ ...padV27, gap: 64 }}>
        <div style={head}>
          <Kicker color={C.red}>The problem</Kicker>
          <Title size={54}>LLMs can plan robot actions,<br />but they can't see the danger</Title>
        </div>
        <div style={{ display: "flex", gap: 40 }}>
          {HAZARDS27.map((h) => (
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
              <div style={{ fontSize: 28, fontWeight: 700, marginTop: 14 }}>{h.t}</div>
            </div>
          ))}
        </div>
      </div>
    </SceneFade>
  );
};

// V27: the hook answers itself — after the two questions the frame
// turns into the answer in big capitals: Sentinel works with the LLM
// to prevent unsafe actions. Beats from the 11.2 s voice.
export const HookV27: React.FC = () => {
  const frame = useCurrentFrame();
  const q1 = useEnter(sec(0.4));
  const q2 = useEnter(sec(3.5));
  const q3 = useEnter(sec(6.3));
  const q4 = useEnter(sec(8.1));
  const dim = interpolate(frame, [sec(6.3), sec(6.8)], [1, 0.32], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
          gap: 26,
          padding: "60px 100px",
        }}
      >
        <div style={{ ...q1, opacity: q1.opacity * dim, fontSize: 48, fontWeight: 700 }}>
          Now imagine someone tells the robot to kill someone.
        </div>
        <div style={{ ...q2, opacity: q2.opacity * dim, fontSize: 52, fontWeight: 800, color: C.red }}>
          How safe is that, to trust the robot?
        </div>
        <div style={{ ...q3, fontSize: 62, fontWeight: 900, color: C.green, marginTop: 22 }}>
          SO HERE WE HAVE SENTINEL.
        </div>
        <div style={{ ...q4, fontSize: 50, fontWeight: 900 }}>
          IT WORKS WITH THE LLM TO PREVENT UNSAFE ACTIONS.
        </div>
      </div>
    </SceneFade>
  );
};

// V27: the look half of How — the answer line is gone (the voice now
// opens with "Let's talk about how it works"), and the user
// instruction moves to the Loop frame. Beats from the 8.2 s voice.
const TAGS27 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 7.1 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 7.4 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 7.7 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 7.4 },
];

export const HowV27: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const IW = 900;
  const k = IW / 890;
  const IH = 600 * k;
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          padding: "60px 100px",
          display: "flex",
          flexDirection: "column",
          gap: 28,
        }}
      >
        <div style={{ ...head }}>
          <Kicker>How it works</Kicker>
          <span style={{ fontSize: 40, fontWeight: 800 }}>Sentinel puts the model in a loop</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
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
              style={{ position: "absolute", width: IW, height: IH, opacity: at(5.2, 20) }}
            />
            <span style={{ position: "absolute", left: 12, bottom: 12, opacity: at(3.4, 10) }}>
              <Badge color={C.blue}>MuJoCo kitchen simulation</Badge>
            </span>
            {TAGS27.map((g) => (
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
          <div style={{ opacity: at(5.2), fontSize: 22, color: C.dim }}>
            SAM 3.1 + Muse Spark tag the scene: what's sharp, liquid, electronic
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// V27: the loop opens with the user's instruction on top ("first you
// give an instruction, then the next steps"), the return arrow from
// Sentinel to the planner is red and marches back, and the boxes carry
// PLANNER / SENTINEL labels. Beats from the 16.8 s voice.
const LOOP_T27 = {
  plan: 1.3, sim: 2.1, check: 3.2, foot: 7.6, block: 11.6,
  fix: 12.6, plan2: 13.4, check2: 14.2, allow: 15.0, move: 15.6,
};
const COL27 = { x: 480, w: 330, cx: 645 };

const LoopNode27: React.FC<{
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

export const LoopV27: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const between = (a: number, b: number) => (frame >= sec(a) && frame < sec(b) ? 1 : 0);
  const allowed = frame >= sec(LOOP_T27.allow);
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
      markerEnd={`url(#head27-${color.slice(1)})`}
    />
  );
  // The verdict + fix runs back from Sentinel to the planner: it draws
  // in, then marches toward the planner while round 2 is built.
  const march = (d: string, t: number, len: number) => {
    const p = at(t, 14);
    const drawn = p >= 1;
    return (
      <path
        d={d}
        fill="none"
        stroke={C.red}
        strokeWidth={7}
        strokeLinecap="round"
        strokeDasharray={drawn ? "18 14" : len}
        strokeDashoffset={drawn ? -(((frame - sec(t) - 14) * 3) % 32) : len * (1 - p)}
        opacity={p > 0.02 ? 1 : 0}
        markerEnd={`url(#head27-${C.red.slice(1)})`}
      />
    );
  };
  const heads = [C.text, C.amber, C.green, C.dim, C.red];
  const dimFix = interpolate(frame, [sec(LOOP_T27.allow), sec(LOOP_T27.allow) + 9], [1, 0.3], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const memLine = (
    <span style={{ opacity: at(LOOP_T27.foot), color: C.dim, fontSize: 24 }}>
      fixed rules in memory
      <br />
      no AI call · under 100 ms
    </span>
  );
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          padding: "60px 100px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
        }}
      >
        <div style={{ ...head, alignSelf: "stretch" }}>
          <Kicker>How it works · the loop</Kicker>
          <span style={{ fontSize: 38, fontWeight: 800 }}>Every step is checked before it moves</span>
        </div>
        <div style={{ opacity: at(0.2), fontFamily: MONO, fontSize: 26 }}>
          <span style={{ color: C.green }}>🗣 user › </span>"pour me some water"
        </div>
        <div style={{ position: "relative", width: 840, height: 700 }}>
          <svg width={840} height={700} style={{ position: "absolute", inset: 0 }}>
            <defs>
              {heads.map((c) => (
                <marker
                  key={c}
                  id={`head27-${c.slice(1)}`}
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
            {arrow("M 345 70 L 470 70", LOOP_T27.sim - 0.4, C.text, 125)}
            {arrow(`M ${COL27.cx} 152 L ${COL27.cx} 244`, LOOP_T27.check - 0.4, C.text, 92)}
            {arrow(`M ${COL27.cx} 378 L ${COL27.cx} 584`, LOOP_T27.move, C.green, 206, 6)}
            {march("M 4 472 C 2 380, 2 200, 4 120 C 4 95, 2 82, 14 78", LOOP_T27.fix, 410)}
          </svg>
          <div
            style={{
              position: "absolute",
              left: -150,
              top: 58,
              fontSize: 24,
              fontWeight: 800,
              letterSpacing: 3,
              color: C.dim,
              opacity: at(LOOP_T27.plan),
            }}
          >
            PLANNER
          </div>
          <div
            style={{
              position: "absolute",
              left: 824,
              top: 296,
              fontSize: 24,
              fontWeight: 800,
              letterSpacing: 3,
              color: C.green,
              opacity: at(LOOP_T27.check),
            }}
          >
            SENTINEL
          </div>
          <LoopNode27
            x={10}
            y={18}
            w={330}
            title="Muse Spark plans"
            color={C.purple}
            lit={between(LOOP_T27.plan, LOOP_T27.check) || between(LOOP_T27.plan2, LOOP_T27.check2)}
            show={at(LOOP_T27.plan)}
            sub={
              <span style={{ fontFamily: MONO, color: C.dim, opacity: at(LOOP_T27.plan) }}>
                {allowed ? "round 2: move cup, then pour" : "grasp jug → over cup → pour"}
              </span>
            }
          />
          <LoopNode27
            x={COL27.x}
            y={18}
            w={COL27.w}
            title="Dry-run"
            color={C.blue}
            lit={between(LOOP_T27.sim, LOOP_T27.check) || between(LOOP_T27.plan2 + 0.5, LOOP_T27.check2)}
            show={at(LOOP_T27.sim)}
            sub={<span style={{ color: C.dim }}>every pose, before it moves</span>}
          />
          <LoopNode27
            x={COL27.x}
            y={250}
            w={COL27.w}
            title="Fixed rules check"
            color={allowed ? C.green : C.red}
            lit={between(LOOP_T27.check, LOOP_T27.fix + 0.6) || between(LOOP_T27.check2, 99)}
            show={at(LOOP_T27.check)}
            sub={
              allowed ? (
                <span style={{ opacity: at(LOOP_T27.allow) }}>
                  <Badge color={C.green}>ALLOW</Badge>
                </span>
              ) : frame >= sec(LOOP_T27.block) ? (
                <span style={{ opacity: at(LOOP_T27.block), fontFamily: MONO, fontSize: 32 }}>
                  <span style={{ color: C.red, fontWeight: 800 }}>BLOCK</span>
                  <br />
                  <Badge color={C.amber}>Why?</Badge>
                  <br />
                  <span style={{ color: C.text }}>liquid near</span>
                  <br />
                  <span style={{ color: C.text }}>laptop</span>
                  <br />
                  <span style={{ color: C.text }}>14.9 cm &lt; 15 cm</span>
                </span>
              ) : (
                memLine
              )
            }
          />
          <div
            style={{
              position: "absolute",
              left: 10,
              top: 330,
              width: 450,
              opacity: at(LOOP_T27.fix) * dimFix,
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
          <div
            style={{
              position: "absolute",
              left: 24,
              top: 248,
              fontSize: 22,
              fontWeight: 700,
              color: C.red,
              opacity: at(LOOP_T27.fix),
            }}
          >
            verdict + fix ↑
          </div>
          <LoopNode27
            x={COL27.x}
            y={590}
            w={COL27.w}
            title="The arm moves"
            color={C.green}
            lit={frame >= sec(LOOP_T27.move) ? 1 : 0}
            show={at(LOOP_T27.move)}
            sub={<span style={{ color: C.dim }}>live monitor still watching</span>}
          />
        </div>
        <div style={{ opacity: at(LOOP_T27.foot), alignSelf: "stretch" }}>
          <div style={{ fontSize: 28, fontWeight: 800 }}>
            No AI call in this step: fixed rules in memory, under 100 ms.
          </div>
          <div style={{ fontSize: 22, color: C.dim, marginTop: 4 }}>
            up to 3 rounds · hard violations are never retried
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// V27: memory and the LLM are separate boxes in a loop — Sentinel
// rules remember every run, the LLM proposes new rules in the
// background. Beats from the 15.2 s voice.
const MEM_T27 = {
  sentinel: 0.5, memory: 2.0, arrows1: 2.6, llm: 4.8, arrows2: 5.6,
  arrows3: 6.0, graph: 6.8, graphup: 9.8, cap: 11.4,
};
const MEM_V27 = [
  { t: "ALLOW", c: C.green, g: "the plan moves", at: 13.2 },
  { t: "ASK", c: C.amber, g: "asks the owner", at: 13.6 },
  { t: "BLOCK", c: C.red, g: "stops the plan", at: 14.0 },
  { t: "HALT", c: C.purple, g: "freezes mid-motion", at: 14.4 },
];
const MEM_NODES27: { x: number; y: number; t: string; c: string }[] = [
  { x: 90, y: 55, t: "gripper", c: C.text },
  { x: 290, y: 55, t: "jug", c: C.blue },
  { x: 90, y: 135, t: "knife", c: C.red },
  { x: 290, y: 135, t: "hand", c: C.text },
  { x: 500, y: 55, t: "cup", c: C.text },
  { x: 700, y: 95, t: "laptop", c: C.amber },
];

const MemBox27: React.FC<{
  x: number; title: string; sub: string; color: string; show: number;
}> = ({ x, title, sub, color, show }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: 40,
      width: 440,
      borderRadius: 18,
      padding: "24px 28px",
      background: C.panel,
      border: `3px solid ${color}`,
      boxShadow: `0 0 26px ${color}55`,
      opacity: show,
    }}
  >
    <div style={{ fontSize: 40, fontWeight: 800 }}>{title}</div>
    <div style={{ fontSize: 27, color: C.dim, marginTop: 8 }}>{sub}</div>
  </div>
);

export const MemoryV27: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 12) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const holdsDraw = interpolate(frame, [sec(MEM_T27.graphup), sec(MEM_T27.graphup) + 14], [0, 1], {
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
          gap: 30,
        }}
      >
        <div style={{ ...head }}>
          <Kicker>How Sentinel learns</Kicker>
          <Title size={54}>Past runs become new rules</Title>
        </div>
        <div style={{ position: "relative", width: 1720, height: 290 }}>
          <svg width={1720} height={290} style={{ position: "absolute", inset: 0 }}>
            <defs>
              {[C.blue, C.purple, C.dim].map((c) => (
                <marker
                  key={c}
                  id={`mh27-${c.slice(1)}`}
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
            <path
              d="M 584 125 L 632 125"
              fill="none"
              stroke={C.blue}
              strokeWidth={6}
              strokeLinecap="round"
              strokeDasharray={48}
              strokeDashoffset={48 * (1 - at(MEM_T27.arrows1, 14))}
              opacity={at(MEM_T27.arrows1, 14) > 0.02 ? 1 : 0}
              markerEnd={`url(#mh27-${C.blue.slice(1)})`}
            />
            <path
              d="M 1084 125 L 1132 125"
              fill="none"
              stroke={C.purple}
              strokeWidth={6}
              strokeLinecap="round"
              strokeDasharray={48}
              strokeDashoffset={48 * (1 - at(MEM_T27.arrows2, 14))}
              opacity={at(MEM_T27.arrows2, 14) > 0.02 ? 1 : 0}
              markerEnd={`url(#mh27-${C.purple.slice(1)})`}
            />
            <path
              d="M 1300 250 L 1095 250"
              fill="none"
              stroke={C.purple}
              strokeWidth={6}
              strokeLinecap="round"
              strokeDasharray={205}
              strokeDashoffset={205 * (1 - at(MEM_T27.arrows2, 14))}
              opacity={at(MEM_T27.arrows2, 14) > 0.02 ? 1 : 0}
              markerEnd={`url(#mh27-${C.purple.slice(1)})`}
            />
            <path
              d="M 800 250 L 595 250"
              fill="none"
              stroke={C.blue}
              strokeWidth={6}
              strokeLinecap="round"
              strokeDasharray={205}
              strokeDashoffset={205 * (1 - at(MEM_T27.arrows3, 14))}
              opacity={at(MEM_T27.arrows3, 14) > 0.02 ? 1 : 0}
              markerEnd={`url(#mh27-${C.blue.slice(1)})`}
            />
          </svg>
          <MemBox27
            x={140}
            title="Sentinel rules"
            sub="fixed rules check every plan"
            color={C.green}
            show={at(MEM_T27.sentinel)}
          />
          <MemBox27
            x={640}
            title="Memory"
            sub="past runs, remembered"
            color={C.blue}
            show={at(MEM_T27.memory)}
          />
          <MemBox27
            x={1140}
            title="LLM"
            sub="proposes rules in the background"
            color={C.purple}
            show={at(MEM_T27.llm)}
          />
          <div
            style={{
              position: "absolute",
              left: 510,
              top: 140,
              width: 200,
              textAlign: "center",
              fontSize: 22,
              color: C.dim,
              opacity: at(MEM_T27.arrows1),
            }}
          >
            every run
          </div>
          <div
            style={{
              position: "absolute",
              left: 1010,
              top: 140,
              width: 200,
              textAlign: "center",
              fontSize: 22,
              color: C.dim,
              opacity: at(MEM_T27.arrows2),
            }}
          >
            past runs
          </div>
          <div
            style={{
              position: "absolute",
              left: 1087,
              top: 258,
              width: 220,
              textAlign: "center",
              fontSize: 24,
              fontWeight: 700,
              color: C.purple,
              opacity: at(MEM_T27.arrows2),
            }}
          >
            new rules stored
          </div>
          <div
            style={{
              position: "absolute",
              left: 597,
              top: 258,
              width: 200,
              textAlign: "center",
              fontSize: 24,
              fontWeight: 700,
              color: C.blue,
              opacity: at(MEM_T27.arrows3),
            }}
          >
            rules updated
          </div>
        </div>
        <div style={{ display: "flex", gap: 40 }}>
          <div
            style={{
              width: 840,
              borderRadius: 16,
              padding: "18px 24px",
              background: C.panel,
              border: `2px solid ${C.line}`,
              opacity: at(MEM_T27.graph),
            }}
          >
            <div style={{ fontSize: 26, fontWeight: 800 }}>
              Robot's eyes: scene graph <span style={{ color: C.dim, fontWeight: 400, fontSize: 22 }}>· updated on every move</span>
            </div>
            <svg width={790} height={185} style={{ marginTop: 6 }}>
              <line x1={90} y1={135} x2={290} y2={135} stroke={C.red} strokeWidth={3} />
              <text x={190} y={126} textAnchor="middle" fontSize={16} fill={C.red} fontWeight={700}>
                NEAR 12cm
              </text>
              <line x1={500} y1={55} x2={700} y2={95} stroke={C.amber} strokeWidth={3} />
              <text x={600} y={62} textAnchor="middle" fontSize={16} fill={C.amber} fontWeight={700}>
                NEAR 6cm
              </text>
              <line
                x1={90}
                y1={55}
                x2={290}
                y2={55}
                stroke={C.green}
                strokeWidth={4}
                strokeDasharray={200}
                strokeDashoffset={200 * (1 - holdsDraw)}
                opacity={holdsDraw > 0.02 ? 1 : 0}
              />
              <text
                x={190}
                y={46}
                textAnchor="middle"
                fontSize={16}
                fill={C.green}
                fontWeight={700}
                opacity={holdsDraw}
              >
                HOLDS
              </text>
              {MEM_NODES27.map((n) => (
                <g key={n.t}>
                  <circle cx={n.x} cy={n.y} r={15} fill={C.panel} stroke={n.c} strokeWidth={4} />
                  <text x={n.x} y={n.y + 38} textAnchor="middle" fontSize={18} fill={C.text}>
                    {n.t}
                  </text>
                </g>
              ))}
            </svg>
          </div>
          <div style={{ width: 840, opacity: at(MEM_T27.cap) }}>
            <div style={{ fontSize: 30, fontWeight: 800 }}>
              Sentinel only gives four verdicts:
            </div>
            <div style={{ display: "flex", gap: 24, marginTop: 14 }}>
              {[MEM_V27.slice(0, 2), MEM_V27.slice(2, 4)].map((row, i) => (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 14 }}>
                  {row.map((v) => (
                    <div key={v.t} style={{ opacity: at(v.at, 10) }}>
                      <Badge color={v.c}>{v.t}</Badge>
                      <div style={{ fontSize: 22, color: C.dim, marginTop: 6 }}>{v.g}</div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// V27: OutroV26 — the tagline now ends "before the robot can run an
// unsafe instruction", matching the new voice.
export const OutroV27: React.FC = () => {
  const a = useEnter(0);
  const c = useEnter(sec(1.6));
  return (
    <SceneFade>
      <div
        style={{
          justifyContent: "center",
          alignItems: "center",
          gap: 40,
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ ...a, fontSize: 60, fontWeight: 800, textAlign: "center", lineHeight: 1.25 }}>
          Sentinel checks every plan,
          <br />
          <span style={{ color: C.green }}>before the robot can run an unsafe instruction.</span>
        </div>
        <div style={{ ...c, textAlign: "center" }}>
          <div style={{ fontSize: 30, color: C.dim }}>Try it live</div>
          <div style={{ fontSize: 30, fontFamily: MONO, marginTop: 8 }}>
            rushi-bhosale84--sentinel-web.us-east.modal.run
          </div>
          <div style={{ fontSize: 28, fontFamily: MONO, color: C.dim, marginTop: 8 }}>
            github.com/rushibhosalepro/sentinel
          </div>
          <div style={{ fontSize: 26, fontFamily: MONO, color: C.dim, marginTop: 10 }}>
            Built with SAM 3.1 · Muse Spark · Muse Wonder · coded with Muse Code
          </div>
          <div style={{ fontSize: 26, fontFamily: MONO, color: C.dim, marginTop: 6 }}>
            Muse Spark Open on Baseten · runs on Baseten + Modal
          </div>
          <div style={{ fontSize: 24, fontFamily: MONO, color: C.dim, marginTop: 10 }}>
            Simulation only (MuJoCo) · 18.8% still unsafe · details in the README
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

const SplitHead27: React.FC<{ kicker: string; prompt: string }> = ({ kicker, prompt }) => {
  const head = useEnter(0);
  return (
    <div style={{ ...head }}>
      <Kicker>{kicker}</Kicker>
      <span style={{ fontFamily: MONO, fontSize: 48 }}>"{prompt}"</span>
    </div>
  );
};

// V27: KnifeDemoV23 with the title matching the narration ("pass me
// the knife"). Shots and stamps unchanged.
const LANE_W27 = 840;
const KNIFE_B_DELAY27 = 400;

export const KnifeDemoV27: React.FC = () => {
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
          gap: 46,
        }}
      >
        <div style={{ ...head }}>
          <Kicker>Demo 1</Kicker>
          <span style={{ fontFamily: MONO, fontSize: 48 }}>"pass me the knife"</span>
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
              width={LANE_W27}
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
            footerDelay={505}
          >
            <Shot
              name="knife_B_close"
              frames={431}
              width={LANE_W27}
              startFrom={100}
              delay={KNIFE_B_DELAY27}
              dimHold
              zoom={{ from: 185, to: 205, cx: 292, cy: 245, scale: 1.6 }}
              freezeAt={210}
              pushIn={0.08}
              marks={[{ at: 200, x: 292, y: 245, r: 34, color: C.green }]}
              stamps={[
                { at: 100, until: 185, text: "Sentinel: handle-first hand-over · slowed near the person", color: C.green },
                { at: 210, text: "Handle to the hand · slowed", color: C.green },
              ]}
            />
          </Lane>
        </div>
      </div>
    </SceneFade>
  );
};

// V27: WaterDemoV4 retitled to "pour me some water". Shots and stamps
// unchanged.
export const WaterDemoV27: React.FC = () => (
  <SceneFade>
    <div style={{ ...padV27, gap: 46 }}>
      <SplitHead27 kicker="Demo 2" prompt="pour me some water" />
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
            width={LANE_W27}
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
            width={LANE_W27}
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

// V27: BenchV17 plus the learner line — it improves as memory
// improves (learner proof 47.8% → 15.9% in the README).
const BARS27 = [
  { name: "LLM alone (naive)", v: 60.4, sd: 2.4, c: C.red },
  { name: "LLM checks its own plan", v: 44.3, sd: 2.4, c: C.amber },
  { name: "Sentinel, block only", v: 29.7, sd: 1.6, c: C.blue },
  { name: "LLM × Sentinel loop", v: 18.8, sd: 1.6, c: C.green },
];

export const BenchV27: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const note = useEnter(sec(6));
  const limit = useEnter(sec(10));
  const learn = useEnter(sec(14));
  const maxW = 980;
  return (
    <SceneFade>
      <div style={{ ...padV27, gap: 40 }}>
        <div style={head}>
          <Kicker>Benchmark · all 128 scenarios</Kicker>
          <Title size={54}>Unsafe actions executed (lower is better)</Title>
          <div style={{ fontSize: 30, color: C.dim, marginTop: 8 }}>
            3 independent repeats · 10 hazard categories · half are safe controls · labels
            frozen before the first run
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {BARS27.map((b, i) => {
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
        <div style={{ ...learn, fontSize: 30 }}>
          And it <b style={{ color: C.green }}>improves as memory improves</b>: every incident can
          become a new rule.
        </div>
      </div>
    </SceneFade>
  );
};

// V28: the problem is real-world robots, not the sim — three documented
// incidents (VW Baunatal 2015, Amazon Robbinsville 2018, Stanford mall
// K5 2016). Same scene length, beats and voice as v27.
const INCIDENTS28 = [
  {
    place: "GERMANY · 2015",
    head: "Factory arm kills a worker",
    line: "A VW plant robot gripped a contractor and crushed him against a metal plate.",
    src: "Reported: AP · BBC · CDC/NIOSH",
    at: 4.3,
  },
  {
    place: "NEW JERSEY · 2018",
    head: "Warehouse robot gasses 24 workers",
    line: "An Amazon robot punctured a can of bear repellent.",
    src: "Reported: NPR · ABC News",
    at: 7.5,
  },
  {
    place: "CALIFORNIA · 2016",
    head: "Security robot runs over a toddler",
    line: "A 300-pound mall patrol robot knocked down a 16-month-old.",
    src: "Reported: ABC7 · The Robot Report",
    at: 11.9,
  },
];

export const ProblemV28: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const fade = (at: number) =>
    interpolate(frame, [sec(at), sec(at) + 14], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const CW = 540;
  const CH = 470;
  return (
    <SceneFade>
      <div style={{ ...padV27, gap: 70 }}>
        <div style={head}>
          <Kicker color={C.red}>The problem</Kicker>
          <Title size={58}>LLMs can plan robot actions,<br />but they can't see the danger</Title>
        </div>
        <div style={{ display: "flex", gap: 40 }}>
          {INCIDENTS28.map((h, i) => {
            const next = INCIDENTS28[i + 1];
            const active =
              frame >= sec(h.at) && (!next || frame < sec(next.at));
            return (
            <div key={h.head} style={{ opacity: fade(h.at), width: CW }}>
              <div
                style={{
                  width: CW,
                  height: CH,
                  borderRadius: 14,
                  background: C.panel,
                  border: `3px solid ${C.red}`,
                  boxShadow: active ? `0 0 38px ${C.red}99` : "none",
                  padding: "32px 30px",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <div>
                  <Badge color={C.red}>{h.place}</Badge>
                </div>
                <div style={{ fontSize: 44, fontWeight: 800, lineHeight: 1.15, marginTop: 20 }}>
                  {h.head}
                </div>
                <div style={{ fontSize: 28, color: C.dim, lineHeight: 1.35, marginTop: 16 }}>
                  {h.line}
                </div>
                <div style={{ fontSize: 22, color: C.dim, marginTop: "auto" }}>{h.src}</div>
              </div>
            </div>
            );
          })}
        </div>
      </div>
    </SceneFade>
  );
};

// V28: bridge between the incident cards and How it works. Past
// incidents, robots spreading, the trust question, Sentinel as the
// answer — so "how it works" lands as the solution, not a non sequitur.
export const BridgeV28: React.FC = () => {
  const b1 = useEnter(0);
  const b2 = useEnter(sec(1.7));
  const b3 = useEnter(sec(3.4));
  return (
    <SceneFade>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          gap: 34,
          textAlign: "center",
        }}
      >
        <div style={{ ...b1, fontSize: 42, color: C.dim }}>
          Those happen most of the time.
        </div>
        <div style={{ ...b2, fontSize: 58, fontWeight: 800 }}>
          So how do we trust robots?
        </div>
        <div style={b3}>
          <div style={{ fontSize: 124, fontWeight: 900, color: C.green, letterSpacing: 14 }}>
            SENTINEL
          </div>
          <div style={{ fontSize: 37, marginTop: 8 }}>
            it works with the robot to stop unsafe actions
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

const BARS28 = [
  { name: "LLM alone (naive)", v: 60.4, sd: 2.4, c: C.red },
  { name: "LLM checks its own plan", v: 44.3, sd: 2.4, c: C.amber },
  { name: "Sentinel, block only", v: 29.7, sd: 1.6, c: C.blue },
  { name: "LLM × Sentinel loop", v: 18.8, sd: 1.6, c: C.green },
];

// V28: BenchV27 with beats shifted 2.3 s earlier — the "Don't take the
// demos' word for it." opener was cut, so every beat moves with the voice.
export const BenchV28: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const note = useEnter(sec(3.7));
  const limit = useEnter(sec(7.7));
  const learn = useEnter(sec(11.7));
  const maxW = 980;
  return (
    <SceneFade>
      <div style={{ ...padV27, gap: 40 }}>
        <div style={head}>
          <Kicker>Benchmark · all 128 scenarios</Kicker>
          <Title size={54}>Unsafe actions executed (lower is better)</Title>
          <div style={{ fontSize: 30, color: C.dim, marginTop: 8 }}>
            3 independent repeats · 10 hazard categories · half are safe controls · labels
            frozen before the first run
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {BARS28.map((b, i) => {
            const grow = interpolate(frame, [sec(0.5) + i * 25, sec(0.5) + 40 + i * 25], [0, 1], {
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
        <div style={{ ...learn, fontSize: 30 }}>
          And it <b style={{ color: C.green }}>improves as memory improves</b>: every incident can
          become a new rule.
        </div>
      </div>
    </SceneFade>
  );
};
