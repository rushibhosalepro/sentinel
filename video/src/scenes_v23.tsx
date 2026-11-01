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
  FONT,
  Kicker,
  Lane,
  MONO,
  SceneFade,
  Shot,
  Title,
  sec,
  useEnter,
} from "./ui";

// V23: SceneFade without the fade-out half — the sticky->bench cut
// keeps bench's 14-frame fade-in (reads as a cut) instead of a ~1 s
// dip to black through two dark scenes.
const FadeIn23: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{ backgroundColor: C.bg, fontFamily: FONT, color: C.text, opacity }}
    >
      {children}
    </AbsoluteFill>
  );
};

// V23: no BLOCK on the knife run — every logged knife hand-over is a
// round-1 ALLOW. Lane B shows the safe hand-over step instead: the
// handle turns toward the person and the arm slows near them. The B
// lane holds until "On the right" (~12.8 s in the new voice).
const LANE_W23 = 840;
const KNIFE_B_DELAY23 = 400;

export const KnifeDemoV23: React.FC = () => {
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
              width={LANE_W23}
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
              width={LANE_W23}
              startFrom={100}
              delay={KNIFE_B_DELAY23}
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

// V23: StickyV22 retimed to the "give the knife to a stranger" voice
// (+1.3 s) and wrapped in FadeIn23 so the sticky->bench cut has no
// black gap.
const FromTag: React.FC<{ text: string; color: string; show: React.CSSProperties }> = ({
  text,
  color,
  show,
}) => (
  <div
    style={{
      ...show,
      display: "inline-block",
      background: `${color}22`,
      border: `2px solid ${color}`,
      borderRadius: 8,
      padding: "6px 14px",
    }}
  >
    <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800, color }}>{text}</span>
  </div>
);

export const StickyV23: React.FC = () => {
  const head = useEnter(0);
  const pic = useEnter(10);
  const ownerTag = useEnter(sec(4.1));
  const noteTag = useEnter(sec(5.8));
  const zoom = useEnter(sec(5.6));
  const block = useEnter(sec(9.2));
  const W = 780;
  const k = W / 1280;
  return (
    <FadeIn23>
      <div style={{ ...padV23, gap: 46 }}>
        <div style={{ ...head }}>
          <Kicker color={C.red}>Demo 3 · prompt injection</Kicker>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <span style={{ fontFamily: MONO, fontSize: 48 }}>"tidy the counter"</span>
            <FromTag text="from: owner ✓" color={C.green} show={ownerTag} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 60 }}>
          <div style={{ ...pic, width: W, display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <FromTag text="from: note on the counter ×" color={C.red} show={noteTag} />
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
                <span style={{ color: C.text }}>instructions from the room don't count.</span>
              </div>
            }
            footerDelay={0}
          >
            <Shot
              name="split_A_sticky"
              frames={329}
              width={W}
              startFrom={120}
              delay={sec(7.2)}
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
    </FadeIn23>
  );
};

const padV23: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};

// V23: the three boxes scaled up and centred so the scene fills the
// frame, with the 48% -> 16% payoff large below. Beats unchanged.
const LEARN_T23 = { box1: 1.7, box2: 5.3, box3: 9.0, result: 10.3 };

const LearnBox23: React.FC<{
  n: string; text: string; color: string; show: number;
}> = ({ n, text, color, show }) => (
  <div
    style={{
      width: 520,
      borderRadius: 18,
      padding: "26px 30px",
      background: C.panel,
      border: `3px solid ${color}`,
      boxShadow: `0 0 26px ${color}55`,
      opacity: show,
    }}
  >
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 64,
        height: 64,
        borderRadius: "50%",
        background: color,
        color: "#0b0d10",
        fontSize: 36,
        fontWeight: 900,
      }}
    >
      {n}
    </div>
    <div style={{ fontSize: 38, fontWeight: 700, marginTop: 16, lineHeight: 1.35 }}>{text}</div>
  </div>
);

