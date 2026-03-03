"""Tests for Supabase game log cache helpers in db.py."""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Provide a fake DATABASE_URL so importing db doesn't crash
os.environ.setdefault("DATABASE_URL", "postgresql://fake/test")

import db


SAMPLE_ROWS = [
    {
        "player_id": "203999", "season": "2024-25", "season_id": "22024",
        "game_id": "0022401001", "game_date": "2025-01-15",
        "matchup": "DEN vs. OKC", "wl": "W",
        "min": 35.0, "fgm": 10.0, "fga": 18.0, "fg_pct": 0.556,
        "fg3m": 3.0, "fg3a": 7.0, "fg3_pct": 0.429,
        "ftm": 4.0, "fta": 5.0, "ft_pct": 0.800,
        "oreb": 1.0, "dreb": 7.0, "reb": 8.0, "ast": 9.0,
        "stl": 2.0, "blk": 1.0, "tov": 3.0, "pf": 2.0,
        "pts": 27.0, "plus_minus": 12.0, "video_available": 1,
    }
]


def make_mock_conn(rows):
    """Build a mock psycopg2 connection that returns `rows` from fetchall."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = False
    return mock_conn, mock_cursor


# ── get_game_logs_from_supabase ───────────────────────────────

class TestGetGameLogsFromSupabase:
    def test_returns_dataframe_when_rows_exist(self):
        mock_conn, mock_cursor = make_mock_conn(SAMPLE_ROWS)
        with patch("db.get_connection", return_value=mock_conn):
            result = db.get_game_logs_from_supabase("203999", "2024-25")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_returns_none_when_no_rows(self):
        mock_conn, mock_cursor = make_mock_conn([])
        with patch("db.get_connection", return_value=mock_conn):
            result = db.get_game_logs_from_supabase("203999", "2024-25")
        assert result is None

    def test_column_names_match_nba_api_format(self):
        """Returned DataFrame must use uppercase column names matching NBA API."""
        mock_conn, mock_cursor = make_mock_conn(SAMPLE_ROWS)
        with patch("db.get_connection", return_value=mock_conn):
            result = db.get_game_logs_from_supabase("203999", "2024-25")
        assert "GAME_DATE" in result.columns
        assert "PTS" in result.columns
        assert "MATCHUP" in result.columns
        assert "Game_ID" in result.columns
        assert "Player_ID" in result.columns
        assert "SEASON" in result.columns

    def test_queries_correct_player_and_season(self):
        mock_conn, mock_cursor = make_mock_conn(SAMPLE_ROWS)
        with patch("db.get_connection", return_value=mock_conn):
            db.get_game_logs_from_supabase("203999", "2024-25")
        call_args = mock_cursor.execute.call_args
        sql, params = call_args[0]
        assert "player_id" in sql.lower()
        assert "season" in sql.lower()
        assert ("203999", "2024-25") == params


# ── insert_game_logs_to_supabase ─────────────────────────────

class TestInsertGameLogsToSupabase:
    def _make_sample_df(self):
        return pd.DataFrame([{
            "SEASON_ID": "22024", "Player_ID": "203999", "Game_ID": "0022401001",
            "GAME_DATE": "JAN 15, 2025", "MATCHUP": "DEN vs. OKC", "WL": "W",
            "MIN": "35:00", "FGM": 10, "FGA": 18, "FG_PCT": 0.556,
            "FG3M": 3, "FG3A": 7, "FG3_PCT": 0.429,
            "FTM": 4, "FTA": 5, "FT_PCT": 0.8,
            "OREB": 1, "DREB": 7, "REB": 8, "AST": 9,
            "STL": 2, "BLK": 1, "TOV": 3, "PF": 2,
            "PTS": 27, "PLUS_MINUS": 12, "VIDEO_AVAILABLE": 1,
            "SEASON": "2024-25",
        }])

    def test_executes_insert(self):
        mock_conn, mock_cursor = make_mock_conn([])
        df = self._make_sample_df()
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(df, "203999", "2024-25")
        assert mock_cursor.executemany.called

    def test_uses_on_conflict_do_nothing(self):
        mock_conn, mock_cursor = make_mock_conn([])
        df = self._make_sample_df()
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(df, "203999", "2024-25")
        call_sql = mock_cursor.executemany.call_args[0][0]
        assert "ON CONFLICT" in call_sql.upper()
        assert "DO NOTHING" in call_sql.upper()

    def test_commits(self):
        mock_conn, _ = make_mock_conn([])
        df = self._make_sample_df()
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(df, "203999", "2024-25")
        mock_conn.commit.assert_called_once()

    def test_empty_df_is_noop(self):
        mock_conn, mock_cursor = make_mock_conn([])
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(pd.DataFrame(), "203999", "2024-25")
        mock_cursor.executemany.assert_not_called()


# ── get_player_game_log integration ──────────────────────────

import nba_evaluator as nba_eval
from nba_evaluator import NBADataScraper


class TestGetPlayerGameLogWithCache:
    """Tests that get_player_game_log() uses Supabase for historical seasons."""

    def _make_fake_api_df(self, season):
        return pd.DataFrame([{
            "SEASON_ID": "22024", "Player_ID": "203999", "Game_ID": f"002240{season[-2:]}01",
            "GAME_DATE": "JAN 15, 2025", "MATCHUP": "DEN vs. OKC", "WL": "W",
            "MIN": "35:00", "FGM": 10, "FGA": 18, "FG_PCT": 0.556,
            "FG3M": 3, "FG3A": 7, "FG3_PCT": 0.429,
            "FTM": 4, "FTA": 5, "FT_PCT": 0.8,
            "OREB": 1, "DREB": 7, "REB": 8, "AST": 9,
            "STL": 2, "BLK": 1, "TOV": 3, "PF": 2,
            "PTS": 27, "PLUS_MINUS": 12, "VIDEO_AVAILABLE": 1,
            "SEASON": season,
        }])

    def test_historical_season_hits_supabase_not_api(self):
        """When Supabase has the data, NBA API must NOT be called for historical seasons."""
        fake_df = self._make_fake_api_df("2024-25")

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase", return_value=fake_df) as mock_get, \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog") as mock_api:
            result = scraper.get_player_game_log("203999", seasons=["2024-25"])

        mock_get.assert_called_once_with("203999", "2024-25")
        mock_api.assert_not_called()
        assert len(result) == 1

    def test_historical_season_miss_calls_api_then_stores(self):
        """On Supabase miss, NBA API is called and result is written to Supabase."""
        fake_df = self._make_fake_api_df("2024-25")
        mock_log = MagicMock()
        mock_log.get_data_frames.return_value = [fake_df]

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase", return_value=None), \
             patch("db.insert_game_logs_to_supabase") as mock_insert, \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog", return_value=mock_log), \
             patch("time.sleep"):
            result = scraper.get_player_game_log("203999", seasons=["2024-25"])

        mock_insert.assert_called_once()
        assert len(result) == 1

    def test_current_season_skips_supabase(self):
        """Current season (2025-26) must always hit the NBA API, never Supabase."""
        fake_df = self._make_fake_api_df("2025-26")
        mock_log = MagicMock()
        mock_log.get_data_frames.return_value = [fake_df]

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase") as mock_get, \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog", return_value=mock_log), \
             patch("time.sleep"), \
             patch("nba_evaluator.CacheManager.get", return_value=None), \
             patch("nba_evaluator.CacheManager.set"):
            result = scraper.get_player_game_log("203999", seasons=["2025-26"])

        mock_get.assert_not_called()

    def test_three_seasons_returns_combined_df(self):
        """Full three-season call returns all games sorted ascending by date."""
        fake_historical_df = pd.concat([
            self._make_fake_api_df("2024-25"),
            self._make_fake_api_df("2023-24"),
        ])
        fake_current_df = self._make_fake_api_df("2025-26")
        mock_log = MagicMock()
        mock_log.get_data_frames.return_value = [fake_current_df]

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase", return_value=fake_historical_df), \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog", return_value=mock_log), \
             patch("time.sleep"), \
             patch("nba_evaluator.CacheManager.get", return_value=None), \
             patch("nba_evaluator.CacheManager.set"):
            result = scraper.get_player_game_log("203999")

        # Should have all 3 seasons' games
        assert len(result) >= 3
