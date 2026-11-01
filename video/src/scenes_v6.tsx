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
  MONO,
  SceneFade,
  Title,
  sec,
  useEnter,
} from "./ui";

// V6: stack restored to the v3 version (per-model rows + RUNNING ON +
// terminal card). Same layout as StackV2; reveals compressed into the
// frozen 6.9 s scene (v3 had 10.3 s): model rows while the narration
// says "Meta API models", Code row on "Muse Code", partners on
// "Baseten and Modal", card alongside.
const STACK6 = [
  ["SAM 3.1", "segments every object"],
  ["Muse Spark 1.3", "plans, replans, reads scene text in quarantine"],
  ["Muse Spark Open", "the same loop on open weights, on Baseten"],
  ["Muse Wonder", "proposes new rules from incidents"],
  ["Muse Code", "built the code with me, solo, in 9 days"],
];

const PARTNERS6 = [
  ["Baseten", "serves Muse Spark Open, the open-weights planner"],
  ["Modal", "hosts the live app anyone can try"],
];

const PROOF6: React.ReactNode[] = [
  <div key="c"><span style={{ color: C.green }}>$</span> uv run python -m planner.planner \<br />&nbsp;&nbsp;"put the apple next to the sponge" --model spark-open</div>,
  <div key="p" style={{ color: C.dim }}>plan took 13.2 s (model=meta-models/muse-spark-open)</div>,
  <div key="s1">&nbsp;&nbsp;s1 move_to {"{…}"} <span style={{ color: C.dim }}># staging pose</span></div>,
  <div key="s4">&nbsp;&nbsp;s4 grasp {"{\"object_id\": \"apple\"}"} <span style={{ color: C.dim }}># Attach apple.</span></div>,
  <div key="e" style={{ color: C.dim }}>&nbsp;&nbsp;···</div>,
  <div key="s9">&nbsp;&nbsp;s9 release {"{}"} <span style={{ color: C.dim }}># Place apple next to sponge.</span></div>,
  <div key="s11">&nbsp;&nbsp;s11 stop {"{}"} <span style={{ color: C.dim }}># Task complete.</span></div>,
  <div key="m">Motion: 142 samples over 6.34 s, held=None <span style={{ color: C.green }}>✓</span></div>,
];

const padV6: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};

