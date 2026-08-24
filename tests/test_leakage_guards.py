"""Regression guards for the 2026-08-19 model remediation.

Covers the four failure modes the remediation was built to remove, each of
which previously failed silently:

1. Target leakage -- five ratio features were computed from the current game's
   own box score, so the AST model could read AST off its own feature vector.
2. The de-leak's ordering trap -- three already-correct rolling features derive
   from those raw ratios and become double-shifted if the shift lands too early.
3. Unpurged OOF folds feeding the calibrator / CQR / residual models.
4. Serving a feature name that ``get_prediction_features`` never emits, which
   the predict paths silently substitute with 0.
"""
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import TimeSeriesSplit

import nba_evaluator as ev
from nba_evaluator import (
    SAME_GAME_RATIO_DEFAULTS,
    TEAM_TENURE_CAP,
    TRADE_WINDOW_GAMES,
    FeatureEngineer,
    MLPredictor,
)

RATIOS = tuple(SAME_GAME_RATIO_DEFAULTS)


def _log(n=40, seed=11, teams=None):
    """Function-scoped synthetic game log; callers mutate it freely.

    Deliberately not the module-scoped ``features_df`` fixture in
    test_ml_season.py -- these tests perturb individual games.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-10-25", periods=n, freq="2D")
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


# ── 1. Target leakage ────────────────────────────────────────────────────────

class TestRatioFeaturesAreNotLeaky:
    @pytest.mark.parametrize("feature", RATIOS)
    def test_extreme_game_n_does_not_move_row_n(self, feature):
        """Row N's feature must be blind to row N's own box score."""
        base = _log()
        spiked = base.copy()
        n = len(base) - 1
        for col, val in (("AST", 40), ("TOV", 0), ("OREB", 25), ("REB", 30),
                         ("FG3A", 20), ("FGA", 21), ("FTA", 20), ("PF", 6)):
            spiked.loc[n, col] = val

        before = FeatureEngineer.create_features(base)[feature].iloc[n]
        after = FeatureEngineer.create_features(spiked)[feature].iloc[n]
        assert before == pytest.approx(after), (
            f"{feature} row {n} changed when row {n}'s own box score changed "
            f"({before} -> {after}) -- the feature is leaking the target"
        )

    def test_ast_tov_ratio_is_exactly_lag_one(self):
        log = _log()
        df = FeatureEngineer.create_features(log)
        for i in (1, 7, 19, 39):
            expected = min(log["AST"].iloc[i - 1] / max(log["TOV"].iloc[i - 1], 2), 6.0)
            assert df["AST_TOV_RATIO"].iloc[i] == pytest.approx(expected)

    def test_row_zero_uses_the_shared_default(self):
        df = FeatureEngineer.create_features(_log())
        for feature, default in SAME_GAME_RATIO_DEFAULTS.items():
            assert df[feature].iloc[0] == pytest.approx(default)

    def test_correlation_with_target_collapses(self):
        """The mirror still tracks the target; the served feature must not."""
        df = FeatureEngineer.create_features(_log(n=80))
        leaky = abs(df["_AST_TOV_RATIO_CURR"].corr(df["AST"]))
        clean = abs(df["AST_TOV_RATIO"].corr(df["AST"]))
        assert clean < leaky / 2, f"clean={clean:.3f} not much below leaky={leaky:.3f}"


# ── 2. The ordering trap ─────────────────────────────────────────────────────

class TestRollingSiblingsNotDoubleShifted:
    """FG3_RATE/FT_RATE are in ``stats_for_rolling`` and AST_TOV_RATIO is rolled
    at ROLL_5_AST_TOV. All three shift internally, so they must consume the RAW
    ratio. Shifting the public column too early makes them lag-2 -- silently."""

    @pytest.mark.parametrize("rate,num,den", [
        ("FG3_RATE", "FG3A", "FGA"),
        ("FT_RATE", "FTA", "FGA"),
    ])
    def test_roll5_matches_shifted_rolling_of_raw(self, rate, num, den):
        log = _log()
        df = FeatureEngineer.create_features(log)
        raw = (log[num] / log[den]).where(log[den] > 0, 0.0)
        expected = raw.rolling(5, min_periods=1).mean().shift(1)
        np.testing.assert_allclose(
            df[f"ROLL_5_{rate}"].values, expected.values, equal_nan=True
        )

    def test_roll5_ast_tov_matches_shifted_rolling_of_raw(self):
        log = _log()
        df = FeatureEngineer.create_features(log)
        raw = log.apply(lambda r: min(r["AST"] / max(r["TOV"], 2), 6.0), axis=1)
        expected = raw.rolling(5, min_periods=1).mean().shift(1)
        np.testing.assert_allclose(
            df["ROLL_5_AST_TOV"].values, expected.values, equal_nan=True
        )


# ── 3. Train/serve parity ────────────────────────────────────────────────────

class TestTrainServeParity:
    """Rewritten for the Phase 1 convention.

    ``create_features(game_info=...)`` appends a synthetic row for the upcoming
    game, so ``df.iloc[-1]`` IS that game. On it the PUBLIC ratio column — which
    create_features already shifted — holds the last completed game's own ratio,
    the correct lag-1 input, while the ``_*_CURR`` mirror holds the synthetic
    row's own (NaN / guard-swallowed 0) value. Without a synthetic row the
    relationship is the exact inverse, and the mirrors remain the right source.

    The invariant that survives both shapes: the SERVED value is the last
    completed game's own ratio either way. That is what this pins.
    """

    @staticmethod
    def _next_game(log, team="LAL", opponent="OKC"):
        last = pd.to_datetime(log["GAME_DATE"]).max()
        return {
            "matchup": f"{team} @ {opponent}",
            "game_date": last + pd.Timedelta(days=2),
            "is_home": 0,
            "opponent": opponent,
        }

    @staticmethod
    def _serve(df, opponent="OKC"):
        return FeatureEngineer.get_prediction_features(
            df, is_home=0, opponent=opponent,
            player_info={"team_abbrev": "LAL", "player_name": "T"},
        )

    def test_serve_reads_the_last_completed_games_own_ratio(self):
        """With the synthetic next-game row present, serve must read the PUBLIC
        (already shifted) column. Reading the _CURR mirror there would hand the
        model the placeholder row's own garbage."""
        log = _log()
        df = FeatureEngineer.create_features(log, game_info=self._next_game(log))
        served = self._serve(df)
        for feature in RATIOS:
            expected = df[f"_{feature}_CURR"].iloc[-2]  # last COMPLETED game
            assert served[feature].iloc[0] == pytest.approx(expected), (
                f"{feature} serve value is not the last completed game's own ratio"
            )
            assert df[feature].iloc[-1] == pytest.approx(expected), (
                f"{feature}'s public column on the upcoming row should be lag-1"
            )
            mirror = df[f"_{feature}_CURR"].iloc[-1]
            assert pd.isna(mirror) or mirror == 0.0, (
                f"_{feature}_CURR on the synthetic row is meaningful — the serve "
                f"rule inversion may no longer be safe"
            )

    def test_served_value_is_the_same_with_or_without_a_synthetic_row(self):
        """The convention flipped; the served number must not. A caller with no
        schedule information (game_info is None) must still get lag-1, never the
        lag-2 value the old code would have produced under the new rule."""
        log = _log()
        with_row = self._serve(
            FeatureEngineer.create_features(log, game_info=self._next_game(log))
        )
        without_row = self._serve(FeatureEngineer.create_features(log))
        for feature in RATIOS:
            assert with_row[feature].iloc[0] == pytest.approx(
                without_row[feature].iloc[0]
            ), f"{feature} serve value depends on the frame shape"

    def test_oreb_interaction_uses_the_same_lag_one_term(self):
        """Pairing a lag-2 player term with a lag-0 opponent term fails silently."""
        log = _log()
        for game_info in (self._next_game(log), None):
            df = FeatureEngineer.create_features(log, game_info=game_info)
            served = self._serve(df)
            assert served["OREB_RATE_x_OPP_OREB"].iloc[0] == pytest.approx(
                served["OREB_RATE"].iloc[0] * ((0.27 - 0.27) / 0.05)
            )
            served_hi = FeatureEngineer.get_prediction_features(
                df, is_home=0, opponent="OKC", opp_oreb_pct=0.32,
                player_info={"team_abbrev": "LAL", "player_name": "T"},
            )
            assert served_hi["OREB_RATE_x_OPP_OREB"].iloc[0] == pytest.approx(
                served_hi["OREB_RATE"].iloc[0] * 1.0
            )

    def test_every_declared_feature_is_emitted_at_serve(self):
        """predict/_quantile_band substitute 0 for missing names, so a feature in
        FEATURE_COLS that serve never emits is served as a silent zero."""
        df = FeatureEngineer.create_features(_log())
        served = FeatureEngineer.get_prediction_features(
            df, is_home=1, opponent="BOS",
            player_info={"team_abbrev": "LAL", "player_name": "T"},
        )
        missing = [f for f in MLPredictor.FEATURE_COLS if f not in served.columns]
        assert not missing, f"declared but never served (silently 0): {missing}"


