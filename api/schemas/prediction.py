"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime


# === Player Schemas ===

class PlayerInfo(BaseModel):
    player_id: int
    player_name: str
    team_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    team_name: Optional[str] = None
    headshot_url: Optional[str] = None


class PlayerSearchResult(BaseModel):
    players: List[PlayerInfo]


# === Prediction Schemas ===

class PredictionRequest(BaseModel):
    player_name: str = Field(..., min_length=2, max_length=100, description="Full player name")
    model_type: Literal["random_forest", "gradient_boost", "neural"] = Field(
        default="gradient_boost", description="Model type"
    )
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
    off_rating: Optional[float] = None
    net_rating: Optional[float] = None
    efg_pct: Optional[float] = None
    ts_pct: Optional[float] = None
    ast_pct: Optional[float] = None
    tov_pct: Optional[float] = None
    oreb_pct: Optional[float] = None
    dreb_pct: Optional[float] = None


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
    headshot_url: Optional[str] = None
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
    player_name: str = Field(..., min_length=2, max_length=100)
    stat: Literal["PTS", "REB", "AST", "PRA"] = Field(..., description="Stat type: PTS, REB, AST, or PRA")
    line: float = Field(..., ge=0, le=200, description="The betting line to evaluate")
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
    player: str = Field(..., min_length=2, max_length=100)
    player_id: Optional[int] = None
    headshot_url: Optional[str] = None
    team_abbrev: Optional[str] = Field(None, max_length=5)
    stat: Literal["PTS", "REB", "AST", "PRA"]
    line: float = Field(..., ge=0, le=200)
    prediction: float = Field(..., ge=0, le=200)
    direction: Literal["OVER", "UNDER"]
    edge: float = Field(..., ge=-100, le=100)
    confidence: Optional[float] = Field(None, ge=0, le=100)
    opponent: Optional[str] = Field(None, max_length=5)
    is_home: Optional[bool] = None
    model_type: str = Field(default="unknown", max_length=50)
    game_date: Optional[str] = Field(None, max_length=20)
    prob_over: Optional[float] = Field(None, ge=0, le=100)
    opening_line: Optional[float] = Field(None, ge=0, le=200, description="Line at time of pick (defaults to line)")
    closing_line: Optional[float] = Field(None, ge=0, le=200, description="Line at game start")


class PickResponse(BaseModel):
    id: int
    timestamp: str
    player: str
    player_id: Optional[int] = None
    headshot_url: Optional[str] = None
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
    opening_line: Optional[float] = None
    closing_line: Optional[float] = None


class PickGradeRequest(BaseModel):
    actual_result: float = Field(..., ge=0, le=250, description="Actual stat result (0–250)")


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


# === Calibration / Brier Score Schemas ===

class CalibrationBucket(BaseModel):
    bucket: str           # e.g. "60-65%"
    predicted: float      # avg predicted probability in bucket (0-100)
    actual: float         # actual win rate in bucket (0-100)
    count: int            # number of picks in bucket


class BrierDecomposition(BaseModel):
    reliability: float    # calibration error (lower = better)
    resolution: float     # discrimination power (higher = better)
    uncertainty: float    # irreducible (base rate variance)


class StatBrier(BaseModel):
    brier_score: float
    skill_score: float
    sample_size: int
    win_rate: float


class ConfidenceBucketBrier(BaseModel):
    brier_score: float
    sample_size: int
    avg_pred_prob: float
    actual_win_rate: float


class CLVStats(BaseModel):
    avg_clv: float              # average closing line value (positive = beating the market)
    positive_clv_rate: float    # % of picks with positive CLV
    sample_size: int


class CalibrationStats(BaseModel):
    brier_score: Optional[float] = None
    brier_skill_score: Optional[float] = None
    calibration_curve: List[CalibrationBucket] = []
    by_stat: Dict[str, StatBrier] = {}
    by_confidence: Dict[str, ConfidenceBucketBrier] = {}
    decomposition: Optional[BrierDecomposition] = None
    clv: Optional[CLVStats] = None
    sample_size: int = 0


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


# === Daily Picks Schemas ===

