import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const FPS = 30;
export const sec = (s: number) => Math.round(s * FPS);

export const C = {
  bg: "#0b0f14",
  panel: "#151b23",
  line: "#263040",
  text: "#e8edf3",
  dim: "#93a1b3",
  green: "#22c55e",
  red: "#ef4444",
  amber: "#f59e0b",
  purple: "#a855f7",
  blue: "#3b82f6",
};

export const FONT = "'Segoe UI', 'Inter', system-ui, sans-serif";
export const MONO = "'Cascadia Code', 'Consolas', monospace";

/** Gentle fade + rise in over ~0.8 s, starting at `delay` frames. */
export const useEnter = (delay = 0) => {
  const frame = useCurrentFrame();
  const s = interpolate(frame - delay, [0, 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  return { opacity: s, transform: `translateY(${(1 - s) * 30}px)` };
};

/** Fade the whole scene out over its last 10 frames. */
export const SceneFade: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = interpolate(
    frame,
    [0, 14, durationInFrames - 14, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return (
    <AbsoluteFill
      style={{ backgroundColor: C.bg, fontFamily: FONT, color: C.text, opacity }}
    >
      {children}
    </AbsoluteFill>
  );
};

export const Kicker: React.FC<{ children: React.ReactNode; color?: string }> = ({
  children,
  color = C.green,
}) => (
  <div
    style={{
      fontSize: 30,
      letterSpacing: 4,
      textTransform: "uppercase",
      color,
      fontWeight: 700,
    }}
  >
    {children}
  </div>
);

export const Title: React.FC<{ children: React.ReactNode; size?: number }> = ({
  children,
  size = 72,
}) => (
  <div style={{ fontSize: size, fontWeight: 800, lineHeight: 1.15 }}>
    {children}
  </div>
);

export const Badge: React.FC<{ color: string; children: React.ReactNode }> = ({
  color,
  children,
}) => (
  <span
    style={{
      background: color,
      color: "#fff",
      fontWeight: 800,
      fontSize: 24,
      padding: "6px 14px",
      borderRadius: 8,
      letterSpacing: 1,
    }}
  >
    {children}
  </span>
);

/** A clip that plays once, then holds its last frame. */
export const Clip: React.FC<{
  name: string;
  frames: number;
  width: number;
  delay?: number;
}> = ({ name, frames, width, delay = 0 }) => {
  const frame = useCurrentFrame();
  const h = (width * 3) / 4;
  const box: React.CSSProperties = {
    width,
    height: h,
    borderRadius: 14,
    overflow: "hidden",
    border: `2px solid ${C.line}`,
    position: "relative",
    background: "#000",
  };
  return (
    <div style={box}>
      <Sequence from={delay} durationInFrames={frames} layout="none">
        <OffthreadVideo
          src={staticFile(`${name}.mp4`)}
          style={{ width, height: h, position: "absolute", top: 0, left: 0 }}
          muted
        />
      </Sequence>
      {frame >= delay + frames ? (
        <Img
          src={staticFile(`${name}_last.png`)}
          style={{ width, height: h, position: "absolute", top: 0, left: 0 }}
        />
      ) : null}
    </div>
  );
};

// ------------------------------------------------------------------ Shot
// A sim clip (640x480 source) with edits keyed to SOURCE frames: zoom in
// on a region, freeze on a moment, circle a point, stamp a verdict.
const SRC_W = 640;
const SRC_H = 480;

export type Mark = {
  at: number; // source frame it appears
  until?: number;
  x: number; // source px
  y: number;
  r: number;
  color: string;
  path?: [number, number, number][]; // [frame, x, y] to follow a moving target
};

export type Stamp = { at: number; until?: number; text: string; color: string };

export const Shot: React.FC<{
  name: string;
  frames: number; // clip length in source frames
  width: number;
  startFrom?: number; // first source frame shown
  delay?: number; // composition frames to hold startFrom before playing
  zoom?: { from: number; to: number; cx: number; cy: number; scale: number };
  freezeAt?: number; // source frame; needs public/<name>_f<n>.png
  holdImg?: string; // still shown during `delay`
  marks?: Mark[];
  stamps?: Stamp[];
  holdStamps?: Stamp[]; // keyed to composition frames, shown during delay
  flash?: { at: number; len: number };
  dimHold?: boolean;
}> = ({
  name,
  frames,
  width,
  startFrom = 0,
  delay = 0,
  zoom,
  freezeAt,
  holdImg,
  marks = [],
  stamps = [],
  holdStamps = [],
  flash,
  dimHold = false,
}) => {
  const frame = useCurrentFrame();
  const h = (width * SRC_H) / SRC_W;
  const playing = frame >= delay;
  let src = startFrom + Math.max(0, frame - delay);
  const frozen = freezeAt !== undefined && src >= freezeAt;
  if (frozen) src = freezeAt!;
  const ended = !frozen && src >= frames - 1;
  if (ended) src = frames - 1;

  const scale = zoom
    ? interpolate(src, [zoom.from, zoom.to], [1, zoom.scale], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.inOut(Easing.cubic),
      })
    : 1;
  const origin = zoom
    ? `${(zoom.cx / SRC_W) * 100}% ${(zoom.cy / SRC_H) * 100}%`
    : "50% 50%";
  const fill: React.CSSProperties = {
    position: "absolute",
    top: 0,
    left: 0,
    width,
    height: h,
  };

  let image: React.ReactNode;
  if (!playing) {
    image = (
      <Img
        src={staticFile(holdImg ?? `${name}_f${startFrom}.png`)}
        style={{ ...fill, opacity: dimHold ? 0.45 : 1 }}
      />
    );
  } else if (frozen) {
    image = <Img src={staticFile(`${name}_f${freezeAt}.png`)} style={fill} />;
  } else if (ended) {
    image = <Img src={staticFile(`${name}_last.png`)} style={fill} />;
  } else {
    image = (
      <Sequence from={delay} layout="none">
        <OffthreadVideo
          src={staticFile(`${name}.mp4`)}
          startFrom={startFrom}
          style={fill}
          muted
        />
      </Sequence>
    );
  }

  const visible = (at: number, until?: number) =>
    playing && src >= at && (until === undefined || src < until);

  const flashOpacity =
    flash && playing
      ? interpolate(src, [flash.at, flash.at + 2, flash.at + flash.len], [0, 0.45, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 0;

  return (
    <div
      style={{
        width,
        height: h,
        borderRadius: 14,
        overflow: "hidden",
        border: `2px solid ${C.line}`,
        position: "relative",
        background: "#000",
      }}
    >
      <div
        style={{ ...fill, transform: `scale(${scale})`, transformOrigin: origin }}
      >
        {image}
        {marks.map((m, i) => {
          if (!visible(m.at, m.until)) return null;
          let { x, y } = m;
          if (m.path) {
            const fs = m.path.map((p) => p[0]);
            x = interpolate(src, fs, m.path.map((p) => p[1]), {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            y = interpolate(src, fs, m.path.map((p) => p[2]), {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
          }
          const pulse = 1 + 0.08 * Math.sin(frame / 4);
          const sx = width / SRC_W;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: (x - m.r * pulse) * sx,
                top: (y - m.r * pulse) * sx,
                width: 2 * m.r * pulse * sx,
                height: 2 * m.r * pulse * sx,
                borderRadius: "50%",
                border: `${Math.max(2, 5 / scale)}px solid ${m.color}`,
                boxShadow: `0 0 ${18 / scale}px ${m.color}`,
              }}
            />
          );
        })}
      </div>
      <div style={{ ...fill, background: "#ef4444", opacity: flashOpacity }} />
      <div
        style={{
          position: "absolute",
          left: 18,
          bottom: 18,
          right: 18,
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          gap: 10,
        }}
      >
        {(playing ? [] : holdStamps.filter((s) => frame >= s.at && (s.until === undefined || frame < s.until)))
          .concat(stamps.filter((s) => visible(s.at, s.until)))
          .map((s, i) => (
            <span
              key={i}
              style={{
                background: "rgba(8,10,14,0.82)",
                border: `3px solid ${s.color}`,
                color: "#fff",
                fontSize: Math.round(width / 30),
                fontWeight: 800,
                padding: "8px 16px",
                borderRadius: 10,
              }}
            >
              {s.text}
            </span>
          ))}
      </div>
    </div>
  );
};

export const Lane: React.FC<{
  label: string;
  color: string;
  sub: string;
  children: React.ReactNode;
  footer: React.ReactNode;
  footerDelay: number;
}> = ({ label, color, sub, children, footer, footerDelay }) => {
  const enter = useEnter(footerDelay);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <Badge color={color}>{label}</Badge>
        <span style={{ fontSize: 24, color: C.dim }}>{sub}</span>
      </div>
      {children}
      <div
        style={{
          ...enter,
          fontSize: 30,
          fontWeight: 700,
          color,
          minHeight: 84,
          lineHeight: 1.3,
        }}
      >
        {footer}
      </div>
    </div>
  );
};
