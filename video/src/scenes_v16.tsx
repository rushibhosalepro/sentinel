import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { Badge, C, Kicker, MONO, SceneFade, sec, useEnter } from "./ui";

// ---------------------------------------------------------------- learning loop
// V16: the learner and the app's Rules tab in one scene, drawn as a cycle:
// owner reports -> Muse Wonder writes a rule -> the gate tests it on past
// runs -> the rule joins the check, and every next plan is checked against
// it. App crops come from public/rules_tab.png (the dashboard Rules tab).
// Beat times are tuned to voice/learner.wav.
export const LEARN_T = { report: 3.3, write: 6.2, gate: 8.7, live: 15.4, result: 20.0 };

const CARD_W = 800;
const CARD_H = 345;

const LearnCard: React.FC<{
  x: number;
  y: number;
  n: string;
  title: string;
  color: string;
  on: number;
  children: React.ReactNode;
}> = ({ x, y, n, title, color, on, children }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: CARD_W,
      height: CARD_H,
      opacity: 0.25 + 0.75 * on,
      background: C.panel,
      border: `3px solid ${on > 0.5 ? color : C.line}`,
      borderRadius: 18,
      padding: "20px 26px",
      boxShadow: on > 0.5 ? `0 0 28px ${color}55` : "none",
      display: "flex",
      flexDirection: "column",
      gap: 14,
    }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 24,
          background: color,
          color: "#0b0f14",
          fontSize: 28,
          fontWeight: 900,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {n}
      </div>
      <div style={{ fontSize: 40, fontWeight: 800 }}>{title}</div>
    </div>
    {children}
  </div>
);

const Check: React.FC<{ on: number; children: React.ReactNode }> = ({ on, children }) => (
  <div style={{ opacity: on, fontSize: 32, display: "flex", gap: 10 }}>
    <span style={{ color: C.green, fontWeight: 900 }}>✓</span>
    <span>{children}</span>
  </div>
);

