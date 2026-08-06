"""Phase-3 ML tests: per-season features, PRA retention, early-season damping."""
import numpy as np
import pandas as pd
import pytest

from nba_evaluator import ALL_STATS, FeatureEngineer, MLPredictor


def _synthetic_log(seasons, games_per_season=60, seed=7) -> pd.DataFrame:
    """Game log spanning multiple seasons with NBA-API-shaped columns."""
    rng = np.random.default_rng(seed)
    rows = []
    for season in seasons:
        start_year = int(season[:4])
        dates = pd.date_range(f"{start_year}-10-25", periods=games_per_season, freq="2D")
        for d in dates:
            mins = rng.uniform(28, 38)
            fga = rng.integers(12, 24)
            fgm = rng.binomial(fga, 0.48)
            fg3a = rng.integers(4, 11)
            fg3m = rng.binomial(fg3a, 0.37)
            fta = rng.integers(2, 9)
            ftm = rng.binomial(fta, 0.8)
            oreb, dreb = rng.integers(0, 3), rng.integers(3, 9)
            rows.append({
                "SEASON": season,
                "SEASON_ID": f"2{start_year}",
                "GAME_DATE": d,
                "MATCHUP": "LAL vs. BOS" if rng.random() < 0.5 else "LAL @ BOS",
                "WL": "W" if rng.random() < 0.5 else "L",
                "MIN": mins,
                "MIN_NUMERIC": mins,
                "PTS": int(2 * (fgm - fg3m) + 3 * fg3m + ftm),
                "REB": int(oreb + dreb),
                "AST": int(rng.integers(3, 12)),
                "FGM": int(fgm), "FGA": int(fga),
                "FG3M": int(fg3m), "FG3A": int(fg3a),
                "FTM": int(ftm), "FTA": int(fta),
                "OREB": int(oreb), "DREB": int(dreb),
                "STL": int(rng.integers(0, 4)), "BLK": int(rng.integers(0, 3)),
                "TOV": int(rng.integers(0, 6)), "PF": int(rng.integers(0, 5)),
                "PLUS_MINUS": int(rng.integers(-15, 16)),
            })
    return pd.DataFrame(rows)


SEASONS = ["2024-25", "2025-26", "2026-27"]


@pytest.fixture(scope="module")
def features_df():
    log = _synthetic_log(SEASONS)
    return FeatureEngineer.create_features(log, player_info={
        "player_id": 1, "player_name": "Test Player", "team_abbrev": "LAL", "position": "G",
    })


@pytest.mark.unit
class TestPerSeasonGameNum:
    def test_game_num_restarts_each_season(self, features_df):
        for season in SEASONS:
            season_rows = features_df[features_df["SEASON"] == season]
            assert list(season_rows["GAME_NUM"]) == list(range(1, len(season_rows) + 1))

    def test_season_phase_never_nan_and_early_for_new_season(self, features_df):
        assert not features_df["SEASON_PHASE"].isna().any()
        # First 25 games of EVERY season are phase 1 (early) — the old global
        # counter marked the 2nd and 3rd seasons as perpetual late/playoffs
        for season in SEASONS:
            first_25 = features_df[features_df["SEASON"] == season].head(25)
            assert (first_25["SEASON_PHASE"] == 1).all()

    def test_games_this_season_matches_game_num(self, features_df):
        assert (features_df["GAMES_THIS_SEASON"] == features_df["GAME_NUM"]).all()
        assert "GAMES_THIS_SEASON" in MLPredictor.FEATURE_COLS

    def test_current_season_games_counts_only_current(self, features_df):
        # Frozen: _current_season_games keys off get_current_season(); today
        # (Aug 2026) that is '2025-26', which has exactly 60 synthetic games
        assert MLPredictor._current_season_games(features_df) == 60


@pytest.mark.unit
class TestEarlySeasonDamping:
    def test_neutral_at_10_games_or_unknown(self):
        assert MLPredictor._early_season_damping(10) == (1.0, 1.0)
        assert MLPredictor._early_season_damping(50) == (1.0, 1.0)
        assert MLPredictor._early_season_damping(None) == (1.0, 1.0)

    def test_zero_games_maximum_damping(self):
        conf, std = MLPredictor._early_season_damping(0)
        assert conf == pytest.approx(0.75)
        assert std == pytest.approx(1.3)

    def test_monotonic_in_games(self):
        confs = [MLPredictor._early_season_damping(g)[0] for g in range(0, 11)]
        stds = [MLPredictor._early_season_damping(g)[1] for g in range(0, 11)]
        assert confs == sorted(confs)          # confidence rises with games
        assert stds == sorted(stds, reverse=True)  # uncertainty falls
        assert confs[-1] == 1.0 and stds[-1] == 1.0


@pytest.mark.slow
class TestAllStatsTrained:
    def test_train_and_update_keep_all_four_models(self, features_df):
        predictor = MLPredictor(model_type="gradient_boost")
        assert predictor.train(features_df) is True
        for stat in ALL_STATS:
            assert stat in predictor.models, f"{stat} model missing after train()"

        # Default update() (the 7-day self-heal path) must not drop PRA
        assert predictor.update(features_df) is True
        for stat in ALL_STATS:
            assert stat in predictor.models, f"{stat} model missing after update()"

        # PRA quantile band artifacts exist (RSS floor path, not fallback)
        assert "PRA_q10" in predictor.quantile_models
        assert "PRA_q90" in predictor.quantile_models


@pytest.mark.unit
def test_prediction_response_schema_has_games_this_season():
    from api.schemas.prediction import PredictionResponse
    assert "games_this_season" in PredictionResponse.model_fields
    resp = PredictionResponse(
        player_name="Test", player_id=1, predictions={}, model_type="gradient_boost",
        games_trained_on=100, games_this_season=3,
    )
    assert resp.games_this_season == 3
