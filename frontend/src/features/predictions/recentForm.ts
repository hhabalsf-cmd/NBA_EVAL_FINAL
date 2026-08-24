import type { GameLogEntry } from './api'

/**
 * Descriptive recent-form arithmetic over a player's game log.
 *
 * Pure box-score math — no model is consulted — so these numbers stay visible
 * with `VITE_ENABLE_PREDICTIONS` off.
 */

export const L10_WINDOW = 10

/** Per-game value of a stat, derived from raw box-score fields. */
export function statValue(game: GameLogEntry, stat: string): number {
  switch (stat) {
    case 'PTS': return game.pts
    case 'REB': return game.reb
    case 'AST': return game.ast
    case 'PRA': return game.pts + game.reb + game.ast
    default: return 0
  }
}

function mean(values: readonly number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
}

export interface RecentForm {
  l10: number | null
  logged: number | null
  loggedGames: number
}

/**
 * Descriptive averages over the returned game log. Pure box-score arithmetic —
 * no model is consulted, so this stays visible with predictions gated off.
 * The log is chronological ascending, so the last N entries are the most recent.
 */
export function recentForm(gameLog: readonly GameLogEntry[], stat: string): RecentForm {
  const values = gameLog.map(g => statValue(g, stat))
  return {
    l10: mean(values.slice(-L10_WINDOW)),
    logged: mean(values),
    loggedGames: values.length,
  }
}

