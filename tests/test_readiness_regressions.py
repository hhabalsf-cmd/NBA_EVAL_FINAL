"""Season-readiness regressions; no credentials, network or database needed."""
from contextlib import nullcontext
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
import os

import pandas as pd
import pytest

import db

pytestmark = pytest.mark.unit


def mock_db(monkeypatch, rows=()):
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.fetchall.return_value = list(rows)
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(db, "borrow_conn", lambda: nullcontext(conn))
    return cur


def pick(**changes):
    return {"id": 1, "player": "Test Player", "player_id": 1,
            "team_abbrev": "LAL", "opponent": "BOS", "stat": "PTS",
            "game_date": "2026-09-20", "line": 20, "prediction": 22,
            "direction": "OVER", **changes}


def log(**changes):
    return pd.DataFrame([{"GAME_DATE": "2026-09-20", "MATCHUP": "LAL vs. BOS",
                          "MIN": "30:30", "PTS": 20, "REB": 5, "AST": 5,
                          **changes}])


def grade(monkeypatch, frame, picks=None):
    monkeypatch.setattr(db, "today_et", lambda: date(2026, 10, 22))
    monkeypatch.setattr(db, "get_pending_picks", lambda: picks or [pick()])
    monkeypatch.setattr(db, "_check_team_played", lambda *args: True)
    void = MagicMock()
    update = MagicMock()
    monkeypatch.setattr(db, "void_pick", void)
    monkeypatch.setattr(db, "update_pick_result", update)
    mock_db(monkeypatch)
    scraper = MagicMock()
    scraper.get_player_game_log.return_value = frame
    result = db.auto_grade_picks(scraper)
    return result, scraper, void, update


@pytest.mark.parametrize("frame", [None, pd.DataFrame(), log(GAME_DATE="2026-09-19"),
                                  log(MATCHUP="LAL vs. NYK")])
def test_missing_or_wrong_game_never_becomes_a_dnp(monkeypatch, frame):
    result, _, void, update = grade(monkeypatch, frame)
    assert result["graded_count"] == 0
    void.assert_not_called()
    update.assert_not_called()


def test_old_pending_pick_is_never_voided_just_for_age(monkeypatch):
    forbidden = MagicMock(side_effect=AssertionError("must not write"))
    monkeypatch.setattr(db, "borrow_conn", forbidden)
    assert db.auto_void_stale_picks(3) == 0
    forbidden.assert_not_called()


def test_grading_uses_pick_season_and_preserves_push(monkeypatch):
    result, scraper, void, update = grade(monkeypatch, log())
    scraper.get_player_game_log.assert_called_once_with(1, seasons=["2025-26"])
    update.assert_called_once_with(1, 20.0, 20, "OVER")
    void.assert_not_called()
    assert result["graded_count"] == 1
    assert result["results"][0]["won"] is None


def test_separate_seasons_do_not_share_a_player_grading_cache(monkeypatch):
    _, scraper, _, _ = grade(monkeypatch, None, [pick(), pick(id=2, game_date="2026-10-21")])
    assert [c.kwargs["seasons"] for c in scraper.get_player_game_log.call_args_list] == [
        ["2025-26"], ["2026-27"]]


@pytest.mark.parametrize("minutes", [None, float("nan")])
def test_missing_minutes_never_voids_a_pick(monkeypatch, minutes):
    result, _, void, update = grade(monkeypatch, log(MIN=minutes, PTS=0, REB=0, AST=0))
    assert result["graded_count"] == 0
    void.assert_not_called()
    update.assert_not_called()


def test_explicit_zero_minutes_final_game_can_be_voided(monkeypatch):
    _, _, void, update = grade(monkeypatch, log(MIN="00:00", PTS=0, REB=0, AST=0))
    void.assert_called_once_with(1, "DNP")
    update.assert_not_called()


@pytest.mark.parametrize("status,expected", [("Final", True), ("Final/OT", True),
                                             ("Scheduled", False), ("3rd Qtr", False)])
def test_scheduled_game_is_not_evidence_of_completed_play(monkeypatch, status, expected):
    import bdl_client
    client = MagicMock()
    client.get_games.return_value = [{"status": status, "home_team": {"abbreviation": "LAL"},
                                     "visitor_team": {"abbreviation": "BOS"}}]
    monkeypatch.setattr(bdl_client, "get_bdl_client", lambda: client)
    monkeypatch.setattr(db, "_team_schedule_cache", {})
    monkeypatch.setattr(db, "_team_schedule_cache_times", {})
    assert db._check_team_played("LAL", date(2026, 9, 20)) is expected


def test_saving_pick_does_not_destroy_history(monkeypatch):
    cur = mock_db(monkeypatch)
    cur.fetchone.side_effect = [None, {"id": 101}]
    assert db.save_pick(pick(user_id="user")) == 101
    assert not any("DELETE" in call.args[0].upper() for call in cur.execute.call_args_list)


def test_push_is_settled_atomically(monkeypatch):
    cur = mock_db(monkeypatch)
    db.update_pick_result(1, 20, 20, "OVER")
    sql, params = cur.execute.call_args.args
    assert "graded_at = NOW()" in sql
    assert params == (20, None, 1)


@pytest.mark.parametrize("user_id", [None, "user"])
def test_pushes_are_not_returned_as_pending(monkeypatch, user_id):
    cur = mock_db(monkeypatch)
    db.get_pending_picks(user_id)
    assert "actual_result IS NULL" in cur.execute.call_args.args[0]