# ── 4. Purged cross-validation ───────────────────────────────────────────────

class TestPurgedSplits:
    @pytest.mark.parametrize("n", [24, 30, 36, 45, 60, 70, 82, 140])
    def test_embargo_is_respected(self, n):
        for train_idx, val_idx in MLPredictor._purged_splits(n):
            assert val_idx.min() - train_idx.max() > MLPredictor.PURGE_GAP - 1

    @pytest.mark.parametrize("n", [24, 30, 36, 45, 60, 70, 82, 140])
    def test_validation_windows_are_disjoint(self, n):
        seen = set()
        for _, val_idx in MLPredictor._purged_splits(n):
            assert not (seen & set(val_idx.tolist()))
            seen |= set(val_idx.tolist())

    @pytest.mark.parametrize("n", range(20, 200))
    def test_coverage_never_falls_more_than_purge_gap_below_tss(self, n):
        """The bound that makes the (threshold - PURGE_GAP) guards safe."""
        purged = set()
        for _, val_idx in MLPredictor._purged_splits(n):
            purged |= set(val_idx.tolist())
        tss = set()
        for _, val_idx in TimeSeriesSplit(n_splits=5).split(np.zeros((n, 2))):
            tss |= set(val_idx.tolist())
        assert len(purged) >= len(tss) - MLPredictor.PURGE_GAP

    def test_no_unpurged_timeseriessplit_left_in_module(self):
        """Guard against reintroduction. Parsed, not grepped, so the explanatory
        comments that reference TimeSeriesSplit by name do not trip it."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(ev))
        used = {
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "TimeSeriesSplit"
        } | {
            alias.asname or alias.name
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            for alias in node.names if alias.name == "TimeSeriesSplit"
        }
        assert not used, (
            "TimeSeriesSplit reintroduced -- OOF folds must go through _purged_splits"
        )


# ── 5. CQR divisor wiring ────────────────────────────────────────────────────

class TestIntervalDivisor:
    def test_learned_divisor_is_gated_off_by_default(self):
        """Pinned to the conservative constant: the learned value measures ~3.3,
        which shrinks std and raises confidence on an already-overconfident model,
        for no measurable Brier benefit (see docs/experiment_cqr_divisor_*)."""
        assert MLPredictor.CONSUME_LEARNED_INTERVAL_DIVISOR is False
        p = MLPredictor()
        p.probability_calibrator = {"PTS": {"interval_to_std_divisor": 3.29}}
        assert p._interval_divisor("PTS") == MLPredictor.DEFAULT_INTERVAL_TO_STD_DIVISOR

    def test_uses_persisted_divisor_when_gate_is_opened(self):
        """The plumbing must still work, so re-enabling stays a one-line change."""
        p = MLPredictor()
        p.CONSUME_LEARNED_INTERVAL_DIVISOR = True
        p.probability_calibrator = {"PTS": {"interval_to_std_divisor": 3.29}}
        assert p._interval_divisor("PTS") == pytest.approx(3.29)

    def test_falls_back_when_key_absent(self):
        p = MLPredictor()
        p.CONSUME_LEARNED_INTERVAL_DIVISOR = True
        p.probability_calibrator = {"PTS": {"std_estimate": 4.0}}
        assert p._interval_divisor("PTS") == MLPredictor.DEFAULT_INTERVAL_TO_STD_DIVISOR
        assert p._interval_divisor("REB") == MLPredictor.DEFAULT_INTERVAL_TO_STD_DIVISOR

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), "x", None])
    def test_corrupt_values_cannot_produce_a_degenerate_std(self, bad):
        p = MLPredictor()
        p.CONSUME_LEARNED_INTERVAL_DIVISOR = True
        p.probability_calibrator = {"PTS": {"interval_to_std_divisor": bad}}
        assert p._interval_divisor("PTS") == MLPredictor.DEFAULT_INTERVAL_TO_STD_DIVISOR


# ── 6. Trade awareness ───────────────────────────────────────────────────────

class TestTradeFeatures:
    def test_tenure_resets_on_team_change(self):
        teams = ["LAL"] * 25 + ["MIA"] * 15
        df = FeatureEngineer.create_features(_log(n=40, teams=teams))
        assert df["GAMES_WITH_CURRENT_TEAM"].iloc[25] == 0
        assert df["GAMES_WITH_CURRENT_TEAM"].iloc[26] == 1
        assert df["GAMES_WITH_CURRENT_TEAM"].iloc[31] == 6

    def test_first_block_is_left_censored_not_treated_as_a_trade(self):
        """The log opening mid-tenure must not look like a fresh trade."""
        df = FeatureEngineer.create_features(_log(n=40))
        assert df["GAMES_WITH_CURRENT_TEAM"].iloc[0] == TEAM_TENURE_CAP
        assert df["TEAM_CHANGED_RECENT"].iloc[0] == 0

    def test_changed_recent_flag_tracks_the_window(self):
        teams = ["LAL"] * 25 + ["MIA"] * 15
        df = FeatureEngineer.create_features(_log(n=40, teams=teams))
        assert df["TEAM_CHANGED_RECENT"].iloc[25] == 1
        assert df["TEAM_CHANGED_RECENT"].iloc[25 + TRADE_WINDOW_GAMES - 1] == 1
        assert df["TEAM_CHANGED_RECENT"].iloc[25 + TRADE_WINDOW_GAMES] == 0

    def test_tenure_is_clamped(self):
        df = FeatureEngineer.create_features(_log(n=60))
        assert df["GAMES_WITH_CURRENT_TEAM"].max() <= TEAM_TENURE_CAP


class TestTradeDamping:
    def test_neutral_at_and_above_the_window(self):
        for g in (TRADE_WINDOW_GAMES, TRADE_WINDOW_GAMES + 5, 100):
            assert MLPredictor._trade_damping(g) == (1.0, 1.0)

    def test_unknown_tenure_is_neutral(self):
        assert MLPredictor._trade_damping(None) == (1.0, 1.0)

    def test_strongest_immediately_after_a_trade(self):
        conf, std = MLPredictor._trade_damping(0)
        assert conf == pytest.approx(0.75)
        assert std == pytest.approx(1.30)

    def test_monotonic_taper(self):
        confs = [MLPredictor._trade_damping(g)[0] for g in range(TRADE_WINDOW_GAMES + 1)]
        stds = [MLPredictor._trade_damping(g)[1] for g in range(TRADE_WINDOW_GAMES + 1)]
        assert confs == sorted(confs)
        assert stds == sorted(stds, reverse=True)


# ── 7. Persistence round-trip ────────────────────────────────────────────────

class TestNewStatePersists:
    """State that predict() reads MUST survive save/load.

    The precedent: ``season_averages`` was written in _update_recent_averages and
    read in predict(), but was absent from save(). Its ``hasattr`` guard therefore
    failed on every reloaded model, so the season-deviation cap silently never
    fired in production and only worked in the process that trained. Any new
    residual state added without a save()/_restore_from_dict() entry fails the
    same way -- and the backtest cannot catch it, because it trains and predicts
    in one process.
    """

    ATTRS = ("recent_averages", "recent_averages_l5", "recent_stds_l10",
             "season_averages", "min_minutes_threshold")

    def test_round_trips_through_save_and_restore(self, tmp_path, monkeypatch):
        import pickle

        monkeypatch.setattr(ev, "MODEL_DIR", tmp_path)
        monkeypatch.setattr(ev.model_storage, "upload_player_model",
                            lambda *a, **k: True)
        monkeypatch.setattr(ev, "_model_cache_put", lambda *a, **k: None)

        p = MLPredictor()
        p.scalers, p.feature_names, p.models = {}, ["A"], {}
        p.recent_averages = {"PTS": 25.0}
        p.recent_averages_l5 = {"PTS": 27.5}
        p.recent_stds_l10 = {"PTS": 6.25}
        p.season_averages = {"PTS": 24.0}
        p.min_minutes_threshold = 17.5
        p.save("Round Trip")

        blob = pickle.loads((tmp_path / "Round_Trip_model.pkl").read_bytes())
        for attr in self.ATTRS:
            assert attr in blob, f"{attr} is not persisted by save()"

        restored = MLPredictor()
        restored._restore_from_dict(blob, "Round Trip")
        for attr in self.ATTRS:
            assert getattr(restored, attr) == getattr(p, attr), f"{attr} did not survive"

    def test_legacy_pickle_without_new_keys_restores(self):
        """Pickles predating these keys must load, not raise."""
        p = MLPredictor()
        assert p._restore_from_dict(
            {"scalers": {}, "feature_names": [], "model_type": "gradient_boost",
             "models": {}}, "Legacy",
        ) is not False
        assert p.recent_averages_l5 == {}
        assert p.min_minutes_threshold is None


class TestResidualServeInputs:
    def test_returns_none_when_state_missing(self):
        """None makes predict() skip the correction rather than fabricate inputs."""
        p = MLPredictor()
        p.recent_averages, p.recent_averages_l5, p.recent_stds_l10 = {}, {}, {}
        assert p._residual_serve_inputs("PTS") is None

    def test_returns_none_on_nan_std(self):
        """< 3 games leaves the std NaN; a linear BayesianRidge must not see it."""
        p = MLPredictor()
        p.recent_averages = {"PTS": 25.0}
        p.recent_averages_l5 = {"PTS": 27.0}
        p.recent_stds_l10 = {"PTS": float("nan")}
        assert p._residual_serve_inputs("PTS") is None

    def test_returns_training_column_order(self):
        p = MLPredictor()
        p.recent_averages = {"PTS": 25.0}
        p.recent_averages_l5 = {"PTS": 27.0}
        p.recent_stds_l10 = {"PTS": 6.0}
        assert p._residual_serve_inputs("PTS") == (27.0, 25.0, 6.0)


# ── 8. Quantile band cannot produce a degenerate std ─────────────────────────

class TestQuantileBandFloor:
    def test_min_quantile_std_is_positive(self):
        assert MLPredictor.MIN_QUANTILE_STD > 0

    def test_crossed_band_would_invert_prob_over(self):
        """Why the ordering fix matters: a negative std flips the sign of z, so
        an UNDER scores as a high-probability OVER."""
        over = ev.ProbabilityCalculator.calculate(20.0, 25.0, 3.0)
        inverted = ev.ProbabilityCalculator.calculate(20.0, 25.0, -3.0)
        assert over < 50 < inverted


# ── 9. Retrain must not reuse a previous search's hyperparameters ────────────

class TestOptunaParamsResetOnRetrain:
    def test_train_resets_optimized_params(self):
        """_optimize_hyperparameters returns early on a cache hit and
        optimized_params is restored from the pickle, so a warm
        load() -> update() -> train() would otherwise silently reuse
        hyperparameters chosen by the old unpurged, last-fold-only search."""
        import inspect
        assert "self.optimized_params = {}" in inspect.getsource(MLPredictor.train)
