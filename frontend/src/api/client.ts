/**
 * API client for NBA Prop Evaluator backend
 */

const API_BASE = '/api'

/** Throw a user-friendly error, with special handling for 429 rate limits. */
async function throwResponseError(response: Response, fallback: string): Promise<never> {
  if (response.status === 429) {
    const body = await response.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? 'Too many requests — please wait a moment and try again.')
  }
  const body = await response.json().catch(() => ({}))
  throw new Error((body as { detail?: string }).detail ?? fallback)
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

// ── Auth helpers ────────────────────────────────────────────

const TOKEN_KEY = 'nba_eval_token'

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(): HeadersInit {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Auth API functions ─────────────────────────────────────

export interface AuthUser {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
  avatar_url?: string
}

export interface AuthResponse {
  token: string
  user: AuthUser
}

export async function authRegister(
  email: string,
  username: string,
  password: string
): Promise<AuthResponse> {
  const r = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username, password }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Registration failed')
  }
  return r.json()
}

export async function authLogin(email: string, password: string): Promise<AuthResponse> {
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Invalid credentials')
  }
  return r.json()
}

export async function authGetMe(): Promise<AuthUser> {
  const r = await fetch(`${API_BASE}/auth/me`, {
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
  })
  if (!r.ok) throw new Error('Not authenticated')
  return r.json()
}

export async function authRefresh(): Promise<AuthResponse> {
  const r = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
  })
  if (!r.ok) throw new Error('Session expired — please log in again')
  const data: AuthResponse = await r.json()
  setAuthToken(data.token)
  return data
}
export async function uploadAvatar(file: File): Promise<AuthUser> {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${API_BASE}/auth/avatar`, {
    method: 'POST',
    headers: { ...authHeaders() },
    body: form,
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Upload failed')
  }
  return r.json()
}
export async function deleteAvatar(): Promise<AuthUser> {
  const r = await fetch(`${API_BASE}/auth/avatar`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Failed to remove avatar')
  }
  return r.json()
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const r = await fetch(`${API_BASE}/auth/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Failed to change password')
  }
}


// API Functions

export async function getPlayerOdds(playerName: string): Promise<PlayerOdds> {
  const response = await fetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/odds`)
  if (!response.ok) return { found: false }
  return response.json()
}

export async function searchPlayers(query: string): Promise<PlayerInfo[]> {
  const response = await fetch(`${API_BASE}/players/search?q=${encodeURIComponent(query)}`)
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
  const response = await fetch(`${API_BASE}/players/predict`, {
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
  const response = await fetch(`${API_BASE}/players/predict/sync`, {
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
  const response = await fetch(`${API_BASE}/players/evaluate-line`, {
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
  const response = await fetch(`${API_BASE}/bets/today?min_edge=${minEdge}&limit=${limit}`)
  if (!response.ok) throw new Error('Failed to fetch best bets')
  return response.json()
}

export async function getPicks(limit = 100, pendingOnly = false): Promise<Pick[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    pending_only: pendingOnly.toString(),
  })
  const response = await fetch(`${API_BASE}/picks?${params}`, {
    headers: { ...authHeaders() },
  })
  if (!response.ok) throw new Error('Failed to fetch picks')
  return response.json()
}

export async function createPick(pick: Omit<Pick, 'id' | 'timestamp' | 'actual_result' | 'won'>): Promise<Pick> {
  const response = await fetch(`${API_BASE}/picks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(pick),
  })

  if (!response.ok) throw new Error('Failed to create pick')
  return response.json()
}

export async function gradePick(pickId: number, actualResult: number): Promise<Pick> {
  const response = await fetch(`${API_BASE}/picks/${pickId}/grade`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ actual_result: actualResult }),
  })

  if (!response.ok) throw new Error('Failed to grade pick')
  return response.json()
}

export async function deletePick(pickId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/picks/${pickId}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  })

  if (!response.ok) throw new Error('Failed to delete pick')
}

export async function autoGradePicks(): Promise<{ graded_count: number; errors: string[]; results: unknown[] }> {
  const response = await fetch(`${API_BASE}/picks/auto-grade`, {
    method: 'POST',
    headers: { ...authHeaders() },
  })

  if (!response.ok) throw new Error('Failed to auto-grade picks')
  return response.json()
}

export async function getPerformanceStats(): Promise<PerformanceStats> {
  const response = await fetch(`${API_BASE}/picks/stats/performance`, {
    headers: { ...authHeaders() },
  })
  if (!response.ok) throw new Error('Failed to fetch performance stats')
  return response.json()
}

export async function getCumulativeProfit(): Promise<CumulativeProfitPoint[]> {
  const response = await fetch(`${API_BASE}/picks/stats/profit`, {
    headers: { ...authHeaders() },
  })
  if (!response.ok) throw new Error('Failed to fetch profit data')
  return response.json()
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
  const response = await fetch(`${API_BASE}/games/today`)
  if (!response.ok) await throwResponseError(response, 'Failed to fetch game predictions')
  return response.json()
}

export async function predictTodaysGames(
  onProgress: (event: ProgressEvent) => void
): Promise<GamePrediction[] | null> {
  const response = await fetch(`${API_BASE}/games/predict`, {
    method: 'POST',
  })

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

export async function getGamePredictionHistory(days = 7): Promise<GamePredictionHistoryItem[]> {
  const response = await fetch(`${API_BASE}/games/history?days=${days}`)
  if (!response.ok) throw new Error('Failed to fetch game history')
  return response.json()
}

export async function autoGradeGamePredictions(): Promise<{
  graded_count: number
  errors: string[]
  results: unknown[]
}> {
  const response = await fetch(`${API_BASE}/games/auto-grade`, {
    method: 'POST',
    headers: { ...authHeaders() },
  })
  if (!response.ok) throw new Error('Failed to auto-grade game predictions')
  return response.json()
}

export async function gradeGamePrediction(id: number, actualWinner: string): Promise<void> {
  const response = await fetch(`${API_BASE}/games/${id}/grade`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actual_winner: actualWinner }),
  })
  if (!response.ok) throw new Error('Failed to grade game prediction')
}

export async function getGameAccuracyStats(): Promise<GameAccuracyStats> {
  const response = await fetch(`${API_BASE}/games/stats/accuracy`)
  if (!response.ok) throw new Error('Failed to fetch game accuracy stats')
  return response.json()
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
  const res = await fetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/team-injuries`)
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
  const res = await fetch(`${API_BASE}/standings`)
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
  const res = await fetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/research`)
  if (!res.ok) throw new Error(`Failed to fetch research data for ${playerName}`)
  return res.json()
}