export const StackV6: React.FC = () => {
  const head = useEnter(0);
  const rows = [useEnter(sec(0.3)), useEnter(sec(0.9)), useEnter(sec(1.5)), useEnter(sec(2.1)), useEnter(sec(2.7))];
  const head2 = useEnter(sec(3.4));
  const prow = [useEnter(sec(3.8)), useEnter(sec(4.6))];
  const proof = useEnter(sec(2.5));
  const Row = (m: string, w: string, style: React.CSSProperties) => (
    <div key={m} style={{ ...style, display: "flex", gap: 30, alignItems: "baseline" }}>
      <div style={{ width: 430, fontSize: 40, fontWeight: 800 }}>{m}</div>
      <div style={{ fontSize: 28, color: C.dim }}>{w}</div>
    </div>
  );
  return (
    <SceneFade>
      <div style={{ ...padV6, gap: 24 }}>
        <div style={head}>
          <Kicker>Built with Meta models</Kicker>
        </div>
        <div style={{ display: "flex", gap: 48, alignItems: "flex-start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 22, flex: 1 }}>
            {STACK6.map(([m, w], i) => Row(m, w, rows[i]))}
            <div style={{ ...head2, marginTop: 14 }}>
              <Kicker color={C.blue}>Running on</Kicker>
            </div>
            {PARTNERS6.map(([m, w], i) => Row(m, w, prow[i]))}
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
            {PROOF6}
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- outro
// V6: tagline restored to the v3 line ("...around the LLM — it's the
// loop the LLM gets safer inside"), loop stays green. Timings unchanged.
export const OutroV6: React.FC = () => {
  const a = useEnter(0);
  const tag = useEnter(sec(3.8));
  const c = useEnter(sec(9.3));
  return (
    <SceneFade>
      <div style={{ justifyContent: "center", alignItems: "center", gap: 30, position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}>
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

// ---------------------------------------------------------------- rule learner
// V6: graph panel cropped tight + shown at 680 (was 560 of an uncropped
// 900) — ~1.5x larger content, still below source resolution so no
// blur. Result line 38 -> 34 to fit the row; gap tightened to hold
// the frame.
const GATE6 = ["schema", "replay", "ratchet", "preflight"];

export const LearnerV6: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const inc = useEnter(sec(1));
  const prop = useEnter(sec(4));
  const v1 = useEnter(sec(8));
  const v2 = useEnter(sec(11));
  const res = useEnter(sec(13.5));
  return (
    <SceneFade>
      <div style={{ ...padV6, gap: 28 }}>
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
              {GATE6.map((g, i) => {
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
        <div style={{ display: "flex", gap: 40, alignItems: "center" }}>
          <div style={{ ...res, fontSize: 34, fontWeight: 700, flex: 1 }}>
            Unseen-hazard scenarios, unsafe executed: 47.8% →{" "}
            <span style={{ color: C.green }}>15.9%</span>
            <div style={{ fontSize: 30, color: C.dim, fontWeight: 400, marginTop: 6 }}>
              The subset of hazards the hand-written rules never covered (69 cells), not the
              whole benchmark.
            </div>
          </div>
          <div style={{ ...res, width: 680, flexShrink: 0 }}>
            <Img
              src={staticFile("learner_graph_v6.png")}
              style={{ width: 680, borderRadius: 14, border: `2px solid ${C.line}` }}
            />
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- how it works
// V6: same two-column loop, reflowed for 2x detail text. The check node
// and fix row go full width (BLOCK reason 40 px mono, fix line 44 px),
// the footnote moves under the video at 40/38 px. Each pipeline box
// fades in when its step starts, and the request line appears before
// the object tags. Beats unchanged (frozen voice).
const HOW_T6 = {
  tags: 2.8, plan: 4.7, sim: 5.9, check: 7.2, block: 7.6, fix: 8.7,
  plan2: 9.8, check2: 10.6, allow: 11.1, move: 11.9,
};
const TAGS6 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 2.8 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 3.1 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 3.4 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 3.7 },
];

const LoopNode6: React.FC<{
  x: number; y: number; w: number; title: string; sub: React.ReactNode;
  color: string; lit: number; show: number;
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

export const HowV6: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const at = (t: number, len = 10) =>
    interpolate(frame, [sec(t), sec(t) + len], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const between = (a: number, b: number) => (frame >= sec(a) && frame < sec(b) ? 1 : 0);
  const round2 = frame >= sec(HOW_T6.plan2);
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
      markerEnd={`url(#head6-${color.slice(1)})`}
    />
  );
  const heads = [C.text, C.amber, C.green, C.dim];
  return (
    <SceneFade>
      <div style={{ ...padV6, gap: 26 }}>
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
              {TAGS6.map((g) => (
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
            <div style={{ opacity: at(HOW_T6.move + 0.4), marginTop: 26 }}>
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
                    id={`head6-${c.slice(1)}`}
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
              {arrow("M 345 70 L 470 70", HOW_T6.sim - 0.4, C.text, 125)}
              {arrow("M 650 150 L 650 245", HOW_T6.check - 0.4, C.text, 95)}
              {arrow("M 650 422 L 650 438", HOW_T6.fix - 0.2, C.text, 16)}
              {arrow("M 650 568 L 650 588", HOW_T6.move, C.green, 20, 6)}
              {arrow("M 3 500 C 1 400, 2 230, 30 135", HOW_T6.fix, C.amber, 380, 7)}
            </svg>
            <LoopNode6
              x={10}
              y={18}
              w={330}
              title="Muse Spark plans"
              color={C.purple}
              lit={between(HOW_T6.plan, HOW_T6.sim) || between(HOW_T6.plan2, HOW_T6.check2)}
              show={at(HOW_T6.plan)}
              sub={
                <span style={{ fontFamily: MONO, color: C.dim, opacity: at(HOW_T6.plan) }}>
                  {round2 ? "round 2: move cup, then pour" : "grasp jug → over cup → pour"}
                </span>
              }
            />
            <LoopNode6
              x={480}
              y={18}
              w={330}
              title="Dry-run"
              color={C.blue}
              lit={between(HOW_T6.sim, HOW_T6.check) || between(HOW_T6.plan2 + 0.5, HOW_T6.check2)}
              show={at(HOW_T6.sim)}
              sub={<span style={{ color: C.dim }}>every pose, before it moves</span>}
            />
            <LoopNode6
              x={10}
              y={250}
              w={820}
              title="Fixed rules check"
              color={frame >= sec(HOW_T6.allow) ? C.green : C.red}
              lit={between(HOW_T6.check, HOW_T6.fix + 0.6) || between(HOW_T6.check2, 99)}
              show={at(HOW_T6.check)}
              sub={
                frame >= sec(HOW_T6.allow) ? (
                  <span style={{ opacity: at(HOW_T6.allow) }}>
                    <Badge color={C.green}>ALLOW</Badge>
                  </span>
                ) : (
                  <span style={{ opacity: at(HOW_T6.block), fontFamily: MONO, fontSize: 40 }}>
                    <span style={{ color: C.red, fontWeight: 800 }}>BLOCK</span>{" "}
                    <span style={{ color: C.text }}>liquid near laptop</span>
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
                top: 440,
                width: 820,
                opacity: at(HOW_T6.fix),
              }}
            >
              <div style={{ fontSize: 40, fontWeight: 700, color: C.amber }}>
                BLOCK + a concrete fix:
              </div>
              <div style={{ fontFamily: MONO, fontSize: 44, color: C.amber, marginTop: 6 }}>
                move the cup to (0.20, 0.15)
              </div>
            </div>
            <LoopNode6
              x={480}
              y={590}
              w={330}
              title="The arm moves"
              color={C.green}
              lit={frame >= sec(HOW_T6.move) ? 1 : 0}
              show={at(HOW_T6.move)}
              sub={<span style={{ color: C.dim }}>live monitor still watching</span>}
            />
          </div>
        </div>
      </div>
    </SceneFade>
  );
};
