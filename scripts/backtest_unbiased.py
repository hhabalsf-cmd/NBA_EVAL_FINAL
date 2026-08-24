"""Unbiased walk-forward backtest of the per-player NBA prop model.

Extends ``scripts/eval_holdout.py`` in four ways:

1. ~50 curated high-minute players spanning guards / wings / bigs.
2. All four served stats — PTS, REB, AST **and PRA** (evaluated as the
   reconciled 0.85/0.15 blend from ``pra_utils.reconcile_pra``, compared
   against the actual PTS+REB+AST).
3. Probability calibration measured through the production
   ``ProbabilityCalculator.calculate`` path against pseudo-lines
   (prediction +/- 0.5/1.5/2.5 and the player's season-to-date median,
   the latter computed only from games *before* the row being predicted).
4. Players are evaluated in a process pool (game logs are fetched
   serially first so stats.nba.com is still hit politely).

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/backtest_unbiased.py --train-games 60
    NBA_EVAL_DISABLE_TF=1 python3 scripts/backtest_unbiased.py --limit 10 --quick
    NBA_EVAL_DISABLE_TF=1 python3 scripts/backtest_unbiased.py --players "LeBron James,Nikola Jokic"
"""
from __future__ import annotations

import argparse
import contextlib
import io
import math
import os
import statistics
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

warnings.filterwarnings("ignore")  # nba_api emits urllib3 warnings on macOS LibreSSL

# Keep BLAS single-threaded — we parallelize across players, not inside sklearn.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
os.environ.setdefault("NBA_EVAL_DISABLE_TF", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ modules
sys.modules.setdefault("tensorflow", None)  # type: ignore[arg-type]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import nba_evaluator as ev  # noqa: E402
from season_utils import get_current_season  # noqa: E402
from team_stats_asof import TeamStatsProvider  # noqa: E402

EVAL_STATS: Tuple[str, ...] = ("PTS", "REB", "AST", "PRA")
COMPONENTS: Tuple[str, ...] = ("PTS", "REB", "AST")
PSEUDO_LINE_OFFSETS: Tuple[float, ...] = (0.5, 1.5, 2.5)
DECILE_LABELS: Tuple[str, ...] = tuple(f"{d}-{d + 10}%" for d in range(0, 100, 10))

# 58 high-minute players spanning positions (18 guards / 22 wings-forwards /
# 18 bigs). Starts from eval_holdout's DEFAULT_PLAYERS and extends outward;
# the chronically-injured 2024-25 names (Embiid, Davis, Mitchell, Fox, Durant,
# Butler, Doncic, Lillard) are deliberately omitted because they cannot clear
# train_games + 5 played games at the default --train-games 60.
DEFAULT_PLAYERS: Tuple[Tuple[str, str], ...] = (
    # ── Guards ────────────────────────────────────────────────────────────
    ("Stephen Curry", "201939"),
    ("Trae Young", "1629027"),
    ("Jalen Brunson", "1628973"),
    ("Tyrese Haliburton", "1630169"),
    ("Shai Gilgeous-Alexander", "1628983"),
    ("Anthony Edwards", "1630162"),
    ("Darius Garland", "1629636"),
    ("Tyrese Maxey", "1630178"),
    ("Cade Cunningham", "1630595"),
    ("Devin Booker", "1626164"),
    ("Derrick White", "1628401"),
    ("Coby White", "1629632"),
    ("Jalen Green", "1630224"),
    ("Austin Reaves", "1630559"),
    ("Immanuel Quickley", "1630193"),
    ("Norman Powell", "1626181"),
    ("Anfernee Simons", "1629014"),
    ("Collin Sexton", "1629012"),
    # ── Wings / forwards ──────────────────────────────────────────────────
    ("LeBron James", "2544"),
    ("Jayson Tatum", "1628369"),
    ("Pascal Siakam", "1627783"),
    ("Paolo Banchero", "1631094"),
    ("Franz Wagner", "1630532"),
    ("Scottie Barnes", "1630567"),
    ("DeMar DeRozan", "201942"),
    ("Mikal Bridges", "1628969"),
    ("OG Anunoby", "1628384"),
    ("RJ Barrett", "1629628"),
    ("Jalen Williams", "1631114"),
    ("Lauri Markkanen", "1628374"),
    ("Julius Randle", "203944"),
    ("Michael Porter Jr.", "1629008"),
    ("Jaden McDaniels", "1630183"),
    ("Kyle Kuzma", "1628398"),
    ("Jerami Grant", "203924"),
    ("Deni Avdija", "1630166"),
    ("Amen Thompson", "1641708"),
    ("Josh Hart", "1628404"),
    ("Aaron Gordon", "203932"),
    ("Cameron Johnson", "1629661"),
    # ── Bigs ──────────────────────────────────────────────────────────────
    ("Nikola Jokic", "203999"),
    ("Giannis Antetokounmpo", "203507"),
    ("Karl-Anthony Towns", "1626157"),
    ("Domantas Sabonis", "1627734"),
    ("Bam Adebayo", "1628389"),
    ("Alperen Sengun", "1630578"),
    ("Evan Mobley", "1630596"),
    ("Jarrett Allen", "1628386"),
    ("Rudy Gobert", "203497"),
    ("Myles Turner", "1626167"),
    ("Nikola Vucevic", "202696"),
    ("Jalen Duren", "1631105"),
    ("Ivica Zubac", "1627826"),
    ("Naz Reid", "1629675"),
    ("Daniel Gafford", "1629655"),
    ("Isaiah Hartenstein", "1628392"),
    ("Onyeka Okongwu", "1630168"),
    ("Walker Kessler", "1631117"),
)


# ── Result containers ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibSample:
    """One (prediction, pseudo-line) probability observation."""

    stat: str
    line_kind: str          # "offset" or "median"
    prob: float             # 0-100, straight from ProbabilityCalculator
    outcome: int            # 1 if actual > line


@dataclass(frozen=True)
class StatResult:
    """Held-out metrics for one (player, stat) pair."""

    stat: str
    n_test: int
    sum_abs: float
    sum_err: float
    sum_sq: float
    train_mae: Optional[float] = None
    train_bias: Optional[float] = None
    train_coverage_80: Optional[float] = None
    cov_raw: Optional[float] = None
    cov_cqr: Optional[float] = None
    cqr_correction: Optional[float] = None

    @property
    def mae(self) -> float:
        return self.sum_abs / self.n_test

    @property
    def bias(self) -> float:
        return self.sum_err / self.n_test

    @property
    def rmse(self) -> float:
        return math.sqrt(self.sum_sq / self.n_test)

    @property
    def gap(self) -> Optional[float]:
        return None if self.train_mae is None else self.mae - self.train_mae


@dataclass(frozen=True)
class PlayerResult:
    name: str
    player_id: str
    n_total: int
    n_train: int
    n_test: int
    stats: Tuple[StatResult, ...] = ()
    samples: Tuple[CalibSample, ...] = ()
    skipped: bool = False
    reason: Optional[str] = None
    seconds: float = 0.0
    # How many of MLPredictor.FEATURE_COLS create_features actually produced.
    # 69 without opponent context, 81 with it — see Gate 0 in the Phase 0 plan.
    n_features_built: Optional[int] = None


@dataclass
class Aggregate:
    """Pooled + per-player-mean metrics for one stat."""

    stat: str
    players: int = 0
    n_test: int = 0
    sum_abs: float = 0.0
    sum_err: float = 0.0
    sum_sq: float = 0.0
    train_mae: List[float] = field(default_factory=list)
    train_bias: List[float] = field(default_factory=list)
    train_cov: List[float] = field(default_factory=list)
    cov_raw: List[float] = field(default_factory=list)
    cov_cqr: List[float] = field(default_factory=list)
    cqr_corr: List[float] = field(default_factory=list)
    gaps: List[float] = field(default_factory=list)


# ── Data fetch ────────────────────────────────────────────────────────────────


LOG_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache" / "backtest_logs"


def log_cache_path(player_id: str, season: str) -> Path:
    """Cache location for one player-season game log.

    Contract (shared with ``scripts/_prewarm_backtest_cache.py``):
    ``cache/backtest_logs/{season}/{player_id}.parquet`` holding exactly what a
    live fetch returns -- ``GAME_DATE`` as a ``'YYYY-MM-DD'`` string, rows
    sorted ascending by date, written with ``index=False``.
    """
    return LOG_CACHE_ROOT / season / "{}.parquet".format(player_id)


def normalize_player_log(df: pd.DataFrame) -> pd.DataFrame:
    """Sort ascending by date and render ``GAME_DATE`` as a plain date string."""
    if df is None or df.empty:
        return df
    df = df.copy()
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], format="mixed")
    df = df.sort_values("GAME_DATE", ascending=True).reset_index(drop=True)
    df["GAME_DATE"] = df["GAME_DATE"].dt.strftime("%Y-%m-%d")
    return df


