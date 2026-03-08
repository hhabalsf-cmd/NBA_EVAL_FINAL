/**
 * API client for NBA Prop Evaluator backend
 */

import { supabase } from '../lib/supabase'

const API_BASE = (import.meta.env.VITE_API_URL ?? '') + '/api'

/** Throw a user-friendly error, with special handling for 429 rate limits. */
async function throwResponseError(response: Response, fallback: string): Promise<never> {
  if (response.status === 429) {
    const body = await response.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? 'Too many requests — please wait a moment and try again.')
  }
  const body = await response.json().catch(() => ({}))
  throw new Error((body as { detail?: string }).detail ?? fallback)
}

/**
 * Fetch wrapper that attaches the Supabase session token as a Bearer header
 * and dispatches a global event on 401 so the auth store can log the user out.
 */
async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(init.headers)
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }

  const res = await fetch(input, { ...init, headers })
  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:unauthorized'))
  }
  return res
}

// Types
export interface PlayerInfo {
  player_id: number
  player_name: string
  team_id?: number
  team_abbrev?: string
  team_name?: string
}

export interface StatPrediction {
  stat: string
  prediction: number
  confidence: number
  range_low: number
  range_high: number
  uncertainty_std?: number
  recent_avg?: number
}

export interface GameInfo {
  matchup: string
  game_date: string
  is_home: boolean
  opponent: string
  opponent_name: string
}

export interface OpponentContext {
  def_rating: number
  pace: number
  def_rank: string
  pace_desc: string
}

export interface VsStats {
  games: number
  avg_pts: number
  avg_reb: number
  avg_ast: number
}

export interface GameLogEntry {
  game_date: string   // "Feb 20"
  opponent: string    // "vs HOU" or "@ BOS"
  min: number
  pts: number
  reb: number
  ast: number
}

export interface PredictionResult {
  player_name: string
  player_id: number
  team_abbrev?: string
  predictions: Record<string, StatPrediction>
  game_info?: GameInfo
  opponent_context?: OpponentContext
  vs_stats?: VsStats
  model_type: string
  games_trained_on: number
  game_log?: GameLogEntry[]
  avg_min_l10?: number
}

export interface LineEvaluation {
  stat: string
  line: number
  prediction: number
  difference: number
  diff_pct: number
  recommendation: string
  strength: string
  prob_over?: number
  confidence?: number
  range_low?: number
  range_high?: number
  high_edge_warning?: boolean
}

export interface Pick {
  id: number
  timestamp: string
  player: string
  player_id?: number
  team_abbrev?: string
  stat: string
  line: number
  prediction: number
  direction: string
  edge: number
  confidence?: number
  opponent?: string
  is_home?: boolean
  actual_result?: number
  won?: boolean
  model_type?: string
  game_date?: string
  voided?: boolean
  void_reason?: string
  prob_over?: number
}

export interface ParlayLegDetail {
  id: number
  pick_id: number
  player: string
  player_id?: number
  team_abbrev?: string
  stat: string
  line: number
  prediction: number
  direction: string
  edge: number
  prob_over?: number
  actual_result?: number
  won?: boolean
  voided?: boolean
  void_reason?: string
  game_date?: string
  opponent?: string
}

export interface SavedParlay {
  id: number
  legs_count: number
  status: 'pending' | 'won' | 'lost' | 'voided'
  graded_at?: string
  created_at: string
  legs: ParlayLegDetail[]
}

export interface PerformanceStats {
  total_picks: number
  graded_picks: number
  wins: number
  losses: number
  pushes: number
  win_rate: number
  roi: number
  avg_edge_winners: number
  by_stat: Record<string, { total: number; wins: number; win_rate: number }>
  by_edge_range: Record<string, { total: number; wins: number; win_rate: number }>
}

export interface CumulativeProfitPoint {
  date: string
  profit: number
  cumulative_profit: number
}

