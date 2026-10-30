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
      fontSize: 26,
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
  size = 64,
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
