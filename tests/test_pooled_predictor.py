"""The pooled predictor must be a drop-in for ``MLPredictor`` on the serve path.

``api/services/prediction_service.py`` calls a fixed sequence of methods on
whatever predictor it holds. If the pooled class does not answer all of them
with the same shapes, the swap breaks at runtime rather than at import, so the
sequence itself is pinned here.
"""
import inspect

import numpy as np
import pandas as pd
import pytest

import nba_evaluator as ev
import pooled_features as pf
from pooled_model import PooledLeagueModel
from pooled_predictor import PooledPredictor

# Exactly what prediction_service + the backtest harness call on a predictor.
SERVE_PATH_METHODS = (
    "load", "train", "update", "save", "_update_recent_averages", "predict",
    "apply_injury_boost", "apply_blowout_discount", "get_confidence",
    "get_prediction_uncertainty", "needs_retrain",
)


def _log(n=45, seed=5):
    """Synthetic game log in NBA-API shape. Mirrors test_upcoming_game_row._log,
    which ``create_features`` needs in full (FGA, OREB, TOV, PF ...)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-10-25", periods=n, freq="2D")
    rows = []
    for i, d in enumerate(dates):
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
            "MATCHUP": "LAL vs. BOS" if i % 2 else "LAL @ BOS",
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


@pytest.fixture(scope="module")
def league():
    rng = np.random.default_rng(11)
    frames = []
    for p in range(20):
        level = rng.uniform(9, 29)
        g = _log(40, seed=100 + p)
        g["PTS"] = np.clip(rng.normal(level, 6, 40), 0, None).round()
        g["player_id"] = "p{}".format(p)
        g["season"] = "2024-25"
        frames.append(g)
    panel = pf.build_panel(pd.concat(frames, ignore_index=True), min_prior=20)
    return PooledLeagueModel.fit(panel, trained_through="2025-02-27")


@pytest.fixture()
def predictor(league):
    p = PooledPredictor(league_model=league)
    p.train(_log())
    return p


@pytest.mark.unit
class TestInterfaceParity:
    def test_is_an_mlpredictor(self):
        assert issubclass(PooledPredictor, ev.MLPredictor)

    @pytest.mark.parametrize("name", SERVE_PATH_METHODS)
    def test_serve_path_method_exists(self, name):
        assert callable(getattr(PooledPredictor, name, None))

    @pytest.mark.parametrize("name", SERVE_PATH_METHODS)
    def test_signature_is_compatible_with_the_base_class(self, name):
        base = inspect.signature(getattr(ev.MLPredictor, name))
        pooled = inspect.signature(getattr(PooledPredictor, name))
        assert list(pooled.parameters) == list(base.parameters), name


@pytest.mark.unit
class TestServeSequence:
    def test_train_then_predict_returns_every_stat(self, predictor):
        preds = predictor.predict(pd.DataFrame([{}]))
        assert set(preds) == set(pf.POOLED_STATS)
        assert all(np.isfinite(v) for v in preds.values())

    def test_confidence_has_the_shape_the_api_serialises(self, predictor):
        info = predictor.get_confidence(_log(), "PTS", 24.0, pd.DataFrame([{}]))
        assert set(info) >= {"low", "high", "confidence", "std"}
        assert info["low"] < info["high"]
        assert 0 < info["confidence"] <= 100
        assert info["std"] > 0

    def test_uncertainty_reports_a_std(self, predictor):
        assert predictor.get_prediction_uncertainty(pd.DataFrame([{}]), "PTS")["std"] > 0

    def test_probability_calibrator_is_populated_for_every_stat(self, predictor):
        for stat in pf.POOLED_STATS:
            entry = predictor.probability_calibrator[stat]
            assert entry["method"] == "platt"
            assert hasattr(entry["calibrator"], "predict_proba")

    def test_probability_flows_through_the_production_calculator(self, predictor):
        preds = predictor.predict(pd.DataFrame([{}]))
        info = predictor.get_confidence(_log(), "PTS", preds["PTS"], pd.DataFrame([{}]))
        prob = ev.ProbabilityCalculator.calculate(
            preds["PTS"], preds["PTS"] - 4.0, info["std"],
            predictor.probability_calibrator["PTS"])
        assert 15.0 <= prob <= 85.0
        assert prob > 50.0

    def test_update_refreshes_the_served_features(self, predictor):
        before = predictor.predict(pd.DataFrame([{}]))["PTS"]
        hot = _log()
        hot.loc[hot.index[-10:], "PTS"] = 45.0
        predictor.update(hot)
        assert predictor.predict(pd.DataFrame([{}]))["PTS"] > before


@pytest.mark.unit
class TestNoSilentState:
    def test_predict_without_history_raises_instead_of_serving_zeros(self, league):
        """The per-player path substituted 0 for absent features. This one
        refuses: a predictor that never saw a game log has nothing to serve."""
        p = PooledPredictor(league_model=league)
        with pytest.raises(RuntimeError, match="no game log"):
            p.predict(pd.DataFrame([{}]))

    def test_load_never_claims_a_per_player_model_exists(self, predictor):
        """There is no per-player state to persist, so load() must return False
        and let the caller fall through to train() -- which is free."""
        assert predictor.load("Nikola Jokic") is False

    def test_save_is_a_no_op_and_writes_nothing(self, predictor, tmp_path, monkeypatch):
        monkeypatch.setattr(ev, "MODEL_DIR", tmp_path)
        predictor.save("Nikola Jokic")
        assert list(tmp_path.iterdir()) == []

    def test_absorbing_a_log_survives_a_round_trip_through_update(self, predictor):
        """Trap: state written in one process and never restored in another.
        The pooled path holds no per-player pickle, so the invariant is that
        every entry point that receives a log refreshes the served features."""
        for method_name in ("train", "update", "_update_recent_averages"):
            fresh = PooledPredictor(league_model=predictor.league_model)
            assert fresh.pooled_inputs is None
            getattr(fresh, method_name)(_log())
            assert fresh.pooled_inputs and fresh.pooled_dispersion
            assert np.isfinite(fresh.predict(pd.DataFrame([{}]))["PTS"])


@pytest.mark.unit
class TestSyntheticRow:
    def test_the_upcoming_row_does_not_shorten_the_windows(self, predictor):
        base = predictor.predict(pd.DataFrame([{}]))
        log = _log()
        frame = ev.FeatureEngineer.create_features(
            log,
            game_info={"matchup": "LAL @ DEN",
                       "game_date": pd.Timestamp("2025-01-30"),
                       "is_home": 0, "opponent": "DEN", "team": "LAL"},
        )
        assert ev.has_upcoming_row(frame)
        predictor.update(frame)
        after = predictor.predict(pd.DataFrame([{}]))
        assert after["PTS"] == pytest.approx(base["PTS"], abs=1e-9)


@pytest.mark.unit
class TestFlagGating:
    """`NBA_EVAL_POOLED_MODEL` follows the repo-wide convention: OFF unless the
    env var is exactly '1' or 'true'. Mirrors api/config.py and
    frontend/src/shared/lib/flags.ts."""

    @pytest.mark.parametrize("raw,expected", [
        (None, False), ("", False), ("0", False), ("false", False),
        ("False", False), ("no", False), ("yes", False), ("2", False),
        ("1", True), ("true", True), ("TRUE", True), ("  true  ", True),
    ])
    def test_parsing_convention(self, raw, expected):
        from api.config import POOLED_MODEL_FLAG_ENV_VAR, pooled_model_enabled
        env = {} if raw is None else {POOLED_MODEL_FLAG_ENV_VAR: raw}
        assert pooled_model_enabled(env) is expected

    def test_default_is_off(self, monkeypatch):
        from api.config import POOLED_MODEL_FLAG_ENV_VAR, pooled_model_enabled
        monkeypatch.delenv(POOLED_MODEL_FLAG_ENV_VAR, raising=False)
        assert pooled_model_enabled() is False

    def test_flag_off_builds_the_legacy_per_player_model(self, monkeypatch):
        from api.config import POOLED_MODEL_FLAG_ENV_VAR
        from api.services.prediction_service import _build_predictor
        monkeypatch.delenv(POOLED_MODEL_FLAG_ENV_VAR, raising=False)
        built = _build_predictor(ev, "gradient_boost", False)
        assert type(built) is ev.MLPredictor

    def test_flag_on_builds_the_pooled_model(self, monkeypatch, league, tmp_path):
        import pooled_model as pm
        from api.config import POOLED_MODEL_FLAG_ENV_VAR
        from api.services import prediction_service as svc
        path = league.save(tmp_path / "league.pkl")
        monkeypatch.setattr(pm, "DEFAULT_MODEL_PATH", path)
        monkeypatch.setenv(POOLED_MODEL_FLAG_ENV_VAR, "1")
        assert isinstance(svc._build_predictor(ev, "gradient_boost", False),
                          PooledPredictor)

    def test_flag_on_without_an_artifact_raises_rather_than_downgrading(
            self, monkeypatch, tmp_path):
        import pooled_model as pm
        from fastapi import HTTPException
        from api.config import POOLED_MODEL_FLAG_ENV_VAR
        from api.services import prediction_service as svc
        monkeypatch.setattr(pm, "DEFAULT_MODEL_PATH", tmp_path / "absent.pkl")
        monkeypatch.setenv(POOLED_MODEL_FLAG_ENV_VAR, "1")
        with pytest.raises(HTTPException) as excinfo:
            svc._build_predictor(ev, "gradient_boost", False)
        assert excinfo.value.status_code == 503
