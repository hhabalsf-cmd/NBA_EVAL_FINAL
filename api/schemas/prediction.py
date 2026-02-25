"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# === Player Schemas ===

class PlayerInfo(BaseModel):
    player_id: int
    player_name: str
    team_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    team_name: Optional[str] = None


class PlayerSearchResult(BaseModel):
    players: List[PlayerInfo]


# === Prediction Schemas ===

class PredictionRequest(BaseModel):
    player_name: str = Field(..., description="Full player name")
    model_type: str = Field(default="gradient_boost", description="Model type: random_forest, gradient_boost, or neural")
    use_ensemble: bool = Field(default=False, description="Use ensemble of models")
    retrain: bool = Field(default=False, description="Force retrain even if model exists")


class StatPrediction(BaseModel):
    stat: str
    prediction: float
    confidence: float
    range_low: float
    range_high: float
    uncertainty_std: Optional[float] = None
    recent_avg: Optional[float] = None


class GameInfo(BaseModel):
    matchup: str
    game_date: str
    is_home: bool
    opponent: str
    opponent_name: str


class OpponentContext(BaseModel):
    def_rating: float
    pace: float
    def_rank: str
    pace_desc: str


class VsStats(BaseModel):
    games: int
    avg_pts: float
    avg_reb: float
    avg_ast: float


class GameLogEntry(BaseModel):
    game_date: str       # "Feb 20"
    opponent: str        # "vs HOU" or "@ BOS"
    min: float
    pts: float
    reb: float
    ast: float


class PredictionResponse(BaseModel):
    player_name: str
    player_id: int
    team_abbrev: Optional[str] = None
    predictions: Dict[str, StatPrediction]
    game_info: Optional[GameInfo] = None
    opponent_context: Optional[OpponentContext] = None
    vs_stats: Optional[VsStats] = None
    model_type: str
    games_trained_on: int
    game_log: Optional[List[GameLogEntry]] = None
    avg_min_l10: Optional[float] = None


# === Line Evaluation Schemas ===

class LineEvaluationRequest(BaseModel):
    player_name: str
    stat: str = Field(..., description="Stat type: PTS, REB, AST, or PRA")
    line: float = Field(..., description="The betting line to evaluate")
    prediction: Optional[float] = Field(None, description="Pre-computed prediction (if available)")


class LineEvaluation(BaseModel):
    stat: str
    line: float
    prediction: float
    difference: float
    diff_pct: float
    recommendation: str  # e.g., "STRONG OVER", "LEAN UNDER"
    strength: str  # "HIGH", "MODERATE", "SLIGHT"
    prob_over: Optional[float] = None
    confidence: Optional[float] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    high_edge_warning: bool = False  # True when |edge| > 50% — historically unreliable


# === Picks Schemas ===

class PickCreate(BaseModel):
    player: str
    player_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    stat: str
    line: float
    prediction: float
    direction: str  # "OVER" or "UNDER"
    edge: float
    confidence: Optional[float] = None
    opponent: Optional[str] = None
    is_home: Optional[bool] = None
    model_type: str = "unknown"
    game_date: Optional[str] = None
    prob_over: Optional[float] = None


class PickResponse(BaseModel):
    id: int
    timestamp: str
    player: str
    player_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    stat: str
    line: float
    prediction: float
    direction: str
    edge: float
    confidence: Optional[float] = None
    opponent: Optional[str] = None
    is_home: Optional[bool] = None
    actual_result: Optional[float] = None
    won: Optional[bool] = None
    model_type: Optional[str] = None
    game_date: Optional[str] = None
    voided: Optional[bool] = None
    void_reason: Optional[str] = None
    prob_over: Optional[float] = None


class PickGradeRequest(BaseModel):
    actual_result: float


class PerformanceByStatItem(BaseModel):
    total: int
    wins: int
    win_rate: float


class PerformanceByEdgeItem(BaseModel):
    total: int
    wins: int
    win_rate: float


