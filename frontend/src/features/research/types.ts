import type { StatSplits, FullGameLogEntry, PlayerResearchData } from './api'

export const STATS = ['PTS', 'REB', 'AST', 'PRA', 'PR', 'PA', 'STL', 'BLK', 'TOV', '3PM'] as const
export type Stat = typeof STATS[number]

export const STAT_LABELS: Record<Stat, string> = {
  PTS: 'Points',
  REB: 'Rebounds',
  AST: 'Assists',
  PRA: 'Pts+Reb+Ast',
  PR: 'Pts+Reb',
  PA: 'Pts+Ast',
  STL: 'Steals',
  BLK: 'Blocks',
  TOV: 'Turnovers',
  '3PM': '3-Pointers',
}

// Primary stats shown by default, secondary revealed via "More" toggle
export const PRIMARY_STATS: Stat[] = ['PTS', 'REB', 'AST', 'PRA']
export const SECONDARY_STATS: Stat[] = ['PR', 'PA', 'STL', 'BLK', 'TOV', '3PM']

export const TABS = ['Overview', 'Game Log', 'Chart', 'Splits', 'Analysis', 'Matchup'] as const
export type Tab = typeof TABS[number]

export function getStatValue(entry: FullGameLogEntry | StatSplits, stat: Stat): number {
  switch (stat) {
    case 'PTS': return entry.pts ?? 0
    case 'REB': return entry.reb ?? 0
    case 'AST': return entry.ast ?? 0
    case 'PRA': return entry.pra ?? 0
    case 'PR': return (entry as FullGameLogEntry).pr ?? ((entry as StatSplits).pr ?? 0)
    case 'PA': return (entry as FullGameLogEntry).pa ?? ((entry as StatSplits).pa ?? 0)
    case 'STL': return (entry as FullGameLogEntry).stl ?? ((entry as StatSplits).stl ?? 0)
    case 'BLK': return (entry as FullGameLogEntry).blk ?? ((entry as StatSplits).blk ?? 0)
    case 'TOV': return (entry as FullGameLogEntry).tov ?? ((entry as StatSplits).tov ?? 0)
    case '3PM': return (entry as FullGameLogEntry).fg3m ?? ((entry as StatSplits).fg3m ?? 0)
    default: return 0
  }
}

export function delta(val: number, base: number): number {
  return Math.round((val - base) * 10) / 10
}

export function hitColor(pct: number): string {
  if (pct >= 60) return 'var(--accent-success)'
  if (pct >= 40) return '#E6A817'
  return 'var(--accent-danger)'
}

export interface ResearchTabProps {
  data: PlayerResearchData
  activeStat: Stat
  setActiveStat: (s: Stat) => void
  parsedLine: number | null
  seasonAvg: number
  playerName: string
}
