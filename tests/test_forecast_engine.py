"""Causality, distribution accounting, exact-price math, and serving contracts."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pandas as pd
import pytest

from forecasting.features import FEATURES, STATS, build_panel, normalize_logs, serve_features
from forecasting.model import CountDistribution, ForecastModel, PointModel
from forecasting.offers import Offer, decimal_odds, evaluate_offer
from forecasting.service import forecast_player


def logs(n=45, start="2023-10-01", player="7"):
    rng = np.random.default_rng(77)
    return pd.DataFrame({"PLAYER_ID": player, "GAME_ID": [str(i) for i in range(n)],
                         "GAME_DATE": pd.date_range(start, periods=n, freq="2D"),
                         "TEAM": "BOS", "HOME": np.arange(n) % 2,
                         "MIN": rng.integers(20, 40, n), "PTS": rng.poisson(20, n),
                         "REB": rng.poisson(6, n), "AST": rng.poisson(4, n)})


@pytest.fixture(scope="module")
def model():
    history = pd.concat([logs(player=str(i)) for i in range(3)], ignore_index=True)
    panel = build_panel(history)
    return ForecastModel.fit(panel[panel.game_date < "2023-12-01"], panel[panel.game_date >= "2023-12-01"],
                             {s: "ridge" for s in STATS})


def test_panel_matches_serve_across_offseason_and_trade():
    data = logs()
    data.loc[30:, "GAME_DATE"] += pd.Timedelta(days=310)
    data.loc[30:, "TEAM"] = "NYK"
    panel = build_panel(data)
    for i in (10, 29, 30, 44):
        row = data.iloc[i]
        served = serve_features(data, row.GAME_DATE, row.TEAM, bool(row.HOME))
        trained = panel[panel.game_date == row.GAME_DATE].iloc[0]
        assert served == {key: trained[key] for key in served}
    first = panel[panel.game_date == data.iloc[30].GAME_DATE].iloc[0]
    assert first.team_changed == 1 and first.long_absence == 1 and first.season_games == 0


def test_target_and_future_outcomes_cannot_change_features():
    data = logs()
    before = build_panel(data).iloc[:20][list(FEATURES)]
    data.loc[29:, ["PTS", "REB", "AST", "MIN"]] = 999
    after = build_panel(data).iloc[:20][list(FEATURES)]
    # Row 29's outcome is unseen by its own prediction; row 30 would change.
    pd.testing.assert_frame_equal(before, after)


def test_pra_is_recomputed_and_upcoming_rows_ignored():
    data = logs()
    data["PRA"] = 999
    data["IS_UPCOMING_GAME"] = 0
    data.loc[44, "IS_UPCOMING_GAME"] = 1
    out = normalize_logs(data)
    assert len(out) == 44
    assert np.array_equal(out.PRA, out.PTS + out.REB + out.AST)


@pytest.mark.parametrize("defect", ["duplicate", "negative", "missing", "nonfinite", "fractional"])
def test_invalid_history_fails_closed(defect):
    data = logs()
    if defect == "duplicate":
        data = pd.concat([data, data.iloc[[0]]])
    elif defect == "negative":
        data.loc[0, "PTS"] = -1
    elif defect == "missing":
        data = data.drop(columns=["AST"])
    elif defect == "nonfinite":
        data["MIN"] = np.nan
    else:
        data["AST"] = 1.5
    with pytest.raises((ValueError, TypeError)):
        normalize_logs(data)


def test_sparse_and_multiple_player_histories_rejected():
    with pytest.raises(ValueError, match="10 prior"):
        serve_features(logs(5), "2024-01-01", "BOS", True)
    with pytest.raises(ValueError, match="one player"):
        serve_features(pd.concat([logs(player="7"), logs(player="8")]), "2024-01-01", "BOS", True)


@pytest.mark.parametrize("line", [0, 0.5, 10, 10.5, 11, 13.5])
def test_discrete_probabilities_match_explicit_samples(line):
    residuals = np.array([-15, -1.5, -1, -0.5, 0, 0.5, 1, 3])
    dist = CountDistribution(10, 1, residuals)
    samples = np.maximum(0, np.floor(10 + residuals + 0.5))
    p = dist.probabilities(line)
    assert p == {"over": float(np.mean(samples > line)), "under": float(np.mean(samples < line)),
                 "push": float(np.mean(samples == line))}
    assert sum(p.values()) == pytest.approx(1)


def test_probability_monotonicity_and_nonnegative_intervals():
    dist = CountDistribution(2, 4, np.linspace(-3, 3, 301))
    overs = [dist.probabilities(x)["over"] for x in np.arange(0, 20, 0.5)]
    assert np.all(np.diff(overs) <= 0)
    assert dist.quantile(0) == 0
    assert dist.quantile(0.1) <= dist.quantile(0.5) <= dist.quantile(0.9)


NOW = datetime(2026, 10, 22, 18, tzinfo=timezone.utc)


def offer(**kwargs):
    item = Offer("event", "7", "PTS", "OVER", 10.5, 1.5, "test-book",
                 NOW - timedelta(minutes=1), NOW + timedelta(hours=2))
    return replace(item, **kwargs)


def evaluate(item, **kwargs):
    # 60% win and 40% loss above 10.5.
    dist = CountDistribution(10, 1, np.array([-2, -1, 1, 2, 3]))
    return evaluate_offer(dist, item, event_id="event", player_id="7", stat="PTS", as_of=NOW,
                          eligible=True, **kwargs)


def test_probability_is_not_price_edge_and_no_unvalidated_recommendation():
    value = evaluate(offer())
    assert value["prob_win"] == pytest.approx(0.6)
    assert value["expected_profit_per_unit_risked"] == pytest.approx(-0.1)
    assert value["recommend"] is False
    positive = evaluate(offer(decimal_odds=2))
    assert positive["expected_profit_per_unit_risked"] == pytest.approx(0.2)
    assert positive["recommend"] is False


def test_push_returns_stake_and_under_uses_opposite_outcome():
    value = evaluate(offer(line=11, side="UNDER", decimal_odds=2))
    assert value["prob_win"] == pytest.approx(0.4)
    assert value["prob_push"] == pytest.approx(0.2)
    assert value["expected_profit_per_unit_risked"] == pytest.approx(0)


@pytest.mark.parametrize("change", [
    {"event_id": "other"}, {"player_id": "8"}, {"stat": "REB"},
    {"captured_at": NOW + timedelta(seconds=1)},
    {"captured_at": NOW - timedelta(hours=1)}, {"starts_at": NOW},
    {"captured_at": NOW.replace(tzinfo=None)}, {"decimal_odds": 1},
    {"decimal_odds": float("inf")}, {"line": float("nan")}, {"side": "SIDE"},
])
def test_invalid_offer_rejected(change):
    with pytest.raises(ValueError):
        evaluate(offer(**change))


def test_american_odds_conversion():
    assert decimal_odds(-200) == 1.5
    assert decimal_odds(150) == 2.5
    with pytest.raises(ValueError):
        decimal_odds(-50)


def test_calibration_cannot_overlap_training():
    panel = build_panel(logs())
    with pytest.raises(ValueError, match="strictly later"):
        ForecastModel.fit(panel, panel, {s: "ridge" for s in STATS})


def test_service_rejects_artifact_from_after_prediction_as_of(model):
    cutoff = datetime.fromisoformat(model.metadata['calibrated_through']).replace(tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='as-of date'):
        forecast_player(logs(), model=model, player_id='7', event_id='e',
                        starts_at=cutoff + timedelta(days=3), team='BOS', home=True, as_of=cutoff)


@pytest.mark.parametrize('defect', ['missing_stat', 'wrong_stat', 'bad_residuals', 'wrong_count', 'manifest'])
def test_artifact_internal_inconsistencies_rejected(model, tmp_path, defect):
    import copy
    changed = copy.deepcopy(model)
    if defect == 'missing_stat': changed.models.pop('AST')
    if defect == 'wrong_stat': changed.models['PTS'].stat = 'REB'
    if defect == 'bad_residuals': changed.residuals['PTS'] = np.array([[1, 2]])
    if defect == 'wrong_count': changed.metadata['calibration_rows'] += 1
    path = tmp_path / 'bad.pkl'
    changed.save(path)
    if defect == 'manifest':
        manifest = json.loads(path.with_suffix('.json').read_text())
        manifest['calibrated_through'] = '1900-01-01'
        path.with_suffix('.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError): ForecastModel.load(path)


def test_future_artifact_cannot_predict_past(model):
    features = serve_features(logs(), "2024-01-01", "BOS", True)
    with pytest.raises(ValueError, match="cutoff"):
        model.distributions(features, "2023-11-01")


def test_artifact_roundtrip_and_corruption(model, tmp_path):
    path = tmp_path / "model.pkl"
    digest = model.save(path)
    loaded = ForecastModel.load(path)
    assert loaded.metadata["artifact_sha256"] == digest
    features = serve_features(logs(), "2024-01-01", "BOS", True)
    assert loaded.distributions(features, "2024-01-01")["PTS"].summary() == model.distributions(features, "2024-01-01")["PTS"].summary()
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="digest"):
        ForecastModel.load(path)


def test_service_returns_forecast_with_no_training_or_heuristic_adjustments(model):
    result = forecast_player(logs(), model=model, player_id="7", event_id="event",
                             starts_at=NOW + timedelta(hours=2), team="BOS", home=True,
                             as_of=NOW, offers=[offer()], availability="available")
    assert set(result["predictions"]) == set(STATS)
    assert result["offers"][0]["recommend"] is False
    assert result["predictions"]["PTS"]["interval_level"] == 0.8


@pytest.mark.parametrize("availability", ["out", "invalid"])
def test_out_or_invalid_status_abstains(model, availability):
    with pytest.raises(ValueError):
        forecast_player(logs(), model=model, player_id="7", event_id="event", starts_at=NOW + timedelta(hours=2),
                        team="BOS", home=True, as_of=NOW, availability=availability)


def test_service_ignores_current_day_box_scores(model):
    data = logs(start="2026-08-01")
    today_row = data.iloc[[-1]].copy()
    today_row["GAME_DATE"] = pd.Timestamp("2026-10-22")
    today_row[["PTS", "REB", "AST"]] = 999
    args = dict(model=model, player_id="7", event_id="event", starts_at=NOW + timedelta(hours=2),
                team="BOS", home=True, as_of=NOW)
    # Last rows in the fixture fall after NOW and must also be excluded.
    a = forecast_player(data, **args)
    data = data[data.GAME_DATE != pd.Timestamp("2026-10-22")]
    b = forecast_player(pd.concat([data, today_row]), **args)
    assert a["predictions"] == b["predictions"]


def test_forecast_endpoint_is_authenticated_and_missing_artifact_is_503(monkeypatch):
    monkeypatch.setenv("FASTAPI_SERVICE_KEY", "audit-local-test-service-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://audit:audit@127.0.0.1:1/audit")
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routers.auth import get_current_user
    from api.routers import forecasts
    client = TestClient(app)
    body = {"player_name": "Test Player", "event_id": "event", "starts_at": NOW.isoformat(), "team": "BOS", "home": True}
    assert client.post("/api/forecasts/player", json=body).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: {"id": "test"}
    try:
        def missing():
            raise FileNotFoundError("missing")
        monkeypatch.setattr(forecasts, "load_model", missing)
        assert client.post("/api/forecasts/player", json=body).status_code == 503
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_candidate_features_exclude_current_game_outcome():
    assert all("actual" not in feature.lower() for feature in FEATURES)
    panel = build_panel(logs())
    train, test = panel.iloc[:20], panel.iloc[20:]
    model = PointModel.fit(train, "PTS", "ridge")
    expected = model.predict(test)
    poisoned = test.copy()
    for stat in STATS:
        poisoned[f"{stat}_actual"] = 999
    np.testing.assert_array_equal(expected, model.predict(poisoned))


def test_authenticated_endpoint_uses_new_model_and_serializes_offer(monkeypatch, model):
    monkeypatch.setenv("FASTAPI_SERVICE_KEY", "audit-local-test-service-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://audit:audit@127.0.0.1:1/audit")
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routers.auth import get_current_user
    from api.routers import forecasts
    now = datetime.now(timezone.utc)
    start = now + timedelta(days=2)
    monkeypatch.setattr(forecasts, "load_model", lambda: model)
    source = SimpleNamespace(get_player_info=lambda name: {"player_id": 7, "player_name": name},
                             scraper=SimpleNamespace(get_player_game_log=lambda *a, **k: logs()))
    monkeypatch.setattr(forecasts, "get_prediction_service", lambda: source)
    body = {"player_name": "Test Player", "event_id": "event", "starts_at": start.isoformat(),
            "team": "BOS", "home": True, "availability": "available", "offers": [{
                "event_id": "event", "player_id": "7", "stat": "PTS", "side": "OVER", "line": 20,
                "decimal_odds": 1.91, "book": "test-book", "captured_at": now.isoformat(),
                "starts_at": start.isoformat()}]}
    app.dependency_overrides[get_current_user] = lambda: {"id": "test"}
    try:
        client = TestClient(app)
        response = client.post("/api/forecasts/player", json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["model_type"] == "forecast_v1"
        assert result["model"]["selected"] == {s: "ridge" for s in STATS}
        quote = result["offers"][0]
        assert quote["prob_win"] + quote["prob_loss"] + quote["prob_push"] == pytest.approx(1)
        assert quote["recommend"] is False
        body["offers"][0]["player_id"] = "8"
        assert client.post("/api/forecasts/player", json=body).status_code == 422
        body["availability"] = "out"
        monkeypatch.setattr(forecasts, "load_model", lambda: pytest.fail("Out players should fail before artifact/provider work"))
        assert client.post("/api/forecasts/player", json=body).status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