export interface BestBet {
  player: string
  player_id?: number
  team_abbrev?: string
  stat: string
  line: number
  prediction: number
  edge: number
  edge_pct: number
  direction: string
  recommendation: string
  prob_over?: number
  game_info?: GameInfo
  home_team?: string
  away_team?: string
  confidence?: number
}

export interface PlayerOdds {
  PTS?: number
  REB?: number
  AST?: number
  PRA?: number
  found: boolean
}

export interface ProgressEvent {
  stage: string
  progress: number
  message: string
  data?: PredictionResult
}

// API Functions

export async function getPlayerOdds(playerName: string): Promise<PlayerOdds> {
  const response = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/odds`)
  if (!response.ok) return { found: false }
  return response.json()
}

export async function searchPlayers(query: string, signal?: AbortSignal): Promise<PlayerInfo[]> {
  const response = await apiFetch(`${API_BASE}/players/search?q=${encodeURIComponent(query)}`, { signal })
  if (!response.ok) await throwResponseError(response, 'Search failed')
  const data = await response.json()
  return data.players
}

export async function predictPlayer(
  playerName: string,
  onProgress: (event: ProgressEvent) => void,
  options: {
    modelType?: string
    useEnsemble?: boolean
    retrain?: boolean
  } = {}
): Promise<PredictionResult | null> {
  const response = await apiFetch(`${API_BASE}/players/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_name: playerName,
      model_type: options.modelType || 'gradient_boost',
      use_ensemble: options.useEnsemble || false,
      retrain: options.retrain || false,
    }),
  })

  if (!response.ok) await throwResponseError(response, 'Prediction failed')
  if (!response.body) throw new Error('No response body')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let result: PredictionResult | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value)
    const lines = chunk.split('\n')

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: ProgressEvent = JSON.parse(line.slice(6))
          onProgress(event)

          if (event.stage === 'complete' && event.data) {
            result = event.data
          }
        } catch {
          // Ignore parse errors
        }
      }
    }
  }

  return result
}

export async function predictPlayerSync(
  playerName: string,
  options: {
    modelType?: string
    useEnsemble?: boolean
    retrain?: boolean
  } = {}
): Promise<PredictionResult> {
  const response = await apiFetch(`${API_BASE}/players/predict/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_name: playerName,
      model_type: options.modelType || 'gradient_boost',
      use_ensemble: options.useEnsemble || false,
      retrain: options.retrain || false,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Prediction failed')
  }

  return response.json()
}

export async function evaluateLine(
  playerName: string,
  stat: string,
  line: number,
  prediction?: number
): Promise<LineEvaluation> {
  const response = await apiFetch(`${API_BASE}/players/evaluate-line`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_name: playerName,
      stat,
      line,
      prediction,
    }),
  })

  if (!response.ok) await throwResponseError(response, 'Evaluation failed')
  return response.json()
}

export async function getTodaysBestBets(minEdge = 5, limit = 10): Promise<{ bets: BestBet[]; generated_at: string; games_count: number }> {
  const response = await apiFetch(`${API_BASE}/bets/today?min_edge=${minEdge}&limit=${limit}`)
  if (!response.ok) throw new Error('Failed to fetch best bets')
  return response.json()
}

export async function getPicks(pendingOnly = false): Promise<Pick[]> {
  let query = supabase
    .from('picks')
    .select('*')
    .order('timestamp', { ascending: false })

  if (pendingOnly) {
    query = query.is('won', null).eq('voided', 0)
  }

  const { data, error } = await query
  if (error) throw new Error(error.message)
  return (data ?? []).map(p => ({
    ...p,
    won: p.won === 1 ? true : p.won === 0 ? false : null,
    voided: Boolean(p.voided),
  }))
}

export async function createPick(pick: Omit<Pick, 'id' | 'timestamp' | 'actual_result' | 'won'>): Promise<Pick> {
  const response = await apiFetch(`${API_BASE}/picks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pick),
  })

  if (!response.ok) throw new Error('Failed to create pick')
  return response.json()
}

