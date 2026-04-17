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

type StatItem = {
  value: number;
  suffix: string;
  label: string;
  color: string;
};

const STATS: StatItem[] = [
  { value: 100, suffix: "+", label: "Features Analyzed", color: CYAN },
  { value: 4, suffix: "", label: "Stat Models", color: GOLD },
  { value: 5, suffix: "", label: "ML Algorithms", color: GREEN },
];

const STAGGER_DELAY = 10;

export const StatsShowcase: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title fades in
  const titleOpacity = interpolate(frame, [0, 15], [0, 1], {
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
        gap: 60,
        padding: "0 80px",
      }}
    >
      {/* Title */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 52,
          color: WHITE,
          letterSpacing: -2,
          opacity: titleOpacity,
        }}
      >
        The Numbers
      </div>

      {/* Stat counters */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 40,
          width: "100%",
          alignItems: "center",
        }}
      >
        {STATS.map((stat, i) => {
          const statSpring = spring({
            frame: frame - 10 - i * STAGGER_DELAY,
            fps,
            config: SPRING_SNAPPY,
            durationInFrames: 30,
          });
          const statOpacity = interpolate(statSpring, [0, 1], [0, 1]);
          const statY = interpolate(statSpring, [0, 1], [40, 0]);

          // Counter animation
          const counterValue = interpolate(
            frame,
            [10 + i * STAGGER_DELAY, 40 + i * STAGGER_DELAY],
            [0, stat.value],
            { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
          );

          // Gold accent bar width
          const barWidth = interpolate(
            frame,
            [20 + i * STAGGER_DELAY, 50 + i * STAGGER_DELAY],
            [0, 200],
            { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
          );

          return (
            <div
              key={stat.label}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                opacity: statOpacity,
                transform: `translateY(${statY}px)`,
              }}
            >
              {/* Number */}
              <div
                style={{
                  fontFamily,
                  fontWeight: 900,
                  fontSize: 96,
                  color: stat.color,
                  letterSpacing: -4,
                  fontVariantNumeric: "tabular-nums",
                  lineHeight: 1,
                }}
              >
                {Math.round(counterValue)}{stat.suffix}
              </div>

              {/* Accent bar */}
              <div
                style={{
                  width: barWidth,
                  height: 3,
                  backgroundColor: stat.color,
                  borderRadius: 2,
                  opacity: 0.6,
                }}
              />

              {/* Label */}
              <div
                style={{
                  fontFamily,
                  fontWeight: 700,
                  fontSize: 24,
                  color: MUTED,
                  letterSpacing: 4,
                  textTransform: "uppercase",
                }}
              >
                {stat.label}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
