"""Point-in-time opponent context for the walk-forward backtest.

``FeatureEngineer.create_features`` accepts a ``team_stats`` dict shaped as
``{TEAM_ABBREV: {lowercase stat -> value}}`` and maps every row's ``OPPONENT``
through it. Feeding it a *season aggregate* would leak: a game played in
November would be described by defensive numbers that include April.

This module builds the same dict from **only the games played strictly before a
given date**, so a replay step sees exactly what was knowable that morning.

Source
------
One call to the NBA stats team-level game log::

    leaguegamelog.LeagueGameLog(season, player_or_team_abbreviation='T',
                                season_type_all_star='Regular Season')

For 2024-25 that is 2,460 team-games / 1,230 games / 30 teams. Each game
contributes exactly two rows, which is what lets us pair a team with its
opponent on ``GAME_ID``. The result is cached to
``cache/team_logs/{season}.parquet`` so repeat runs never touch the network.

Definitions
-----------
``poss = FGA - OREB + TOV + 0.44 * FTA``; ``pace`` is possessions per 48
minutes (team ``MIN`` is 240 = 48 x 5 in regulation, more in overtime, so
game-minutes are ``MIN / 5``); ``off_rating`` / ``def_rating`` are points per
100 own / opponent possessions.

Cold start
----------
A team with **zero** prior games on the as-of date is *absent* from the dict
rather than present with NaNs, so ``extract_opp_stats`` falls back to its own
league-average defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Union

import pandas as pd

__all__ = [
    "OPP_STAT_KEYS",
    "TeamStatsProvider",
    "build_paired_team_games",
    "load_team_game_log",
    "team_log_cache_path",
    "team_stats_asof",
]

# Exactly the lowercase keys ``FeatureEngineer.extract_opp_stats`` reads
# (nba_evaluator.py:1221-1239). Uppercase keys silently return the fallbacks,
# so this tuple is load-bearing -- do not "tidy" it into upper case.
OPP_STAT_KEYS = (
    "def_rating",
    "pace",
    "opp_ast",
    "off_rating",
    "net_rating",
    "efg_pct",
    "tov_pct",
    "oreb_pct",
    "dreb_pct",
)

# Box-score columns pulled from the team game log. Everything downstream is
# derived from sums of these.
BOX_COLS = (
    "MIN", "FGM", "FGA", "FG3M", "FTA", "OREB", "DREB", "TOV", "PTS", "AST",
)

CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache" / "team_logs"

DateLike = Union[str, pd.Timestamp, "pd.DatetimeTZDtype"]

# Sanity envelope for a full-season aggregate. Used by ``describe_league`` and
# by the tests; deliberately generous so a legitimately weird early-season
# sample does not trip it.
PLAUSIBLE_RANGES: Mapping[str, tuple] = {
    "pace": (90.0, 110.0),
    "off_rating": (95.0, 130.0),
    "def_rating": (95.0, 130.0),
    "net_rating": (-25.0, 25.0),
    "opp_ast": (15.0, 40.0),
    "efg_pct": (0.40, 0.65),
    "tov_pct": (8.0, 22.0),
    "oreb_pct": (0.15, 0.45),
    "dreb_pct": (0.55, 0.90),
}


# ── Raw log: fetch + parquet cache ────────────────────────────────────────────


def team_log_cache_path(season: str) -> Path:
    """Where the raw team game log for ``season`` is cached."""
    return CACHE_ROOT / "{}.parquet".format(season)


def _fetch_team_game_log(season: str) -> pd.DataFrame:
    """One live call to stats.nba.com for the team-level regular-season log."""
    from nba_api.stats.endpoints import leaguegamelog

    df = leaguegamelog.LeagueGameLog(
        season=season,
        player_or_team_abbreviation="T",
        season_type_all_star="Regular Season",
    ).get_data_frames()[0]
    if df is None or df.empty:
        raise RuntimeError(
            "leaguegamelog returned no rows for season {!r}".format(season)
        )
    return df


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write via a tmp file + ``os.replace`` so a killed run leaves no partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def load_team_game_log(
    season: str,
    refresh: bool = False,
    allow_fetch: bool = True,
) -> pd.DataFrame:
    """Return the raw team game log for ``season``, using the parquet cache.

    Args:
        season: NBA season string, e.g. ``"2024-25"``.
        refresh: Ignore any cached copy and re-fetch, rewriting the cache.
        allow_fetch: When False, raise instead of hitting the network. Worker
            processes set this so a cold cache fails loudly in the parent
            rather than firing N concurrent identical requests.

    Raises:
        FileNotFoundError: ``allow_fetch`` is False and nothing is cached.
        RuntimeError: the endpoint returned an empty frame.
    """
    path = team_log_cache_path(season)
    if not refresh and path.exists():
        try:
            return pd.read_parquet(path)
        except Exception as exc:  # corrupt/truncated cache -> re-fetch
            if not allow_fetch:
                raise RuntimeError(
                    "cached team log {} is unreadable: {}".format(path, exc)
                ) from exc

    if not allow_fetch:
        raise FileNotFoundError(
            "no cached team game log at {}. Warm it in the parent process with "
            "load_team_game_log({!r}) before fanning out.".format(path, season)
        )

    df = _fetch_team_game_log(season)
    _write_parquet_atomic(df, path)
    return df


# ── Pairing ───────────────────────────────────────────────────────────────────


def build_paired_team_games(raw: pd.DataFrame) -> pd.DataFrame:
    """Pair every team-game with its opponent's box score on ``GAME_ID``.

    Returns one row per team-game with the team's own ``BOX_COLS`` plus the
    opponent's under a ``_OPP`` suffix, sorted ascending by ``GAME_DATE``.

    Raises:
        ValueError: a required column is missing, or some ``GAME_ID`` does not
            have exactly two rows (which would make the pairing ambiguous).
    """
    required = ("GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION") + BOX_COLS
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError("team game log is missing columns: {}".format(missing))

    df = raw.loc[:, list(required)].copy()
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], format="mixed")
    for col in BOX_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=list(BOX_COLS))

    sizes = df.groupby("GAME_ID").size()
    bad = sizes[sizes != 2]
    if len(bad):
        raise ValueError(
            "expected exactly 2 rows per GAME_ID, got {} ids with a different "
            "count (e.g. {})".format(len(bad), dict(bad.head(3)))
        )

    merged = df.merge(df, on="GAME_ID", suffixes=("", "_OPP"))
    merged = merged[merged["TEAM_ABBREVIATION"] != merged["TEAM_ABBREVIATION_OPP"]]
    merged = merged.drop(columns=["GAME_DATE_OPP"])
    return merged.sort_values("GAME_DATE").reset_index(drop=True)


# ── Aggregation ───────────────────────────────────────────────────────────────


def _team_context(group: pd.DataFrame) -> Optional[Dict[str, float]]:
    """Aggregate one team's prior games into the ``extract_opp_stats`` shape.

    Returns None when the sample cannot produce a meaningful rate (no
    possessions, no shots, no minutes) so the caller can omit the team and let
    the league-average defaults apply.
    """
    n_games = len(group)
    if n_games == 0:
        return None

    fgm = float(group["FGM"].sum())
    fga = float(group["FGA"].sum())
    fg3m = float(group["FG3M"].sum())
    fta = float(group["FTA"].sum())
    oreb = float(group["OREB"].sum())
    dreb = float(group["DREB"].sum())
    tov = float(group["TOV"].sum())
    pts = float(group["PTS"].sum())
    team_minutes = float(group["MIN"].sum())

    opp_fga = float(group["FGA_OPP"].sum())
    opp_fta = float(group["FTA_OPP"].sum())
    opp_oreb = float(group["OREB_OPP"].sum())
    opp_dreb = float(group["DREB_OPP"].sum())
    opp_tov = float(group["TOV_OPP"].sum())
    opp_pts = float(group["PTS_OPP"].sum())
    opp_ast = float(group["AST_OPP"].sum())

    poss = fga - oreb + tov + 0.44 * fta
    opp_poss = opp_fga - opp_oreb + opp_tov + 0.44 * opp_fta
    # Team MIN is 5 players x game length (240 in regulation, more in OT).
    game_minutes = team_minutes / 5.0

    if poss <= 0 or opp_poss <= 0 or game_minutes <= 0 or fga <= 0:
        return None

    off_rating = pts / poss * 100.0
    def_rating = opp_pts / opp_poss * 100.0
    oreb_den = oreb + opp_dreb
    dreb_den = dreb + opp_oreb

    return {
        "def_rating": def_rating,
        "pace": poss * 48.0 / game_minutes,
        "opp_ast": opp_ast / n_games,
        "off_rating": off_rating,
        "net_rating": off_rating - def_rating,
        "efg_pct": (fgm + 0.5 * fg3m) / fga,
        "tov_pct": tov / poss * 100.0,
        "oreb_pct": (oreb / oreb_den) if oreb_den > 0 else 0.27,
        "dreb_pct": (dreb / dreb_den) if dreb_den > 0 else 0.73,
    }


def aggregate_prior_games(prior: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Aggregate an already-filtered frame of prior team-games per team."""
    out: Dict[str, Dict[str, float]] = {}
    if prior.empty:
        return out
    for team, group in prior.groupby("TEAM_ABBREVIATION", sort=True):
        ctx = _team_context(group)
        if ctx is not None:
            out[str(team)] = ctx
    return out


