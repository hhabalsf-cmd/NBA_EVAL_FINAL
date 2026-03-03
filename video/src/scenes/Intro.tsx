import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";
import { DATE_LABEL, PICKS } from "../data/picks";

const { fontFamily } = loadFont("normal", {
  weights: ["700", "900"],
  subsets: ["latin"],
});

const GOLD = "#C9A87C";
const BG = "#09090B";
const WHITE = "#EDEDEC";
const MUTED = "#8F8B87";

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // "TOP 5 PLAYS" slides up and fades in
  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 120 },
    durationInFrames: 30,
  });

  const titleY = interpolate(titleSpring, [0, 1], [60, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 1], [0, 1]);

  // Subtitle fades in after title
  const subtitleOpacity = interpolate(frame, [20, 40], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Gold divider scales in
  const dividerScale = spring({
    frame: frame - 10,
    fps,
    config: { damping: 200 },
    durationInFrames: 25,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 16,
      }}
    >
      {/* Basketball emoji */}
      <div
        style={{
          fontSize: 80,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          marginBottom: 8,
        }}
      >
        🏀
      </div>

      {/* Curiosity-gap hook */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 76,
          color: WHITE,
          letterSpacing: -2,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
          lineHeight: 1.05,
          padding: "0 40px",
        }}
      >
        ARE THESE{"\n"}HITTING?
      </div>

      {/* Gold divider */}
      <div
        style={{
          width: interpolate(dividerScale, [0, 1], [0, 280]),
          height: 3,
          backgroundColor: GOLD,
          borderRadius: 2,
          margin: "8px 0",
        }}
      />

      {/* TOP PREDICTIONS subtitle */}
      <div
        style={{
          fontFamily,
          fontWeight: 700,
          fontSize: 32,
          color: GOLD,
          letterSpacing: 8,
          opacity: subtitleOpacity,
        }}
      >
        TOP PREDICTIONS
      </div>

      {/* Pick count · Date */}
      <div
        style={{
          fontFamily,
          fontWeight: 400,
          fontSize: 24,
          color: MUTED,
          letterSpacing: 3,
          opacity: subtitleOpacity,
        }}
      >
        {PICKS.length} PICKS · {DATE_LABEL}
      </div>
    </AbsoluteFill>
  );
};
