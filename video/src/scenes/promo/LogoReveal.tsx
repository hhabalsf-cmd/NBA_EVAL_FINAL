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
import { BG, GOLD, MUTED, WHITE, fontFamily, SPRING_BOUNCY } from "../../theme";

export const LogoReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Basketball emoji bounces in
  const emojiSpring = spring({
    frame,
    fps,
    config: SPRING_BOUNCY,
    durationInFrames: 25,
  });
  const emojiScale = interpolate(emojiSpring, [0, 1], [0.3, 1]);
  const emojiOpacity = interpolate(emojiSpring, [0, 1], [0, 1]);

  // Brand name types in letter-by-letter
  const brandText = "BETTIN' JRYS";
  const charsVisible = Math.min(
    brandText.length,
    Math.max(0, Math.floor(interpolate(frame, [15, 50], [0, brandText.length], {
      extrapolateRight: "clamp",
      extrapolateLeft: "clamp",
    })))
  );
  const displayedBrand = brandText.substring(0, charsVisible);

  // Gold divider scales from center
  const dividerProgress = spring({
    frame: frame - 35,
    fps,
    config: { damping: 200 },
    durationInFrames: 20,
  });

  // Subtitle fades in
  const subtitleOpacity = interpolate(frame, [50, 70], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const subtitleY = interpolate(frame, [50, 70], [15, 0], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Dot-grid background
  const dotSize = 2;
  const dotSpacing = 40;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 20,
      }}
    >
      {/* Dot grid background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `radial-gradient(circle, ${MUTED}30 ${dotSize}px, transparent ${dotSize}px)`,
          backgroundSize: `${dotSpacing}px ${dotSpacing}px`,
          opacity: 0.4,
        }}
      />

      {/* Glow behind logo */}
      <div
        style={{
          position: "absolute",
          width: 400,
          height: 400,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${GOLD}20 0%, transparent 70%)`,
          filter: "blur(60px)",
          opacity: interpolate(frame, [0, 30], [0, 0.6], {
            extrapolateRight: "clamp",
          }),
        }}
      />

      {/* Logo */}
      <div
        style={{
          transform: `scale(${emojiScale})`,
          opacity: emojiOpacity,
          marginBottom: 12,
        }}
      >
        <Img
          src={staticFile("justlogo2.png")}
          style={{ width: 400, objectFit: "contain" }}
        />
      </div>

      {/* Brand name — typewriter */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 80,
          color: WHITE,
          letterSpacing: -2,
          textAlign: "center",
          lineHeight: 1.05,
          minHeight: 90,
        }}
      >
        {displayedBrand}
        {charsVisible < brandText.length && (
          <span
            style={{
              color: GOLD,
              opacity: frame % 10 < 5 ? 1 : 0.3,
            }}
          >
            |
          </span>
        )}
      </div>

      {/* Gold divider */}
      <div
        style={{
          width: interpolate(dividerProgress, [0, 1], [0, 320]),
          height: 3,
          backgroundColor: GOLD,
          borderRadius: 2,
          margin: "4px 0",
        }}
      />

      {/* Subtitle */}
      <div
        style={{
          fontFamily,
          fontWeight: 700,
          fontSize: 28,
          color: GOLD,
          letterSpacing: 6,
          opacity: subtitleOpacity,
          transform: `translateY(${subtitleY}px)`,
        }}
      >
        ML-POWERED NBA ANALYTICS
      </div>
    </AbsoluteFill>
  );
};
