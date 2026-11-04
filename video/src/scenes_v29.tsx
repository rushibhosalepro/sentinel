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
  MONO,
  SceneFade,
  Title,
  sec,
  useEnter,
} from "./ui";

// V29: HowV27 with beats shifted earlier to match the pause-shaved voice
// (8.68 s -> 7.34 s). Badge -0.5 s, masks/caption -0.85 s, tags -1.2 s.
const TAGS29 = [
  { x: 370, y: 300, t: "knife · SHARP", c: C.red, at: 5.9 },
  { x: 107, y: 60, t: "jug · LIQUID", c: C.blue, at: 6.2 },
  { x: 490, y: 75, t: "laptop · ELECTRONIC", c: C.amber, at: 6.5 },
  { x: 355, y: 205, t: "cup", c: C.dim, at: 6.2 },
];

export const HowV29: React.FC = () => {
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
              style={{ position: "absolute", width: IW, height: IH, opacity: at(4.35, 20) }}
            />
            <span style={{ position: "absolute", left: 12, bottom: 12, opacity: at(2.9, 10) }}>
              <Badge color={C.blue}>MuJoCo kitchen simulation</Badge>
            </span>
            {TAGS29.map((g) => (
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
          <div style={{ opacity: at(4.35), fontSize: 22, color: C.dim }}>
            SAM 3.1 + Muse Spark tag the scene: what's sharp, liquid, electronic
          </div>
        </div>
      </div>
    </SceneFade>
  );
};

// V29: BridgeV28 without the "those happen most of the time" beat (cut from
// the voice too). b2 moves to 0, SENTINEL title to 1.8.
export const BridgeV29: React.FC = () => {
  const b2 = useEnter(0);
  const b3 = useEnter(sec(1.8));
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

const padV29: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};

// V29: BenchV28 with tighter beats and the 3rd bottom line cut (it restated
// the memory scene). The voice lost the "scenarios:" opener and the
// "forty-four" line; the 44.3 bar keeps its on-screen label.
const BARS29 = [
  { name: "LLM alone (naive)", v: 60.4, sd: 2.4, c: C.red },
  { name: "LLM checks its own plan", v: 44.3, sd: 2.4, c: C.amber },
  { name: "Sentinel, block only", v: 29.7, sd: 1.6, c: C.blue },
  { name: "LLM × Sentinel loop", v: 18.8, sd: 1.6, c: C.green },
];

export const BenchV29: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const note = useEnter(sec(3.0));
  const limit = useEnter(sec(6.0));
  const maxW = 980;
  return (
    <SceneFade>
      <div style={{ ...padV29, gap: 40 }}>
        <div style={head}>
          <Kicker>Benchmark · all 128 scenarios</Kicker>
          <Title size={54}>Unsafe actions executed (lower is better)</Title>
          <div style={{ fontSize: 30, color: C.dim, marginTop: 8 }}>
            3 independent repeats · 10 hazard categories · half are safe controls · labels
            frozen before the first run
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {BARS29.map((b, i) => {
            const grow = interpolate(frame, [sec(0.5) + i * 20, sec(0.5) + 35 + i * 20], [0, 1], {
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
          Not zero yet. Most misses are hazards no rule covers, which is what the rule learner is for.
        </div>
      </div>
    </SceneFade>
  );
};

// V29 live scene: one continuous run from the new recording ("hand me the
// knife, quickly"), played at 1x-2x with honest speed badges — no jump cuts,
// no 6x. Segments are contiguous (7 -> 13 -> 27 -> 39); the hold still is the
// same run's outcome (lane A done blade-first, lane B mid-handover).
type Cam29 = { s: number; x: number; y: number };

const REC29 = [
  { from: 7, to: 13, rate: 1, stamp: "Typed live — then Run both", color: C.amber,
    cam: { s: 1, x: 50, y: 50 } },
  { from: 13, to: 27, rate: 2, stamp: "Both lanes plan — Sentinel checks every step", color: C.dim,
    cam: { s: 1.15, x: 50, y: 55 } },
  { from: 27, to: 39, rate: 2, stamp: "A rushes blade-first · B slows, handle-first", color: C.green,
    cam: { s: 1.35, x: 50, y: 58 } },
];
const HOLD_CAM29: Cam29 = { s: 1.3, x: 50, y: 60 };
const HOLD_STAMP29 = "A: \"offered blade-first\" · B: ALLOW, handle first";

const camTransform29 = ({ s, x, y }: Cam29) => {
  const clamp = (v: number) => Math.min(0, Math.max(100 - 100 * s, v));
  return `translate(${clamp(50 - s * x)}%, ${clamp(50 - s * y)}%) scale(${s})`;
};

const padLive29: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
};

// "visit the link in the description" lands ~2.6 s in (voice starts 0.4 s
// in), so the TRY IT LIVE bar fades in with it and stays to the end.
const LINK_AT29 = 2.6;

export const LiveV29: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const link = useEnter(sec(LINK_AT29));
  let t = 0;
  let idx = REC29.length;
  const starts: number[] = [];
  const parts = REC29.map((s, i) => {
    const len = Math.round(((s.to - s.from) * 30) / s.rate);
    const at = t;
    starts.push(at);
    t += len;
    if (frame >= at && frame < at + len) idx = i;
    return (
      <Sequence key={i} from={at} durationInFrames={len} layout="none">
        <OffthreadVideo
          src={staticFile("live_new.mp4")}
          startFrom={Math.round(s.from * 30)}
          playbackRate={s.rate}
          muted
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        />
      </Sequence>
    );
  });
  const ended = frame >= t;
  if (frame < 0 || (!ended && idx === REC29.length)) idx = 0;
  const camOf = (i: number): Cam29 => (i >= REC29.length ? HOLD_CAM29 : REC29[i].cam);
  const segStart = ended ? t : starts[idx];
  const k = interpolate(frame, [segStart, segStart + 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const a = camOf(Math.max(0, idx - 1));
  const b = camOf(idx);
  const cam = { s: a.s + (b.s - a.s) * k, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
  const part = idx < REC29.length ? REC29[idx] : null;
  const W = 1180;
  const H = (W * 1080) / 1920;
  return (
    <SceneFade>
      <div style={{ ...padLive29, alignItems: "center", gap: 26 }}>
        <div style={{ ...head, alignSelf: "stretch", paddingLeft: 160 }}>
          <Kicker>Live app</Kicker>
          <span style={{ fontSize: 34, color: C.dim }}>
            the live demo — try it yourself
          </span>
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
              transform: camTransform29(cam),
              transformOrigin: "0 0",
            }}
          >
            {parts}
            {ended ? (
              <Img
                src={staticFile("live_new_last.png")}
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
          {part ? part.stamp : HOLD_STAMP29}
        </div>
        <div
          style={{
            ...link,
            alignSelf: "flex-start",
            marginLeft: (1920 - 200 - W) / 2,
            display: "flex",
            alignItems: "center",
            gap: 16,
            background: C.panel,
            border: `2px solid ${C.green}`,
            borderRadius: 10,
            padding: "10px 18px",
          }}
        >
          <Badge color={C.green}>TRY IT LIVE</Badge>
          <span style={{ fontFamily: MONO, fontSize: 40, color: "#fff" }}>
            rushi-bhosale84--sentinel-web.us-east.modal.run
          </span>
        </div>
      </div>
    </SceneFade>
  );
};