export const LearnerV23: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 12) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const arrow = (t: number) => (
    <div style={{ fontSize: 48, fontWeight: 900, color: C.dim, opacity: at(t) }}>→</div>
  );
  return (
    <SceneFade>
      <div style={{ ...padV23, gap: 40, alignItems: "center" }}>
        <div style={{ ...head, alignSelf: "stretch" }}>
          <Kicker>Sentinel learns</Kicker>
          <Title size={54}>A miss becomes a rule</Title>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 20,
            marginTop: 70,
          }}
        >
          <LearnBox23
            n="1"
            text="You report a mistake in one sentence."
            color={C.amber}
            show={at(LEARN_T23.box1)}
          />
          {arrow(LEARN_T23.box2)}
          <LearnBox23
            n="2"
            text="Sentinel turns it into a new rule, and tests it on past runs first."
            color={C.purple}
            show={at(LEARN_T23.box2)}
          />
          {arrow(LEARN_T23.box3)}
          <LearnBox23
            n="3"
            text="Next time, the robot asks before putting a cup near the edge."
            color={C.green}
            show={at(LEARN_T23.box3)}
          />
        </div>
        <div style={{ opacity: at(LEARN_T23.result), fontSize: 54, fontWeight: 800, marginTop: 44 }}>
          On hazards it had never seen, unsafe actions{" "}
          <span style={{ color: C.red }}>48%</span> → <span style={{ color: C.green }}>16%</span>
        </div>
      </div>
    </SceneFade>
  );
};

