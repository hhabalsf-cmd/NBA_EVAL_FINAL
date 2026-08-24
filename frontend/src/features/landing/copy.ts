import type { ElementType } from 'react'
import { BarChart3, LineChart, Search as SearchIcon, Target } from 'lucide-react'
import type { GhostPredictionCard, GhostResearchCard } from './GhostStatCard'

/**
 * Landing page copy, split by whether `VITE_ENABLE_PREDICTIONS` is on.
 *
 * With the flag off the page makes no claim about predicting outcomes, finding
 * an edge, or win rates — it describes the research data the app actually
 * provides.
 */

export interface LandingHeroCopy {
  badge: string
  headingTop: string
  headingAccent: string
  subheading: string
}

export interface LandingSectionCopy {
  title: string
  subtitle: string
}

export interface LandingCtaCopy {
  heading: string
  body: string
  sampleLink: string
}

export interface LandingStep {
  Icon: ElementType
  step: string
  title: string
  desc: string
  color: string
}

const PREDICTION_HERO: LandingHeroCopy = {
  badge: 'ML-Powered Analytics',
  headingTop: 'Stop guessing.',
  headingAccent: 'Start evaluating.',
  subheading:
    'ML models trained on NBA data surface the edge in player props. Know when to bet — and when to pass.',
}

const RESEARCH_HERO: LandingHeroCopy = {
  badge: 'NBA Research & Analytics',
  headingTop: 'NBA player data,',
  headingAccent: 'in full detail.',
  subheading:
    'Game logs, rolling averages, home/away and matchup splits, and opponent defensive context — the numbers, without predictions or picks.',
}

const PREDICTION_SAMPLE: LandingSectionCopy = {
  // Illustrative only: the cards below are fixed sample values, not live output.
  title: 'Sample Output',
  subtitle: 'An illustrative example of what a model card looks like — not live predictions',
}

const RESEARCH_SAMPLE: LandingSectionCopy = {
  title: "What's Inside",
  subtitle: 'An illustrative example of the player data on every research page',
}

const PREDICTION_CTA: LandingCtaCopy = {
  heading: 'Ready to find an edge?',
  body: 'Create a free account to get started with ML-powered prop analysis.',
  sampleLink: 'Create a free account to run your own predictions →',
}

const RESEARCH_CTA: LandingCtaCopy = {
  heading: 'Ready to dig into the numbers?',
  body: 'Create a free account to pull game logs, splits, and matchup context for any NBA player.',
  sampleLink: 'Create a free account to research any player →',
}

const PREDICTION_STEPS: readonly LandingStep[] = [
  { Icon: SearchIcon, step: '01', title: 'Search Player', desc: "Enter any NBA player's name to begin analysis", color: 'var(--accent)' },
  { Icon: BarChart3, step: '02', title: 'ML Prediction', desc: 'Our model analyzes historical data, matchups, and trends', color: 'var(--accent-warning)' },
  { Icon: Target, step: '03', title: 'Evaluate Lines', desc: 'Compare predictions to betting lines and save your picks', color: 'var(--accent-success)' },
]

const RESEARCH_STEPS: readonly LandingStep[] = [
  { Icon: SearchIcon, step: '01', title: 'Search Player', desc: "Enter any NBA player's name to pull their data", color: 'var(--accent)' },
  { Icon: BarChart3, step: '02', title: 'Read the Splits', desc: 'Game logs, rolling averages, home/away and matchup splits', color: 'var(--accent-warning)' },
  { Icon: LineChart, step: '03', title: 'Compare Context', desc: 'Opponent defensive ranks, pace, and usage alongside the trend', color: 'var(--accent-success)' },
]

export const GHOST_PREDICTION_CARDS: readonly GhostPredictionCard[] = [
  { player: 'LeBron James', stat: 'PTS', value: 27.5, line: 26.5, isOver: true, conf: 78 },
  { player: 'S. Curry', stat: 'PTS', value: 31.2, line: 29.5, isOver: true, conf: 82 },
  { player: 'N. Jokić', stat: 'REB', value: 12.1, line: 11.5, isOver: true, conf: 71 },
  { player: 'A. Edwards', stat: 'AST', value: 4.2, line: 5.0, isOver: false, conf: 68 },
]

export const GHOST_RESEARCH_CARDS: readonly GhostResearchCard[] = [
  { player: 'LeBron James', stat: 'PTS', l10: 27.5, season: 25.8, split: 'Home' },
  { player: 'S. Curry', stat: 'PTS', l10: 31.2, season: 28.9, split: 'Away' },
  { player: 'N. Jokić', stat: 'REB', l10: 12.1, season: 12.6, split: 'Home' },
  { player: 'A. Edwards', stat: 'AST', l10: 4.2, season: 4.9, split: 'Away' },
]

export function landingHeroCopy(predictionsEnabled: boolean): LandingHeroCopy {
  return predictionsEnabled ? PREDICTION_HERO : RESEARCH_HERO
}

export function landingSampleCopy(predictionsEnabled: boolean): LandingSectionCopy {
  return predictionsEnabled ? PREDICTION_SAMPLE : RESEARCH_SAMPLE
}

export function landingCtaCopy(predictionsEnabled: boolean): LandingCtaCopy {
  return predictionsEnabled ? PREDICTION_CTA : RESEARCH_CTA
}

export function landingSteps(predictionsEnabled: boolean): readonly LandingStep[] {
  return predictionsEnabled ? PREDICTION_STEPS : RESEARCH_STEPS
}
