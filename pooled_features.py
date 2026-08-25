"""Causal recency features for the pooled cross-player prop model.

The per-player model this replaces fitted 81 features on ~60 rows (p/n = 1.35),
and the 2026-08 diagnosis showed accuracy degraded monotonically as features
were added: a ridge on a single ``ROLL_10_<stat>`` beat the full 81-feature
ensemble on every stat. Pooling across players turns n = 60 into n ~ 33,000, so
the fix is to keep the feature count small and the training set large.

Six features per stat, all plain summaries of games the player has ALREADY
played:

====================  ==========================================================
``<STAT>_L5``         mean of the last 5 completed games
``<STAT>_L10``        mean of the last 10
``<STAT>_L20``        mean of the last 20
``<STAT>_MEDIAN``     median over the whole in-season history
``<STAT>_MEAN``       mean over the whole in-season history
``<STAT>_EWMA5``      exponentially-weighted mean, five-game half-life
====================  ==========================================================

Every one of them is a trivial baseline in its own right, which is deliberate:
the linear span of the six contains L5, L10, L20, the season median, the season
mean and EWMA5 exactly, so the pooled model can never be structurally incapable
of matching the baseline it must beat.

``PRA`` is always recomputed as ``PTS + REB + AST`` from the history and never
read out of a ``PRA`` column. Phase 0's harness stripped PTS/REB/AST from the
row being predicted but left the derived ``PRA`` in place, which let the serve
path read the realized PRA of that very game.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

#: Stats the pooled model serves. PRA is fitted directly, not summed.
POOLED_STATS: Tuple[str, ...] = ("PTS", "REB", "AST", "PRA")

#: Component stats PRA is derived from.
COMPONENT_STATS: Tuple[str, ...] = ("PTS", "REB", "AST")

#: Suffixes of the six PRODUCTION recency features, in estimator order. This is
#: the set the pooled model serves; it stays at six.
RECENCY_KINDS: Tuple[str, ...] = ("L5", "L10", "L20", "MEDIAN", "MEAN", "EWMA5")

#: Every kind the builders can emit. ``L3`` / ``LAST`` / ``STD`` exist only so
#: the nine-feature reference variant the 2026-08 diagnosis measured can be
#: refitted and scored from committed code. They are not production features:
#: the diagnosis found accuracy degraded monotonically as features were added.
ALL_KINDS: Tuple[str, ...] = RECENCY_KINDS + ("L3", "LAST", "STD")

#: Trailing-window length for each windowed kind.
_WINDOWS: Mapping[str, int] = {"L3": 3, "L5": 5, "L10": 10, "L20": 20}

#: Half-life, in games, of ``<STAT>_EWMA5``. Matches the ``b_ewma5`` baseline
#: measured in ``docs/diagnosis_resolution_failure_2026-08-23.md``.
EWMA_HALFLIFE_GAMES: float = 5.0

#: Games of in-season history a training row requires. Serving needs far less
#: (see ``MIN_SERVE_GAMES``); this is about not training on noise.
MIN_PRIOR_GAMES: int = 20

#: Below this many completed games the pooled features are too thin to serve.
MIN_SERVE_GAMES: int = 5

_CANONICAL_COLUMNS: Mapping[str, str] = {
    "pts": "PTS", "reb": "REB", "ast": "AST", "min": "MIN",
    "game_date": "GAME_DATE", "player_name": "PLAYER_NAME",
}


def feature_names(stat: str,
                  kinds: Sequence[str] = RECENCY_KINDS) -> Tuple[str, ...]:
    """Feature names for ``stat``, in estimator order."""
    unknown = [k for k in kinds if k not in ALL_KINDS]
    if unknown:
        raise ValueError("unknown recency kind(s): {}".format(", ".join(unknown)))
    return tuple("{}_{}".format(stat, kind) for kind in kinds)


def all_feature_names(kinds: Sequence[str] = RECENCY_KINDS) -> Tuple[str, ...]:
    """Every pooled feature name across every served stat."""
    return tuple(name for stat in POOLED_STATS for name in feature_names(stat, kinds))


def ewma_mean(values: Sequence[float],
              halflife: float = EWMA_HALFLIFE_GAMES) -> float:
    """Exponentially-weighted mean with a ``halflife``-game half-life."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("ewma_mean needs at least one observation")
    weights = 0.5 ** (np.arange(arr.size - 1, -1, -1) / float(halflife))
    return float(np.sum(weights * arr) / np.sum(weights))


def recency_features(stat: str, history: Sequence[float],
                     kinds: Sequence[str] = RECENCY_KINDS) -> Dict[str, float]:
    """The recency features for ``stat`` over a completed-game ``history``.

    ``history`` must hold only games played strictly BEFORE the game being
    predicted. An empty history is an error rather than a zero-fill: the
    81-feature path substituted 0 for anything missing, which is precisely how
    a feature could silently stop existing.
    """
    arr = np.asarray(history, dtype=float)
    if arr.size == 0:
        raise ValueError("{}: cannot build recency features from no games".format(stat))
    if not np.all(np.isfinite(arr)):
        raise ValueError("{}: history contains non-finite values".format(stat))
    out = {"{}_{}".format(stat, kind): float(arr[-_WINDOWS[kind]:].mean())
           for kind in _WINDOWS}
    out["{}_MEDIAN".format(stat)] = float(np.median(arr))
    out["{}_MEAN".format(stat)] = float(arr.mean())
    out["{}_EWMA5".format(stat)] = ewma_mean(arr)
    out["{}_LAST".format(stat)] = float(arr[-1])
    out["{}_STD".format(stat)] = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    return {name: out[name] for name in feature_names(stat, kinds)}


