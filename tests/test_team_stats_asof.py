"""Guards for the point-in-time opponent context built in Phase 0.

The whole reason ``scripts/team_stats_asof.py`` exists is that a *season*
aggregate leaks: describing a November game with April's defensive numbers
tells the model something nobody knew that night. These tests pin the four
properties that make it non-leaky and non-silent:

1. ``as_of`` is **strictly** before — same-day games are excluded.
2. The dict keys are exactly the lowercase set ``extract_opp_stats`` reads
   (uppercase silently returns the league-average fallbacks instead).
3. Ratings land in plausible NBA ranges rather than being quietly degenerate.
4. A team with no prior games is **absent**, not present with NaNs.

Everything here is hermetic: a synthetic six-team league, no network, no
dependency on ``cache/`` (which is gitignored).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from nba_evaluator import FeatureEngineer  # noqa: E402

from team_stats_asof import (  # noqa: E402
    OPP_STAT_KEYS,
    PLAUSIBLE_RANGES,
    TeamStatsProvider,
    aggregate_prior_games,
    build_paired_team_games,
)

TEAMS = ("BOS", "LAL", "DEN", "MIA", "NYK", "PHX")
FIRST_DAY = "2024-10-22"


def _team_box(rng):
    """One realistic team box score line (2024-25 league averages-ish)."""
    fga = int(rng.integers(80, 95))
    fgm = int(rng.binomial(fga, 0.47))
    fg3a = int(rng.integers(30, 45))
    fg3m = int(rng.binomial(fg3a, 0.36))
    fta = int(rng.integers(16, 28))
    ftm = int(rng.binomial(fta, 0.78))
    oreb = int(rng.integers(7, 14))
    dreb = int(rng.integers(28, 38))
    tov = int(rng.integers(10, 18))
    return {
        "MIN": 240,
        "FGM": fgm, "FGA": fga, "FG3M": fg3m, "FG3A": fg3a,
        "FTM": ftm, "FTA": fta, "OREB": oreb, "DREB": dreb,
        "REB": oreb + dreb, "TOV": tov,
        "AST": int(rng.integers(20, 33)),
        "PTS": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
    }


def synthetic_team_log(n_days=20, seed=7):
    """A six-team league: three games a night, two rows per game."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(FIRST_DAY, periods=n_days, freq="2D")
    rows = []
    for d_i, date in enumerate(dates):
        pairs = ((0, 1), (2, 3), (4, 5)) if d_i % 2 == 0 else ((0, 3), (2, 5), (4, 1))
        for g_i, (a, b) in enumerate(pairs):
            game_id = "00224{:03d}{:02d}".format(d_i, g_i)
            for home, away in ((a, b), (b, a)):
                rows.append({
                    "SEASON_ID": "22024",
                    "TEAM_ABBREVIATION": TEAMS[home],
                    "GAME_ID": game_id,
                    "GAME_DATE": date.strftime("%Y-%m-%d"),
                    "MATCHUP": "{} vs. {}".format(TEAMS[home], TEAMS[away]),
                    **_team_box(rng),
                })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def raw_log():
    return synthetic_team_log()


@pytest.fixture(scope="module")
def provider(raw_log):
    return TeamStatsProvider("2024-25", paired=build_paired_team_games(raw_log))


# ── Pairing ───────────────────────────────────────────────────────────────────


class TestPairing:
    def test_every_game_yields_two_paired_rows(self, raw_log):
        paired = build_paired_team_games(raw_log)
        assert len(paired) == len(raw_log)
        assert (paired.groupby("GAME_ID").size() == 2).all()

    def test_opponent_columns_are_the_other_team(self, raw_log):
        paired = build_paired_team_games(raw_log)
        assert (paired["TEAM_ABBREVIATION"] != paired["TEAM_ABBREVIATION_OPP"]).all()
        # Own PTS of one row must equal opponent PTS of its partner row.
        for _, game in paired.groupby("GAME_ID"):
            a, b = game.iloc[0], game.iloc[1]
            assert a["PTS"] == b["PTS_OPP"]
            assert b["PTS"] == a["PTS_OPP"]

    def test_lopsided_game_id_is_rejected_not_silently_paired(self, raw_log):
        broken = raw_log.iloc[1:].copy()  # first GAME_ID now has a single row
        with pytest.raises(ValueError, match="exactly 2 rows per GAME_ID"):
            build_paired_team_games(broken)

    def test_missing_column_is_rejected(self, raw_log):
        with pytest.raises(ValueError, match="missing columns"):
            build_paired_team_games(raw_log.drop(columns=["TOV"]))