export async function gradePick(pickId: number, actualResult: number): Promise<Pick> {
  const response = await apiFetch(`${API_BASE}/picks/${pickId}/grade`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actual_result: actualResult }),
  })

  if (!response.ok) throw new Error('Failed to grade pick')
  return response.json()
}

export async function deletePick(pickId: number): Promise<void> {
  const response = await apiFetch(`${API_BASE}/picks/${pickId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete pick')
}

export async function createParlay(pickIds: number[]): Promise<SavedParlay> {
  const response = await apiFetch(`${API_BASE}/parlays`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pick_ids: pickIds }),
  })
  if (!response.ok) await throwResponseError(response, 'Failed to save parlay')
  return response.json()
}

export async function getParlays(): Promise<SavedParlay[]> {
  const { data, error } = await supabase
    .from('parlays')
    .select('*, parlay_legs(*)')
    .order('created_at', { ascending: false })

  if (error) throw new Error(error.message)
  return (data ?? []).map(p => ({
    ...p,
    legs: (p.parlay_legs ?? []).map((leg: Record<string, unknown>) => ({
      ...leg,
      won: leg.won === 1 ? true : leg.won === 0 ? false : (leg.won ?? null),
      voided: leg.voided === 1 ? true : false,
    })),
  })) as SavedParlay[]
}

export async function deleteParlay(parlayId: number): Promise<void> {
  const response = await apiFetch(`${API_BASE}/parlays/${parlayId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete parlay')
}

export async function autoGradePicks(): Promise<{ graded_count: number; parlays_graded: number; errors: string[]; results: unknown[] }> {
  const response = await apiFetch(`${API_BASE}/picks/auto-grade`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to auto-grade picks')
  return response.json()
}

export async function getPerformanceStats(): Promise<PerformanceStats> {
  const { data: picks, error } = await supabase
    .from('picks')
    .select('stat, edge, won, voided')

  if (error) throw new Error(error.message)
  if (!picks) return emptyPerformanceStats()

  const graded = picks.filter(p => p.won !== null && p.voided !== 1)
  const wins = graded.filter(p => p.won === 1 || p.won === true)
  const losses = graded.filter(p => p.won === 0 || p.won === false)
  const pushes = picks.filter(p => p.voided === 1)

  const win_rate = graded.length > 0 ? wins.length / graded.length : 0
  const roi = graded.length > 0 ? (wins.length - losses.length) / graded.length : 0
  const avg_edge_winners = wins.length > 0
    ? wins.reduce((sum, p) => sum + (p.edge ?? 0), 0) / wins.length
    : 0

  const by_stat: Record<string, { total: number; wins: number; win_rate: number }> = {}
  for (const p of graded) {
    if (!by_stat[p.stat]) by_stat[p.stat] = { total: 0, wins: 0, win_rate: 0 }
    by_stat[p.stat].total++
    if (p.won === 1 || p.won === true) by_stat[p.stat].wins++
  }
  for (const stat of Object.keys(by_stat)) {
    const s = by_stat[stat]
    s.win_rate = s.total > 0 ? s.wins / s.total : 0
  }

  const edgeRanges = [
    { label: '0-5', min: 0, max: 5 },
    { label: '5-10', min: 5, max: 10 },
    { label: '10-15', min: 10, max: 15 },
    { label: '15+', min: 15, max: Infinity },
  ]
  const by_edge_range: Record<string, { total: number; wins: number; win_rate: number }> = {}
  for (const range of edgeRanges) {
    const inRange = graded.filter(p => (p.edge ?? 0) >= range.min && (p.edge ?? 0) < range.max)
    const rangeWins = inRange.filter(p => p.won === 1 || p.won === true)
    by_edge_range[range.label] = {
      total: inRange.length,
      wins: rangeWins.length,
      win_rate: inRange.length > 0 ? rangeWins.length / inRange.length : 0,
    }
  }

  return {
    total_picks: picks.length,
    graded_picks: graded.length,
    wins: wins.length,
    losses: losses.length,
    pushes: pushes.length,
    win_rate,
    roi,
    avg_edge_winners,
    by_stat,
    by_edge_range,
  }
}

function emptyPerformanceStats(): PerformanceStats {
  return {
    total_picks: 0, graded_picks: 0, wins: 0, losses: 0, pushes: 0,
    win_rate: 0, roi: 0, avg_edge_winners: 0, by_stat: {}, by_edge_range: {},
  }
}

export async function getCumulativeProfit(): Promise<CumulativeProfitPoint[]> {
  const { data, error } = await supabase
    .from('picks')
    .select('game_date, won, voided')
    .not('won', 'is', null)
    .not('game_date', 'is', null)
    .order('game_date', { ascending: true })

  if (error) throw new Error(error.message)

  let cumulative = 0
  return (data ?? []).map(p => {
    const profit = p.won === 1 ? 1 : (p.voided !== 1 ? -1 : 0)
    cumulative += profit
    return {
      date: p.game_date as string,
      profit,
      cumulative_profit: cumulative,
    }
  })
}

// === Game Prediction Types ===

export interface TeamInfoGame {
  team_id: number
  team_abbrev: string
  team_name: string
  record: string
  off_rating: number
  def_rating: number
  net_rating: number
  pace: number
}

export interface GameMatchup {
  home_team: TeamInfoGame
  away_team: TeamInfoGame
  game_date: string
  game_time?: string
}

export interface KeyFactor {
  factor: string
  impact: string
  description: string
  favors: string
}

export interface GamePrediction {
  matchup: GameMatchup
  predicted_winner: string
  home_win_prob: number
  away_win_prob: number
  confidence: number
  key_factors: KeyFactor[]
  prediction_id?: number
}

export interface TodaysGamesResponse {
  predictions: GamePrediction[]
  generated_at: string
  games_count: number
}

export interface GamePredictionHistoryItem {
  id: number
  timestamp: string
  game_date: string
  home_team: string
  away_team: string
  predicted_winner: string
  home_win_prob: number
  away_win_prob: number
  confidence?: number
  actual_winner?: string
  correct?: boolean | number
  key_factors: KeyFactor[]
}

export interface ConfidenceRangeItem {
  total: number
  correct: number
  accuracy: number
}

export interface GameAccuracyStats {
  total_predictions: number
  graded_predictions: number
  correct: number
  incorrect: number
  accuracy: number
  by_confidence_range: Record<string, ConfidenceRangeItem>
  recent_streak: string
}

// === Game Prediction API Functions ===

export async function getTodaysGamePredictions(): Promise<TodaysGamesResponse> {
  const response = await apiFetch(`${API_BASE}/games/today`)
  if (!response.ok) await throwResponseError(response, 'Failed to fetch game predictions')
  return response.json()
}

export async function predictTodaysGames(
  onProgress: (event: ProgressEvent) => void
): Promise<GamePrediction[] | null> {
  const response = await apiFetch(`${API_BASE}/games/predict`, { method: 'POST' })

  if (!response.ok) throw new Error('Prediction failed')
  if (!response.body) throw new Error('No response body')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let result: GamePrediction[] | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value)
    const lines = chunk.split('\n')

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: ProgressEvent = JSON.parse(line.slice(6))
          onProgress(event)

          if (event.stage === 'complete' && event.data) {
            const responseData = event.data as unknown as TodaysGamesResponse
            result = responseData.predictions
          }
        } catch {
          // Ignore parse errors
        }
      }
    }
  }

  return result
}

