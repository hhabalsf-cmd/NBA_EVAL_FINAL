import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { BG, CYAN, MUTED, WHITE, fontFamily, SPRING_SNAPPY } from "../../theme";

export const HookStatement: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // "Stop guessing." slides up
  const line1Spring = spring({
    frame,
    fps,
    config: SPRING_SNAPPY,
    durationInFrames: 30,
  });
  const line1Y = interpolate(line1Spring, [0, 1], [60, 0]);
  const line1Opacity = interpolate(line1Spring, [0, 1], [0, 1]);

  // "Start evaluating." slides up — staggered
  const line2Spring = spring({
    frame: frame - 15,
    fps,
    config: SPRING_SNAPPY,
    durationInFrames: 30,
  });
  const line2Y = interpolate(line2Spring, [0, 1], [60, 0]);
  const line2Opacity = interpolate(line2Spring, [0, 1], [0, 1]);

  // Tagline fades in
  const taglineOpacity = interpolate(frame, [40, 60], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const taglineY = interpolate(frame, [40, 60], [10, 0], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 8,
        padding: "0 60px",
      }}
    >
      {/* Line 1 */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 72,
          color: WHITE,
          letterSpacing: -2,
          textAlign: "center",
          lineHeight: 1.1,
          opacity: line1Opacity,
          transform: `translateY(${line1Y}px)`,
        }}
      >
        Stop guessing.
      </div>

      {/* Line 2 — accent color */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 72,
          color: CYAN,
          letterSpacing: -2,
          textAlign: "center",
          lineHeight: 1.1,
          opacity: line2Opacity,
          transform: `translateY(${line2Y}px)`,
        }}
      >
        Start evaluating.
      </div>

      {/* Tagline */}
      <div
        style={{
          fontFamily,
          fontWeight: 400,
          fontSize: 24,
          color: MUTED,
          letterSpacing: 2,
          textAlign: "center",
          marginTop: 24,
          opacity: taglineOpacity,
          transform: `translateY(${taglineY}px)`,
        }}
      >
        100 ML features · 4 stat models · Real edge
      </div>
    </AbsoluteFill>
  );
};