# ── As-of semantics: the actual point of the module ───────────────────────────


class TestAsOfIsStrictlyBefore:
    def test_first_day_has_no_prior_games_at_all(self, provider):
        assert provider.as_of(FIRST_DAY) == {}

    def test_same_day_games_are_excluded(self, provider, raw_log):
        """A team's own game on date D must not inform its context on date D."""
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        second, third = dates[1], dates[2]
        # Context on day 3 must equal context built from days 1-2 only, i.e.
        # asking as-of day 3 must not have absorbed day 3.
        paired = build_paired_team_games(raw_log)
        manual = aggregate_prior_games(paired[paired["GAME_DATE"] < third])
        assert provider.as_of(third) == manual
        # And it must differ from the (leaky) inclusive version.
        inclusive = aggregate_prior_games(paired[paired["GAME_DATE"] <= third])
        assert provider.as_of(third) != inclusive
        # Day 2's context is built from day 1 alone.
        one_day = aggregate_prior_games(paired[paired["GAME_DATE"] < second])
        assert provider.as_of(second) == one_day

    def test_later_games_never_influence_an_earlier_date(self, raw_log):
        """Truncating the season after date D leaves as-of(D) unchanged."""
        paired = build_paired_team_games(raw_log)
        cutoff = pd.Timestamp(sorted(paired["GAME_DATE"].unique())[10])
        full = TeamStatsProvider("2024-25", paired=paired)
        truncated = TeamStatsProvider(
            "2024-25", paired=paired[paired["GAME_DATE"] < cutoff].reset_index(drop=True)
        )
        assert full.as_of(cutoff) == truncated.as_of(cutoff)

    def test_context_accumulates_games_over_the_season(self, provider, raw_log):
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        early = provider.as_of(dates[3])
        late = provider.as_of(dates[-1])
        assert set(early) and set(early) <= set(late)
        assert early["BOS"] != late["BOS"]

    def test_accepts_str_timestamp_and_datetime(self, provider, raw_log):
        d = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())[5]
        as_str = provider.as_of(pd.Timestamp(d).strftime("%Y-%m-%d"))
        assert as_str == provider.as_of(pd.Timestamp(d))
        assert as_str == provider.as_of(pd.Timestamp(d).to_pydatetime())

    def test_repeat_calls_are_memoized_to_the_same_object(self, provider):
        first = provider.as_of("2025-01-01")
        assert provider.as_of("2025-01-01") is first


# ── Cold start ────────────────────────────────────────────────────────────────


class TestColdStart:
    def test_team_with_zero_prior_games_is_absent_not_nan(self, raw_log):
        """Absent lets extract_opp_stats fall back; NaN would poison the model."""
        paired = build_paired_team_games(raw_log)
        dates = sorted(paired["GAME_DATE"].unique())
        # PHX only plays from day 1, so drop its early games to simulate a
        # team that has not yet appeared.
        no_phx = paired[
            (paired["TEAM_ABBREVIATION"] != "PHX")
            | (paired["GAME_DATE"] > pd.Timestamp(dates[5]))
        ]
        stats = TeamStatsProvider("2024-25", paired=no_phx.reset_index(drop=True))
        early = stats.as_of(dates[3])
        assert "PHX" not in early
        assert all(not np.isnan(v) for ctx in early.values() for v in ctx.values())

    def test_absent_team_falls_back_to_league_average_defaults(self, provider):
        opp = FeatureEngineer.extract_opp_stats(provider.as_of(FIRST_DAY), "BOS")
        assert opp["opp_def_rating"] == 110
        assert opp["opp_pace"] == 100
        assert opp["opp_ast_allowed"] == 25

    def test_zero_possession_team_is_omitted(self, raw_log):
        paired = build_paired_team_games(raw_log)
        degenerate = paired[paired["TEAM_ABBREVIATION"] == "BOS"].copy()
        for col in ("FGA", "TOV", "FTA", "OREB"):
            degenerate[col] = 0
        assert aggregate_prior_games(degenerate) == {}


