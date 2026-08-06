"""Tests for line_sources — key resolution and source fallback chain."""
import json
from unittest.mock import patch

import pytest

import line_sources


@pytest.mark.unit
class TestResolveOddsApiKey:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("ODDS_API_KEY", "env-key")
        assert line_sources._resolve_odds_api_key() == "env-key"

    def test_config_json_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"odds_api_key": "config-key"}))
        monkeypatch.setattr(line_sources, "_CONFIG_PATH", cfg)
        assert line_sources._resolve_odds_api_key() == "config-key"

    def test_none_when_nothing_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        monkeypatch.setattr(line_sources, "_CONFIG_PATH", tmp_path / "missing.json")
        assert line_sources._resolve_odds_api_key() is None

    def test_malformed_config_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        cfg = tmp_path / "config.json"
        cfg.write_text("{not json")
        monkeypatch.setattr(line_sources, "_CONFIG_PATH", cfg)
        assert line_sources._resolve_odds_api_key() is None


_PROPS = [{"player": "LeBron James", "stat": "PTS", "consensus_line": 25.5,
           "home_team": "LAL", "away_team": "BOS"}]


@pytest.mark.unit
class TestFetchTodaysProps:
    def test_odds_api_first(self):
        with patch.object(line_sources, "_fetch_odds_api_props", return_value=_PROPS), \
             patch.object(line_sources, "_fetch_manual_props") as manual:
            assert line_sources.fetch_todays_props() == _PROPS
            manual.assert_not_called()

    def test_manual_fallback_when_odds_api_empty(self):
        with patch.object(line_sources, "_fetch_odds_api_props", return_value=[]), \
             patch.object(line_sources, "_fetch_manual_props", return_value=_PROPS):
            assert line_sources.fetch_todays_props() == _PROPS

    def test_empty_when_no_source(self):
        with patch.object(line_sources, "_fetch_odds_api_props", return_value=[]), \
             patch.object(line_sources, "_fetch_manual_props", return_value=[]):
            assert line_sources.fetch_todays_props() == []

    def test_manual_rows_normalized(self, monkeypatch):
        rows = [{"player": "Jayson Tatum", "stat": "PRA", "line": "41.5",
                 "home_team": "BOS", "away_team": None}]

        class _FakeDb:
            @staticmethod
            def get_manual_lines(date_str=None):
                return rows

        monkeypatch.setitem(__import__("sys").modules, "db", _FakeDb)
        props = line_sources._fetch_manual_props()
        assert props == [{"player": "Jayson Tatum", "stat": "PRA",
                          "consensus_line": 41.5, "home_team": "BOS", "away_team": ""}]