def write_log_cache(df: pd.DataFrame, path: Path) -> None:
    """Atomic write -- a killed run never leaves a half-written parquet behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def fetch_player_log(
    player_id: str,
    season: str,
    sleep_s: float = 0.6,
    use_cache: bool = True,
    refresh_cache: bool = False,
) -> pd.DataFrame:
    """One player's regular-season game log, sorted ascending by date.

    stats.nba.com stays the source of truth; the parquet cache only ever holds
    what a live fetch returned, so cached and cold runs are byte-comparable and
    the numbers stay comparable with earlier reports. The cache is written per
    player immediately after each fetch, which is what makes a cold run
    resumable: a crash at player 57 keeps the first 56.

    Args:
        use_cache: read from / write to ``cache/backtest_logs``.
        refresh_cache: ignore any cached copy and rewrite it from a live fetch.
    """
    path = log_cache_path(player_id, season)
    if use_cache and not refresh_cache and path.exists():
        try:
            return pd.read_parquet(path)
        except Exception as exc:  # corrupt/truncated cache -> fall through
            warnings.warn(
                "unreadable game-log cache {} ({}); re-fetching".format(path, exc)
            )

    from nba_api.stats.endpoints import playergamelog

    df = playergamelog.PlayerGameLog(
        player_id=str(player_id), season=season
    ).get_data_frames()[0]
    time.sleep(sleep_s)  # be polite to stats.nba.com

    df = normalize_player_log(df)
    if use_cache:
        write_log_cache(df, path)
    return df


# ── Prediction-path helpers ───────────────────────────────────────────────────


def schedule_game_info(row: pd.Series, team: str) -> Dict[str, object]:
    """A ``get_player_next_game``-shaped dict for one scheduled game.

    Everything here is published months in advance — who plays whom, where, and
    on what date. The row's realized box score is never touched, which is what
    makes this replay lookahead-free even though the row itself is the game
    being predicted.
    """
    matchup = str(row["MATCHUP"])
    is_home = 1 if "vs." in matchup else 0
    return {
        "matchup": matchup,
        "game_date": pd.to_datetime(row["GAME_DATE"]),
        "is_home": is_home,
        "opponent": matchup.split(" ")[-1],
        "team": team,
    }


def history_vs_stats(history: pd.DataFrame, opponent: str) -> Optional[Dict[str, float]]:
    """Head-to-head stats scoped to ``history`` only.

    Production calls ``NBADataScraper.get_vs_team_stats``, which re-reads the
    player's FULL multi-season log — in a walk-forward replay that would pull
    the rest of the season into every step. Same return shape, strictly
    backward-looking source.
    """
    if history is None or history.empty or not opponent:
        return None
    vs = history[history["MATCHUP"].astype(str).str.contains(opponent, na=False)]
    if vs.empty:
        return None
    return {
        "games": int(len(vs)),
        "avg_pts": float(vs["PTS"].mean()),
        "avg_reb": float(vs["REB"].mean()),
        "avg_ast": float(vs["AST"].mean()),
    }


def _row_float(row: pd.Series, key: str, default: float) -> float:
    value = row.get(key, default)
    return default if pd.isna(value) else float(value)


def game_context(serve_frame: pd.DataFrame) -> Dict[str, object]:
    """Schedule context for the upcoming game, read off the synthetic row.

    create_features derives every one of these from the MATCHUP and GAME_DATE
    alone -- published months in advance -- so none of it is lookahead. Days of
    rest comes from the row's own DAYS_REST rather than production's
    ``datetime.now()`` formula, which in a replay would measure the gap to
    today instead of the gap to the game.

    Production sources these from ``get_player_next_game`` plus its own
    schedule_ctx block, so they are correct in BOTH serve modes -- which is
    what makes the stale/fresh comparison isolate feature staleness alone.
    """
    latest = serve_frame.iloc[-1]
    return {
        "is_home": int(_row_float(latest, "IS_HOME", 0)),
        "opponent": str(latest["OPPONENT"]),
        "days_rest": ev.FeatureEngineer.serve_days_rest(serve_frame),
        "games_in_last_7": int(_row_float(latest, "GAMES_IN_LAST_7", 2)),
        "games_in_last_4": int(_row_float(latest, "GAMES_IN_LAST_4", 1)),
        "travel_miles": _row_float(latest, "TRAVEL_MILES", 0.0),
        "timezone_shift": int(_row_float(latest, "TIMEZONE_SHIFT", 0)),
        "is_altitude": int(_row_float(latest, "IS_ALTITUDE", 0)),
    }


def serve_features(
    frame: pd.DataFrame,
    game_ctx: Dict[str, object],
    team_stats: Dict[str, Dict[str, float]],
    history: pd.DataFrame,
) -> pd.DataFrame:
    """Production's served feature vector, via ``get_prediction_features``.

    ``frame`` ending in the synthetic next-game row is the post-Phase-1 serve
    path. ``frame`` ending in the last COMPLETED game (pass ``frame.iloc[:-1]``)
    reproduces the pre-Phase-1 one exactly, which is what ``--stale-serve``
    measures: create_features on the history alone is bit-identical to the
    synthetic-row frame minus its last row, so the two modes differ in nothing
    but which row ``get_prediction_features`` reads.

    ``injuries_team`` / ``injuries_opp`` and the three ``vegas_*`` inputs used
    to be listed here as "not derivable, left at their defaults". They are gone:
    all five fed features that ``create_features`` never built, so no model was
    ever trained on them, and Phase 2 removed them from ``FEATURE_COLS``, from
    ``get_prediction_features`` and from its signature (2026-08-22).
    """
    opponent = str(game_ctx["opponent"])
    opp_ctx = ev.FeatureEngineer.extract_opp_stats(team_stats, opponent)
    return ev.FeatureEngineer.get_prediction_features(
        frame,
        vs_stats=history_vs_stats(history, opponent),
        player_info={"team_abbrev": str(history.iloc[-1]["PLAYER_TEAM"])}
        if len(history) else None,
        **game_ctx,
        **opp_ctx,
    )


def actual_value(row: pd.DataFrame, stat: str) -> Optional[float]:
    """Realized value for ``stat``; PRA is the component sum."""
    cols = COMPONENTS if stat == "PRA" else (stat,)
    if not all(c in row.columns for c in cols):
        return None
    total = 0.0
    for c in cols:
        v = row[c].values[0]
        if pd.isna(v):
            return None
        total += float(v)
    return total


def raw_quantiles(
    predictor: "ev.MLPredictor", stat: str, pred_row: pd.DataFrame
) -> Tuple[float, float]:
    """Uncorrected (q10, q90) for ``stat``, or (nan, nan) when unavailable."""
    lo = predictor.quantile_models.get(stat + "_q10")
    hi = predictor.quantile_models.get(stat + "_q90")
    if lo is None or hi is None:
        return float("nan"), float("nan")
    try:
        x = np.array(
            [
                pred_row[f].values[0] if f in pred_row.columns else 0
                for f in predictor.feature_names
            ]
        ).reshape(1, -1)
        x = predictor.scalers["features"].transform(x)
        if predictor.selected_features and stat in predictor.selected_features:
            expected = getattr(lo, "n_features_in_", x.shape[1])
            sel = predictor.selected_features[stat]
            if len(sel) == expected:
                x = x[:, sel]
        return float(lo.predict(x)[0]), float(hi.predict(x)[0])
    except Exception:
        return float("nan"), float("nan")


def history_series(history: pd.DataFrame, stat: str) -> Optional[pd.Series]:
    """Series of realized values for ``stat`` over the pre-current-row history."""
    if stat == "PRA":
        if not all(c in history.columns for c in COMPONENTS):
            return None
        return history["PTS"] + history["REB"] + history["AST"]
    return history[stat] if stat in history.columns else None


def pseudo_lines(prediction: float, median: Optional[float]) -> List[Tuple[str, float]]:
    """Pseudo-lines around the prediction plus the season-to-date median."""
    lines: List[Tuple[str, float]] = []
    for off in PSEUDO_LINE_OFFSETS:
        lines.append(("offset", prediction - off))
        lines.append(("offset", prediction + off))
    if median is not None and not math.isnan(median):
        lines.append(("median", float(median)))
    return lines


# ── Lookahead probe ───────────────────────────────────────────────────────────


# Never spiked: schedule facts (published months ahead) and identity columns.
_SCHEDULE_COLS = frozenset({
    "MATCHUP", "GAME_DATE", "SEASON", "SEASON_ID", "WL",
    "Game_ID", "GAME_ID", "Player_ID", "PLAYER_ID", "PLAYER_NAME",
})


def lookahead_probe(log, played, step, as_of, build_serve, served,
                    stale_serve=False) -> Optional[str]:
    """Re-run one serve step with the future rewritten, and demand no change.

    Every realized number from the game being predicted **and every game after
    it** is replaced with an absurd value, then the served vector is rebuilt. If
    a single feature moves, something downstream of the split boundary reached
    the prediction. Schedule columns are left alone: who plays whom, where and
    when is published months in advance and is legitimately known pre-tip.

    Returns a description of the first contaminated feature, or None.
    """
    target_label = played[step]
    spiked = log.copy()
    future = spiked.index >= target_label
    for col in spiked.columns:
        if col in _SCHEDULE_COLS or not pd.api.types.is_numeric_dtype(spiked[col]):
            continue
        spiked.loc[future, col] = 999.0

    frame, stats = build_serve(
        spiked.loc[played[:step]], spiked.loc[target_label], as_of
    )
    history = frame.iloc[:-1]
    if not ev.has_upcoming_row(frame):
        return "serve frame lost its synthetic next-game row"
    if len(history) != step:
        return "history is {} rows, expected {}".format(len(history), step)
    hist_max = pd.to_datetime(history["GAME_DATE"]).max()
    target_date = pd.to_datetime(frame["GAME_DATE"].iloc[-1])
    if not hist_max < target_date:
        return "history reaches {} but the target game is {}".format(
            hist_max, target_date)
    for stat in COMPONENTS:
        if stat in frame.columns and pd.notna(frame[stat].iloc[-1]):
            return "{} is realized on the synthetic row".format(stat)

    # game_context always comes from the synthetic row -- in stale mode only the
    # frame `get_prediction_features` reads `latest` from is rolled back.
    ctx = game_context(frame)
    probe_served = serve_features(
        frame.iloc[:-1] if stale_serve else frame, ctx, stats, history
    )
    for col in served.columns:
        if col not in probe_served.columns:
            return "{} vanished when the future was rewritten".format(col)
        a = float(served[col].iloc[0])
        b = float(probe_served[col].iloc[0])
        if not np.isclose(a, b, equal_nan=True):
            return "{} moved {} -> {} when the future was rewritten".format(col, a, b)
    return None


# ── Per-player walk-forward ───────────────────────────────────────────────────


def built_feature_count(frame: pd.DataFrame) -> int:
    """How many declared ``FEATURE_COLS`` this frame actually carries.

    Anything absent is silently substituted with 0 by ``predict`` (see
    nba_evaluator.py:3266-3270), so this number *is* the width of the model
    under test. Without opponent context it is 69; with it, 81.
    """
    return sum(1 for c in ev.MLPredictor.FEATURE_COLS if c in frame.columns)


def evaluate_player(
    name: str,
    player_id: str,
    log: pd.DataFrame,
    train_games: int,
    quick: bool,
    season: str = "2024-25",
    team_provider: Optional[TeamStatsProvider] = None,
    assert_no_lookahead: bool = True,
    stale_serve: bool = False,
) -> PlayerResult:
    """Train on the first ``train_games`` rows, walk forward through the rest.

    Opponent context is **point-in-time**: the feature frame is rebuilt at each
    replay step with ``team_stats`` aggregated only from team-games played
    strictly before that step's date. The training frame is built once, as of
    the first held-out game — i.e. from everything knowable at the moment of
    the fit, and nothing from the held-out period.

    Each replay step goes through **production's serve path**: the raw log is
    truncated to games played strictly before the test game, a synthetic row for
    the test game is appended from its schedule facts alone (matchup + date),
    features are rebuilt on that, and ``get_prediction_features`` produces the
    vector handed to ``predict``. Nothing of the test game's box score is read
    until the prediction has been made; ``--assert-no-lookahead`` proves it per
    player by re-running the first step against a spiked box score and requiring
    a bit-identical served vector.
    """
    started = time.time()
    if log is None or len(log) < train_games + 5:
        n = 0 if log is None else len(log)
        return PlayerResult(
            name, player_id, n, 0, 0, skipped=True,
            reason="only {} games available (need >= {})".format(n, train_games + 5),
        )
    # probe.index is used below to map feature rows back to raw log rows.
    log = log.reset_index(drop=True)

    if team_provider is None:
        try:
            # allow_fetch=False: worker processes must never fan out N identical
            # requests at stats.nba.com. main() warms the cache first.
            team_provider = TeamStatsProvider(season, allow_fetch=False)
        except Exception as exc:
            return PlayerResult(
                name, player_id, len(log), 0, 0, skipped=True,
                reason="team context unavailable: {}".format(exc),
            )

    def build(as_of) -> pd.DataFrame:
        return ev.FeatureEngineer.create_features(
            log, team_stats=team_provider.as_of(as_of)
        )

    def build_serve(history_log: pd.DataFrame, target_row: pd.Series, as_of):
        """(feature frame ending in the synthetic next-game row, team_stats).

        ``history_log`` holds only games played strictly before the target, so
        every rolling window is causal by construction rather than by relying on
        ``.shift(1)`` alone.
        """
        team = str(target_row["MATCHUP"]).split(" ")[0]
        stats = team_provider.as_of(as_of)
        frame = ev.FeatureEngineer.create_features(
            history_log,
            game_info=schedule_game_info(target_row, team),
            team_stats=stats,
        )
        return frame, stats

    # The DNP filter and row ordering inside create_features do not depend on
    # team_stats, so one cheap probe frame fixes the split boundary and the
    # per-step as-of dates for every later rebuild.
    try:
        probe = build(log["GAME_DATE"].iloc[-1])
    except Exception as exc:
        return PlayerResult(
            name, player_id, len(log), 0, 0, skipped=True,
            reason="create_features failed: {}".format(exc),
        )

    if probe.empty or len(probe) < train_games + 5:
        return PlayerResult(
            name, player_id, len(log), 0, 0, skipped=True,
            reason="create_features yielded {} rows after DNP filter".format(len(probe)),
        )

    row_dates = list(probe["GAME_DATE"])
    # Positional labels into `log` of the games that survived the DNP filter.
    # create_features preserves the caller's index, so these map feature rows
    # back to raw log rows one-for-one.
    played = list(probe.index)

    # Training frame: everything knowable the morning of the first held-out
    # game. Later team-games are excluded, so nothing from the test period
    # reaches the fit.
    features_df = build(row_dates[train_games])
    # Narrowest frame the model actually sees. An as-of snapshot with no teams
    # in it is falsy, which would make create_features skip the whole opponent
    # block and silently drop back to 69 features — so track the minimum rather
    # than trusting one probe.
    n_built = built_feature_count(features_df)
    if len(features_df) != len(probe):
        return PlayerResult(
            name, player_id, len(log), 0, 0, skipped=True,
            reason="feature frame length changed with team_stats ({} vs {})".format(
                len(features_df), len(probe)),
        )

    train_df = features_df.iloc[:train_games].copy()
    test_df = features_df.iloc[train_games:]

    predictor = ev.MLPredictor(model_type="gradient_boost", use_ensemble=not quick)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ok = predictor.train(train_df, stats=list(COMPONENTS))
    except Exception as exc:
        return PlayerResult(
            name, player_id, len(log), train_games, len(test_df), skipped=True,
            reason="train failed: {}".format(exc),
        )
    if not ok:
        return PlayerResult(
            name, player_id, len(log), train_games, len(test_df), skipped=True,
            reason="train returned False",
        )

    cqr = {
        s: float(predictor.probability_calibrator.get(s, {}).get("cqr_correction", 0.0))
        for s in EVAL_STATS
    }
    sums = {s: [0, 0.0, 0.0, 0.0] for s in EVAL_STATS}      # n, |e|, e, e^2
    band = {s: [0, 0, 0] for s in EVAL_STATS}               # n, in_raw, in_cqr
    samples: List[CalibSample] = []

    for i in range(len(test_df)):
        step = train_games + i
        target_label = played[step]
        target_raw = log.loc[target_label]
        history_log = log.loc[played[:step]]

        # Rebuild with opponent context as of THIS game's date. A season
        # aggregate here would leak the rest of the season into every row.
        try:
            step_frame, step_team_stats = build_serve(
                history_log, target_raw, row_dates[step]
            )
        except Exception:
            continue
        if len(step_frame) != step + 1:
            continue
        n_built = min(n_built, built_feature_count(step_frame))

        history = step_frame.iloc[:-1]
        if not ev.has_upcoming_row(step_frame) or len(history) != step:
            continue

        try:
            ctx = game_context(step_frame)
            # --stale-serve rolls the frame back to the last COMPLETED game,
            # reproducing the pre-Phase-1 production serve path exactly. The
            # schedule context above is unchanged, so the two runs differ in
            # nothing but the staleness of the `latest`-derived features.
            pred_row = serve_features(
                step_frame.iloc[:-1] if stale_serve else step_frame,
                ctx, step_team_stats, history,
            )
        except Exception:
            continue

        if assert_no_lookahead and i == 0:
            problem = lookahead_probe(
                log, played, step, row_dates[step], build_serve, pred_row,
                stale_serve=stale_serve,
            )
            if problem:
                return PlayerResult(
                    name, player_id, len(log), train_games, len(test_df),
                    skipped=True, reason="LOOKAHEAD: {}".format(problem),
                )

        row = probe.iloc[[step]]
        # Stamping the current season neutralizes the early-season damping,
        # which would otherwise fire on every row (a 2024-25 log has zero games
        # in the *calendar* current season). Mid-season production sees >= 10.
        hist_ctx = history.assign(SEASON=get_current_season())

        try:
            with contextlib.redirect_stdout(io.StringIO()):
                # Production refreshes L10 / season anchors before every predict.
                predictor._update_recent_averages(history)
                preds = predictor.predict(pred_row)
        except Exception:
            continue

        for stat in EVAL_STATS:
            if stat not in preds:
                continue
            actual = actual_value(row, stat)
            if actual is None:
                continue
            pred = float(preds[stat])
            err = pred - actual
            acc = sums[stat]
            acc[0] += 1
            acc[1] += abs(err)
            acc[2] += err
            acc[3] += err * err

            q10, q90 = raw_quantiles(predictor, stat, pred_row)
            if not math.isnan(q10) and not math.isnan(q90):
                b = band[stat]
                b[0] += 1
                b[1] += int(q10 <= actual <= q90)
                b[2] += int(q10 - cqr[stat] <= actual <= q90 + cqr[stat])

            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    conf = predictor.get_confidence(hist_ctx, stat, pred, pred_row)
            except Exception:
                continue
            std = conf.get("std")
            if std is None or std <= 0:
                continue

            series = history_series(history, stat)
            median = float(series.median()) if series is not None and len(series) else None
            calib = predictor.probability_calibrator.get(stat)
            for kind, line in pseudo_lines(pred, median):
                if actual == line:
                    continue  # push — excluded rather than scored as an under
                prob = float(
                    ev.ProbabilityCalculator.calculate(pred, line, float(std), calib)
                )
                samples.append(CalibSample(stat, kind, prob, int(actual > line)))

    train_metrics = predictor.training_metrics
    results: List[StatResult] = []
    for stat in EVAL_STATS:
        n, s_abs, s_err, s_sq = sums[stat]
        if n == 0:
            continue
        tm = train_metrics.get(stat, {})
        bn, b_raw, b_cqr = band[stat]
        results.append(
            StatResult(
                stat=stat,
                n_test=int(n),
                sum_abs=s_abs,
                sum_err=s_err,
                sum_sq=s_sq,
                train_mae=tm.get("mae"),
                train_bias=tm.get("bias"),
                train_coverage_80=tm.get("coverage_80"),
                cov_raw=(b_raw / bn) if bn else None,
                cov_cqr=(b_cqr / bn) if bn else None,
                cqr_correction=cqr[stat],
            )
        )

    return PlayerResult(
        name=name,
        player_id=player_id,
        n_total=len(log),
        n_train=train_games,
        n_test=len(test_df),
        stats=tuple(results),
        samples=tuple(samples),
        seconds=time.time() - started,
        n_features_built=n_built,
    )


def _worker(payload):
    """Process-pool entry point (must be importable at module level)."""
    name, pid, log, train_games, quick, season, check_lookahead, stale = payload
    try:
        return evaluate_player(name, pid, log, train_games, quick, season=season,
                               assert_no_lookahead=check_lookahead,
                               stale_serve=stale)
    except Exception as exc:  # never let one player abort the pool
        return PlayerResult(
            name, pid, 0, 0, 0, skipped=True, reason="worker crashed: {}".format(exc)
        )


# ── Aggregation ───────────────────────────────────────────────────────────────


def aggregate(results: Sequence[PlayerResult]) -> Dict[str, Aggregate]:
    agg = {s: Aggregate(s) for s in EVAL_STATS}
    for r in results:
        if r.skipped:
            continue
        for sr in r.stats:
            a = agg[sr.stat]
            a.players += 1
            a.n_test += sr.n_test
            a.sum_abs += sr.sum_abs
            a.sum_err += sr.sum_err
            a.sum_sq += sr.sum_sq
            for value, bucket in (
                (sr.train_mae, a.train_mae),
                (sr.train_bias, a.train_bias),
                (sr.train_coverage_80, a.train_cov),
                (sr.cov_raw, a.cov_raw),
                (sr.cov_cqr, a.cov_cqr),
                (sr.cqr_correction, a.cqr_corr),
                (sr.gap, a.gaps),
            ):
                if value is not None:
                    bucket.append(float(value))
    return agg


def brier(samples: Sequence[CalibSample]) -> Optional[float]:
    if not samples:
        return None
    return statistics.fmean(((s.prob / 100.0) - s.outcome) ** 2 for s in samples)


def deciles(samples: Sequence[CalibSample]) -> List[Tuple[str, int, float, float]]:
    """(label, n, mean predicted prob, realized over-rate) per probability decile."""
    buckets: Dict[int, List[CalibSample]] = {}
    for s in samples:
        idx = min(int(s.prob // 10), 9)
        buckets.setdefault(idx, []).append(s)
    out = []
    for idx in range(10):
        rows = buckets.get(idx, [])
        if not rows:
            continue
        out.append(
            (
                DECILE_LABELS[idx],
                len(rows),
                statistics.fmean(r.prob for r in rows),
                100.0 * statistics.fmean(r.outcome for r in rows),
            )
        )
    return out


def _mean(xs: Sequence[float]) -> Optional[float]:
    return statistics.fmean(xs) if xs else None


def _fmt(value: Optional[float], digits: int = 2, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return ("{:+.%df}" % digits).format(value) if signed else ("{:.%df}" % digits).format(value)


# ── Report ────────────────────────────────────────────────────────────────────


def render_report(
    results: Sequence[PlayerResult],
    agg: Dict[str, Aggregate],
    samples: Sequence[CalibSample],
    season: str,
    train_games: int,
    quick: bool,
    elapsed: float,
    label: str = "Baseline",
    note: Optional[str] = None,
    stale_serve: bool = False,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    done = [r for r in results if not r.skipped]
    skipped = [r for r in results if r.skipped]
    L: List[str] = []

    L.append("# Unbiased Walk-Forward Backtest — {} ({})".format(label, today))
    L.append("")
    if note:
        L.append(note.strip())
    elif label.lower().startswith("baseline"):
        L.append("Measured **before** any model fixes land. This is the \"before\" column.")
    else:
        L.append("Measured **after** the model fixes landed. Compare against the "
                 "baseline report of the same date.")
    L.append("")
    L.append("- **Season:** {}".format(season))
    L.append("- **Train:** first {} feature rows per player (single fit, never refit)".format(train_games))
    L.append("- **Test:** every remaining row, predicted one at a time")
    L.append("- **Pipeline:** `{}`".format("quick (no ensemble)" if quick else "full (ensemble + meta-learner)"))
    L.append("- **Stats:** {} (PRA = reconciled 0.85·(P+R+A) + 0.15·independent)".format(", ".join(EVAL_STATS)))
    L.append("- **Players attempted / evaluated / skipped:** {} / {} / {}".format(
        len(results), len(done), len(skipped)))
    L.append("- **Held-out predictions:** {}".format(sum(a.n_test for a in agg.values())))
    L.append("- **Pseudo-line probability samples:** {}".format(len(samples)))
    widths = sorted({r.n_features_built for r in done if r.n_features_built is not None})
    if widths:
        L.append(
            "- **Model width under test:** {} of {} declared `FEATURE_COLS` are "
            "actually built by `create_features`; the rest are zero-filled by "
            "`predict`".format(
                widths[0] if len(widths) == 1 else "/".join(str(w) for w in widths),
                len(ev.MLPredictor.FEATURE_COLS),
            )
        )
    L.append(
        "- **Opponent context:** point-in-time via `scripts/team_stats_asof.py` — "
        "team aggregates recomputed from games strictly *before* each replay date"
    )
    L.append(
        "- **Serve path:** `get_prediction_features` on a frame whose last row is "
        + ("the **last completed game** — the *pre-Phase-1* production path, "
           "i.e. one-game-stale rolling features (`--stale-serve`)"
           if stale_serve else
           "the **synthetic next-game row** — production's post-Phase-1 path")
    )
    L.append("- **Wall clock:** {:.1f} min".format(elapsed / 60.0))
    L.append("")

    # ── Accuracy ──
    L.append("## 1. Per-stat holdout accuracy")
    L.append("")
    L.append(
        "`MAE (pooled)` weights every held-out game equally; `MAE (player mean)` is the "
        "unweighted mean of per-player MAEs (comparable with `eval_holdout.py`). "
        "**MAE gap** is the mean per-player `holdout MAE − train OOF MAE` — the overfitting measure."
    )
    L.append("")
    L.append(
        "| Stat | Players | N test | MAE (pooled) | MAE (player mean) | Bias (pred−actual) | "
        "RMSE | Train OOF MAE | MAE gap |"
    )
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    per_player_mae = {s: [] for s in EVAL_STATS}
    for r in done:
        for sr in r.stats:
            per_player_mae[sr.stat].append(sr.mae)
    for stat in EVAL_STATS:
        a = agg[stat]
        if not a.n_test:
            L.append("| {} | 0 | 0 | — | — | — | — | — | — |".format(stat))
            continue
        L.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | **{}** |".format(
                stat, a.players, a.n_test,
                _fmt(a.sum_abs / a.n_test),
                _fmt(_mean(per_player_mae[stat])),
                _fmt(a.sum_err / a.n_test, signed=True),
                _fmt(math.sqrt(a.sum_sq / a.n_test)),
                _fmt(_mean(a.train_mae)),
                _fmt(_mean(a.gaps), signed=True),
            )
        )
    L.append("")

    # ── Coverage ──
    L.append("## 2. 80% interval coverage")
    L.append("")
    L.append(
        "Raw band is the untouched (q10, q90) quantile pair — target 0.80. "
        "The CQR band adds the per-stat conformal correction learned at training "
        "time, which targets ~0.90-0.92."
    )
    L.append("")
    L.append(
        "| Stat | Train OOF cov (raw) | Holdout cov RAW (target 0.80) | "
        "Mean CQR correction | Holdout cov CQR (target ~0.90) |"
    )
    L.append("|---|---:|---:|---:|---:|")
    for stat in EVAL_STATS:
        a = agg[stat]
        L.append(
            "| {} | {} | {} | {} | {} |".format(
                stat, _fmt(_mean(a.train_cov)), _fmt(_mean(a.cov_raw)),
                _fmt(_mean(a.cqr_corr)), _fmt(_mean(a.cov_cqr)),
            )
        )
    L.append("")

    # ── Calibration ──
    L.append("## 3. Probability calibration (pseudo-lines)")
    L.append("")
    L.append(
        "Each held-out prediction is scored against 7 pseudo-lines: prediction ± "
        "{0.5, 1.5, 2.5} and the player's season-to-date median (computed only from "
        "games before the row being predicted). `prob_over` comes from the production "
        "`ProbabilityCalculator.calculate` path — same std from `get_confidence`, same "
        "Platt calibrator — and is clipped to [15%, 85%] by `PROB_FLOOR`/`PROB_CEIL`."
    )
    L.append("")
    L.append("### 3a. Overall reliability by predicted-probability decile")
    L.append("")
    L.append("| Predicted bucket | N | Mean predicted | Realized over-rate | Gap (pred − realized) |")
    L.append("|---|---:|---:|---:|---:|")
    for label, n, mp, real in deciles(samples):
        L.append("| {} | {} | {}% | {}% | {} |".format(
            label, n, _fmt(mp, 1), _fmt(real, 1), _fmt(mp - real, 1, signed=True)))
    L.append("")
    L.append("- **Overall Brier score:** {}".format(_fmt(brier(samples), 4)))
    L.append("")

    L.append("### 3b. By stat")
    L.append("")
    L.append("| Stat | N | Mean predicted | Realized over-rate | Gap | Brier |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for stat in EVAL_STATS:
        rows = [s for s in samples if s.stat == stat]
        if not rows:
            L.append("| {} | 0 | — | — | — | — |".format(stat))
            continue
        mp = statistics.fmean(r.prob for r in rows)
        real = 100.0 * statistics.fmean(r.outcome for r in rows)
        L.append("| {} | {} | {}% | {}% | {} | {} |".format(
            stat, len(rows), _fmt(mp, 1), _fmt(real, 1),
            _fmt(mp - real, 1, signed=True), _fmt(brier(rows), 4)))
    L.append("")

    L.append("### 3c. By pseudo-line type")
    L.append("")
    L.append(
        "`offset` lines are centred on the prediction (half are near coin-flips by "
        "construction); `median` lines sit at the player's season-to-date median and "
        "are the closest stand-in for a real market line."
    )
    L.append("")
    L.append("| Line type | N | Mean predicted | Realized over-rate | Gap | Brier |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for kind in ("offset", "median"):
        rows = [s for s in samples if s.line_kind == kind]
        if not rows:
            continue
        mp = statistics.fmean(r.prob for r in rows)
        real = 100.0 * statistics.fmean(r.outcome for r in rows)
        L.append("| {} | {} | {}% | {}% | {} | {} |".format(
            kind, len(rows), _fmt(mp, 1), _fmt(real, 1),
            _fmt(mp - real, 1, signed=True), _fmt(brier(rows), 4)))
    L.append("")

    L.append("### 3d. Median-line reliability by decile")
    L.append("")
    L.append("| Predicted bucket | N | Mean predicted | Realized over-rate | Gap |")
    L.append("|---|---:|---:|---:|---:|")
    med = [s for s in samples if s.line_kind == "median"]
    for label, n, mp, real in deciles(med):
        L.append("| {} | {} | {}% | {}% | {} |".format(
            label, n, _fmt(mp, 1), _fmt(real, 1), _fmt(mp - real, 1, signed=True)))
    L.append("")

    # ── Per-player appendix ──
    L.append("## 4. Per-player appendix")
    L.append("")
    L.append(
        "| Player | Games | N test | Stat | Holdout MAE | Bias | RMSE | Train OOF MAE | "
        "MAE gap | Cov RAW | Cov CQR |"
    )
    L.append("|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(done, key=lambda x: x.name):
        for sr in r.stats:
            L.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    r.name, r.n_total, sr.n_test, sr.stat,
                    _fmt(sr.mae), _fmt(sr.bias, signed=True), _fmt(sr.rmse),
                    _fmt(sr.train_mae), _fmt(sr.gap, signed=True),
                    _fmt(sr.cov_raw), _fmt(sr.cov_cqr),
                )
            )
    if not done:
        L.append("| _no players evaluated_ | | | | | | | | | | |")
    L.append("")

    if skipped:
        L.append("## 5. Skipped players")
        L.append("")
        for r in sorted(skipped, key=lambda x: x.name):
            L.append("- **{}** ({}): {}".format(r.name, r.player_id, r.reason))
        L.append("")

    # ── Caveats ──
    L.append("## 6. Caveats")
    L.append("")
    L.append(
        "1. **Opponent context is point-in-time (fixed in Phase 0).** The feature "
        "frame is rebuilt at every replay step with `team_stats` aggregated by "
        "`scripts/team_stats_asof.py` from team-games played **strictly before** "
        "that step's date — same-day games excluded. The training frame is built "
        "once, as of the first held-out game, so nothing from the test period "
        "reaches the fit. A team with no prior games on a given date is omitted "
        "from the dict, which lets `extract_opp_stats` fall back to its "
        "league-average defaults rather than emitting NaN. Rolling features remain "
        "`shift(1)`-safe: row *i* only summarizes rows `0..i-1`. Earlier reports "
        "carried a caveat about season-aggregate opponent leakage; that caveat was "
        "vacuous, because the harness passed `team_stats=None` and built no "
        "opponent aggregate at all — it is now genuinely satisfied instead."
    )
    L.append(
        "2. **The model is frozen after the initial fit.** Production retrains nightly; "
        "here a single fit on the first {} rows predicts every later game. Late-season "
        "holdout rows are therefore predicted by an increasingly stale model, which "
        "inflates holdout MAE relative to production.".format(train_games)
    )
    L.append(
        "3. **L10 / season anchors are refreshed, the GBM is not.** "
        "`_update_recent_averages` is called on the pre-row history before every "
        "prediction (production does the same), so the regression-to-mean and "
        "deviation-cap anchors stay current with no lookahead."
    )
    L.append(
        "4. **Early-season damping neutralized.** `_current_season_games` compares the "
        "log against the *calendar* current season, so a {} backtest would trip the "
        "<10-games damping (confidence ×0.75, std ×1.3) on every row. The history "
        "frame passed to `get_confidence` is stamped with the current season string so "
        "damping stays neutral, matching a mid-season production run.".format(season)
    )
    L.append(
        "5. **No serve-time context adjustments.** `estimated_minutes` is not supplied "
        "(so the rate-model blend and minutes scaling never fire), and the injury "
        "boost, blowout discount and questionable dampener are all skipped. This "
        "isolates the core model from the context layer."
    )
    L.append(
        "6. **The serve path is now exercised (Phase 1), and the harness was "
        "never where the staleness lived.** Each step truncates the raw log to "
        "games played strictly before the test game, appends a synthetic row "
        "built from that game's schedule facts alone (matchup + date — "
        "published months ahead), rebuilds features, and calls "
        "`get_prediction_features`. A per-player probe rewrites every realized "
        "number from the test game onward and requires a bit-identical served "
        "vector; any player failing it is skipped with a `LOOKAHEAD:` reason. "
        "Reports up to and including Phase 0 read the feature row of the game "
        "being predicted **directly**, and that row already carried correct "
        "lag-1 values — so the harness never reproduced the one-game staleness "
        "that production served. `--stale-serve` reproduces the pre-Phase-1 "
        "production path exactly (identical schedule context; frame rolled back "
        "to the last completed game) and is the only way to measure what that "
        "staleness cost."
    )
    L.append(
        "7. **Head-to-head is re-scoped to the replay history.** Production calls "
        "`NBADataScraper.get_vs_team_stats`, which re-reads the player's full "
        "multi-season log; used verbatim in a walk-forward replay it would pull "
        "the rest of the season into every step. The harness computes the same "
        "shape from games strictly before the test game."
    )
    L.append(
        "8. **Pseudo-lines are model-derived, not market lines.** The ±0.5/1.5/2.5 "
        "family is centred on the prediction, so it measures the *internal* "
        "consistency of prediction + std + calibrator, not edge against a bookmaker. "
        "The season-to-date median line is the closest stand-in for a market line — "
        "read 3c/3d for that view. **Every calibration number in this report is "
        "against synthetic pseudo-lines, not real sportsbook lines. Beating a "
        "player's season-to-date median is not evidence of beating a sportsbook.** "
        "`manual_lines` is empty and there is no historical odds source, so real-line "
        "validation can only come from a forward test."
    )
    L.append(
        "9. **PRA's train-OOF MAE is not the served quantity.** `training_metrics['PRA']` "
        "is computed from the *independent* PRA model's OOF predictions, while the "
        "holdout column evaluates the reconciled 85/15 blend. The PRA MAE gap therefore "
        "compares two slightly different estimators; the PTS/REB/AST gaps are apples-to-apples."
    )
    L.append(
        "10. **Probabilities are hard-clipped to [15%, 85%]** by "
        "`ProbabilityCalculator.PROB_FLOOR/PROB_CEIL`, so the 0-10% and 90-100% deciles "
        "are structurally empty and the Brier score is floored by that clipping."
    )
    L.append(
        "11. **Ties are dropped.** When a realized value lands exactly on a pseudo-line "
        "(possible for integer median lines) the sample is excluded rather than scored "
        "as an under."
    )
    L.append(
        "12. **Sample size.** One season, ~50 players, and per-player holdout sets of "
        "roughly 5-25 games. Per-player rows in the appendix are noisy; the pooled "
        "per-stat numbers are the ones to act on."
    )
    L.append("")

    L.append("## 7. Reading guide")
    L.append("")
    L.append("- **MAE gap > 0** ⇒ the OOF metrics stored on the pickle are optimistic (overfitting).")
    L.append("- **Bias > 0** ⇒ the model over-predicts held-out games; **< 0** ⇒ under-predicts.")
    L.append("- **Holdout cov RAW ≪ 0.80** ⇒ quantile intervals are too narrow before CQR.")
    L.append("- **Calibration gap > 0** in a decile ⇒ the model claims more OVER probability than it delivers.")
    L.append("- **Brier** is the headline probability score (lower is better; 0.25 = always saying 50%).")
    L.append("")
    return "\n".join(L)


# ── Entry point ───────────────────────────────────────────────────────────────


def select_players(names_arg: Optional[str], limit: Optional[int]):
    if names_arg:
        wanted = [n.strip().lower() for n in names_arg.split(",") if n.strip()]
        chosen = [p for p in DEFAULT_PLAYERS if p[0].lower() in wanted]
        missing = [w for w in wanted if not any(p[0].lower() == w for p in DEFAULT_PLAYERS)]
        if missing:
            print("WARNING: not in curated list, ignored: {}".format(", ".join(missing)))
        return chosen
    return list(DEFAULT_PLAYERS[:limit] if limit else DEFAULT_PLAYERS)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--train-games", type=int, default=60)
    parser.add_argument("--quick", action="store_true",
                        help="Skip the ensemble for faster runs (single GBM only).")
    parser.add_argument("--players", default=None,
                        help="Comma-separated player names from the curated list.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Evaluate only the first N curated players.")
    parser.add_argument("--workers", type=int, default=5,
                        help="Process-pool size for per-player training (default 5).")
    parser.add_argument("--refresh-cache", action="store_true",
                        help="Ignore cache/backtest_logs and re-fetch every game "
                             "log from stats.nba.com, rewriting the cache.")
    parser.add_argument("--refresh-team-cache", action="store_true",
                        help="Re-fetch the team-level game log used for "
                             "point-in-time opponent context.")
    parser.add_argument("--stale-serve", action="store_true",
                        help="serve from the last COMPLETED game's row instead of "
                             "the synthetic next-game row -- reproduces the "
                             "pre-Phase-1 production serve path, for measuring "
                             "what the one-game staleness was costing")
    parser.add_argument("--skip-lookahead-check", action="store_true",
                        help="skip the per-player probe that rewrites the future "
                             "and demands a bit-identical served vector")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--label", default=None,
                        help="Report heading, e.g. 'Baseline' or 'Post-fix'. "
                             "Defaults to a label inferred from --out.")
    parser.add_argument("--note", default=None,
                        help="Markdown blurb (literal text, or a path to a file) "
                             "placed directly under the report heading, replacing "
                             "the default before/after blurb.")
    args = parser.parse_args(argv)

    selected = select_players(args.players, args.limit)
    if not selected:
        print("No players selected.")
        return 1

    started = time.time()
    print("Backtesting {} players | season={} | train={} | quick={} | workers={}".format(
        len(selected), args.season, args.train_games, args.quick, args.workers))

    # Phase 0 — warm the team-level log ONCE in the parent. Workers open it
    # read-only (allow_fetch=False), so a cold cache fails here rather than
    # firing `workers` identical requests at stats.nba.com.
    print("\nLoading point-in-time opponent context...")
    provider = TeamStatsProvider(args.season, refresh=args.refresh_team_cache)
    lo, hi = provider.date_range
    print("  {} team-games | {} teams | {} .. {}".format(
        provider.n_team_games, len(provider.teams),
        lo.date() if lo is not None else "?", hi.date() if hi is not None else "?"))

    # Phase 1 — serial fetch, served from the per-player parquet cache when warm.
    print("\nFetching game logs...")
    payloads = []
    results: List[PlayerResult] = []
    for idx, (name, pid) in enumerate(selected, start=1):
        cached = log_cache_path(pid, args.season).exists() and not args.refresh_cache
        try:
            log = fetch_player_log(pid, args.season, refresh_cache=args.refresh_cache)
        except Exception as exc:
            print("  [{}/{}] {}: FETCH FAILED — {}".format(idx, len(selected), name, exc))
            results.append(PlayerResult(name, pid, 0, 0, 0, skipped=True,
                                        reason="fetch failed: {}".format(exc)))
            continue
        print("  [{}/{}] {}: {} games{}".format(
            idx, len(selected), name, len(log), " (cached)" if cached else ""))
        payloads.append((name, pid, log, args.train_games, args.quick, args.season,
                         not args.skip_lookahead_check, args.stale_serve))

    # Phase 2 — parallel training / walk-forward.
    print("\nTraining + walking forward ({} players)...".format(len(payloads)))
    workers = max(1, min(args.workers, len(payloads)))
    if workers == 1:
        for p in payloads:
            results.append(_worker(p))
            _echo(results[-1], len(results), len(selected))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_worker, p): p[0] for p in payloads}
            for done_n, fut in enumerate(as_completed(futures), start=1):
                try:
                    res = fut.result()
                except Exception as exc:
                    name = futures[fut]
                    res = PlayerResult(name, "?", 0, 0, 0, skipped=True,
                                       reason="pool error: {}".format(exc))
                results.append(res)
                _echo(res, done_n, len(payloads))

    agg = aggregate(results)
    samples = [s for r in results for s in r.samples]
    elapsed = time.time() - started
    if args.label:
        label = args.label
    elif args.out and "postfix" in args.out.stem.lower():
        label = "Post-fix"
    elif args.out and "baseline" not in args.out.stem.lower():
        label = args.out.stem.replace("backtest_unbiased_", "").replace("_", " ")
    else:
        label = "Baseline"
    note = args.note
    if note and Path(note).expanduser().is_file():
        note = Path(note).expanduser().read_text(encoding="utf-8")
    report = render_report(results, agg, samples, args.season,
                           args.train_games, args.quick, elapsed, label, note,
                           stale_serve=args.stale_serve)

    out_path = args.out or (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "backtest_unbiased_baseline_{}.md".format(datetime.now().strftime("%Y-%m-%d"))
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print("\nReport written to {} ({:.1f} min)".format(out_path, elapsed / 60.0))
    return 0


def _echo(res: PlayerResult, done_n: int, total: int) -> None:
    if res.skipped:
        print("  [{}/{}] {}: SKIP — {}".format(done_n, total, res.name, res.reason))
        return
    parts = ["{}={:.2f}({:+.2f})".format(sr.stat, sr.mae, sr.bias) for sr in res.stats]
    print("  [{}/{}] {}: n={} {} [{:.0f}s]".format(
        done_n, total, res.name, res.n_test, " ".join(parts), res.seconds))


if __name__ == "__main__":
    raise SystemExit(main())
