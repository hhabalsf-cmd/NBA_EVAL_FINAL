"""Tests for db.get_game_logs_multi_season with a mocked connection."""
import contextlib
from unittest.mock import MagicMock

import pytest

import db


def _mock_conn(monkeypatch, rows):
    """Patch db.borrow_conn to yield a fake connection returning `rows`."""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor

    @contextlib.contextmanager
    def fake_borrow_conn():
        yield conn

    monkeypatch.setattr(db, "borrow_conn", fake_borrow_conn)
    return cursor


def _row(game_date: str, season: str, pts: int) -> dict:
    return {
        "player_id": "2544",
        "game_id": f"g{game_date}",
        "game_date": game_date,
        "season": season,
        "matchup": "LAL vs. BOS",
        "pts": pts,
        "reb": 7,
        "ast": 8,
        "min": 35.0,
    }


@pytest.mark.unit
class TestGetGameLogsMultiSeason:
    def test_pools_rows_across_seasons_with_nba_columns(self, monkeypatch):
        rows = [
            _row("2024-11-01", "2024-25", 25),
            _row("2025-11-01", "2025-26", 30),
            _row("2026-10-25", "2026-27", 28),
        ]
        cursor = _mock_conn(monkeypatch, rows)

        df = db.get_game_logs_multi_season("2544", ["2026-27", "2025-26", "2024-25"])

        assert len(df) == 3
        # Renamed to NBA API column format
        for col in ("GAME_DATE", "PTS", "REB", "AST", "SEASON", "MATCHUP"):
            assert col in df.columns
        assert sorted(df["SEASON"].unique()) == ["2024-25", "2025-26", "2026-27"]

        # The SQL must filter by ANY(seasons)
        sql, params = cursor.execute.call_args[0]
        assert "season = ANY(%s)" in sql
        assert "ORDER BY game_date ASC" in sql
        assert params == ("2544", ["2026-27", "2025-26", "2024-25"])

    def test_returns_none_when_no_rows(self, monkeypatch):
        _mock_conn(monkeypatch, [])
        assert db.get_game_logs_multi_season("2544", ["2026-27"]) is None

    def test_rejects_empty_seasons(self):
        with pytest.raises(ValueError):
            db.get_game_logs_multi_season("2544", [])
