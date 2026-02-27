import { AbsoluteFill } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { slide } from "@remotion/transitions/slide";
import { Intro } from "../scenes/Intro";
import { PickSlide } from "../scenes/PickSlide";
import { Outro } from "../scenes/Outro";
import { PICKS } from "../data/picks";

// Scene durations (frames at 30fps)
const INTRO_FRAMES = 60; // 2s
const PICK_FRAMES = 90; // 3s each
const OUTRO_FRAMES = 30; // 1s
const TRANSITION_FRAMES = 15; // 0.5s

const transition = slide({ direction: "from-bottom" });
const timing = linearTiming({ durationInFrames: TRANSITION_FRAMES });

export const Top5Picks: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#09090B" }}>
      <TransitionSeries>
        {/* Intro */}
        <TransitionSeries.Sequence durationInFrames={INTRO_FRAMES}>
          <Intro />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Picks — flatMap avoids fragment wrappers which break TransitionSeries */}
        {PICKS.flatMap((pick, i) => [
          <TransitionSeries.Sequence
            key={`pick-${pick.rank}`}
            durationInFrames={PICK_FRAMES}
          >
            <PickSlide pick={pick} />
          </TransitionSeries.Sequence>,
          ...(i < PICKS.length - 1
            ? [
                <TransitionSeries.Transition
                  key={`t-${pick.rank}`}
                  presentation={transition}
                  timing={timing}
                />,
              ]
            : []),
        ])}

        {/* Transition to outro */}
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Outro */}
        <TransitionSeries.Sequence durationInFrames={OUTRO_FRAMES}>
          <Outro />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
