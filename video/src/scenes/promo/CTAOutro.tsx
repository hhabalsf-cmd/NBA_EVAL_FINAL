import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  BG, GOLD, WHITE, MUTED,
  fontFamily, SPRING_BOUNCY, SPRING_SNAPPY,
} from "../../theme";

export const CTAOutro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // "Find Your Edge" title springs in
  const titleSpring = spring({
    frame,
    fps,
    config: SPRING_BOUNCY,
    durationInFrames: 25,
  });
  const titleScale = interpolate(titleSpring, [0, 1], [0.7, 1]);
  const titleOpacity = interpolate(titleSpring, [0, 1], [0, 1]);

  // URL fades in
  const urlOpacity = interpolate(frame, [20, 40], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const urlY = interpolate(frame, [20, 40], [15, 0], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // CTA text pulses
  const ctaOpacity = interpolate(frame, [40, 55], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const ctaPulse = interpolate(
    frame % 30,
    [0, 15, 30],
    [1, 1.03, 1],
  );

  // Logo fades in
  const logoOpacity = interpolate(frame, [50, 70], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const logoScale = spring({
    frame: frame - 50,
    fps,
    config: { damping: 200 },
    durationInFrames: 20,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 24,
      }}
    >
      {/* Background glow */}
      <div
        style={{
          position: "absolute",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${GOLD}15 0%, transparent 70%)`,
          filter: "blur(80px)",
        }}
      />

      {/* Main title */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 76,
          color: WHITE,
          letterSpacing: -3,
          textAlign: "center",
          lineHeight: 1.05,
          opacity: titleOpacity,
          transform: `scale(${titleScale})`,
        }}
      >
        Find Your{"\n"}Edge
      </div>

      {/* URL */}
      <div
        style={{
          fontFamily,
          fontWeight: 700,
          fontSize: 28,
          color: GOLD,
          letterSpacing: 1,
          opacity: urlOpacity,
          transform: `translateY(${urlY}px)`,
          marginTop: 8,
        }}
      >
        nba-eval-final.vercel.app
      </div>

      {/* CTA */}
      <div
        style={{
          marginTop: 16,
          backgroundColor: `${GOLD}20`,
          border: `1px solid ${GOLD}50`,
          borderRadius: 12,
          padding: "14px 36px",
          opacity: ctaOpacity,
          transform: `scale(${ctaPulse})`,
        }}
      >
        <span
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 26,
            color: GOLD,
            letterSpacing: 3,
          }}
        >
          START ANALYZING TODAY
        </span>
      </div>

      {/* Logo */}
      <div
        style={{
          marginTop: 32,
          opacity: logoOpacity,
          transform: `scale(${interpolate(logoScale, [0, 1], [0.8, 1])})`,
        }}
      >
        <Img
          src={staticFile("justlogo2.png")}
          style={{
            width: 120,
            objectFit: "contain",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