export const LearningV16: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 12) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  // card positions inside the 1720-wide content box
  const L = 40;
  const R = 880;
  const TOP = 0;
  const BOT = 420;
  const arrow = (d: string, t: number, color: string, len: number) => (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={6}
      strokeLinecap="round"
      strokeDasharray={len}
      strokeDashoffset={len * (1 - at(t, 14))}
      opacity={at(t, 14) > 0.02 ? 1 : 0}
      markerEnd={`url(#lh-${color.slice(1)})`}
    />
  );
  return (
    <SceneFade>
      <AbsoluteFill style={{ padding: "48px 100px", display: "flex", flexDirection: "column", gap: 22 }}>
        <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 26 }}>
          <Kicker>Sentinel learns</Kicker>
          <span style={{ fontSize: 42, fontWeight: 800 }}>a miss becomes a rule, but only if it passes a test</span>
        </div>
        <div style={{ position: "relative", width: 1720, height: 770 }}>
          <svg width={1720} height={770} style={{ position: "absolute", inset: 0 }}>
            <defs>
              {[C.amber, C.purple, C.green, C.blue].map((c) => (
                <marker
                  key={c}
                  id={`lh-${c.slice(1)}`}
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
            {arrow(`M ${L + CARD_W + 2} ${CARD_H / 2} L ${R - 8} ${CARD_H / 2}`, LEARN_T.write - 0.3, C.amber, 36)}
            {arrow(`M ${R + CARD_W / 2} ${TOP + CARD_H + 2} L ${R + CARD_W / 2} ${BOT - 8}`, LEARN_T.gate - 0.3, C.purple, 70)}
            {arrow(`M ${R - 2} ${BOT + CARD_H / 2} L ${L + CARD_W + 8} ${BOT + CARD_H / 2}`, LEARN_T.live - 0.3, C.green, 36)}
            {arrow(`M ${L + CARD_W / 2} ${BOT - 2} L ${L + CARD_W / 2} ${TOP + CARD_H + 8}`, 17.4, C.blue, 70)}
          </svg>

          <LearnCard x={L} y={TOP} n="1" title="The owner reports a miss" color={C.amber} on={at(LEARN_T.report)}>
            <div style={{ fontSize: 30, color: C.dim }}>
              The cup was set down at the counter edge. Every rule said ALLOW.
            </div>
            <Img
              src={staticFile("rules_incident.png")}
              style={{ width: CARD_W - 52, borderRadius: 8, border: `2px solid ${C.line}` }}
            />
            <div style={{ fontSize: 22, color: C.dim }}>one line, in the app's Rules tab</div>
          </LearnCard>

          <LearnCard x={R} y={TOP} n="2" title="Muse Wonder writes a rule" color={C.purple} on={at(LEARN_T.write)}>
            <div style={{ fontSize: 38, lineHeight: 1.35 }}>
              Let go of something within <b style={{ color: C.amber }}>8 cm</b> of the counter edge
              {" → "}
              <b style={{ color: C.amber }}>ASK</b> the owner
            </div>
            <div style={{ fontFamily: MONO, fontSize: 24, color: C.dim }}>
              release_near_edge(edge_cm=8) → ASK
            </div>
            <div style={{ fontSize: 22, color: C.dim }}>
              built from a fixed rule vocabulary, never free-form code
            </div>
          </LearnCard>

          <LearnCard x={R} y={BOT} n="3" title="A gate tests it on past runs" color={C.green} on={at(LEARN_T.gate)}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 24px" }}>
              <Check on={at(11.6, 8)}>catches the incident</Check>
              <Check on={at(13.0, 8)}>safe runs still pass</Check>
              <Check on={at(13.9, 8)}>never weakens a block</Check>
              <Check on={at(14.5, 8)}>catches 4 variations</Check>
            </div>
            <div style={{ opacity: at(14.9), fontSize: 26, color: C.dim, lineHeight: 1.35 }}>
              A first try at 15 cm refused <b style={{ color: C.red }}>38%</b> of safe placements in the
              audit, so it was tightened to 8 cm.
            </div>
          </LearnCard>

          <LearnCard x={L} y={BOT} n="4" title="It joins the rule check" color={C.blue} on={at(LEARN_T.live)}>
            <Img
              src={staticFile("rules_rule.png")}
              style={{ width: CARD_W - 52, borderRadius: 8, border: `2px solid ${C.line}` }}
            />
            <div style={{ fontSize: 32 }}>
              Next time: cup near the edge → <Badge color={C.amber}>ASK</Badge>
            </div>
            <div style={{ fontSize: 22, color: C.dim }}>the owner can roll it back any time</div>
          </LearnCard>

          <div
            style={{
              position: "absolute",
              left: L + CARD_W / 2 + 22,
              top: TOP + CARD_H + 14,
              opacity: at(17.8),
              fontSize: 22,
              fontWeight: 700,
              color: C.blue,
            }}
          >
            every next plan is checked against it
          </div>
        </div>
        <div style={{ opacity: at(LEARN_T.result), fontSize: 36, fontWeight: 700 }}>
          Hazards the hand-written rules never covered: unsafe actions{" "}
          <span style={{ color: C.red }}>48%</span> → <span style={{ color: C.green }}>16%</span>
          <span style={{ fontSize: 24, color: C.dim, fontWeight: 400 }}>
            {"  "}(69 benchmark cells)
          </span>
        </div>
      </AbsoluteFill>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- outro
// V16: OutroV6 with the link block brought in at 4.2 s (it was at 9.3 s in
// a 6 s scene, so the URL and repo never showed).
export const OutroV16: React.FC = () => {
  const a = useEnter(0);
  const tag = useEnter(sec(2.2));
  const c = useEnter(sec(4.2));
  return (
    <SceneFade>
      <div
        style={{
          justifyContent: "center",
          alignItems: "center",
          gap: 30,
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
        </div>
      </div>
    </SceneFade>
  );
};
