import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";
import type { Pick } from "../data/picks";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "700", "900"],
  subsets: ["latin"],
});

const GOLD = "#C9A87C";
const BG = "#09090B";
const CARD_BG = "#131316";
const WHITE = "#EDEDEC";
const MUTED = "#8F8B87";
const GREEN = "#6BBF8A";
const BORDER = "#232329";

export const PickSlide: React.FC<{ pick: Pick }> = ({ pick }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Card slides up on entry
  const cardSpring = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 120 },
    durationInFrames: 35,
  });
  const cardY = interpolate(cardSpring, [0, 1], [80, 0]);
  const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

  // Rank badge pops in
  const badgeSpring = spring({
    frame: frame - 5,
    fps,
    config: { damping: 12, stiffness: 200 },
    durationInFrames: 25,
  });
  const badgeScale = interpolate(badgeSpring, [0, 1], [0.5, 1]);

  // Hit prob bar fills in (starts at frame 20)
  const barProgress = interpolate(frame, [20, 55], [0, pick.hitProb / 100], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Player name fades in with slight delay
  const nameOpacity = interpolate(frame, [8, 22], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const CARD_WIDTH = 860;
  const BAR_MAX_WIDTH = CARD_WIDTH - 80;

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
      {/* Rank badge */}
      <div
        style={{
          transform: `scale(${badgeScale})`,
          backgroundColor: GOLD,
          borderRadius: 50,
          width: 80,
          height: 80,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 40,
            color: BG,
            lineHeight: 1,
          }}
        >
          #{pick.rank}
        </span>
      </div>

      {/* Main card */}
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
          gap: 24,
        }}
      >
        {/* Player name */}
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 72,
            color: WHITE,
            letterSpacing: -2,
            lineHeight: 1.05,
            opacity: nameOpacity,
          }}
        >
          {pick.player}
        </div>

        {/* Team · Stat row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            opacity: nameOpacity,
          }}
        >
          <span
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: 32,
              color: GOLD,
              letterSpacing: 1,
            }}
          >
            {pick.team}
          </span>
          <span style={{ color: MUTED, fontSize: 28 }}>·</span>
          <span
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: 32,
              color: MUTED,
              letterSpacing: 1,
            }}
          >
            {pick.stat}
          </span>
        </div>

        {/* OVER / UNDER pill + line */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              backgroundColor: GREEN,
              borderRadius: 8,
              padding: "8px 20px",
              display: "inline-flex",
            }}
          >
            <span
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: 28,
                color: BG,
                letterSpacing: 2,
              }}
            >
              {pick.direction === "OVER" ? "↑" : "↓"}
            </span>
          </div>
          <span
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: 52,
              color: WHITE,
              letterSpacing: -1,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {pick.line}
          </span>
        </div>

        {/* Hit prob bar */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontFamily,
                fontSize: 22,
                color: MUTED,
                fontWeight: 400,
              }}
            >
              Confidence
            </span>
            <span
              style={{
                fontFamily,
                fontWeight: 700,
                fontSize: 26,
                color: GREEN,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {Math.round(barProgress * 100)}%
            </span>
          </div>

          {/* Track */}
          <div
            style={{
              width: BAR_MAX_WIDTH,
              height: 12,
              backgroundColor: BORDER,
              borderRadius: 6,
              overflow: "hidden",
            }}
          >
            {/* Fill */}
            <div
              style={{
                width: BAR_MAX_WIDTH * barProgress,
                height: "100%",
                backgroundColor: GREEN,
                borderRadius: 6,
              }}
            />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
