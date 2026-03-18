/**
 * Shared types for NBA Prop Evaluator API
 */

// === Player / Prediction Types ===

export interface PlayerInfo {
  player_id: number
  player_name: string
  team_id?: number
  team_abbrev?: string
  team_name?: string
  headshot_url?: string
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
  off_rating?: number
  net_rating?: number
  efg_pct?: number
  ts_pct?: number
  ast_pct?: number
  tov_pct?: number
  oreb_pct?: number
  dreb_pct?: number
}

export interface VsStats {
  games: number
  avg_pts: number
  avg_reb: number
  avg_ast: number
}

export interface GameLogEntry {
  game_date: string
  opponent: string
  min: number
  pts: number
  reb: number
  ast: number
}

export interface PredictionResult {
  player_name: string
  player_id: number
  headshot_url?: string
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

// === Pick Types ===

export interface Pick {
  id: number
  timestamp: string
  player: string
  player_id?: number
  headshot_url?: string
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

export interface CalibrationBucket {
  bucket: string
  predicted: number
  actual: number
  count: number
}

export interface BrierDecomposition {
  reliability: number
  resolution: number
  uncertainty: number
}

export interface StatBrier {
  brier_score: number
  skill_score: number
  sample_size: number
  win_rate: number
}

export interface CLVStats {
  avg_clv: number
  positive_clv_rate: number
  sample_size: number
}

export interface CalibrationStats {
  brier_score: number | null
  brier_skill_score: number | null
  calibration_curve: CalibrationBucket[]
  by_stat: Record<string, StatBrier>
  by_confidence: Record<string, { brier_score: number; sample_size: number; avg_pred_prob: number; actual_win_rate: number }>
  decomposition: BrierDecomposition | null
  clv: CLVStats | null
  sample_size: number
}

// === Home / Daily Picks Types ===

export interface BestBet {
  player: string
  player_id?: number
  headshot_url?: string
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
  line_is_real?: boolean
}

export interface DailyPick {
  id: number
  generated_date: string
  player: string
  player_id?: number
  headshot_url?: string
  team_abbrev?: string
  stat: string
  prediction: number
  confidence?: number
  range_low?: number
  range_high?: number
  recent_avg?: number
  odds_line?: number
  edge?: number
  direction: string
  opponent?: string
  is_home?: boolean
  matchup?: string
  game_date?: string
  model_type?: string
  prob_over?: number
  rank?: number
  created_at?: string
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

// === Research Types ===

export interface FullGameLogEntry {
  game_date: string
  opponent: string
  is_home: boolean
  min: number
  pts: number
  reb: number
  ast: number
  pra: number
  pr: number
  pa: number
  fg_pct: number
  fg3_pct: number
  ft_pct: number
  fg3m: number
  stl: number
  blk: number
  tov: number
  plus_minus: number
  result?: string
}

export interface StatSplits {
  games: number
  pts: number
  reb: number
  ast: number
  pra: number
  pr: number
  pa: number
  stl: number
  blk: number
  tov: number
  fg3m: number
  min: number
}

export interface StatAnalysis {
  std_dev: number
  consistency_score: number
  ceiling: number
  floor: number
  median: number
  over_streak: number
  under_streak: number
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
  win_splits?: StatSplits
  loss_splits?: StatSplits
  opponent_context?: OpponentContext
  vs_stats?: VsStats
  analysis?: Record<string, StatAnalysis>
}

export interface PlayerScenario {
  player_name: string
  player_id: number
  role: 'teammate' | 'opponent'
  with_splits: StatSplits
  without_splits: StatSplits
  currently_out: boolean
}

export interface ScenariosData {
  teammate_scenarios: PlayerScenario[]
  opponent_scenarios: PlayerScenario[]
}

// === Social / Leaderboard Types ===

export interface LeaderboardEntry {
  user_id: string
  username: string
  avatar_url: string | null
  total_graded: number
  total_won: number
  win_rate: number
  roi_units: number
}

export interface PublicProfile {
  user_id: string
  username: string
  avatar_url: string | null
  is_public: boolean
  total_graded: number
  total_won: number
  win_rate: number
  roi_units: number
  followers_count: number
  following_count: number
  is_following: boolean | null
}

export interface PublicPick {
  id: number
  player: string
  stat: string
  line: number
  prediction: number
  direction: string
  edge: number
  confidence: number | null
  opponent: string | null
  is_home: boolean | null
  actual_result: number | null
  won: boolean | null
  game_date: string | null
  model_type: string | null
}

export interface FollowInfo {
  following: Array<{ id: string; username: string; avatar_url: string | null }>
  followers: Array<{ id: string; username: string; avatar_url: string | null }>
}

export interface FeedPick {
  id: number
  username: string
  avatar_url: string | null
  player: string
  stat: string
  line: number
  prediction: number
  direction: string
  won: boolean | null
  game_date: string | null
  timestamp: string
}
