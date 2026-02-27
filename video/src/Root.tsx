import { Composition } from "remotion";
import { Top5Picks } from "./compositions/Top5Picks";

// Total: 60 + (90×5) + 30 - (15×6 transitions) = 450 frames
const DURATION = 450;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Top5Picks"
      component={Top5Picks}
      durationInFrames={DURATION}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