class PerformanceStats(BaseModel):
    total_picks: int
    graded_picks: int
    wins: int
    losses: int
    pushes: int
    win_rate: float
    roi: float
    avg_edge_winners: float
    by_stat: Dict[str, PerformanceByStatItem]
    by_edge_range: Dict[str, PerformanceByEdgeItem]


class CumulativeProfitPoint(BaseModel):
    date: str
    profit: float
    cumulative_profit: float


# === Best Bets Schemas ===

class BestBet(BaseModel):
    player: str
    player_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    stat: str
    line: float
    prediction: float
    edge: float
    edge_pct: float
    direction: str
    recommendation: str
    prob_over: Optional[float] = None
    game_info: Optional[GameInfo] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    confidence: Optional[float] = None


class BestBetsResponse(BaseModel):
    bets: List[BestBet]
    generated_at: str
    games_count: int


# === SSE Progress Events ===

class ProgressEvent(BaseModel):
    stage: str  # fetching_data, training_model, predicting, complete
    progress: int  # 0-100
    message: str
    data: Optional[Any] = None


# === Game Prediction Schemas ===

class TeamInfoGame(BaseModel):
    team_id: int
    team_abbrev: str
    team_name: str
    record: str
    off_rating: float
    def_rating: float
    net_rating: float
    pace: float


class GameMatchup(BaseModel):
    home_team: TeamInfoGame
    away_team: TeamInfoGame
    game_date: str
    game_time: Optional[str] = None


class KeyFactor(BaseModel):
    factor: str
    impact: str  # MAJOR, MODERATE, MINOR
    description: str
    favors: str  # HOME or AWAY


class GamePrediction(BaseModel):
    matchup: GameMatchup
    predicted_winner: str
    home_win_prob: float
    away_win_prob: float
    confidence: float
    edge: Optional[float] = None
    bet_quality: Optional[str] = None
    calibrated: Optional[bool] = None
    key_factors: List[KeyFactor]
    prediction_id: Optional[int] = None


class TodaysGamesResponse(BaseModel):
    predictions: List[GamePrediction]
    generated_at: str
    games_count: int


class GamePredictionHistoryItem(BaseModel):
    id: int
    timestamp: str
    game_date: str
    home_team: str
    away_team: str
    predicted_winner: str
    home_win_prob: float
    away_win_prob: float
    confidence: Optional[float] = None
    actual_winner: Optional[str] = None
    correct: Optional[bool] = None
    key_factors: List[KeyFactor] = []


class ConfidenceRangeItem(BaseModel):
    total: int
    correct: int
    accuracy: float


class GameAccuracyStats(BaseModel):
    total_predictions: int
    graded_predictions: int
    correct: int
    incorrect: int
    accuracy: float
    by_confidence_range: Dict[str, ConfidenceRangeItem]
    recent_streak: str


# === Research Mode Schemas ===

class FullGameLogEntry(BaseModel):
    game_date: str       # e.g. "Feb 20"
    opponent: str        # e.g. "vs HOU" or "@ BOS"
    is_home: bool
    min: float
    pts: float
    reb: float
    ast: float
    pra: float           # pts + reb + ast
    fg_pct: float
    fg3_pct: float
    ft_pct: float
    stl: float
    blk: float
    tov: float
    plus_minus: float


class StatSplits(BaseModel):
    games: int
    pts: float
    reb: float
    ast: float
    pra: float
    min: float


class RollingAverages(BaseModel):
    L3: StatSplits
    L5: StatSplits
    L10: StatSplits
    L15: StatSplits
    L20: StatSplits


class PlayerResearchResponse(BaseModel):
    player_name: str
    player_id: int
    team_abbrev: Optional[str] = None
    next_game: Optional[GameInfo] = None
    game_log: List[FullGameLogEntry]
    season_averages: StatSplits
    rolling_averages: RollingAverages
    home_splits: StatSplits
    away_splits: StatSplits
    b2b_splits: StatSplits
    rest_splits: StatSplits
    vs_elite_def: StatSplits
    vs_weak_def: StatSplits
    opponent_context: Optional[OpponentContext] = None
    vs_stats: Optional[VsStats] = None