export async function getGamePredictionHistory(): Promise<GamePredictionHistoryItem[]> {
  const { data, error } = await supabase
    .from('game_predictions')
    .select('*')
    .order('timestamp', { ascending: false })

  if (error) throw new Error(error.message)
  return (data ?? []).map(item => ({
    ...item,
    key_factors: typeof item.key_factors === 'string'
      ? JSON.parse(item.key_factors)
      : (item.key_factors ?? []),
  }))
}

export async function autoGradeGamePredictions(): Promise<{
  graded_count: number
  errors: string[]
  results: unknown[]
}> {
  const response = await apiFetch(`${API_BASE}/games/auto-grade`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to auto-grade game predictions')
  return response.json()
}

export async function gradeGamePrediction(id: number, actualWinner: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/games/${id}/grade`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actual_winner: actualWinner }),
  })
  if (!response.ok) throw new Error('Failed to grade game prediction')
}

export async function getGameAccuracyStats(): Promise<GameAccuracyStats> {
  const { data, error } = await supabase
    .from('game_accuracy_stats')
    .select('*')
    .single()

  if (error) throw new Error(error.message)
  return {
    total_predictions: data.total_predictions ?? 0,
    graded_predictions: data.graded_predictions ?? 0,
    correct: data.correct ?? 0,
    incorrect: data.incorrect ?? 0,
    accuracy: data.accuracy ?? 0,
    by_confidence_range: {},
    recent_streak: '',
  }
}

// === Injury Types ===

export interface InjuredPlayer {
  name: string
  status: 'out' | 'questionable'
}

export interface TeamInjuryInfo {
  abbrev: string
  out: InjuredPlayer[]
  questionable: InjuredPlayer[]
}

export interface TeamInjuriesData {
  team: TeamInjuryInfo | null
  opponent: TeamInjuryInfo | null
}

export async function getTeamInjuries(playerName: string): Promise<TeamInjuriesData> {
  const res = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/team-injuries`)
  if (!res.ok) throw new Error('Failed to fetch injuries')
  return res.json()
}

