import { supabase } from '../../shared/lib/supabase'
import { createPick } from '../picks/api'
import type { BestBet, DailyPick, Pick } from '../../api/types'

export type { BestBet, DailyPick } from '../../api/types'

/** Convert a DailyPick to a BestBet so existing BetCard works unchanged. */
export function dailyPickToBestBet(pick: DailyPick): BestBet {
  const lineIsReal = pick.odds_line != null
  const displayLine = pick.odds_line ?? pick.recent_avg ?? 0
  const recommendation = lineIsReal
    ? `${pick.direction} ${displayLine}`
    : `${pick.direction} ${displayLine} (avg)`

  return {
    player: pick.player,
    player_id: pick.player_id,
    headshot_url: pick.headshot_url,
    team_abbrev: pick.team_abbrev,
    stat: pick.stat,
    line: displayLine,
    prediction: pick.prediction,
    edge: pick.edge ?? 0,
    edge_pct: pick.edge ?? 0,
    direction: pick.direction,
    recommendation,
    prob_over: pick.prob_over,
    confidence: pick.confidence,
    home_team: pick.is_home ? pick.team_abbrev : pick.opponent,
    away_team: pick.is_home ? pick.opponent : pick.team_abbrev,
    line_is_real: lineIsReal,
  }
}

/**
 * Fetch today's daily picks directly from Supabase (no FastAPI round-trip).
 */
export async function getTodaysDailyPicks(): Promise<DailyPick[]> {
  const today = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' })).toISOString().slice(0, 10)
  const { data, error } = await supabase
    .from('daily_picks')
    .select('*')
    .eq('generated_date', today)
    .order('rank', { ascending: true })

  if (error) throw new Error(error.message)
  return (data ?? []) as DailyPick[]
}

/**
 * Save a daily pick to the user's personal picks via the existing createPick API.
 */
export async function saveDailyPickToMyPicks(pick: DailyPick): Promise<Pick> {
  return createPick({
    player: pick.player,
    player_id: pick.player_id,
    headshot_url: pick.headshot_url,
    team_abbrev: pick.team_abbrev,
    stat: pick.stat as Pick['stat'],
    line: pick.odds_line ?? pick.recent_avg ?? 0,
    prediction: pick.prediction,
    direction: pick.direction as Pick['direction'],
    edge: pick.edge ?? 0,
    confidence: pick.confidence,
    opponent: pick.opponent,
    is_home: pick.is_home,
    model_type: pick.model_type ?? 'line_anchored',
    game_date: pick.game_date,
    prob_over: pick.prob_over,
  })
}
