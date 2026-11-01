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
  sec,
  useEnter,
} from "./ui";

// V15: LiveV5 with a smaller frame (1240 wide) to make room for a TRY IT
// LIVE link bar under the caption. Segments, cameras and stamps are
// unchanged.
type Cam15 = { s: number; x: number; y: number };

const REC15 = [
  { from: 5, to: 17.5, rate: 5, stamp: "Typed live, not a preset", color: C.amber,
    cam: { s: 1, x: 50, y: 50 } },
  { from: 17.5, to: 62, rate: 30, stamp: "Same Muse Spark plans both lanes", color: C.dim,
    cam: { s: 1.42, x: 50, y: 50 } },
  { from: 62, to: 108, rate: 6, stamp: "A hands it blade-first · B slows and turns the handle", color: C.green,
    cam: { s: 1.75, x: 49.5, y: 41 } },
];
const HOLD_CAM15: Cam15 = { s: 1.3, x: 50, y: 60 };
const HOLD_STAMP15 = "A: \"offered blade-first\" · B: ALLOW, handle first";

const camTransform15 = ({ s, x, y }: Cam15) => {
  const clamp = (v: number) => Math.min(0, Math.max(100 - 100 * s, v));
  return `translate(${clamp(50 - s * x)}%, ${clamp(50 - s * y)}%) scale(${s})`;
};

// Voice is 11.54 s starting 0.4 s in; "The link is on screen" lands in
// its last ~2.5 s, so the bar fades in at 9.4 s and stays to the end.
const LINK_AT = 9.4;

const padV15: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
};

export const LiveV15: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const link = useEnter(sec(LINK_AT));
  let t = 0;
  let idx = REC15.length;
  const starts: number[] = [];
  const parts = REC15.map((s, i) => {
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
  if (frame < 0 || (!ended && idx === REC15.length)) idx = 0;
  const camOf = (i: number): Cam15 => (i >= REC15.length ? HOLD_CAM15 : REC15[i].cam);
  const segStart = ended ? t : starts[idx];
  const k = interpolate(frame, [segStart, segStart + 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const a = camOf(Math.max(0, idx - 1));
  const b = camOf(idx);
  const cam = { s: a.s + (b.s - a.s) * k, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
  const part = idx < REC15.length ? REC15[idx] : null;
  const W = 1180;
  const H = (W * 1080) / 1920;
  return (
    <SceneFade>
      <div style={{ ...padV15, alignItems: "center", gap: 26 }}>
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
              transform: camTransform15(cam),
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
          {part ? part.stamp : HOLD_STAMP15}
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
