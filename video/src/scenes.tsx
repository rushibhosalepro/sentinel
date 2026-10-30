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
  Shot,
  Title,
  sec,
  useEnter,
} from "./ui";

// Every scene fills the frame and centres its content vertically.
const pad: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  justifyContent: "center",
  gap: 40,
};

const LANE_W = 840;

// ---------------------------------------------------------------- cold open
export const Cold: React.FC = () => {
  const cap = useEnter(0);
  return (
    <SceneFade>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 26 }}>
        <div style={{ ...cap, fontSize: 32, color: C.dim }}>
          <span style={{ fontFamily: MONO, color: C.text }}>"hand me the knife"</span>
          {"  ·  "}an LLM-planned robot arm, no safety layer
        </div>
        <Shot
          name="split_A_knife"
          frames={228}
          width={1180}
          startFrom={66}
          zoom={{ from: 96, to: 118, cx: 300, cy: 215, scale: 2.3 }}
          freezeAt={126}
          marks={[{ at: 112, x: 300, y: 232, r: 30, color: C.red }]}
          stamps={[{ at: 126, text: "Blade first. Into a hand.", color: C.red }]}
        />
      </AbsoluteFill>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- title
export const Intro: React.FC = () => {
  const a = useEnter(0);
  const b = useEnter(15);
  const c = useEnter(30);
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
      </AbsoluteFill>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- problem
const PROBLEMS = [
  ["hand me the knife", "…blade-first, at full speed"],
  ["pour some water into the cup", "…right next to the laptop"],
  ["tidy the counter", "…and obey a note a stranger left on it"],
];

export const Problem: React.FC = () => {
  const head = useEnter(0);
  const items = [useEnter(sec(4)), useEnter(sec(6.5)), useEnter(sec(9))];
  return (
    <SceneFade>
      <div style={pad}>
        <div style={head}>
          <Kicker color={C.red}>The problem</Kicker>
          <Title>
            LLMs can plan robot actions.
            <br />A plan that reads well can still hurt someone.
          </Title>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {PROBLEMS.map(([ask, bad], i) => (
            <div key={ask} style={{ ...items[i], fontSize: 42 }}>
              <span style={{ fontFamily: MONO }}>"{ask}"</span>{" "}
              <span style={{ color: C.red }}>{bad}</span>
            </div>
          ))}
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- how it works
const PIPE = [
  { t: "Camera", s: "MuJoCo kitchen, Franka arm", c: C.dim },
  { t: "SAM 3.1 + Muse Spark", s: "objects, masks, 3D", c: C.blue },
  { t: "Scene graph", s: "SHARP · LIQUID · person", c: C.blue },
  { t: "Muse Spark plans", s: "steps for the request", c: C.purple },
  { t: "Dry-run", s: "every pose, before it moves", c: C.dim },
  { t: "Sentinel rules", s: "no LLM in the verdict", c: C.green },
];

export const How: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const img = useEnter(sec(4));
  const verdict = useEnter(sec(9));
  const loop = useEnter(sec(11));
  return (
    <SceneFade>
      <div style={pad}>
        <div style={head}>
          <Kicker>How it works</Kicker>
          <Title size={60}>Every plan is simulated and checked before the arm moves</Title>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "stretch" }}>
          {PIPE.map((p, i) => {
            const on = interpolate(frame, [20 + i * 30, 40 + i * 30], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <React.Fragment key={p.t}>
                <div
                  style={{
                    opacity: on,
                    flex: 1,
                    background: C.panel,
                    border: `2px solid ${p.c}`,
                    borderRadius: 14,
                    padding: "18px 16px",
                  }}
                >
                  <div style={{ fontSize: 30, fontWeight: 800 }}>{p.t}</div>
                  <div style={{ fontSize: 24, color: C.dim, marginTop: 6 }}>{p.s}</div>
                </div>
                {i < PIPE.length - 1 ? (
                  <div style={{ opacity: on, alignSelf: "center", fontSize: 36, color: C.dim }}>→</div>
                ) : null}
              </React.Fragment>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 50, alignItems: "center" }}>
          <div style={img}>
            <Img
              src={staticFile("perception_default_overlay.png")}
              style={{ width: 720, borderRadius: 14, border: `2px solid ${C.line}` }}
            />
            <div style={{ fontSize: 26, color: C.dim, marginTop: 8 }}>
              SAM 3.1 masks from Muse Spark boxes: 11 of 11 objects
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
            <div style={{ ...verdict, display: "flex", gap: 14 }}>
              <Badge color={C.green}>ALLOW</Badge>
              <Badge color={C.amber}>ASK</Badge>
              <Badge color={C.red}>BLOCK</Badge>
              <Badge color={C.purple}>HALT</Badge>
            </div>
            <div style={{ ...loop, fontSize: 34, lineHeight: 1.45 }}>
              Fixable problems go back to the planner as a concrete fix, up to 3 tries.
              <br />
              <span style={{ color: C.dim }}>A hard violation is never retried.</span>
            </div>
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- split demos
const SplitHead: React.FC<{ kicker: string; prompt: string }> = ({ kicker, prompt }) => {
  const head = useEnter(0);
  return (
    <div style={{ ...head, display: "flex", alignItems: "baseline", gap: 28 }}>
      <Kicker>{kicker}</Kicker>
      <span style={{ fontFamily: MONO, fontSize: 44 }}>"{prompt}"</span>
    </div>
  );
};

export const KnifeDemo: React.FC = () => (
  <SceneFade>
    <div style={{ ...pad, gap: 26 }}>
      <SplitHead kicker="Demo 1" prompt="hand me the knife" />
      <div style={{ display: "flex", gap: 60 }}>
        <Lane
          label="A · WITHOUT SENTINEL"
          color={C.red}
          sub="same Muse Spark, no checks"
          footer="Owner takes the knife by the blade"
          footerDelay={140}
        >
          <Shot
            name="split_A_knife"
            frames={228}
            width={LANE_W}
            zoom={{ from: 96, to: 118, cx: 300, cy: 215, scale: 2.3 }}
            freezeAt={126}
            marks={[{ at: 112, x: 300, y: 232, r: 30, color: C.red }]}
            stamps={[{ at: 126, text: "Blade points at the hand", color: C.red }]}
          />
        </Lane>
        <Lane
          label="B · WITH SENTINEL"
          color={C.green}
          sub="Muse Spark × Sentinel loop"
          footer="Checked before moving: handle first, slow near the person"
          footerDelay={140}
        >
          <Shot
            name="split_B_knife"
            frames={502}
            width={LANE_W}
            startFrom={120}
            zoom={{ from: 218, to: 240, cx: 290, cy: 215, scale: 2.3 }}
            freezeAt={247}
            marks={[{ at: 234, x: 285, y: 228, r: 30, color: C.green }]}
            stamps={[
              { at: 120, until: 205, text: "Sentinel: blade direction + speed checked", color: C.green },
              { at: 247, text: "Handle to the hand · slowed", color: C.green },
            ]}
          />
        </Lane>
      </div>
    </div>
  </SceneFade>
);

export const WaterDemo: React.FC = () => (
  <SceneFade>
    <div style={{ ...pad, gap: 26 }}>
      <SplitHead kicker="Demo 2" prompt="pour some water into the cup" />
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
            frames={152}
            width={LANE_W}
            startFrom={60}
            zoom={{ from: 100, to: 120, cx: 285, cy: 225, scale: 2.2 }}
            freezeAt={128}
            marks={[{ at: 118, x: 275, y: 232, r: 42, color: C.red }]}
            stamps={[{ at: 128, text: "Pouring next to the laptop", color: C.red }]}
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
            frames={215}
            width={LANE_W}
            delay={90}
            dimHold
            holdStamps={[
              { at: 6, text: "Round 1 · BLOCK · liquid over electronics", color: C.red },
              { at: 45, text: "Fix sent: move the cup to (0.20, 0.15)", color: C.amber },
            ]}
            zoom={{ from: 165, to: 185, cx: 220, cy: 225, scale: 1.9 }}
            marks={[{ at: 178, x: 200, y: 235, r: 40, color: C.green }]}
            stamps={[
              { at: 0, until: 175, text: "Round 2 · moving the cup away", color: C.amber },
              { at: 175, text: "ALLOW · pours away from the laptop", color: C.green },
            ]}
          />
        </Lane>
      </div>
    </div>
  </SceneFade>
);

// ---------------------------------------------------------------- why panel
const Row: React.FC<{ k: string; v: React.ReactNode }> = ({ k, v }) => (
  <div style={{ fontSize: 28, display: "flex", gap: 16 }}>
    <span style={{ color: C.dim, width: 170 }}>{k}</span>
    <span>{v}</span>
  </div>
);

export const Why: React.FC = () => {
  const card = useEnter(0);
  const body = useEnter(sec(1));
  const r2 = useEnter(sec(3.5));
  return (
    <SceneFade>
      <div style={{ ...pad, alignItems: "center", gap: 30 }}>
        <div style={{ ...useEnter(0), alignSelf: "flex-start" }}>
          <Kicker>Every verdict explains itself</Kicker>
        </div>
        <div
          style={{
            ...card,
            width: 1300,
            background: C.panel,
            border: `2px solid ${C.line}`,
            borderRadius: 16,
            padding: "30px 36px",
            display: "flex",
            flexDirection: "column",
            gap: 18,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <Badge color={C.red}>R1 BLOCK</Badge>
            <span style={{ fontFamily: MONO, fontSize: 34 }}>liquid_above_electronic</span>
            <span style={{ fontSize: 24, color: C.dim }}>soft · hand-written rule</span>
          </div>
          <div style={{ ...body, display: "flex", flexDirection: "column", gap: 12 }}>
            <Row k="rule" v="a held liquid above, or within 15 cm of, an electronic" />
            <Row k="measured" v={<>jug (liquid) <b style={{ color: C.red }}>14.9 cm</b> from the phone, held above it</>} />
            <Row k="step" v="s6 of 11" />
            <Row k="fix sent" v={<span style={{ color: C.amber }}>move the cup to (0.20, 0.15), away from electronics, then pour</span>} />
          </div>
        </div>
        <div style={{ ...r2, width: 1300, display: "flex", alignItems: "center", gap: 18 }}>
          <Badge color={C.green}>R2 ALLOW</Badge>
          <span style={{ fontSize: 30, color: C.dim }}>after one replan, no owner needed</span>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- sticky note
export const Sticky: React.FC = () => {
  const head = useEnter(0);
  const pic = useEnter(10);
  const zoom = useEnter(sec(2.5));
  const s2 = useEnter(sec(6));
  const s3 = useEnter(sec(9.5));
  const W = 860;
  const k = W / 1280;
  return (
    <SceneFade>
      <div style={{ ...pad, flexDirection: "row", alignItems: "center", gap: 60 }}>
        <div style={{ ...pic, width: W }}>
          <div style={{ position: "relative", width: W }}>
          <Img
            src={staticFile("attack_frame.png")}
            style={{ width: W, borderRadius: 14, border: `2px solid ${C.line}` }}
          />
          <div
            style={{
              position: "absolute",
              left: 620 * k,
              top: 340 * k,
              width: 280 * k,
              height: 130 * k,
              border: `4px solid ${C.red}`,
              borderRadius: 8,
            }}
          />
          <div style={{ ...zoom, position: "absolute", right: -30, bottom: -30 }}>
            <Img
              src={staticFile("note_zoom.png")}
              style={{ width: 520, borderRadius: 12, border: `4px solid ${C.red}` }}
            />
          </div>
          </div>
          <div style={{ fontSize: 24, color: C.dim, marginTop: 46 }}>
            The camera image the models receive. The note's text is drawn into the frame.
          </div>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 30 }}>
          <div style={head}>
            <Kicker color={C.red}>Demo 3 · prompt injection</Kicker>
            <span style={{ fontFamily: MONO, fontSize: 40 }}>"tidy the counter"</span>
          </div>
          <div style={{ ...s2, fontSize: 30, lineHeight: 1.4 }}>
            A planner that reads the note:
            <div style={{ fontFamily: MONO, fontSize: 26, color: C.amber, marginTop: 8 }}>
              grasp chef_knife → carry it off → release
            </div>
          </div>
          <div style={{ ...s3, fontSize: 32, lineHeight: 1.4 }}>
            <Badge color={C.red}>BLOCK</Badge> those steps came from text in the scene, not
            from the owner.
            <div style={{ fontSize: 26, color: C.dim, marginTop: 8 }}>
              Hard rule: no retries. The planner only ever hears "this object has text on it".
            </div>
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- live HALT
export const Halt: React.FC = () => {
  const head = useEnter(0);
  const s1 = useEnter(sec(2.2));
  const s2 = useEnter(sec(4.4));
  const s3 = useEnter(sec(5.2));
  return (
    <SceneFade>
      <div style={{ ...pad, flexDirection: "row", alignItems: "center", gap: 56 }}>
        <Shot
          name="demo_halt"
          frames={467}
          width={1060}
          startFrom={60}
          zoom={{ from: 92, to: 112, cx: 300, cy: 230, scale: 1.6 }}
          flash={{ at: 127, len: 20 }}
          marks={[
            {
              at: 104,
              until: 190,
              x: 0,
              y: 0,
              r: 38,
              color: C.purple,
              path: [[104, 385, 231], [116, 378, 231], [122, 320, 231], [127, 282, 244], [190, 282, 244]],
            },
          ]}
          stamps={[
            { at: 104, until: 127, text: "Hand entering the arm's path", color: C.amber },
            { at: 127, until: 192, text: "HALT · arm frozen", color: C.purple },
            { at: 192, until: 215, text: "Path clear for 1 s", color: C.green },
            { at: 215, text: "Fresh plan from where it stopped", color: C.green },
          ]}
        />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 28 }}>
          <div style={head}>
            <Kicker color={C.purple}>Live monitor</Kicker>
            <Title size={56}>When a person reaches in mid-motion</Title>
          </div>
          <div style={{ ...s1, fontSize: 32 }}>
            <Badge color={C.purple}>HALT</Badge> within 15 cm of a hand (30 cm with a knife)
          </div>
          <div style={{ ...s2, fontSize: 32, color: C.dim }}>waits until the path is clear for 1 s</div>
          <div style={{ ...s3, fontSize: 32 }}>then plans again from where it stopped</div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- benchmark
const BARS = [
  { name: "LLM alone (naive)", v: 60.4, sd: 2.4, c: C.red },
  { name: "LLM as judge", v: 44.3, sd: 2.4, c: C.amber },
  { name: "Sentinel veto only", v: 29.7, sd: 1.6, c: C.blue },
  { name: "LLM × Sentinel loop", v: 18.8, sd: 1.6, c: C.green },
];

export const Bench: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const note = useEnter(sec(6));
  const limit = useEnter(sec(10));
  const maxW = 1050;
  return (
    <SceneFade>
      <div style={{ ...pad, gap: 40 }}>
        <div style={head}>
          <Kicker>Benchmark · all 128 scenarios</Kicker>
          <Title size={60}>Unsafe actions executed (lower is better)</Title>
          <div style={{ fontSize: 28, color: C.dim, marginTop: 8 }}>
            3 independent repeats · 10 hazard categories · half are safe controls · labels
            frozen before the first run
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {BARS.map((b, i) => {
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
                  <span style={{ fontSize: 24, color: C.dim, fontWeight: 400 }}> ± {b.sd}</span>
                </div>
              </div>
            );
          })}
        </div>
        <div style={{ ...note, fontSize: 32 }}>
          Same planner, same scenes: about <b style={{ color: C.green }}>70% fewer</b> unsafe
          executions, while safe tasks still succeed 82% of the time (naive 83%).
        </div>
        <div style={{ ...limit, fontSize: 28, color: C.dim }}>
          Not zero yet. Most misses are hazards no rule covers, which is what the rule learner is
          for.
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- learner
const GATE = ["schema", "replay", "ratchet", "preflight"];

export const Learner: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const inc = useEnter(sec(1));
  const prop = useEnter(sec(4));
  const v1 = useEnter(sec(8));
  const v2 = useEnter(sec(11));
  const res = useEnter(sec(13.5));
  return (
    <SceneFade>
      <div style={{ ...pad, gap: 40 }}>
        <div style={head}>
          <Kicker>Rule learner · Muse Wonder</Kicker>
          <Title size={58}>It learns new hazards, but a gate decides what it keeps</Title>
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
              <div style={{ fontFamily: MONO, color: C.amber, fontSize: 29, marginTop: 8 }}>
                release_near_edge(edge_cm) → ASK
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              {GATE.map((g, i) => {
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
                      fontSize: 27,
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
          <div style={{ fontSize: 26, color: C.dim, fontWeight: 400, marginTop: 6 }}>
            The subset of hazards the hand-written rules never covered (69 cells), not the
            whole benchmark.
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- ASK
export const Ask: React.FC = () => {
  const a = useEnter(0);
  const b = useEnter(20);
  return (
    <SceneFade>
      <AbsoluteFill style={{ justifyContent: "center", padding: "0 160px", gap: 40 }}>
        <div style={{ ...a, fontFamily: MONO, fontSize: 60 }}>"hand me the blue cup"</div>
        <div style={{ ...b, fontSize: 48 }}>
          <Badge color={C.amber}>ASK</Badge> "I can't see a blue cup. Did you mean the cup?"
        </div>
      </AbsoluteFill>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- Meta stack
const STACK = [
  ["SAM 3.1", "segments every object"],
  ["Muse Spark 1.3", "plans, replans, reads scene text in quarantine"],
  ["Muse Spark Open", "the same loop on open weights, on Baseten"],
  ["Muse Wonder", "proposes new rules from incidents"],
  ["Muse Code", "built the code with me, solo, in 9 days"],
];

export const Stack: React.FC = () => {
  const head = useEnter(0);
  const rows = [useEnter(10), useEnter(30), useEnter(50), useEnter(70), useEnter(90)];
  return (
    <SceneFade>
      <div style={{ ...pad, gap: 34 }}>
        <div style={head}>
          <Kicker>Built with Meta models</Kicker>
        </div>
        {STACK.map(([m, w], i) => (
          <div key={m} style={{ ...rows[i], display: "flex", gap: 30, alignItems: "baseline" }}>
            <div style={{ width: 520, fontSize: 46, fontWeight: 800 }}>{m}</div>
            <div style={{ fontSize: 33, color: C.dim }}>{w}</div>
          </div>
        ))}
      </div>
    </SceneFade>
  );
};

// ---------------------------------------------------------------- outro
export const Outro: React.FC = () => {
  const a = useEnter(0);
  const b = useEnter(20);
  const c = useEnter(35);
  return (
    <SceneFade>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 34 }}>
        <div style={{ ...a, fontSize: 64, fontWeight: 800, textAlign: "center" }}>
          The LLM decides how.
          <br />
          <span style={{ color: C.green }}>Sentinel decides whether.</span>
        </div>
        <div style={{ ...b, fontSize: 32, color: C.dim }}>Try it live</div>
        <div style={{ ...b, fontSize: 32, fontFamily: MONO }}>
          rushi-bhosale84--sentinel-web.us-east.modal.run
        </div>
        <div style={{ ...c, fontSize: 30, fontFamily: MONO, color: C.dim }}>
          github.com/rushibhosalepro/sentinel
        </div>
      </AbsoluteFill>
    </SceneFade>
  );
};
