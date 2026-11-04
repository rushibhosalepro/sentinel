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

// V30 live scene: LiveV29 with the loading dead air cut (12 -> 27 skipped,
// stamped honestly) and 2 s deeper into the robot action, funded by the
// outro's dropped last line. Segments: 7 -> 12 @1x, 27 -> 43 @2x,
// 43 -> 58 @2x; the hold still is the same run's outcome.
type Cam30 = { s: number; x: number; y: number };

const REC30 = [
  { from: 7, to: 12, rate: 1, stamp: "Typed live — then Run both", color: C.amber,
    cam: { s: 1, x: 50, y: 50 } },
  { from: 27, to: 43, rate: 2, stamp: "Loading skipped — both arms move", color: C.dim,
    cam: { s: 1.15, x: 50, y: 55 } },
  { from: 43, to: 58, rate: 2, stamp: "A rushes blade-first · B slows, handle-first", color: C.green,
    cam: { s: 1.35, x: 50, y: 58 } },
];
const HOLD_CAM30: Cam30 = { s: 1.3, x: 50, y: 60 };
const HOLD_STAMP30 = "A: \"offered blade-first\" · B: ALLOW, handle first";

const camTransform30 = ({ s, x, y }: Cam30) => {
  const clamp = (v: number) => Math.min(0, Math.max(100 - 100 * s, v));
  return `translate(${clamp(50 - s * x)}%, ${clamp(50 - s * y)}%) scale(${s})`;
};

const padLive30: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  padding: "60px 100px",
  display: "flex",
  flexDirection: "column",
};

// "visit the link in the description" lands ~2.6 s in (voice starts 0.4 s
// in), so the TRY IT LIVE bar fades in with it and stays to the end.
const LINK_AT30 = 2.6;

export const LiveV30: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useEnter(0);
  const link = useEnter(sec(LINK_AT30));
  let t = 0;
  let idx = REC30.length;
  const starts: number[] = [];
  const parts = REC30.map((s, i) => {
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
  if (frame < 0 || (!ended && idx === REC30.length)) idx = 0;
  const camOf = (i: number): Cam30 => (i >= REC30.length ? HOLD_CAM30 : REC30[i].cam);
  const segStart = ended ? t : starts[idx];
  const k = interpolate(frame, [segStart, segStart + 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const a = camOf(Math.max(0, idx - 1));
  const b = camOf(idx);
  const cam = { s: a.s + (b.s - a.s) * k, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
  const part = idx < REC30.length ? REC30[idx] : null;
  const W = 1180;
  const H = (W * 1080) / 1920;
  return (
    <SceneFade>
      <div style={{ ...padLive30, alignItems: "center", gap: 26 }}>
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
              transform: camTransform30(cam),
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
          {part ? part.stamp : HOLD_STAMP30}
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
