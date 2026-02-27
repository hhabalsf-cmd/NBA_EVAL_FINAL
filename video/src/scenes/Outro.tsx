import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";

const { fontFamily } = loadFont("normal", {
  weights: ["700", "900"],
  subsets: ["latin"],
});

const GOLD = "#C9A87C";
const BG = "#09090B";
const WHITE = "#EDEDEC";

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const spring1 = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 200 },
    durationInFrames: 20,
  });

  const scale = interpolate(spring1, [0, 1], [0.8, 1]);
  const opacity = interpolate(spring1, [0, 1], [0, 1]);

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
      <Audio src={staticFile("audio/outro.mp3")} />
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
        }}
      >
        <div style={{ fontSize: 72 }}>🏀</div>
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 56,
            color: WHITE,
            letterSpacing: -1,
            lineHeight: 1.1,
            textAlign: "center",
          }}
        >
          FOLLOW FOR MORE
          {"\n"}PICKS
        </div>
        <div
          style={{
            fontFamily,
            fontWeight: 700,
            fontSize: 28,
            color: GOLD,
            letterSpacing: 3,
            marginTop: 8,
          }}
        >
          DAILY NBA PROPS
        </div>
      </div>
    </AbsoluteFill>
  );
};