# ── The lowercase-key trap ────────────────────────────────────────────────────


class TestKeysMatchExtractOppStats:
    def test_keys_are_exactly_the_lowercase_set(self, provider, raw_log):
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        stats = provider.as_of(dates[-1])
        assert stats, "expected a populated snapshot"
        for team, ctx in stats.items():
            assert set(ctx) == set(OPP_STAT_KEYS), team

    def test_every_key_is_consumed_no_default_survives(self, provider, raw_log):
        """Sentinel values must all appear downstream.

        ``extract_opp_stats`` reads lowercase keys; an uppercase (or misspelled)
        key returns the fallback with no error at all. Feeding sentinels proves
        every one of the nine is genuinely wired through.
        """
        sentinels = {key: 12345.0 + i for i, key in enumerate(OPP_STAT_KEYS)}
        opp = FeatureEngineer.extract_opp_stats({"BOS": sentinels}, "BOS")
        assert sorted(opp.values()) == sorted(sentinels.values())

    def test_real_snapshot_produces_no_fallback_values(self, provider, raw_log):
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        stats = provider.as_of(dates[-1])
        opp = FeatureEngineer.extract_opp_stats(stats, "BOS")
        defaults = FeatureEngineer.extract_opp_stats({}, "BOS")
        assert opp != defaults
        for key, value in opp.items():
            assert value != defaults[key], key


# ── Sanity of the numbers themselves ──────────────────────────────────────────


class TestPlausibleRanges:
    def test_full_season_ratings_are_in_nba_ranges(self, provider, raw_log):
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        stats = provider.as_of(pd.Timestamp(dates[-1]) + pd.Timedelta(days=1))
        assert len(stats) == len(TEAMS)
        for team, ctx in stats.items():
            for key, (lo, hi) in PLAUSIBLE_RANGES.items():
                assert lo <= ctx[key] <= hi, "{} {}={}".format(team, key, ctx[key])

    def test_league_net_rating_sums_to_about_zero(self, provider, raw_log):
        """Every point scored is a point allowed — a real closure check."""
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        stats = provider.as_of(pd.Timestamp(dates[-1]) + pd.Timedelta(days=1))
        net = sum(c["net_rating"] for c in stats.values()) / len(stats)
        assert abs(net) < 1.0

    def test_oreb_and_dreb_rates_are_complementary(self, provider, raw_log):
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        stats = provider.as_of(pd.Timestamp(dates[-1]) + pd.Timedelta(days=1))
        mean_oreb = sum(c["oreb_pct"] for c in stats.values()) / len(stats)
        mean_dreb = sum(c["dreb_pct"] for c in stats.values()) / len(stats)
        assert abs((mean_oreb + mean_dreb) - 1.0) < 0.05

    def test_ratings_are_finite(self, provider, raw_log):
        dates = sorted(pd.to_datetime(raw_log["GAME_DATE"]).unique())
        for date in (dates[2], dates[len(dates) // 2], dates[-1]):
            for ctx in provider.as_of(date).values():
                assert all(np.isfinite(v) for v in ctx.values())

    def test_overtime_minutes_do_not_inflate_pace(self, raw_log):
        """Team MIN is 5 x game length, so OT must lengthen the denominator."""
        paired = build_paired_team_games(raw_log)
        bos = paired[paired["TEAM_ABBREVIATION"] == "BOS"].copy()
        regulation = aggregate_prior_games(bos)["BOS"]["pace"]
        ot = bos.copy()
        ot["MIN"] = 265  # every game went to overtime
        assert aggregate_prior_games(ot)["BOS"]["pace"] < regulation
