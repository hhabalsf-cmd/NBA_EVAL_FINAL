"""Gate 0 guards for the backtest harness itself.

Two defects this pins, both of which failed *silently*:

1. The harness called ``create_features(log)`` with no ``team_stats``, so 12 of
   the declared ``FEATURE_COLS`` were never built. ``predict`` substitutes 0
   for anything absent, so the harness was measuring a **69-feature** model
   while production serves a wider one. With opponent context supplied the
   harness builds **81** — and since Phase 2 removed the 5 declared-but-never-
   built entries (2 INJURIES + 3 VEGAS), 81 is now also the declared width, so
   declared and built finally agree.
2. The per-player game-log cache must be read without touching the network,
   or a cold run is not resumable and a warm run is not fast.

Hermetic: synthetic player log, synthetic team log, no ``cache/`` dependency.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import nba_evaluator as ev  # noqa: E402

import backtest_unbiased as bt  # noqa: E402
from team_stats_asof import TeamStatsProvider, build_paired_team_games  # noqa: E402

from tests.test_team_stats_asof import TEAMS, synthetic_team_log  # noqa: E402

# The 12 declared features the harness never built before Phase 0.
FEATURES_UNBUILT_WITHOUT_TEAM_STATS = frozenset({
    "OPP_DEF_RATING_NORM", "OPP_PACE_NORM", "OPP_AST_ALLOWED_NORM",
    "OPP_OFF_RATING_NORM", "OPP_NET_RATING_NORM", "OPP_EFG_PCT_NORM",
    "OPP_OREB_PCT_NORM", "OPP_DREB_PCT_NORM", "OPP_DEF_RATING_ROLL10",
    "ROLL_5_USG", "ROLL_10_USG", "OREB_RATE_x_OPP_OREB",
})

# Declared but never built by create_features under ANY argument. Phase 2
# removed all five (INJURIES_TEAM/OPP and the three VEGAS_*) from both
# FEATURE_COLS and get_prediction_features, so this set is now empty and the
# emptiness is itself the assertion: a future feature declared without being
# built would repopulate it and fail ``test_no_declared_feature_is_dead``.
DEAD_FEATURES = frozenset()

# Names removed in Phase 2. Re-declaring any of them without also building it
# in create_features would silently reintroduce a zero-filled column.
REMOVED_IN_PHASE_2 = frozenset({
    "INJURIES_TEAM", "INJURIES_OPP",
    "VEGAS_GAME_TOTAL_NORM", "VEGAS_SPREAD_NORM", "VEGAS_IMPLIED_TEAM_TOTAL_NORM",
})

WIDTH_WITHOUT_TEAM_STATS = 69
WIDTH_WITH_TEAM_STATS = 81
DECLARED_WIDTH = 81


def synthetic_player_log(n=70, seed=3):
    """A one-season player log whose opponents are the synthetic league."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-10-22", periods=n, freq="2D")
    rows = []
    for i, date in enumerate(dates):
        opp = TEAMS[1:][i % (len(TEAMS) - 1)]
        fga = int(rng.integers(14, 26))
        fgm = int(rng.binomial(fga, 0.5))
        fg3a = int(rng.integers(3, 10))
        fg3m = int(rng.binomial(fg3a, 0.36))
        fta = int(rng.integers(3, 11))
        ftm = int(rng.binomial(fta, 0.8))
        oreb, dreb = int(rng.integers(1, 5)), int(rng.integers(4, 11))
        rows.append({
            "SEASON_ID": "22024",
            "Player_ID": 999,
            "Game_ID": "00224{:05d}".format(i),
            "GAME_DATE": date.strftime("%Y-%m-%d"),
            "MATCHUP": "{} {} {}".format(TEAMS[0], "vs." if i % 2 else "@", opp),
            "WL": "W",
            "MIN": int(rng.integers(28, 39)),
            "FGM": fgm, "FGA": fga, "FG_PCT": fgm / fga,
            "FG3M": fg3m, "FG3A": fg3a, "FG3_PCT": fg3m / max(fg3a, 1),
            "FTM": ftm, "FTA": fta, "FT_PCT": ftm / max(fta, 1),
            "OREB": oreb, "DREB": dreb, "REB": oreb + dreb,
            "AST": int(rng.integers(3, 13)),
            "STL": int(rng.integers(0, 4)), "BLK": int(rng.integers(0, 4)),
            "TOV": int(rng.integers(1, 6)), "PF": int(rng.integers(0, 5)),
            "PTS": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
            "PLUS_MINUS": int(rng.integers(-15, 16)),
            "VIDEO_AVAILABLE": 1,
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def player_log():
    return synthetic_player_log()


@pytest.fixture(scope="module")
def provider():
    return TeamStatsProvider(
        "2024-25", paired=build_paired_team_games(synthetic_team_log(n_days=40))
    )


@pytest.fixture(scope="module")
def frame_without(player_log):
    return ev.FeatureEngineer.create_features(player_log)


@pytest.fixture(scope="module")
def frame_with(player_log, provider):
    as_of = player_log["GAME_DATE"].iloc[-1]
    return ev.FeatureEngineer.create_features(
        player_log, team_stats=provider.as_of(as_of)
    )


def served_vector(frame):
    """The vector ``MLPredictor.predict`` would build — zero-filling absences."""
    return np.array(
        [
            float(frame[c].values[-1]) if c in frame.columns else 0.0
            for c in ev.MLPredictor.FEATURE_COLS
        ],
        dtype=float,
    )


# ── The headline gate ─────────────────────────────────────────────────────────


class TestBuiltFeatureWidth:
    def test_without_team_stats_the_harness_measured_69(self, frame_without):
        assert bt.built_feature_count(frame_without) == WIDTH_WITHOUT_TEAM_STATS

    def test_with_point_in_time_context_the_harness_measures_81(self, frame_with):
        assert bt.built_feature_count(frame_with) == WIDTH_WITH_TEAM_STATS

    def test_exactly_the_expected_12_features_were_unbuilt(self, frame_without):
        missing = {
            c for c in ev.MLPredictor.FEATURE_COLS if c not in frame_without.columns
        }
        assert missing == FEATURES_UNBUILT_WITHOUT_TEAM_STATS

    def test_no_declared_feature_is_dead(self, frame_with):
        """Every name in FEATURE_COLS is actually built. Phase 2's headline."""
        missing = {
            c for c in ev.MLPredictor.FEATURE_COLS if c not in frame_with.columns
        }
        assert missing == DEAD_FEATURES == frozenset()

    def test_declared_width_matches_trained_width(self):
        assert len(ev.MLPredictor.FEATURE_COLS) == DECLARED_WIDTH == WIDTH_WITH_TEAM_STATS

    def test_removed_features_stay_removed(self):
        assert REMOVED_IN_PHASE_2.isdisjoint(ev.MLPredictor.FEATURE_COLS)

    def test_width_arithmetic_is_self_consistent(self, frame_with):
        declared = len(ev.MLPredictor.FEATURE_COLS)
        assert declared - len(DEAD_FEATURES) == WIDTH_WITH_TEAM_STATS
        assert (
            WIDTH_WITH_TEAM_STATS - WIDTH_WITHOUT_TEAM_STATS
            == len(FEATURES_UNBUILT_WITHOUT_TEAM_STATS) - len(DEAD_FEATURES)
        )


class TestOppFeaturesAreNonZeroWhenServed:
    def test_every_opp_feature_is_present_and_non_zero(self, frame_with):
        opp = [c for c in ev.MLPredictor.FEATURE_COLS if c.startswith("OPP_")]
        assert opp, "expected OPP_* features in FEATURE_COLS"
        last = frame_with.iloc[-1]
        for col in opp:
            assert col in frame_with.columns, col
            value = float(last[col])
            assert np.isfinite(value), col
            assert value != 0.0, col

    def test_opp_features_are_all_zero_without_team_stats(self, frame_without):
        """The defect, pinned: the old harness served a zeroed opponent block."""
        vec = served_vector(frame_without)
        for i, col in enumerate(ev.MLPredictor.FEATURE_COLS):
            if col.startswith("OPP_"):
                assert vec[i] == 0.0, col

    def test_fourteen_served_entries_gain_signal(self, frame_without, frame_with):
        """12 newly built + POSITION_x_OPP_DEF/PACE, which were constant zero."""
        before, after = served_vector(frame_without), served_vector(frame_with)
        changed = {
            col
            for col, a, b in zip(ev.MLPredictor.FEATURE_COLS, before, after)
            if not np.isclose(a, b, equal_nan=True)
        }
        expected = (FEATURES_UNBUILT_WITHOUT_TEAM_STATS - DEAD_FEATURES) | {
            "POSITION_x_OPP_DEF", "POSITION_x_OPP_PACE",
        }
        assert changed == expected
        assert len(changed) == 14

    def test_usage_features_are_real_rates_not_placeholders(self, frame_with):
        for col in ("ROLL_5_USG", "ROLL_10_USG"):
            value = float(frame_with.iloc[-1][col])
            assert 5.0 < value < 80.0, "{}={}".format(col, value)

    def test_position_interactions_track_the_opponent(self, frame_with):
        last = frame_with.iloc[-1]
        pos = float(last["POSITION_ORD"])
        assert np.isclose(
            float(last["POSITION_x_OPP_DEF"]), pos * float(last["OPP_DEF_RATING_NORM"])
        )
        assert np.isclose(
            float(last["POSITION_x_OPP_PACE"]), pos * float(last["OPP_PACE_NORM"])
        )


class TestPointInTimeContextVariesAcrossReplaySteps:
    def test_early_and_late_as_of_dates_give_different_served_vectors(
        self, player_log, provider
    ):
        """If the harness reused one snapshot, these would be identical."""
        dates = list(player_log["GAME_DATE"])
        early = ev.FeatureEngineer.create_features(
            player_log, team_stats=provider.as_of(dates[20])
        )
        late = ev.FeatureEngineer.create_features(
            player_log, team_stats=provider.as_of(dates[-1])
        )
        assert not np.allclose(served_vector(early), served_vector(late))

    def test_team_stats_does_not_change_row_count_or_ordering(
        self, frame_without, frame_with
    ):
        """The harness slices both frames by position — they must line up."""
        assert len(frame_without) == len(frame_with)
        assert list(frame_without.index) == list(frame_with.index)
        assert list(frame_without["GAME_DATE"]) == list(frame_with["GAME_DATE"])


# ── Cache contract ────────────────────────────────────────────────────────────


class _NoNetwork:
    """Stands in for nba_api.stats.endpoints; explodes if anything reaches it."""

    def __getattr__(self, name):
        raise AssertionError(
            "network fetch attempted ({}) — the cache should have served this".format(name)
        )


@pytest.fixture
def cache_root(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "LOG_CACHE_ROOT", tmp_path / "backtest_logs")
    return tmp_path / "backtest_logs"


class TestGameLogCache:
    def test_cache_path_matches_the_documented_contract(self, cache_root):
        path = bt.log_cache_path("203999", "2024-25")
        assert path == cache_root / "2024-25" / "203999.parquet"

    def test_cached_read_never_touches_the_network(
        self, player_log, cache_root, monkeypatch
    ):
        path = bt.log_cache_path("203999", "2024-25")
        bt.write_log_cache(bt.normalize_player_log(player_log), path)
        monkeypatch.setitem(sys.modules, "nba_api.stats.endpoints", _NoNetwork())
        got = bt.fetch_player_log("203999", "2024-25")
        assert len(got) == len(player_log)
        assert list(got["GAME_DATE"]) == list(player_log["GAME_DATE"])

    def test_refresh_cache_bypasses_the_cached_copy(
        self, player_log, cache_root, monkeypatch
    ):
        bt.write_log_cache(
            bt.normalize_player_log(player_log), bt.log_cache_path("203999", "2024-25")
        )
        monkeypatch.setitem(sys.modules, "nba_api.stats.endpoints", _NoNetwork())
        with pytest.raises(AssertionError, match="network fetch attempted"):
            bt.fetch_player_log("203999", "2024-25", refresh_cache=True)

    def test_normalized_log_is_sorted_ascending_with_string_dates(self, player_log):
        shuffled = player_log.sample(frac=1.0, random_state=1)
        out = bt.normalize_player_log(shuffled)
        assert list(out["GAME_DATE"]) == sorted(out["GAME_DATE"])
        assert isinstance(out["GAME_DATE"].iloc[0], str)
        assert len(out["GAME_DATE"].iloc[0]) == len("YYYY-MM-DD")

    def test_write_is_atomic_leaving_no_tmp_file(self, player_log, cache_root):
        path = bt.log_cache_path("203999", "2024-25")
        bt.write_log_cache(bt.normalize_player_log(player_log), path)
        assert path.exists()
        assert not path.with_suffix(".parquet.tmp").exists()
        assert not any(p.suffix == ".tmp" for p in path.parent.iterdir())

    def test_partial_run_is_resumable(self, player_log, cache_root, monkeypatch):
        """Half the fleet cached: those reads must succeed offline."""
        for pid in ("111", "222"):
            bt.write_log_cache(
                bt.normalize_player_log(player_log), bt.log_cache_path(pid, "2024-25")
            )
        monkeypatch.setitem(sys.modules, "nba_api.stats.endpoints", _NoNetwork())
        for pid in ("111", "222"):
            assert len(bt.fetch_player_log(pid, "2024-25")) == len(player_log)
        with pytest.raises(AssertionError):
            bt.fetch_player_log("333", "2024-25")

    def test_corrupt_cache_falls_through_to_a_fetch(self, cache_root, monkeypatch):
        path = bt.log_cache_path("203999", "2024-25")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a parquet file")
        monkeypatch.setitem(sys.modules, "nba_api.stats.endpoints", _NoNetwork())
        with pytest.warns(UserWarning, match="unreadable game-log cache"):
            with pytest.raises(AssertionError, match="network fetch attempted"):
                bt.fetch_player_log("203999", "2024-25")


class TestWorkerNeverFetchesTeamStats:
    def test_provider_refuses_to_fetch_when_cache_is_cold(self, tmp_path, monkeypatch):
        """Workers open the team log read-only; main() warms it first."""
        import team_stats_asof as tsa

        monkeypatch.setattr(tsa, "CACHE_ROOT", tmp_path / "team_logs")
        with pytest.raises(FileNotFoundError, match="no cached team game log"):
            tsa.load_team_game_log("2024-25", allow_fetch=False)

    def test_evaluate_player_skips_cleanly_without_team_context(
        self, player_log, tmp_path, monkeypatch
    ):
        import team_stats_asof as tsa

        monkeypatch.setattr(tsa, "CACHE_ROOT", tmp_path / "team_logs")
        result = bt.evaluate_player(
            "Test Player", "999", player_log, train_games=60, quick=True
        )
        assert result.skipped
        assert "team context unavailable" in (result.reason or "")