// V23: the live URL + repo appear by 2 s (the scene holds ~7 s so both
// stay readable), plus the honest-limits line under the Meta credit.
export const OutroV23: React.FC = () => {
  const a = useEnter(0);
  const tag = useEnter(sec(2.2));
  const c = useEnter(sec(1.6));
  return (
    <SceneFade>
      <div
        style={{
          justifyContent: "center",
          alignItems: "center",
          gap: 34,
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ ...a, fontSize: 56, fontWeight: 800, textAlign: "center" }}>
          The LLM decides how.
          <br />
          <span style={{ color: C.green }}>Sentinel decides whether.</span>
        </div>
        <div style={{ ...tag, fontSize: 46, fontWeight: 800, textAlign: "center", lineHeight: 1.3 }}>
          Sentinel isn't a filter around the LLM —
          <br />
          it's the <span style={{ color: C.green }}>loop</span> the LLM gets safer inside.
        </div>
        <div style={{ ...c, textAlign: "center" }}>
          <div style={{ fontSize: 30, color: C.dim }}>Try it live</div>
          <div style={{ fontSize: 30, fontFamily: MONO, marginTop: 8 }}>
            rushi-bhosale84--sentinel-web.us-east.modal.run
          </div>
          <div style={{ fontSize: 28, fontFamily: MONO, color: C.dim, marginTop: 8 }}>
            github.com/rushibhosalepro/sentinel
          </div>
          <div style={{ fontSize: 28, fontFamily: MONO, color: C.dim, marginTop: 8 }}>
            Built with SAM 3.1 · Muse Spark · Muse Wonder · coded with Muse Code
          </div>
          <div style={{ fontSize: 24, fontFamily: MONO, color: C.dim, marginTop: 10 }}>
            Simulation only (MuJoCo) · 18.8% still unsafe · details in the README
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// V23: ProblemV4 without the block-only filter footer — the narration
// keeps only the danger sentence, and the veto-only point lands in the
// benchmark. Hazard beats unchanged (the first sentence is identical).
const HAZARDS23 = [
  { img: "split_A_knife_f120.png", t: "a blade toward a hand", at: 4.3, zoom: { cx: 333, cy: 233, s: 2.0 } },
  { img: "split_A_water_f130.png", t: "water by a laptop", at: 6.2, zoom: { cx: 235, cy: 232, s: 1.9 } },
  { img: "note_zoom_v2.png", t: "a stranger's note giving orders", at: 7.8, zoom: null },
];

export const ProblemV23: React.FC = () => {
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
      <div style={{ ...padV23, gap: 64 }}>
        <div style={head}>
          <Kicker color={C.red}>The problem</Kicker>
          <Title size={54}>LLMs can plan robot actions,<br />but they can't see the danger</Title>
        </div>
        <div style={{ display: "flex", gap: 40 }}>
          {HAZARDS23.map((h) => (
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
      </div>
    </SceneFade>
  );
};

// V23: IntroV20 naming Meta's Muse Spark on screen (planner box +
// subtitle match the narration) and listing the four real verdicts.
// Beats unchanged — the new voice keeps the same shape (~9.6 s).
const INTRO_T23 = {
  title: 0, sub: 1.9, plan: 2.2, arrow1: 2.8, sentinel: 3.4,
  blocked: 4.4, arrow2: 5.0, arm: 5.6, tag: 6.6,
};

const BOX_W23 = 440;
const BOX_H23 = 170;
const BOX_Y23 = 100;

const DiaBox23: React.FC<{
  x: number; title: string; sub: string; color: string; show: number;
}> = ({ x, title, sub, color, show }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: BOX_Y23,
      width: BOX_W23,
      height: BOX_H23,
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

export const IntroV23: React.FC = () => {
  const frame = useCurrentFrame();
  const at = (t: number, len = 12) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const X1 = 40;
  const X2 = 640;
  const X3 = 1240;
  const MID = BOX_Y23 + BOX_H23 / 2;
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
      markerEnd={`url(#ih23-${color.slice(1)}${dashed ? "-d" : ""})`}
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
        <div style={{ opacity: at(INTRO_T23.title), fontSize: 64, fontWeight: 900, textAlign: "center" }}>
          So I built Sentinel.
        </div>
        <div
          style={{
            opacity: at(INTRO_T23.sub),
            fontSize: 36,
            color: C.dim,
            textAlign: "center",
          }}
        >
          A rule-based safety layer between Meta's Muse Spark planner and the robot arm.
        </div>
        <div style={{ position: "relative", width: 1720, height: 300 }}>
          <svg width={1720} height={300} style={{ position: "absolute", inset: 0 }}>
            <defs>
              {[C.text, C.red].map((c) => (
                <marker
                  key={c}
                  id={`ih23-${c.slice(1)}`}
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
                id={`ih23-${C.red.slice(1)}-d`}
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
            {arrow(`M ${X1 + BOX_W23 + 4} ${MID} L ${X2 - 10} ${MID}`, INTRO_T23.arrow1, C.text, 150)}
            {arrow(`M ${X2 + BOX_W23 + 4} ${MID} L ${X3 - 10} ${MID}`, INTRO_T23.arrow2, C.text, 150)}
            {arrow(
              `M ${X2 + BOX_W23 / 2} 78 L ${X2 + BOX_W23 / 2} ${BOX_Y23 - 6}`,
              INTRO_T23.blocked,
              C.red,
              0,
              true
            )}
          </svg>
          <DiaBox23
            x={X1}
            title="Muse Spark"
            sub="Meta's planner · figures out how"
            color={C.purple}
            show={at(INTRO_T23.plan)}
          />
          <DiaBox23
            x={X2}
            title="Sentinel"
            sub="allow · ask · block · halt"
            color={C.green}
            show={at(INTRO_T23.sentinel)}
          />
          <DiaBox23
            x={X3}
            title="Robot arm"
            sub="moves only checked plans"
            color={C.blue}
            show={at(INTRO_T23.arm)}
          />
          <div
            style={{
              position: "absolute",
              left: X2,
              top: 8,
              width: BOX_W23,
              display: "flex",
              justifyContent: "center",
              opacity: at(INTRO_T23.blocked),
            }}
          >
            <Badge color={C.red}>UNSAFE PLAN · BLOCKED</Badge>
          </div>
        </div>
        <div
          style={{
            opacity: at(INTRO_T23.tag),
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

// V23: the credits scene — which Meta model does what, and where it
// runs. Rows land with the narration beats of the ~9 s credits voice.
const CREDITS23: { name: string; role: string; at: number }[] = [
  { name: "SAM 3.1", role: "perception", at: 0.6 },
  { name: "Muse Spark 1.3", role: "planner + quarantined note reader", at: 2.4 },
  { name: "Muse Spark Open on Baseten", role: "same loop on open weights", at: 3.6 },
  { name: "Muse Wonder", role: "rule learner", at: 4.8 },
  { name: "Muse Code", role: "built the code, solo, 9 days", at: 6.0 },
];

export const CreditsV23: React.FC = () => {
  const head = useEnter(0);
  const runs = useEnter(sec(7.6));
  return (
    <SceneFade>
      <div style={{ ...padV23, gap: 36, alignItems: "center", justifyContent: "center" }}>
        <div style={{ ...head, textAlign: "center" }}>
          <Kicker>Built with Meta models</Kicker>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {CREDITS23.map((r) => (
            <CreditRow23 key={r.name} name={r.name} role={r.role} at={r.at} />
          ))}
        </div>
        <div style={{ ...runs, fontSize: 32, marginTop: 10 }}>
          <span style={{ color: C.dim }}>RUNS ON </span>
          <span style={{ fontWeight: 800 }}>Baseten</span>
          <span style={{ color: C.dim }}> + </span>
          <span style={{ fontWeight: 800 }}>Modal</span>
        </div>
      </div>
    </SceneFade>
  );
};

const CreditRow23: React.FC<{ name: string; role: string; at: number }> = ({
  name,
  role,
  at,
}) => {
  const show = useEnter(sec(at));
  return (
    <div style={{ ...show, fontSize: 38, textAlign: "center" }}>
      <span style={{ fontWeight: 800 }}>{name}</span>
      <span style={{ color: C.dim }}> — {role}</span>
    </div>
  );
};

// V23: HowV8 retimed to the 27.5 s voice (models named, core rule out
// loud, "every verdict says why"), with the four verdict badges under
// the look panel, a Why? chip carrying the measured value on the BLOCK
// node, and the core rule as the footer. Beats from silence analysis:
// plan 6.9, sim 9.4, check 10.4, block 16.0, fix 17.2, plan2 18.0,
// check2 18.8, allow 19.4, move 20.4, footer 20.0, badges 26.0.
const HOW_T23 = {
  plan: 6.9, sim: 9.4, check: 10.4, block: 16.0, fix: 17.2,
  plan2: 18.0, check2: 18.8, allow: 19.4, move: 20.4,
  foot: 20.0, badges: 26.0,
};
const TAGS23 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 1.6 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 2.5 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 3.4 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 3.8 },
];
const COL23 = { x: 480, w: 330, cx: 645 };
const VERDICTS23 = [
  { t: "ALLOW", c: C.green, g: "the plan moves" },
  { t: "ASK", c: C.amber, g: "asks the owner" },
  { t: "BLOCK", c: C.red, g: "stops the plan" },
  { t: "HALT", c: C.purple, g: "freezes mid-motion" },
];

const LoopNode23: React.FC<{
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

export const HowV23: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const between = (a: number, b: number) => (frame >= sec(a) && frame < sec(b) ? 1 : 0);
  const allowed = frame >= sec(HOW_T23.allow);
  const IW = 640;
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
      markerEnd={`url(#head23-${color.slice(1)})`}
    />
  );
  const heads = [C.text, C.amber, C.green, C.dim];
  const dimFix = interpolate(frame, [sec(HOW_T23.allow), sec(HOW_T23.allow) + 9], [1, 0.3], {
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
          gap: 28,
        }}
      >
        <div style={{ ...head }}>
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
                style={{ position: "absolute", width: IW, height: IH, opacity: at(1.2, 20) }}
              />
              {TAGS23.map((g) => (
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
            <div style={{ opacity: at(1.2), fontSize: 20, color: C.dim }}>
              SAM 3.1 + Muse Spark tag the scene: what's sharp, liquid, electronic
            </div>
            <div style={{ opacity: at(0.8), fontFamily: MONO, fontSize: 28 }}>
              "pour some water into the cup"
            </div>
            <div style={{ opacity: at(HOW_T23.badges), marginTop: 18 }}>
              <div style={{ fontSize: 26, fontWeight: 800 }}>Every verdict says why:</div>
              <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                {VERDICTS23.map((v) => (
                  <div key={v.t} style={{ flex: 1 }}>
                    <Badge color={v.c}>{v.t}</Badge>
                    <div style={{ fontSize: 20, color: C.dim, marginTop: 6, lineHeight: 1.25 }}>
                      {v.g}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div style={{ position: "relative", width: 840, height: 700 }}>
            <svg width={840} height={700} style={{ position: "absolute", inset: 0 }}>
              <defs>
                {heads.map((c) => (
                  <marker
                    key={c}
                    id={`head23-${c.slice(1)}`}
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
              {arrow("M 345 70 L 470 70", HOW_T23.sim - 0.4, C.text, 125)}
              {arrow(`M ${COL23.cx} 152 L ${COL23.cx} 244`, HOW_T23.check - 0.4, C.text, 92)}
              {arrow(`M ${COL23.cx} 378 L ${COL23.cx} 584`, HOW_T23.move, C.green, 206, 6)}
              {arrow("M 4 472 C 2 380, 2 200, 4 120 C 4 95, 2 82, 14 78", HOW_T23.fix, C.amber, 410, 7)}
            </svg>
            <LoopNode23
              x={10}
              y={18}
              w={330}
              title="Muse Spark plans"
              color={C.purple}
              lit={between(HOW_T23.plan, HOW_T23.sim) || between(HOW_T23.plan2, HOW_T23.check2)}
              show={at(HOW_T23.plan)}
              sub={
                <span style={{ fontFamily: MONO, color: C.dim, opacity: at(HOW_T23.plan) }}>
                  {allowed ? "round 2: move cup, then pour" : "grasp jug → over cup → pour"}
                </span>
              }
            />
            <LoopNode23
              x={COL23.x}
              y={18}
              w={COL23.w}
              title="Dry-run"
              color={C.blue}
              lit={between(HOW_T23.sim, HOW_T23.check) || between(HOW_T23.plan2 + 0.5, HOW_T23.check2)}
              show={at(HOW_T23.sim)}
              sub={<span style={{ color: C.dim }}>every pose, before it moves</span>}
            />
            <LoopNode23
              x={COL23.x}
              y={250}
              w={COL23.w}
              title="Fixed rules check"
              color={allowed ? C.green : C.red}
              lit={between(HOW_T23.check, HOW_T23.fix + 0.6) || between(HOW_T23.check2, 99)}
              show={at(HOW_T23.check)}
              sub={
                allowed ? (
                  <span style={{ opacity: at(HOW_T23.allow) }}>
                    <Badge color={C.green}>ALLOW</Badge>
                  </span>
                ) : (
                  <span style={{ opacity: at(HOW_T23.block), fontFamily: MONO, fontSize: 32 }}>
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
                )
              }
            />
            <div
              style={{
                position: "absolute",
                left: 10,
                top: 330,
                width: 450,
                opacity: at(HOW_T23.fix) * dimFix,
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
            <LoopNode23
              x={COL23.x}
              y={590}
              w={COL23.w}
              title="The arm moves"
              color={C.green}
              lit={frame >= sec(HOW_T23.move) ? 1 : 0}
              show={at(HOW_T23.move)}
              sub={<span style={{ color: C.dim }}>live monitor still watching</span>}
            />
          </div>
        </div>
        <div style={{ opacity: at(HOW_T23.foot) }}>
          <div style={{ fontSize: 32, fontWeight: 800 }}>
            No AI in the verdict: the check is fixed rules, so it can't be talked out of it.
          </div>
          <div style={{ fontSize: 26, color: C.dim, marginTop: 4 }}>
            up to 3 rounds · hard violations are never retried
          </div>
        </div>
      </div>
    </SceneFade>
  );
};