# ── Provider ──────────────────────────────────────────────────────────────────


class TeamStatsProvider:
    """Memoized point-in-time ``team_stats`` dicts for one season.

    Construct once per process; ``as_of`` is cached per distinct date, so a
    replay that asks for the same date across 44 players pays for it once.
    """

    def __init__(
        self,
        season: str,
        paired: Optional[pd.DataFrame] = None,
        refresh: bool = False,
        allow_fetch: bool = True,
    ) -> None:
        self.season = season
        if paired is None:
            paired = build_paired_team_games(
                load_team_game_log(season, refresh=refresh, allow_fetch=allow_fetch)
            )
        self._paired = paired
        self._dates = paired["GAME_DATE"].to_numpy()
        self._cache: Dict[pd.Timestamp, Dict[str, Dict[str, float]]] = {}

    # -- introspection -----------------------------------------------------

    @property
    def n_team_games(self) -> int:
        return len(self._paired)

    @property
    def teams(self) -> tuple:
        return tuple(sorted(self._paired["TEAM_ABBREVIATION"].unique()))

    @property
    def date_range(self) -> tuple:
        if self._paired.empty:
            return (None, None)
        return (self._paired["GAME_DATE"].min(), self._paired["GAME_DATE"].max())

    # -- the point of the module -------------------------------------------

    def as_of(self, date: DateLike) -> Dict[str, Dict[str, float]]:
        """Team context computed from games **strictly before** ``date``.

        Same-day games are excluded: on the morning of a game you know last
        night's box scores and nothing else.
        """
        key = pd.Timestamp(date).normalize()
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        prior = self._paired[self._paired["GAME_DATE"] < key]
        result = aggregate_prior_games(prior)
        self._cache[key] = result
        return result

    def season_totals(self) -> Dict[str, Dict[str, float]]:
        """Whole-season aggregate. Leaky by construction -- diagnostics only."""
        return aggregate_prior_games(self._paired)