// === Standings Types ===

export interface StandingsTeam {
  team_id: number
  team: string
  conference: string
  rank: number
  wins: number
  losses: number
  pct: number
  gb: number | string
  home: string
  away: string
  l10: string
  streak: string
}

export interface StandingsData {
  east: StandingsTeam[]
  west: StandingsTeam[]
  fetched_at: number
}

// === Standings API Functions ===

export async function getStandings(): Promise<StandingsData> {
  const res = await apiFetch(`${API_BASE}/standings`)
  if (!res.ok) throw new Error('Failed to fetch standings')
  return res.json()
}

// === Research Mode Types ===

export interface FullGameLogEntry {
  game_date: string      // "Feb 20"
  opponent: string       // "vs HOU" or "@ BOS"
  is_home: boolean
  min: number
  pts: number
  reb: number
  ast: number
  pra: number
  fg_pct: number
  fg3_pct: number
  ft_pct: number
  stl: number
  blk: number
  tov: number
  plus_minus: number
}

export interface StatSplits {
  games: number
  pts: number
  reb: number
  ast: number
  pra: number
  min: number
}

export interface RollingAverages {
  L3: StatSplits
  L5: StatSplits
  L10: StatSplits
  L15: StatSplits
  L20: StatSplits
}

export interface PlayerResearchData {
  player_name: string
  player_id: number
  team_abbrev?: string
  next_game?: GameInfo
  game_log: FullGameLogEntry[]
  season_averages: StatSplits
  rolling_averages: RollingAverages
  home_splits: StatSplits
  away_splits: StatSplits
  b2b_splits: StatSplits
  rest_splits: StatSplits
  vs_elite_def: StatSplits
  vs_weak_def: StatSplits
  opponent_context?: OpponentContext
  vs_stats?: VsStats
}

export async function getPlayerResearch(playerName: string): Promise<PlayerResearchData> {
  const res = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/research`)
  if (!res.ok) throw new Error(`Failed to fetch research data for ${playerName}`)
  return res.json()
}
