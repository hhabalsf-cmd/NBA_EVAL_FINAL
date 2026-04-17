import React from "react";
import { AbsoluteFill } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { LogoReveal } from "../scenes/promo/LogoReveal";
import { HookStatement } from "../scenes/promo/HookStatement";
import { FeaturePrediction } from "../scenes/promo/FeaturePrediction";
import { FeatureResearch } from "../scenes/promo/FeatureResearch";
import { FeatureGames } from "../scenes/promo/FeatureGames";
import { StatsShowcase } from "../scenes/promo/StatsShowcase";
import { CTAOutro } from "../scenes/promo/CTAOutro";
import { BG } from "../theme";

// Scene durations (frames at 30fps)
const LOGO_FRAMES = 90; // 3s
const HOOK_FRAMES = 75; // 2.5s
const PREDICTION_FRAMES = 120; // 4s
const RESEARCH_FRAMES = 105; // 3.5s
const GAMES_FRAMES = 90; // 3s
const STATS_FRAMES = 90; // 3s
const CTA_FRAMES = 90; // 3s
const TRANSITION_FRAMES = 15; // 0.5s fade

// Total = sum of scenes - (num_transitions × transition_duration)
const NUM_TRANSITIONS = 6;
export const PROMO_TOTAL_FRAMES =
  LOGO_FRAMES +
  HOOK_FRAMES +
  PREDICTION_FRAMES +
  RESEARCH_FRAMES +
  GAMES_FRAMES +
  STATS_FRAMES +
  CTA_FRAMES -
  TRANSITION_FRAMES * NUM_TRANSITIONS;

const transition = fade();
const timing = linearTiming({ durationInFrames: TRANSITION_FRAMES });

export const PromoVideo: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <TransitionSeries>
        {/* Scene 1: Logo Reveal */}
        <TransitionSeries.Sequence durationInFrames={LOGO_FRAMES}>
          <LogoReveal />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Scene 2: Hook Statement */}
        <TransitionSeries.Sequence durationInFrames={HOOK_FRAMES}>
          <HookStatement />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Scene 3: Feature — Predictions */}
        <TransitionSeries.Sequence durationInFrames={PREDICTION_FRAMES}>
          <FeaturePrediction />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Scene 4: Feature — Research */}
        <TransitionSeries.Sequence durationInFrames={RESEARCH_FRAMES}>
          <FeatureResearch />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Scene 5: Feature — Games */}
        <TransitionSeries.Sequence durationInFrames={GAMES_FRAMES}>
          <FeatureGames />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Scene 6: Stats Showcase */}
        <TransitionSeries.Sequence durationInFrames={STATS_FRAMES}>
          <StatsShowcase />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Scene 7: CTA Outro */}
        <TransitionSeries.Sequence durationInFrames={CTA_FRAMES}>
          <CTAOutro />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