class DailyPick(BaseModel):
    id: int
    generated_date: str
    player: str
    player_id: Optional[int] = None
    headshot_url: Optional[str] = None
    team_abbrev: Optional[str] = None
    stat: str
    prediction: float
    confidence: Optional[float] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    recent_avg: Optional[float] = None     # L10 avg (proxy line)
    odds_line: Optional[float] = None      # NULL until new OddsAPI key
    edge: Optional[float] = None
    direction: str
    opponent: Optional[str] = None
    is_home: Optional[bool] = None
    matchup: Optional[str] = None
    game_date: Optional[str] = None
    model_type: Optional[str] = None
    prob_over: Optional[float] = None
    rank: Optional[int] = None
    created_at: Optional[datetime] = None


class DailyPicksResponse(BaseModel):
    picks: List[DailyPick]
    generated_at: str
    date: str


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
    pr: float = 0.0      # pts + reb
    pa: float = 0.0      # pts + ast
    fg_pct: float
    fg3_pct: float
    ft_pct: float
    fg3m: float = 0.0    # 3-pointers made
    stl: float
    blk: float
    tov: float
    plus_minus: float
    result: Optional[str] = None  # "W" or "L"


class StatSplits(BaseModel):
    games: int
    pts: float
    reb: float
    ast: float
    pra: float
    pr: float = 0.0
    pa: float = 0.0
    stl: float = 0.0
    blk: float = 0.0
    tov: float = 0.0
    fg3m: float = 0.0
    min: float


class RollingAverages(BaseModel):
    L3: StatSplits
    L5: StatSplits
    L10: StatSplits
    L15: StatSplits
    L20: StatSplits


class StatAnalysis(BaseModel):
    """Per-stat deviation and consistency metrics."""
    std_dev: float
    consistency_score: float   # 100 - (CV * 100), higher = more consistent
    ceiling: float             # max in sample
    floor: float               # min in sample
    median: float
    over_streak: int = 0       # consecutive games >= season avg
    under_streak: int = 0      # consecutive games < season avg


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
    win_splits: Optional[StatSplits] = None
    loss_splits: Optional[StatSplits] = None
    opponent_context: Optional[OpponentContext] = None
    vs_stats: Optional[VsStats] = None
    analysis: Optional[Dict[str, StatAnalysis]] = None  # keyed by stat name


# === Scenarios Schemas ===

class PlayerScenario(BaseModel):
    """A teammate or opponent with 'with/without' stat splits."""
    player_name: str
    player_id: int
    role: str  # "teammate" or "opponent"
    with_splits: StatSplits
    without_splits: StatSplits
    currently_out: bool = False


class ScenariosResponse(BaseModel):
    teammate_scenarios: List[PlayerScenario]
    opponent_scenarios: List[PlayerScenario]


# === Parlay Schemas ===

class ParlayLegDetail(BaseModel):
    id: int
    pick_id: int
    player: str
    player_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    stat: str
    line: float
    prediction: float
    direction: str
    edge: float
    prob_over: Optional[float] = None
    actual_result: Optional[float] = None
    won: Optional[bool] = None
    voided: Optional[bool] = None
    void_reason: Optional[str] = None
    game_date: Optional[str] = None
    opponent: Optional[str] = None


class ParlayResponse(BaseModel):
    id: int
    legs_count: int
    status: str  # 'pending' | 'won' | 'lost' | 'voided'
    graded_at: Optional[datetime] = None
    created_at: datetime
    legs: List[ParlayLegDetail] = []


class ParlayCreate(BaseModel):
    pick_ids: List[int] = Field(..., min_length=2, max_length=6)


# ── Manual line entry (fallback line source) ─────────────────────────


class ManualLineCreate(BaseModel):
    """One manually entered betting line."""
    player: str = Field(..., min_length=2, max_length=100)
    stat: Literal['PTS', 'REB', 'AST', 'PRA']
    line: float = Field(..., gt=0, lt=200)
    home_team: Optional[str] = Field(default=None, max_length=3)
    away_team: Optional[str] = Field(default=None, max_length=3)


class ManualLinesUpsert(BaseModel):
    """Batch upsert of manual lines for a date (defaults to today)."""
    lines: List[ManualLineCreate] = Field(..., min_length=1, max_length=200)
    game_date: Optional[str] = Field(
        default=None, pattern=r'^\d{4}-\d{2}-\d{2}$',
        description="YYYY-MM-DD; defaults to today",
    )


class ManualLine(BaseModel):
    id: int
    game_date: str
    player: str
    stat: str
    line: float
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    created_at: Optional[datetime] = None


class ManualLinesResponse(BaseModel):
    lines: List[ManualLine]
    date: str