def test_profit_uses_minus_110_and_excludes_voids_and_paper(monkeypatch):
    cur = mock_db(monkeypatch, [{"timestamp": datetime(2026, 9, 20), "won": w}
                               for w in [1, 0, None]])
    monkeypatch.setattr(db, "_real_picks_clause", lambda: "AND COALESCE(is_paper, 0) = 0")
    result = db.get_cumulative_profit("user")
    assert [r["profit"] for r in result] == [1.0, -1.1, 0]
    assert result[-1]["cumulative_profit"] == -0.1
    assert result[0]["date"] == "2026-09-20"
    sql = cur.execute.call_args.args[0]
    assert "is_paper" in sql and "voided" in sql and "user_id = %s" in sql


def test_cache_configuration_and_age_are_checked(monkeypatch, tmp_path):
    from api.services import prediction_service as svc
    monkeypatch.setattr(svc, "PRED_CACHE_DIR", tmp_path)
    monkeypatch.delenv("NBA_EVAL_POOLED_MODEL", raising=False)
    svc._save_prediction_cache("Test Player", {"model_type": "gradient_boost"})
    assert svc._load_prediction_cache("Test Player") is not None
    assert svc._load_prediction_cache("Test Player", "random_forest") is None
    assert svc._load_prediction_cache("Test Player", use_ensemble=True) is None
    monkeypatch.setenv("NBA_EVAL_POOLED_MODEL", "1")
    assert svc._load_prediction_cache("Test Player") is None
    monkeypatch.delenv("NBA_EVAL_POOLED_MODEL")
    path = svc._prediction_cache_path("Test Player")
    old = svc.time.time() - svc.PREDICTION_CACHE_TTL - 1
    os.utime(path, (old, old))
    assert svc._load_prediction_cache("Test Player") is None


def test_cache_path_cannot_escape_directory(monkeypatch, tmp_path):
    from api.services import prediction_service as svc
    monkeypatch.setattr(svc, "PRED_CACHE_DIR", tmp_path)
    assert svc._prediction_cache_path("../../outside").parent == tmp_path


def test_portable_player_lock_excludes_concurrent_writers(monkeypatch, tmp_path):
    from filelock import FileLock, Timeout
    from api.services import prediction_service as svc
    monkeypatch.setattr(svc, "_load_nba_evaluator", lambda: SimpleNamespace(MODEL_DIR=tmp_path))
    with svc._player_model_lock("Test Player"):
        with pytest.raises(Timeout):
            with FileLock(str(tmp_path / "Test_Player.lock"), timeout=0):
                pytest.fail("second writer acquired held lock")


def test_empty_slate_does_not_borrow_tomorrows_games(monkeypatch):
    from scripts import daily_best_picks as daily
    client = MagicMock()
    client.get_games.return_value = []
    monkeypatch.setattr(daily, "get_bdl_client", lambda: client)
    monkeypatch.setattr(daily, "today_et", lambda: date(2026, 10, 19))
    assert daily._get_teams_playing_today() == []
    client.get_games.assert_called_once_with(dates=["2026-10-19"])


def test_daily_picks_use_shared_model_selector(monkeypatch):
    from scripts import daily_best_picks as daily
    from predictor_factory import build_predictor
    import pooled_predictor
    sentinel = object()
    monkeypatch.setenv("NBA_EVAL_POOLED_MODEL", "1")
    monkeypatch.setattr(pooled_predictor, "PooledPredictor", lambda: sentinel)
    assert daily.build_predictor is build_predictor
    assert daily.build_predictor(daily.ev) is sentinel


def test_disabled_generation_returns_503_before_scheduling(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routers import bets
    monkeypatch.delenv("NBA_EVAL_ENABLE_PICKS", raising=False)
    monkeypatch.setattr(bets, "verify_service_key", lambda request: None)
    response = TestClient(app).post("/api/bets/generate")
    assert response.status_code == 503


@pytest.mark.parametrize("last_date,expected", [("2026-10-20", 1), ("2026-10-21", 0)])
def test_nightly_sync_does_not_skip_second_back_to_back(monkeypatch, last_date, expected):
    from scripts import nightly_sync as sync
    monkeypatch.setattr(sync, "now_et", lambda: datetime(2026, 10, 22, 2))
    monkeypatch.setattr(db, "get_game_logs_from_supabase", lambda *args: log(GAME_DATE=last_date))
    insert = MagicMock()
    monkeypatch.setattr(db, "insert_game_logs_to_supabase", insert)
    scraper = MagicMock()
    scraper.get_player_game_log.return_value = log(GAME_DATE="2026-10-21")
    monkeypatch.setattr(sync, "NBADataScraper", lambda: scraper)
    assert sync.sync_player_game_logs([{"id": 1, "name": "Test Player"}], "2026-27") == expected
    assert scraper.get_player_game_log.call_count == expected
    assert insert.call_count == expected


def test_paper_report_distinguishes_push_from_pending(monkeypatch):
    import paper_tracking as paper
    monkeypatch.setattr(paper.ts, "missing_schema", lambda: [])
    monkeypatch.setattr(paper, "get_paper_picks", lambda: [
        {"won": None, "actual_result": 20}, {"won": None, "actual_result": None}])
    report = paper.build_report()
    assert report["pending"] == 1
    assert report["pushes"] == 1
    assert report["record"]["n"] == 0


@pytest.mark.parametrize("outcomes,status", [([1, "push"], "won"), ([0, "push"], "lost"),
                                             (["push"], "voided"), ([1, None], None)])
def test_parlay_pushes_do_not_remain_pending(monkeypatch, outcomes, status):
    cur = mock_db(monkeypatch)
    legs = [{"won": None if v == "push" else v, "voided": 0,
             "actual_result": 20 if v == "push" else None} for v in outcomes]
    cur.fetchall.side_effect = [[{"id": 7}], legs]
    result = db.grade_pending_parlays("user")
    assert result["parlays_graded"] == (1 if status else 0)
    if status:
        assert cur.execute.call_args.args[1] == (status, 7)
