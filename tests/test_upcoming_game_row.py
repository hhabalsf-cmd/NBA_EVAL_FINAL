"""Phase 1 guards: the model must serve the UPCOMING game, not the last one.

Before this phase ``create_features`` stored row *i* = mean(games *i-k..i-1*)
and ``get_prediction_features`` read ``df.iloc[-1]`` of the already-shifted
column -- so the game being predicted was handed mean(*n-k-1..n-2*) and the most
recent completed game was excluded from 51 of 86 features. On Nikola Jokic's
real 2024-25 log that was 36.2 served where 27.6 was correct: 8.6 points of
error on one feature.

The fix appends a synthetic row for the upcoming game before the rolling
windows are built, so ``iloc[-1]`` genuinely is the next game. These tests pin:

1. the served rolling value is mean(*n-k..n-1*), the direct inverse of the old
   behaviour (``TestServedRollingIsLagOne``);
2. nothing the synthetic row carries can reach the served vector
   (``TestSyntheticRowCannotContaminate``);
3. the off-by-one counters compensating for the old convention are gone and are
   not double-counted (``TestNextGameCounters``);
4. the row is invisible to everything that summarises completed games --
   ``update``'s "any new games?" short-circuit above all
   (``TestUpcomingRowIsInvisibleToCompletedGameStats``);
5. ``estimate_minutes``, which reads ``ROLL_20_MIN_NUMERIC`` -- a column that is
   NOT in ``FEATURE_COLS`` and is therefore missed by any list-scoped fix --
   picks the fix up for free (``TestEstimateMinutes``).
"""
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

