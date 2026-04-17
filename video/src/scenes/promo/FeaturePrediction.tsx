import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  BG, CARD_BG, BORDER, WHITE, MUTED, GOLD, GREEN,
  fontFamily, SPRING_SNAPPY,
} from "../../theme";

export const FeaturePrediction: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Card slides up from bottom
  const cardSpring = spring({
    frame,
    fps,
    config: SPRING_SNAPPY,
    durationInFrames: 35,
  });
  const cardY = interpolate(cardSpring, [0, 1], [120, 0]);
  const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

  // Confidence bar fills
  const barProgress = interpolate(frame, [30, 70], [0, 0.82], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Range fades in
  const rangeOpacity = interpolate(frame, [40, 55], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Suspense reveal: OVER pill + line
  const revealOpacity = interpolate(frame, [50, 70], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const revealBlur = interpolate(frame, [50, 70], [8, 0], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Edge counter appears
  const edgeOpacity = interpolate(frame, [60, 80], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });
  const edgeScale = spring({
    frame: frame - 60,
    fps,
    config: { damping: 12, stiffness: 200 },
    durationInFrames: 20,
  });

  // Caption at bottom
  const captionOpacity = interpolate(frame, [70, 90], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const CARD_WIDTH = 860;
  const BAR_MAX = CARD_WIDTH - 80;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 32,
      }}
    >
      {/* Main prediction card */}
      <div
        style={{
          width: CARD_WIDTH,
          backgroundColor: CARD_BG,
          borderRadius: 24,
          border: `1px solid ${BORDER}`,
          padding: "48px 40px",
          transform: `translateY(${cardY}px)`,
          opacity: cardOpacity,
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        {/* Stat badge */}
        <div
          style={{
            display: "inline-flex",
            alignSelf: "flex-start",
            backgroundColor: `${GOLD}20`,
            border: `1px solid ${GOLD}40`,
            borderRadius: 8,
            padding: "6px 16px",
          }}
        >
          <span
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: 18,
              color: GOLD,
              letterSpacing: 3,
            }}
          >
            POINTS
          </span>
        </div>

        {/* Player name */}
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 64,
            color: WHITE,
            letterSpacing: -2,
            lineHeight: 1.05,
          }}
        >
          LeBron James
        </div>

        {/* Team */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: 28,
              color: GOLD,
              letterSpacing: 1,
            }}
          >
            LAL
          </span>
          <span style={{ color: MUTED, fontSize: 24 }}>·</span>
          <span
            style={{
              fontFamily,
              fontWeight: 400,
              fontSize: 22,
              color: MUTED,
            }}
          >
            vs. BOS · Strong Defense (#3)
          </span>
        </div>

        {/* Predicted value — large */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 8 }}>
          <span
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: 88,
              color: WHITE,
              letterSpacing: -3,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            27.5
          </span>
          <span
            style={{
              fontFamily,
              fontWeight: 400,
              fontSize: 24,
              color: MUTED,
            }}
          >
            predicted
          </span>
        </div>

        {/* Range */}
        <div
          style={{
            fontFamily,
            fontWeight: 400,
            fontSize: 22,
            color: MUTED,
            opacity: rangeOpacity,
          }}
        >
          Range: 24.1 — 31.2
        </div>

        {/* OVER pill + line — suspense reveal */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            opacity: revealOpacity,
            filter: `blur(${revealBlur}px)`,
            marginTop: 4,
          }}
        >
          <div
            style={{
              backgroundColor: GREEN,
              borderRadius: 8,
              padding: "8px 24px",
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: 26,
                color: BG,
                letterSpacing: 2,
              }}
            >
              OVER
            </span>
          </div>
          <span
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: 48,
              color: WHITE,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            26.5
          </span>
        </div>

        {/* Confidence bar */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ fontFamily, fontSize: 20, color: MUTED, fontWeight: 400 }}>
              Confidence
            </span>
            <span
              style={{
                fontFamily,
                fontWeight: 700,
                fontSize: 24,
                color: GREEN,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {Math.round(barProgress * 100)}%
            </span>
          </div>
          <div
            style={{
              width: BAR_MAX,
              height: 12,
              backgroundColor: BORDER,
              borderRadius: 6,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: BAR_MAX * barProgress,
                height: "100%",
                backgroundColor: GREEN,
                borderRadius: 6,
              }}
            />
          </div>
        </div>

        {/* Edge indicator */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            opacity: edgeOpacity,
            transform: `scale(${interpolate(edgeScale, [0, 1], [0.8, 1])})`,
            marginTop: 4,
          }}
        >
          <span style={{ fontFamily, fontSize: 20, color: MUTED, fontWeight: 400 }}>
            Edge
          </span>
          <span
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: 32,
              color: GREEN,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            +3.8%
          </span>
        </div>
      </div>

      {/* Caption */}
      <div
        style={{
          fontFamily,
          fontWeight: 700,
          fontSize: 26,
          color: GOLD,
          letterSpacing: 4,
          opacity: captionOpacity,
        }}
      >
        AI-POWERED PREDICTIONS
      </div>
    </AbsoluteFill>
  );
};
