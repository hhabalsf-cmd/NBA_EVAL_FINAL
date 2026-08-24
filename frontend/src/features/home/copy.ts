import type { ElementType } from 'react'
import { BarChart3, LineChart, Search as SearchIcon, Target } from 'lucide-react'

/**
 * Home page copy, split by whether `VITE_ENABLE_PREDICTIONS` is on.
 *
 * With the flag off the product is research and analytics: no prediction
 * language, no "evaluate lines and save your picks" framing.
 */

export interface HowItWorksStep {
  icon: ElementType
  title: string
  desc: string
}

export interface HomeHeroCopy {
  heading: string
  subheading: string
}

const RESEARCH_HERO: HomeHeroCopy = {
  heading: 'Research NBA Players',
  subheading:
    'Game logs, rolling averages, home/away and matchup splits, and opponent defensive context.',
}

const PREDICTION_HERO: HomeHeroCopy = {
  heading: 'Evaluate Player Props',
  subheading: 'ML-powered predictions for points, rebounds, assists, and combined stats.',
}

const RESEARCH_STEPS: readonly HowItWorksStep[] = [
  { icon: SearchIcon, title: 'Search Player', desc: "Enter any NBA player's name to pull their data" },
  { icon: BarChart3, title: 'Read the Splits', desc: 'Game logs, rolling averages, home/away and matchup splits' },
  { icon: LineChart, title: 'Compare Context', desc: 'Opponent defensive ranks, pace, and usage alongside the trend' },
]

const PREDICTION_STEPS: readonly HowItWorksStep[] = [
  { icon: SearchIcon, title: 'Search Player', desc: "Enter any NBA player's name to begin analysis" },
  { icon: BarChart3, title: 'ML Prediction', desc: 'Our model analyzes historical data, matchups, and trends' },
  { icon: Target, title: 'Evaluate Lines', desc: 'Compare predictions to betting lines and save your picks' },
]

export function homeHeroCopy(predictionsEnabled: boolean): HomeHeroCopy {
  return predictionsEnabled ? PREDICTION_HERO : RESEARCH_HERO
}

export function howItWorksSteps(predictionsEnabled: boolean): readonly HowItWorksStep[] {
  return predictionsEnabled ? PREDICTION_STEPS : RESEARCH_STEPS
}
