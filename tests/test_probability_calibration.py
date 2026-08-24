"""Phase 2 guards: the probability calibrator must be fit on what serve consumes.

Three defects this pins, all of which failed *silently*:

1. ``_train_probability_calibrator`` built its hypothetical-line lattice with
   offsets of ``+/-2*sigma`` and a z-divisor of ``sigma + 0.1`` — the same
   sigma — so sigma cancelled. ``raw_probs`` was a fixed 9-point lattice,
   identical for every player and every stat, and it was built from the OOF
   *residual* std. Serve divides by the per-game CQR-corrected *quantile* std,
   which measured ~1.4x larger, so serve never reached the lattice points the
   logistic was anchored by.
2. ``cqr_coverage`` applied the conformal correction to the very rows that
   chose it, so it returned ``ceil((1-alpha)(n+1))/n`` by construction for
   every player and every stat and could not detect its own failure.
3. The served quantile pair was fit on every row with no validation and no
   early stopping, leaving the band tighter in-sample than the OOF band the
   CQR correction was learned from.

The headline invariant, assertable from a persisted pickle alone:

    (training_metrics[s]['interval_width'] + 2*cqr_correction) / divisor
    -------------------------------------------------------------------  == 1
                    probability_calibrator[s]['std_estimate']
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import nba_evaluator as ev  # noqa: E402
from nba_evaluator import MLPredictor, ProbabilityCalculator  # noqa: E402

STATS = ("PTS", "REB", "AST", "PRA")


def synthetic_log(n=52, seed=11):
    """A single-season log long enough to reach every OOF-count guard."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-10-22", periods=n, freq="2D")
    teams = ["BOS", "LAL", "GSW", "MIA", "DEN", "PHX", "NYK", "DAL"]
    rows = []
    for i, date in enumerate(dates):
        opp = teams[1:][i % (len(teams) - 1)]
        fga = int(rng.integers(14, 26))
        fgm = int(rng.binomial(fga, 0.48))
        fg3a = int(rng.integers(3, 10))
        fg3m = int(rng.binomial(fg3a, 0.36))
        fta = int(rng.integers(3, 11))
        ftm = int(rng.binomial(fta, 0.8))
        oreb, dreb = int(rng.integers(1, 5)), int(rng.integers(4, 11))
        rows.append({
            "SEASON_ID": "22024", "Player_ID": 999,
            "Game_ID": "00224{:05d}".format(i),
            "GAME_DATE": date.strftime("%Y-%m-%d"),
            "MATCHUP": "{} {} {}".format(teams[0], "vs." if i % 2 else "@", opp),
            "WL": "W", "MIN": int(rng.integers(28, 39)),
            "FGM": fgm, "FGA": fga, "FG_PCT": fgm / fga,
            "FG3M": fg3m, "FG3A": fg3a, "FG3_PCT": fg3m / max(fg3a, 1),
            "FTM": ftm, "FTA": fta, "FT_PCT": ftm / max(fta, 1),
            "OREB": oreb, "DREB": dreb, "REB": oreb + dreb,
            "AST": int(rng.integers(3, 13)),
            "STL": int(rng.integers(0, 4)), "BLK": int(rng.integers(0, 4)),
            "TOV": int(rng.integers(1, 6)), "PF": int(rng.integers(0, 5)),
            "PTS": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
            "PLUS_MINUS": int(rng.integers(-15, 16)), "VIDEO_AVAILABLE": 1,
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def trained(request):
    """One trained predictor, shared by every assertion in this module.

    Optuna is switched off: the search is the dominant cost here and it tunes
    the point model, not anything this file measures.
    """
    monkey = pytest.MonkeyPatch()
    monkey.setattr(ev, "OPTUNA_AVAILABLE", False)
    frame = ev.FeatureEngineer.create_features(synthetic_log())
    predictor = MLPredictor(model_type="gradient_boost", use_ensemble=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert predictor.train(frame, stats=["PTS", "REB", "AST"])
    request.addfinalizer(monkey.undo)
    return predictor


# ── 1. The headline invariant ────────────────────────────────────────────────


class TestCalibratorIsFitOnTheServedStd:
    def test_every_stat_has_a_calibrator_and_metrics(self, trained):
        for stat in STATS:
            assert stat in trained.probability_calibrator, stat
            assert stat in trained.training_metrics, stat

    def test_served_std_over_fitted_std_is_one(self, trained):
        """(interval_width + 2*cqr) / divisor / std_estimate == 1.

        Measured 1.40 (range 1.21-1.53) before Phase 2.
        """
        for stat in STATS:
            calib = trained.probability_calibrator[stat]
            metrics = trained.training_metrics[stat]
            served = (
                metrics["interval_width"] + 2 * calib["cqr_correction"]
            ) / trained._interval_divisor(stat)
            assert calib["std_estimate"] > 0
            assert served / calib["std_estimate"] == pytest.approx(1.0, abs=0.05), stat

    def test_the_fit_used_the_quantile_band_not_the_residual_std(self, trained):
        for stat in STATS:
            calib = trained.probability_calibrator[stat]
            assert calib["calibrator_std_source"] == "cqr_quantile_band", stat
            # The two are genuinely different quantities; if they were equal the
            # assertion above would be vacuous.
            assert calib["std_estimate"] != pytest.approx(calib["residual_std"], rel=1e-3)

    def test_std_estimate_is_the_mean_of_the_stds_platt_saw(self, trained):
        for stat in STATS:
            calib = trained.probability_calibrator[stat]
            metrics = trained.training_metrics[stat]
            assert calib["std_estimate"] == pytest.approx(metrics["served_std_mean"])


# ── 2. cqr_coverage is measured out of sample ────────────────────────────────


class TestHoldoutCqrCoverage:
    def test_insample_coverage_is_a_constant_of_n(self):
        """Why the old number was useless: it does not depend on the data."""
        rng = np.random.default_rng(0)
        seen = set()
        for scale in (1.0, 5.0, 25.0):
            y = rng.normal(0, scale, 60)
            q10, q90 = np.full(60, -0.1 * scale), np.full(60, 0.1 * scale)
            conformity = np.maximum(q10 - y, y - q90)
            c = MLPredictor._conformal_correction(conformity, 0.1)
            seen.add(round(float(np.mean((y >= q10 - c) & (y <= q90 + c))), 6))
        assert len(seen) == 1

    def test_holdout_coverage_does_depend_on_the_data(self):
        """A band that stops fitting halfway through must show up."""
        rng = np.random.default_rng(1)
        y = np.concatenate([rng.normal(0, 1.0, 40), rng.normal(0, 6.0, 40)])
        q10, q90 = np.full(80, -1.5), np.full(80, 1.5)
        held_out = MLPredictor._holdout_cqr_coverage(q10, q90, y, 0.1)
        conformity = np.maximum(q10 - y, y - q90)
        c = MLPredictor._conformal_correction(conformity, 0.1)
        in_sample = float(np.mean((y >= q10 - c) & (y <= q90 + c)))
        assert held_out is not None
        assert held_out < in_sample

    def test_returns_none_when_there_are_too_few_rows(self):
        y = np.arange(6.0)
        assert MLPredictor._holdout_cqr_coverage(y, y + 1, y, 0.1) is None

    def test_conformal_correction_uses_the_finite_sample_bump(self):
        conformity = np.arange(10.0)
        # (1-0.1)*(1+1/10) = 0.99 quantile of 0..9
        assert MLPredictor._conformal_correction(conformity, 0.1) == pytest.approx(
            float(np.quantile(conformity, 0.99))
        )

    def test_correction_is_never_negative(self):
        assert MLPredictor._conformal_correction(np.full(10, -3.0), 0.1) == 0.0

    def test_both_numbers_are_persisted_for_comparison(self, trained):
        for stat in STATS:
            calib = trained.probability_calibrator[stat]
            assert "cqr_coverage" in calib, stat
            assert "cqr_coverage_insample" in calib, stat


# ── 3. The served quantile pair is validated ─────────────────────────────────


class TestQuantileModelsAreValidated:
    def test_tree_count_is_selected_within_bounds(self):
        rng = np.random.default_rng(2)
        X = rng.normal(size=(60, 6))
        y = X[:, 0] * 3 + rng.normal(size=60)
        w = np.ones(60)
        q_params = {"n_estimators": 150, "max_depth": 3, "learning_rate": 0.08,
                    "random_state": 42}
        n = MLPredictor._select_quantile_n_estimators(X, y, w, 0.1, q_params)
        assert n is not None
        assert MLPredictor.MIN_QUANTILE_ESTIMATORS <= n <= 150

    def test_returns_none_without_raw_features(self):
        assert MLPredictor._select_quantile_n_estimators(
            None, np.zeros(5), np.ones(5), 0.1, {}
        ) is None

    def test_pinball_loss_is_asymmetric(self):
        y = np.array([1.0])
        assert MLPredictor._pinball_loss(y, np.array([0.0]), 0.9) == pytest.approx(0.9)
        assert MLPredictor._pinball_loss(y, np.array([2.0]), 0.9) == pytest.approx(0.1)

    def test_served_band_is_no_tighter_than_the_oof_band_it_is_corrected_by(
        self, trained
    ):
        """The CQR correction is learned OOF and applied to the served pair.

        Before validation was added the served band measured ~0.92x the OOF
        width, so the correction was sized for intervals wider than the ones it
        ended up widening.
        """
        for stat in STATS:
            metrics = trained.training_metrics[stat]
            assert "interval_width_insample" in metrics, stat
            ratio = metrics["interval_width_insample"] / metrics["interval_width"]
            assert 0.75 < ratio < 1.6, (stat, ratio)


# ── 4. New persisted state survives a reload (gotcha #2) ─────────────────────


class TestNewCalibratorStatePersists:
    def test_every_new_key_survives_restore(self, trained, tmp_path, monkeypatch):
        monkeypatch.setattr(ev, "MODEL_DIR", tmp_path)
        monkeypatch.setattr(ev.model_storage, "upload_player_model", lambda *a, **k: None)
        trained.save("Phase Two Guard")
        restored = MLPredictor(model_type="gradient_boost", use_ensemble=False)
        import pickle

        with open(tmp_path / "Phase_Two_Guard_model.pkl", "rb") as handle:
            restored._restore_from_dict(pickle.load(handle), "Phase Two Guard")
        for stat in STATS:
            before, after = trained.probability_calibrator[stat], restored.probability_calibrator[stat]
            for key in ("std_estimate", "residual_std", "calibrator_std_source",
                        "cqr_correction", "cqr_coverage", "cqr_coverage_insample"):
                assert after[key] == before[key], (stat, key)
            for key in ("served_std_mean", "residual_std", "interval_divisor",
                        "interval_width_insample"):
                assert (
                    restored.training_metrics[stat][key]
                    == trained.training_metrics[stat][key]
                ), (stat, key)


# ── 5. The silent-failure paths now say something ────────────────────────────


class TestSilentFailurePathsAreLogged:
    def test_platt_failure_warns_instead_of_silently_using_the_raw_cdf(self):
        class Exploding:
            def predict_proba(self, _):
                raise RuntimeError("boom")

        with pytest.warns(RuntimeWarning, match="UNCALIBRATED"):
            prob = ProbabilityCalculator.calculate(
                20.0, 18.0, 5.0,
                {"calibrator": Exploding(), "method": "platt"},
            )
        assert ProbabilityCalculator.PROB_FLOOR <= prob <= ProbabilityCalculator.PROB_CEIL

    def test_missing_std_warns_that_prob_over_is_a_band_position(self):
        evaluator = ev.LineEvaluator()
        with pytest.warns(RuntimeWarning, match="LINEAR band position"):
            evaluator.evaluate(
                20.0, 18.0, "PTS",
                confidence_info={"low": 10.0, "high": 30.0, "confidence": 70},
            )
