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
  fontFamily, SPRING_SNAPPY,
} from "../../theme";

type ResearchCard = {
  title: string;
  detail: string;
  accent: string;
  icon: string;
};

const CARDS: ResearchCard[] = [
  {
    title: "Game Logs",
    detail: "Rolling averages · Trend arrows · L20 history",
    accent: CYAN,
    icon: "📊",
  },
  {
    title: "Matchup Analysis",
    detail: "Elite vs weak defense · Opponent context",
    accent: GOLD,
    icon: "🎯",
  },
  {
    title: "Smart Splits",
    detail: "Home/Away · Rest days · Back-to-back",
    accent: GREEN,
    icon: "📈",
  },
];

const STAGGER_DELAY = 12;

export const FeatureResearch: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title slides in
  const titleSpring = spring({
    frame,
    fps,
    config: SPRING_SNAPPY,
    durationInFrames: 30,
  });
  const titleY = interpolate(titleSpring, [0, 1], [40, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 1], [0, 1]);

  // Scan-line animation
  const scanX = interpolate(frame, [0, 105], [-200, 1280], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 40,
        padding: "0 60px",
      }}
    >
      {/* Scan line */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: scanX,
          width: 150,
          height: "100%",
          background: `linear-gradient(90deg, transparent 0%, ${CYAN}08 50%, transparent 100%)`,
          pointerEvents: "none",
        }}
      />

      {/* Section title */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
        }}
      >
        <span style={{ fontSize: 48 }}>🔬</span>
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 56,
            color: WHITE,
            letterSpacing: -2,
          }}
        >
          Deep Research
        </div>
      </div>

      {/* Research cards — staggered */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 20,
          width: "100%",
          maxWidth: 860,
        }}
      >
        {CARDS.map((card, i) => {
          const cardSpring = spring({
            frame: frame - 15 - i * STAGGER_DELAY,
            fps,
            config: SPRING_SNAPPY,
            durationInFrames: 30,
          });
          const cardX = interpolate(cardSpring, [0, 1], [80, 0]);
          const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

          return (
            <div
              key={card.title}
              style={{
                backgroundColor: CARD_BG,
                borderRadius: 20,
                border: `1px solid ${BORDER}`,
                padding: "32px 36px",
                display: "flex",
                alignItems: "center",
                gap: 24,
                opacity: cardOpacity,
                transform: `translateX(${cardX}px)`,
              }}
            >
              {/* Icon */}
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: 16,
                  backgroundColor: `${card.accent}18`,
                  border: `1px solid ${card.accent}30`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 32,
                  flexShrink: 0,
                }}
              >
                {card.icon}
              </div>

              {/* Text */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div
                  style={{
                    fontFamily,
                    fontWeight: 700,
                    fontSize: 30,
                    color: WHITE,
                  }}
                >
                  {card.title}
                </div>
                <div
                  style={{
                    fontFamily,
                    fontWeight: 400,
                    fontSize: 20,
                    color: MUTED,
                    letterSpacing: 0.5,
                  }}
                >
                  {card.detail}
                </div>
              </div>

              {/* Accent bar on left edge */}
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: "15%",
                  bottom: "15%",
                  width: 3,
                  backgroundColor: card.accent,
                  borderRadius: 2,
                }}
              />
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
