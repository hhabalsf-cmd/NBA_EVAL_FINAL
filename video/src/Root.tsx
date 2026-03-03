import React from "react";
import { Composition } from "remotion";
import { Top5Picks, TOTAL_FRAMES } from "./compositions/Top5Picks";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Top5Picks"
      component={Top5Picks}
      durationInFrames={TOTAL_FRAMES}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
