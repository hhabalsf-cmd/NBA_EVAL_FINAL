import { supabase } from '../../shared/lib/supabase'
import { apiFetch, API_BASE, throwResponseError } from '../../api/client'
import { createPick } from '../picks/api'
import type { BestBet, DailyPick, Pick } from '../../api/types'
import type { LineSnapshotSummary } from './lineObservations'

export type { BestBet, DailyPick } from '../../api/types'

// ── Manual line entry (fallback line source) ──────────────────────────

export interface ManualLine {
  id: number
  game_date: string
  player: string
  stat: 'PTS' | 'REB' | 'AST' | 'PRA'
  line: number
  home_team?: string | null
  away_team?: string | null
  /** When the line was first entered. Fallback when the snapshot log is unavailable. */
  created_at?: string | null
}

export interface ManualLineInput {
  player: string
  stat: ManualLine['stat']
  line: number
  home_team?: string | null
  away_team?: string | null
}

export async function getManualLines(date?: string): Promise<ManualLine[]> {
  const qs = date ? `?date=${encodeURIComponent(date)}` : ''
  const res = await apiFetch(`${API_BASE}/bets/lines${qs}`)
  if (!res.ok) await throwResponseError(res, 'Failed to load manual lines')
  const body = (await res.json()) as { lines: ManualLine[] }
  return body.lines
}

export async function upsertManualLines(lines: ManualLineInput[], gameDate?: string): Promise<ManualLine[]> {
  const res = await apiFetch(`${API_BASE}/bets/lines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines, game_date: gameDate }),
  })
  if (!res.ok) await throwResponseError(res, 'Failed to save lines')
  const body = (await res.json()) as { lines: ManualLine[] }
  return body.lines
}

export async function deleteManualLine(id: number): Promise<void> {
  const res = await apiFetch(`${API_BASE}/bets/lines/${id}`, { method: 'DELETE' })
  if (!res.ok) await throwResponseError(res, 'Failed to delete line')
}

// ── Line observations (closing-line value) ────────────────────────────

/**
 * Observation counts and timestamps for each line on a date.
 *
 * Admin-only: `line_snapshots` is service-role measurement infrastructure.
 */
export async function getLineSnapshots(date?: string): Promise<LineSnapshotSummary[]> {
  const qs = date ? `?date=${encodeURIComponent(date)}` : ''
  const res = await apiFetch(`${API_BASE}/bets/lines/snapshots${qs}`)
  if (!res.ok) await throwResponseError(res, 'Failed to load line observations')
  const body = (await res.json()) as { snapshots: LineSnapshotSummary[] }
  return body.snapshots
}

/**
 * Append a fresh observation of lines already on the board.
 *
 * The earlier observation is never overwritten — that path is what closing
 * line value is derived from. Capturing an unmoved line is valid: it records
 * that the line held, which is a real measurement.
 */
export async function captureLineSnapshots(
  lines: ManualLineInput[],
  gameDate?: string,
): Promise<LineSnapshotSummary[]> {
  const res = await apiFetch(`${API_BASE}/bets/lines/snapshots`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines, game_date: gameDate }),
  })
  if (!res.ok) await throwResponseError(res, 'Failed to capture line observation')
  const body = (await res.json()) as { snapshots: LineSnapshotSummary[] }
  return body.snapshots
}

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