def _rename_to_canonical(frame: pd.DataFrame) -> pd.DataFrame:
    renames = {c: _CANONICAL_COLUMNS[c.lower()] for c in frame.columns
               if c.lower() in _CANONICAL_COLUMNS and c not in _CANONICAL_COLUMNS.values()}
    return frame.rename(columns=renames) if renames else frame


def normalize_game_log(frame: pd.DataFrame) -> pd.DataFrame:
    """Canonical completed-game log: DNPs dropped, sorted ascending by date.

    Accepts the column casing of every source in the tree — ``create_features``
    frames (``PTS``/``MIN_NUMERIC``), the stats.nba.com backtest cache
    (``PTS``/``MIN``) and the Supabase mirror (``pts``/``min``). Returns a NEW
    frame; the input is never mutated.
    """
    if frame is None or not len(frame):
        raise ValueError("pooled features need a non-empty game log")
    df = _rename_to_canonical(frame.copy())

    missing = [c for c in COMPONENT_STATS if c not in df.columns]
    if missing:
        raise ValueError("game log is missing {}".format(", ".join(missing)))

    # Drop the synthetic next-game row create_features appends. Its box score is
    # NaN, but leaving it in would shorten every trailing window by one.
    from nba_evaluator import UPCOMING_GAME_FLAG
    if UPCOMING_GAME_FLAG in df.columns:
        df = df[df[UPCOMING_GAME_FLAG].fillna(0) == 0]

    minutes_col = "MIN_NUMERIC" if "MIN_NUMERIC" in df.columns else "MIN"
    if minutes_col not in df.columns:
        raise ValueError("game log is missing minutes ({} / MIN)".format(minutes_col))
    df["MIN_NUMERIC"] = pd.to_numeric(df[minutes_col], errors="coerce").fillna(0.0)

    # Production's DNP filter, applied at the top of create_features.
    df = df[df["MIN_NUMERIC"] > 0]
    df = df.dropna(subset=list(COMPONENT_STATS))
    if "GAME_DATE" in df.columns:
        df = df.assign(GAME_DATE=pd.to_datetime(df["GAME_DATE"], format="mixed"))
        df = df.sort_values("GAME_DATE", kind="mergesort")
    # PRA is always recomputed; any PRA column already on the frame is ignored.
    df = df.assign(PRA=df["PTS"].astype(float) + df["REB"].astype(float)
                   + df["AST"].astype(float))
    return df.reset_index(drop=True)


def _history_matrix(log: pd.DataFrame) -> Dict[str, np.ndarray]:
    return {stat: log[stat].to_numpy(dtype=float) for stat in POOLED_STATS}


def serve_features(game_log: pd.DataFrame,
                   kinds: Sequence[str] = RECENCY_KINDS) -> Dict[str, float]:
    """Pooled features for the NEXT game, from a player's completed-game log.

    Every value summarises games already in ``game_log``; nothing about the
    upcoming game enters, which is what makes the serve path lookahead-free.
    """
    log = normalize_game_log(game_log)
    if len(log) < MIN_SERVE_GAMES:
        raise ValueError(
            "pooled features need >= {} completed games, got {}".format(
                MIN_SERVE_GAMES, len(log)))
    columns = _history_matrix(log)
    out: Dict[str, float] = {}
    for stat in POOLED_STATS:
        out.update(recency_features(stat, columns[stat], kinds))
    return out


def dispersion(game_log: pd.DataFrame, stat: str) -> float:
    """In-season standard deviation of ``stat`` over completed games.

    Feeds the pooled uncertainty model. Deliberately NOT a point-prediction
    feature — the six recency features are the whole point model.
    """
    log = normalize_game_log(game_log)
    values = log[stat].to_numpy(dtype=float)
    if values.size < 2:
        raise ValueError("{}: dispersion needs at least two games".format(stat))
    return float(np.std(values, ddof=1))


def build_panel(logs: pd.DataFrame,
                min_prior: int = MIN_PRIOR_GAMES,
                group_cols: Iterable[str] = ("player_id", "season"),
                kinds: Sequence[str] = RECENCY_KINDS) -> pd.DataFrame:
    """League-wide training panel: one row per (player-season, game).

    Each row carries the six features per stat computed from that player-season's
    games strictly before it, plus the realized ``<STAT>_ACTUAL`` targets. Groups
    never span seasons, so no feature reaches back across an offseason.
    """
    group_cols = list(group_cols)
    missing = [c for c in group_cols if c not in logs.columns]
    if missing:
        raise ValueError("build_panel needs {} on the log".format(", ".join(missing)))

    records = []
    for keys, raw in logs.groupby(group_cols, sort=False):
        log = normalize_game_log(raw)
        n = len(log)
        if n <= min_prior:
            continue
        key_values = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
        columns = _history_matrix(log)
        dates = log["GAME_DATE"].to_numpy() if "GAME_DATE" in log.columns else np.full(n, None)
        for t in range(min_prior, n):
            row = dict(key_values, game_date=dates[t], prior_games=t)
            for stat in POOLED_STATS:
                values = columns[stat]
                row.update(recency_features(stat, values[:t], kinds))
                row["{}_ACTUAL".format(stat)] = float(values[t])
            for stat in POOLED_STATS:
                row["{}_DISPERSION".format(stat)] = float(
                    np.std(columns[stat][:t], ddof=1))
            records.append(row)
    if not records:
        raise ValueError("no player-season had more than {} games".format(min_prior))
    return pd.DataFrame.from_records(records)