# ── Module-level convenience ──────────────────────────────────────────────────

_PROVIDERS: Dict[str, TeamStatsProvider] = {}


def get_provider(
    season: str,
    refresh: bool = False,
    allow_fetch: bool = True,
) -> TeamStatsProvider:
    """Process-local memoized provider for ``season``."""
    if refresh or season not in _PROVIDERS:
        _PROVIDERS[season] = TeamStatsProvider(
            season, refresh=refresh, allow_fetch=allow_fetch
        )
    return _PROVIDERS[season]


def team_stats_asof(
    date: DateLike,
    season: str = "2024-25",
    allow_fetch: bool = True,
) -> Dict[str, Dict[str, float]]:
    """``{TEAM: {def_rating, pace, ...}}`` from games strictly before ``date``."""
    return get_provider(season, allow_fetch=allow_fetch).as_of(date)


def describe_league(stats: Mapping[str, Mapping[str, float]]) -> Dict[str, float]:
    """League-mean of each stat -- a quick sanity read on an as-of snapshot."""
    if not stats:
        return {}
    return {
        key: sum(float(v[key]) for v in stats.values()) / len(stats)
        for key in OPP_STAT_KEYS
    }


def _cli(argv: Optional[Iterable[str]] = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--date", default=None,
                        help="As-of date (YYYY-MM-DD). Default: end of season.")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-fetch the team game log, rewriting the cache.")
    parser.add_argument("--team", default=None, help="Print only this team.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    provider = get_provider(args.season, refresh=args.refresh)
    lo, hi = provider.date_range
    print("season={} team-games={} teams={} dates={}..{}".format(
        args.season, provider.n_team_games, len(provider.teams),
        lo.date() if lo is not None else "?", hi.date() if hi is not None else "?"))

    as_of = args.date or (hi + pd.Timedelta(days=1))
    stats = provider.as_of(as_of)
    print("as-of {}: {} teams with prior games".format(
        pd.Timestamp(as_of).date(), len(stats)))
    if args.team:
        print(json.dumps(stats.get(args.team, {}), indent=2, sort_keys=True))
    else:
        print(json.dumps(describe_league(stats), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