import nba_evaluator as ev
from nba_evaluator import (
    SAME_GAME_RATIO_DEFAULTS,
    UPCOMING_GAME_FLAG,
    FeatureEngineer,
    MLPredictor,
    drop_upcoming_rows,
    has_upcoming_row,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
JOKIC_LOG = REPO_ROOT / "cache" / "backtest_logs" / "2024-25" / "203999.parquet"


def _log(n=40, seed=11, teams=None, start="2024-10-25"):
    """Synthetic game log in NBA-API shape. Mirrors test_leakage_guards._log."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="2D")
    rows = []
    for i, d in enumerate(dates):
        team = teams[i] if teams else "LAL"
        fga = int(rng.integers(12, 24))
        fgm = int(rng.binomial(fga, 0.48))
        fg3a = int(rng.integers(4, 11))
        fg3m = int(rng.binomial(fg3a, 0.37))
        fta = int(rng.integers(2, 9))
        ftm = int(rng.binomial(fta, 0.8))
        oreb, dreb = int(rng.integers(0, 4)), int(rng.integers(3, 9))
        mins = float(rng.uniform(28, 38))
        rows.append({
            "SEASON": "2024-25", "SEASON_ID": "22024", "GAME_DATE": d,
            "Game_ID": "002240{:04d}".format(i),
            "MATCHUP": f"{team} vs. BOS" if i % 2 else f"{team} @ BOS",
            "WL": "W", "MIN": mins, "MIN_NUMERIC": mins,
            "PTS": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
            "REB": oreb + dreb, "AST": int(rng.integers(3, 12)),
            "FGM": fgm, "FGA": fga, "FG3M": fg3m, "FG3A": fg3a,
            "FTM": ftm, "FTA": fta, "OREB": oreb, "DREB": dreb,
            "STL": int(rng.integers(0, 4)), "BLK": int(rng.integers(0, 3)),
            "TOV": int(rng.integers(0, 6)), "PF": int(rng.integers(0, 5)),
            "PLUS_MINUS": int(rng.integers(-15, 16)),
        })
    return pd.DataFrame(rows)


def _next_game(log, opponent="OKC", is_home=False, days_later=2, team="LAL"):
    """A ``get_player_next_game``-shaped dict for the game after ``log``."""
    last = pd.to_datetime(log["GAME_DATE"]).max()
    return {
        "matchup": f"{team} vs. {opponent}" if is_home else f"{team} @ {opponent}",
        "game_date": last + pd.Timedelta(days=days_later),
        "is_home": 1 if is_home else 0,
        "opponent": opponent,
    }


def _serve(df, opponent="OKC", is_home=0, team="LAL"):
    return FeatureEngineer.get_prediction_features(
        df, is_home=is_home, opponent=opponent,
        player_info={"team_abbrev": team, "player_name": "T"},
    )


# ── 1. The staleness defect, inverted ────────────────────────────────────────

class TestServedRollingIsLagOne:
    """mean(n-k..n-1), NOT mean(n-k-1..n-2)."""

    @pytest.mark.parametrize("stat,window", [
        ("PTS", 5), ("PTS", 10), ("PTS", 20),
        ("REB", 5), ("AST", 5), ("MIN_NUMERIC", 20),
    ])
    def test_served_rolling_is_the_mean_of_the_last_k_completed_games(self, stat, window):
        # seed 1 is chosen so correct != stale for every (stat, window) pair --
        # otherwise the assertion below could pass on a coincidence.
        log = _log(n=40, seed=1)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        served = df[f"ROLL_{window}_{stat}"].iloc[-1]

        correct = log[stat].tail(window).mean()
        stale = log[stat].iloc[-window - 1:-1].mean()

        assert served == pytest.approx(correct), (
            f"ROLL_{window}_{stat} served {served}, expected mean of the last "
            f"{window} completed games ({correct})"
        )
        assert served != pytest.approx(stale), (
            "the fixture is degenerate -- correct and stale values coincide"
        )

    def test_the_defect_is_still_there_without_a_synthetic_row(self):
        """Negative control: no game_info, no synthetic row, old (stale) value."""
        log = _log(n=40)
        df = FeatureEngineer.create_features(log)
        assert df["ROLL_5_PTS"].iloc[-1] == pytest.approx(
            log["PTS"].iloc[-6:-1].mean()
        )

    @pytest.mark.skipif(not JOKIC_LOG.exists(), reason="backtest log cache absent")
    def test_jokic_2024_25_real_log(self):
        """The reproduction the phase was scoped around: 36.2 -> 27.6."""
        log = pd.read_parquet(JOKIC_LOG)
        stale = FeatureEngineer.create_features(log)["ROLL_5_PTS"].iloc[-1]
        fresh = FeatureEngineer.create_features(
            log, game_info=_next_game(log, opponent="OKC", team="DEN"),
        )["ROLL_5_PTS"].iloc[-1]

        assert stale == pytest.approx(36.2, abs=0.05)
        assert fresh == pytest.approx(27.6, abs=0.05)
        assert fresh == pytest.approx(log["PTS"].tail(5).mean())

    def test_the_whole_served_vector_moves_off_the_stale_value(self):
        """Not a one-feature fix: a large share of FEATURE_COLS changes value."""
        log = _log(n=40, seed=1)
        team_stats = {"BOS": {"def_rating": 105.0, "pace": 96.0},
                      "OKC": {"def_rating": 120.0, "pace": 106.0}}
        stale = _serve(FeatureEngineer.create_features(log, team_stats=team_stats))
        fresh = _serve(FeatureEngineer.create_features(
            log, game_info=_next_game(log), team_stats=team_stats))
        shared = [c for c in MLPredictor.FEATURE_COLS
                  if c in stale.columns and c in fresh.columns]
        moved = [
            c for c in shared
            if not np.isclose(
                float(stale[c].iloc[0]), float(fresh[c].iloc[0]), equal_nan=True
            )
        ]
        assert len(moved) >= 40, f"only {len(moved)} of {len(shared)} features moved"


# ── 2. The synthetic row cannot leak ─────────────────────────────────────────

class TestSyntheticRowCannotContaminate:
    def test_placeholder_box_score_never_reaches_the_served_vector(self):
        """Two upcoming rows with wildly different contents must serve the SAME
        vector. Every rolling/EMA/std feature is .shift(1)-ed and the five
        same-game ratios are lag-1 shifted, so the appended row's own numbers
        are never read back out. If an unshifted ``.rolling(`` call is ever
        added to create_features, this is what catches it.

        Both variants must keep the IS_UPCOMING_GAME flag: without it
        create_features treats the row as a real completed game and serve
        correctly falls back to the legacy `_CURR` convention, which DOES read
        the row's own box score."""
        log = _log(n=40, seed=1)
        info = _next_game(log)

        base = FeatureEngineer.append_upcoming_game_row(log, info)
        assert base[UPCOMING_GAME_FLAG].iloc[-1]

        quiet = base.copy()                       # MIN=1, all-NaN box score
        loud = base.copy()                        # MIN=48, every stat 99
        keep = {"SEASON", "SEASON_ID", "GAME_DATE", "MATCHUP", "WL", "Game_ID",
                UPCOMING_GAME_FLAG}
        last = loud.index[-1]
        for col in loud.columns:
            if col not in keep:
                loud.at[last, col] = 99.0
        loud.at[last, "MIN"] = 48.0
        loud.at[last, "MIN_NUMERIC"] = 48.0
        loud.at[last, "WL"] = "W"

        a = _serve(FeatureEngineer.create_features(quiet))
        b = _serve(FeatureEngineer.create_features(loud))
        assert list(a.columns) == list(b.columns)
        contaminated = [
            c for c in a.columns
            if not np.isclose(float(a[c].iloc[0]), float(b[c].iloc[0]), equal_nan=True)
        ]
        assert not contaminated, f"upcoming row leaked into: {contaminated}"

    def test_no_nan_in_the_served_vector(self):
        log = _log(n=40)
        served = _serve(FeatureEngineer.create_features(log, game_info=_next_game(log)))
        nans = [c for c in served.columns if pd.isna(served[c].iloc[0])]
        assert not nans, f"NaN served for: {nans}"

    def test_synthetic_row_survives_the_dnp_filter(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        assert len(df) == len(log) + 1
        assert has_upcoming_row(df)
        assert df[UPCOMING_GAME_FLAG].sum() == 1


# ── 3. Schedule context resolves to the UPCOMING opponent ────────────────────

class TestUpcomingScheduleContext:
    def test_home_away_and_opponent_come_from_the_next_game(self):
        log = _log(n=40)  # last logged game is vs. BOS
        df = FeatureEngineer.create_features(
            log, game_info=_next_game(log, opponent="OKC", is_home=False)
        )
        assert df["IS_HOME"].iloc[-1] == 0
        assert df["OPPONENT"].iloc[-1] == "OKC"
        assert df["PLAYER_TEAM"].iloc[-1] == "LAL"

    def test_position_interactions_use_the_upcoming_opponent(self):
        """POSITION_x_OPP_DEF multiplied against LAST night's opponent before."""
        log = _log(n=40)
        team_stats = {"BOS": {"def_rating": 105.0, "pace": 96.0},
                      "OKC": {"def_rating": 120.0, "pace": 106.0}}
        df = FeatureEngineer.create_features(
            log, game_info=_next_game(log, opponent="OKC"),
            player_info={"position": "Center"}, team_stats=team_stats,
        )
        assert df["OPP_DEF_RATING"].iloc[-1] == pytest.approx(120.0)
        assert df["POSITION_x_OPP_DEF"].iloc[-1] == pytest.approx(4 * (120.0 - 110) / 5)

    def test_days_rest_is_the_gap_to_the_scheduled_game(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(
            log, game_info=_next_game(log, days_later=3)
        )
        assert df["DAYS_REST"].iloc[-1] == pytest.approx(3.0)
        assert FeatureEngineer.serve_days_rest(df) == 3

    def test_serve_days_rest_falls_back_without_a_synthetic_row(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log)
        last = pd.to_datetime(df["GAME_DATE"].iloc[-1])
        assert FeatureEngineer.serve_days_rest(
            df, now=last + pd.Timedelta(days=2)
        ) == 2

    def test_stale_or_missing_game_info_is_ignored(self):
        """A game_info describing a game already in the log would sort into the
        middle of the frame and corrupt every rolling window."""
        log = _log(n=40)
        last = pd.to_datetime(log["GAME_DATE"]).max()
        for info in (
            None, {}, {"matchup": "LAL @ OKC"},
            {"matchup": "LAL @ OKC", "game_date": last},                 # same day
            {"matchup": "LAL @ OKC", "game_date": last - pd.Timedelta(days=5)},
            {"matchup": "", "game_date": last + pd.Timedelta(days=2)},
        ):
            df = FeatureEngineer.create_features(log, game_info=info)
            assert len(df) == len(log), f"appended for {info}"
            assert not has_upcoming_row(df)


# ── 4. Off-by-one counters ───────────────────────────────────────────────────

class TestNextGameCounters:
    def test_games_this_season_is_not_double_counted(self):
        log = _log(n=40)
        with_row = FeatureEngineer.create_features(log, game_info=_next_game(log))
        without = FeatureEngineer.create_features(log)
        assert _serve(with_row)["GAMES_THIS_SEASON"].iloc[0] == 41
        assert _serve(without)["GAMES_THIS_SEASON"].iloc[0] == 41

    def test_tenure_is_not_double_counted(self):
        teams = ["LAL"] * 30 + ["MIA"] * 5
        log = _log(n=35, teams=teams)
        info = _next_game(log, team="MIA")
        with_row = FeatureEngineer.create_features(log, game_info=info)
        without = FeatureEngineer.create_features(log)
        served_with = _serve(with_row, team="MIA")["GAMES_WITH_CURRENT_TEAM"].iloc[0]
        served_without = _serve(without, team="MIA")["GAMES_WITH_CURRENT_TEAM"].iloc[0]
        assert served_with == pytest.approx(5.0)
        assert served_with == pytest.approx(served_without)

    def test_tenure_resets_to_zero_on_the_debut_game_after_a_trade(self):
        log = _log(n=35, teams=["LAL"] * 35)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log, team="MIA"))
        assert df["GAMES_WITH_CURRENT_TEAM"].iloc[-1] == 0.0
        served = _serve(df, team="MIA")
        assert served["GAMES_WITH_CURRENT_TEAM"].iloc[0] == 0.0
        assert served["TEAM_CHANGED_RECENT"].iloc[0] == 1

    def test_current_team_games_helper_matches_the_served_value(self):
        """Both frame shapes must report the same next-game tenure: the
        synthetic row already carries it, the legacy frame needs the +1."""
        teams = ["LAL"] * 30 + ["MIA"] * 5
        log = _log(n=35, teams=teams)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log, team="MIA"))
        without = FeatureEngineer.create_features(log)
        assert MLPredictor._current_team_games(df) == 5
        assert MLPredictor._current_team_games(without) == 5
        served = _serve(df, team="MIA")["GAMES_WITH_CURRENT_TEAM"].iloc[0]
        assert served == pytest.approx(5.0)

    def test_current_season_games_counts_only_completed_games(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        # SEASON column present -> the count branch, not the iloc[-1] branch.
        assert MLPredictor._current_season_games(
            df.assign(SEASON=ev.get_current_season())
        ) == 40


# ── 5. Invisible to everything that summarises completed games ───────────────

class TestUpcomingRowIsInvisibleToCompletedGameStats:
    def test_drop_and_detect_helpers(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        assert has_upcoming_row(df)
        completed = drop_upcoming_rows(df)
        assert len(completed) == len(df) - 1
        assert not has_upcoming_row(completed)
        assert len(df) == len(log) + 1, "drop_upcoming_rows mutated its input"

    def test_recent_averages_stay_l10_not_l9(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        p = MLPredictor()
        p._update_recent_averages(df, stats=["PTS", "REB", "AST"])
        assert p.recent_averages["PTS"] == pytest.approx(log["PTS"].tail(10).mean())
        assert p.recent_averages_l5["PTS"] == pytest.approx(log["PTS"].tail(5).mean())
        assert p.season_averages["PTS"] == pytest.approx(log["PTS"].mean())

    @staticmethod
    def _stub_predictor(df, features=None, n_estimators=50):
        """A minimal fitted predictor.

        ``feature_names`` must cover every FEATURE_COLS entry the frame carries:
        update() force-retrains when the data offers a feature the model was
        never trained on, which would mask the behaviour under test.
        """
        if features is None:
            features = [f for f in MLPredictor.FEATURE_COLS if f in df.columns]
        p = MLPredictor(model_type="gradient_boost")
        completed = drop_upcoming_rows(df).dropna(subset=list(features) + ["PTS"])
        X = completed[features].values
        y = completed["PTS"].values
        scaler = StandardScaler().fit(X)
        model = GradientBoostingRegressor(n_estimators=n_estimators, random_state=0)
        model.fit(scaler.transform(X), y)
        p.models = {"PTS": model}
        p.feature_names = list(features)
        p.scalers = {"features": scaler}
        p.selected_features = None
        p.last_game_date = pd.to_datetime(
            completed["GAME_DATE"]
        ).max().strftime("%Y-%m-%d")
        p.trained_at = datetime.now().strftime("%Y-%m-%d")
        return p

    def test_update_does_not_refit_when_there_are_no_genuinely_new_games(self, capsys):
        """The bug this guards: a future-dated row makes `new_games` non-empty on
        EVERY serve call, so the model warm-starts +20 estimators each time and
        trips _needs_full_retrain within a handful of predictions."""
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        p = self._stub_predictor(df)

        before = p.models["PTS"].n_estimators
        assert p.update(df, stats=["PTS"]) is True
        assert p.models["PTS"].n_estimators == before, (
            "update() refit on a synthetic next-game row"
        )
        assert "No new games since" in capsys.readouterr().out

    def test_update_still_refits_on_a_genuinely_new_game(self):
        """Negative control -- the guard above must not be vacuous."""
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        # Trained through the second-to-last completed game, so the last logged
        # game IS genuinely new. Feature names come from the same frame the
        # update sees, so the new-features force-retrain cannot fire.
        stale_df = df.iloc[:-2]
        p = self._stub_predictor(stale_df)
        before = p.models["PTS"].n_estimators
        assert p.update(df, stats=["PTS"]) is True
        assert p.models["PTS"].n_estimators > before

    def test_repeated_serves_never_grow_the_model(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        p = self._stub_predictor(df)
        before = p.models["PTS"].n_estimators
        for _ in range(5):
            p.update(df, stats=["PTS"])
        assert p.models["PTS"].n_estimators == before

    def test_train_ignores_the_upcoming_row(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        p = MLPredictor(model_type="gradient_boost")
        assert p.train(df, stats=["PTS"]) is True
        assert p.last_game_date == pd.to_datetime(
            log["GAME_DATE"]
        ).max().strftime("%Y-%m-%d")

    def test_confidence_fallback_uses_completed_games_only(self):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        p = MLPredictor()
        without = MLPredictor().get_confidence(
            FeatureEngineer.create_features(log), "PTS", 25.0
        )
        assert p.get_confidence(df, "PTS", 25.0)["std"] == pytest.approx(
            without["std"]
        )


# ── 6. estimate_minutes — reads a column outside FEATURE_COLS ────────────────

class TestEstimateMinutes:
    def test_roll_20_min_numeric_is_not_in_feature_cols(self):
        """Which is exactly why a list-scoped fix would have missed it."""
        assert "ROLL_20_MIN_NUMERIC" not in MLPredictor.FEATURE_COLS

    def test_estimate_minutes_reads_the_upcoming_row(self):
        log = _log(n=40)
        fresh = FeatureEngineer.create_features(log, game_info=_next_game(log))
        stale = FeatureEngineer.create_features(log)

        assert fresh["ROLL_20_MIN_NUMERIC"].iloc[-1] == pytest.approx(
            log["MIN_NUMERIC"].tail(20).mean()
        )
        assert stale["ROLL_20_MIN_NUMERIC"].iloc[-1] == pytest.approx(
            log["MIN_NUMERIC"].iloc[-21:-1].mean()
        )
        a = FeatureEngineer.estimate_minutes(fresh, is_home=1, days_rest=2)
        b = FeatureEngineer.estimate_minutes(stale, is_home=1, days_rest=2)
        assert a != pytest.approx(b), "estimate_minutes did not pick up the fix"
        # The blend is 0.7*EMA_5 + 0.3*ROLL_20, both read off `latest`.
        expected_base = (
            0.7 * fresh["EMA_5_MIN_NUMERIC"].iloc[-1]
            + 0.3 * fresh["ROLL_20_MIN_NUMERIC"].iloc[-1]
        )
        assert a == pytest.approx(expected_base + 0.5, abs=1e-6)


# ── 7. Same-game ratios: the serve rule inverted ─────────────────────────────

class TestSameGameRatioServeRule:
    @pytest.mark.parametrize("feature", tuple(SAME_GAME_RATIO_DEFAULTS))
    def test_public_column_on_the_upcoming_row_is_the_last_completed_ratio(self, feature):
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        assert df[feature].iloc[-1] == pytest.approx(df[f"_{feature}_CURR"].iloc[-2])

    @pytest.mark.parametrize("feature", tuple(SAME_GAME_RATIO_DEFAULTS))
    def test_curr_mirror_on_the_upcoming_row_is_garbage(self, feature):
        """Which is why serve must read the public column when it is present."""
        log = _log(n=40)
        df = FeatureEngineer.create_features(log, game_info=_next_game(log))
        mirror = df[f"_{feature}_CURR"].iloc[-1]
        assert pd.isna(mirror) or mirror == 0.0
