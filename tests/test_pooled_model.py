"""Fit / persist / serve guards for the pooled league model.

Two failure modes from ``nba-model-gotchas`` are pinned here because neither
raises: state that is written but never saved (``season_averages`` worked only
inside the training process), and features that are silently substituted with 0
when the served frame does not carry them.
"""
import numpy as np
import pandas as pd
import pytest

import pooled_features as pf
from pooled_model import PooledLeagueModel, ProbabilityShrinker


def _panel(n_players=25, n_games=45, seed=3):
    rng = np.random.default_rng(seed)
    frames = []
    for p in range(n_players):
        level = rng.uniform(8, 30)
        frames.append(pd.DataFrame({
            "player_id": "p{}".format(p),
            "season": "2024-25",
            "GAME_DATE": pd.date_range("2024-10-25", periods=n_games, freq="2D"),
            "MIN": rng.uniform(20, 38, n_games),
            "PTS": np.clip(rng.normal(level, 6, n_games), 0, None).round(),
            "REB": np.clip(rng.normal(level / 4, 2, n_games), 0, None).round(),
            "AST": np.clip(rng.normal(level / 5, 2, n_games), 0, None).round(),
        }))
    return pf.build_panel(pd.concat(frames, ignore_index=True), min_prior=20)


@pytest.fixture(scope="module")
def model():
    return PooledLeagueModel.fit(_panel(), trained_through="2025-02-27")


@pytest.mark.unit
class TestFit:
    def test_one_fit_per_served_stat(self, model):
        assert set(model.stats) == set(pf.POOLED_STATS)

    def test_each_fit_uses_only_its_own_stats_features(self, model):
        for stat, fit in model.stats.items():
            assert fit.feature_names == pf.feature_names(stat)

    def test_training_pools_every_player(self, model):
        # 25 players x (45 - 20) rows.
        assert model.stats["PTS"].n_train == 625

    def test_fit_is_immutable(self, model):
        with pytest.raises((AttributeError, TypeError)):
            model.stats["PTS"].coef = np.zeros(6)

    def test_refuses_a_panel_missing_a_declared_feature(self):
        panel = _panel(n_players=6)
        with pytest.raises(ValueError, match="PTS_EWMA5"):
            PooledLeagueModel.fit(panel.drop(columns=["PTS_EWMA5"]),
                                  trained_through="2025-02-27")


@pytest.mark.unit
class TestPredict:
    def test_predicts_every_stat(self, model):
        feats = {n: 10.0 for n in pf.all_feature_names()}
        preds = model.predict(feats)
        assert set(preds) == set(pf.POOLED_STATS)
        assert all(np.isfinite(v) for v in preds.values())

    def test_a_missing_feature_raises_instead_of_serving_zero(self, model):
        feats = {n: 10.0 for n in pf.all_feature_names()}
        del feats["AST_L10"]
        with pytest.raises(KeyError, match="AST_L10"):
            model.predict(feats)

    def test_prediction_tracks_the_players_level(self, model):
        low = model.predict({n: 5.0 for n in pf.all_feature_names()})
        high = model.predict({n: 25.0 for n in pf.all_feature_names()})
        assert high["PTS"] > low["PTS"]


@pytest.mark.unit
class TestPersistence:
    def test_round_trip_reproduces_predictions_exactly(self, model, tmp_path):
        """Trap: state written in the training process but absent from save().
        A reloaded model must predict bit-identically."""
        path = tmp_path / "league.pkl"
        model.save(path)
        reloaded = PooledLeagueModel.load(path)
        feats = {n: 12.5 for n in pf.all_feature_names()}
        assert reloaded.predict(feats) == model.predict(feats)

    def test_round_trip_preserves_every_serve_time_attribute(self, model, tmp_path):
        path = tmp_path / "league.pkl"
        model.save(path)
        reloaded = PooledLeagueModel.load(path)
        assert reloaded.trained_through == model.trained_through
        for stat in pf.POOLED_STATS:
            assert reloaded.sigma(stat, 6.0) == model.sigma(stat, 6.0)
            assert reloaded.prob_over(stat, 20.0, 18.0, 6.0) == \
                model.prob_over(stat, 20.0, 18.0, 6.0)

    def test_load_of_a_missing_artifact_is_explicit(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PooledLeagueModel.load(tmp_path / "absent.pkl")


@pytest.mark.unit
class TestUncertaintyAndProbability:
    def test_sigma_grows_with_the_players_own_dispersion(self, model):
        assert model.sigma("PTS", 9.0) > model.sigma("PTS", 3.0)

    def test_sigma_has_a_positive_floor(self, model):
        assert model.sigma("PTS", 0.0) > 0

    def test_shrinkage_can_never_sharpen(self, model):
        """Phase 2 fitted a free Platt map and it SHARPENED a prediction with
        AUC ~ 0.50, manufacturing confidence out of noise. The pooled shrinker
        is one-directional by construction."""
        for stat in pf.POOLED_STATS:
            assert model.stats[stat].shrinker.slope <= 1.0

    def test_probability_never_exceeds_the_unshrunk_normal_cdf(self, model):
        raw = 100 * (1 - _norm_cdf((18.0 - 26.0) / (6.0 + 0.1)))
        assert 50.0 < model.prob_over("PTS", 26.0, 18.0, 6.0) <= raw + 1e-9

    def test_probability_is_symmetric_about_the_line(self, model):
        over = model.prob_over("PTS", 24.0, 20.0, 6.0)
        under = model.prob_over("PTS", 16.0, 20.0, 6.0)
        assert over + under == pytest.approx(100.0, abs=1.5)


def _norm_cdf(z):
    from scipy import stats
    return float(stats.norm.cdf(z))


@pytest.mark.unit
class TestProbabilityShrinker:
    def test_duck_types_the_platt_calibrator_the_serve_path_expects(self):
        """``ProbabilityCalculator.calculate`` calls ``predict_proba`` on
        whatever sits in ``probability_calibrator[stat]['calibrator']``."""
        shrinker = ProbabilityShrinker(intercept=0.05, slope=0.5)
        out = shrinker.predict_proba(np.array([[0.9]]))
        assert out.shape == (1, 2)
        assert out[0, 1] == pytest.approx(1 - out[0, 0])

    def test_slope_below_one_pulls_toward_the_base_rate(self):
        sharp = ProbabilityShrinker(intercept=0.0, slope=1.0).predict_proba([[0.9]])[0, 1]
        soft = ProbabilityShrinker(intercept=0.0, slope=0.4).predict_proba([[0.9]])[0, 1]
        assert 0.5 < soft < sharp

    def test_extreme_inputs_stay_finite(self):
        shrinker = ProbabilityShrinker(intercept=0.0, slope=0.5)
        for p in (0.0, 1.0, 1e-12, 1 - 1e-12):
            value = shrinker.predict_proba([[p]])[0, 1]
            assert 0.0 < value < 1.0
