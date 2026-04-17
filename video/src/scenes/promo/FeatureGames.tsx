import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  BG, CARD_BG, BORDER, WHITE, MUTED, GOLD, CYAN, GREEN,
  fontFamily, SPRING_SNAPPY, SPRING_BOUNCY,
} from "../../theme";

export const FeatureGames: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title slides in
  const titleSpring = spring({
    frame,
    fps,
    config: SPRING_SNAPPY,
    durationInFrames: 25,
  });
  const titleY = interpolate(titleSpring, [0, 1], [40, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 1], [0, 1]);

  // Game card slides up
  const cardSpring = spring({
    frame: frame - 10,
    fps,
    config: SPRING_SNAPPY,
    durationInFrames: 30,
  });
  const cardY = interpolate(cardSpring, [0, 1], [100, 0]);
  const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

  // Win probability bars fill
  const homeProb = 0.33;
  const awayProb = 0.67;
  const barFill = interpolate(frame, [30, 60], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Winner indicator pops in
  const winnerSpring = spring({
    frame: frame - 55,
    fps,
    config: SPRING_BOUNCY,
    durationInFrames: 20,
  });
  const winnerScale = interpolate(winnerSpring, [0, 1], [0.5, 1]);
  const winnerOpacity = interpolate(winnerSpring, [0, 1], [0, 1]);

  // Key factors fade in
  const factorsOpacity = interpolate(frame, [50, 70], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const BAR_WIDTH = 700;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 40,
      }}
    >
      {/* Title */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
        }}
      >
        <span style={{ fontSize: 48 }}>🏟️</span>
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 56,
            color: WHITE,
            letterSpacing: -2,
          }}
        >
          Game Predictions
        </div>
      </div>

      {/* Game matchup card */}
      <div
        style={{
          width: 860,
          backgroundColor: CARD_BG,
          borderRadius: 24,
          border: `1px solid ${BORDER}`,
          padding: "48px 40px",
          opacity: cardOpacity,
          transform: `translateY(${cardY}px)`,
          display: "flex",
          flexDirection: "column",
          gap: 32,
        }}
      >
        {/* Teams row */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          {/* Home team */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <div
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: 52,
                color: WHITE,
                letterSpacing: -1,
              }}
            >
              LAL
            </div>
            <div style={{ fontFamily, fontSize: 18, color: MUTED, fontWeight: 400 }}>
              Home
            </div>
          </div>

          {/* VS divider */}
          <div
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: 32,
              color: MUTED,
              letterSpacing: 4,
            }}
          >
            VS
          </div>

          {/* Away team */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <div
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: 52,
                color: WHITE,
                letterSpacing: -1,
              }}
            >
              BOS
            </div>
            <div style={{ fontFamily, fontSize: 18, color: MUTED, fontWeight: 400 }}>
              Away
            </div>
          </div>
        </div>

        {/* Win probability bar — two-sided */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ fontFamily, fontWeight: 700, fontSize: 24, color: MUTED }}>
              {Math.round(homeProb * barFill * 100)}%
            </span>
            <span style={{ fontFamily, fontSize: 18, color: MUTED, fontWeight: 400 }}>
              Win Probability
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
              {Math.round(awayProb * barFill * 100)}%
            </span>
          </div>

          {/* Bar track */}
          <div
            style={{
              width: BAR_WIDTH,
              height: 16,
              backgroundColor: BORDER,
              borderRadius: 8,
              overflow: "hidden",
              display: "flex",
              alignSelf: "center",
            }}
          >
            <div
              style={{
                width: BAR_WIDTH * homeProb * barFill,
                height: "100%",
                backgroundColor: MUTED,
                borderRadius: "8px 0 0 8px",
              }}
            />
            <div
              style={{
                width: BAR_WIDTH * awayProb * barFill,
                height: "100%",
                backgroundColor: GREEN,
                borderRadius: "0 8px 8px 0",
              }}
            />
          </div>
        </div>

        {/* Winner callout */}
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            opacity: winnerOpacity,
            transform: `scale(${winnerScale})`,
          }}
        >
          <div
            style={{
              backgroundColor: `${GREEN}20`,
              border: `1px solid ${GREEN}40`,
              borderRadius: 12,
              padding: "12px 32px",
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <span style={{ fontFamily, fontWeight: 900, fontSize: 28, color: GREEN }}>
              BOS FAVORED
            </span>
            <span style={{ fontFamily, fontWeight: 400, fontSize: 20, color: MUTED }}>
              67% ELO
            </span>
          </div>
        </div>
      </div>

      {/* Key factors */}
      <div
        style={{
          display: "flex",
          gap: 24,
          opacity: factorsOpacity,
        }}
      >
        {["Pace", "Defense", "Rest", "Four Factors"].map((factor) => (
          <div
            key={factor}
            style={{
              fontFamily,
              fontWeight: 400,
              fontSize: 20,
              color: MUTED,
              backgroundColor: `${BORDER}80`,
              borderRadius: 8,
              padding: "8px 16px",
            }}
          >
            {factor}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
