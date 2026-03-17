"""Tests for the /api/players/{name}/scenarios endpoint."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Provide required env vars before importing the app
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-supabase-jwt-secret-that-is-long-enough-32ch")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("FASTAPI_SERVICE_KEY", "test-fastapi-service-key")

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
import pandas as pd


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


def _make_game_log_df(game_ids, matchups):
    """Helper: build a minimal game log DataFrame."""
    rows = []
    for i, (gid, matchup) in enumerate(zip(game_ids, matchups)):
        rows.append({
            'Game_ID': gid,
            'GAME_DATE': f'2026-01-{10 + i:02d}',
            'MATCHUP': matchup,
            'WL': 'W',
            'PTS': 25.0 + i,
            'REB': 5.0,
            'AST': 7.0,
            'STL': 1.0,
            'BLK': 0.5,
            'TOV': 2.0,
            'FG3M': 3.0,
            'MIN': 35.0,
        })
    return pd.DataFrame(rows)


def _make_bdl_stats(player_id, player_name, game_ids, team_abbrev,
                    home_team_id=1, visitor_team_id=2):
    """Helper: build mock BDL get_player_stats response entries."""
    stats = []
    for gid in game_ids:
        stats.append({
            'player': {
                'id': player_id,
                'first_name': player_name.split()[0],
                'last_name': player_name.split()[-1],
            },
            'game': {
                'id': gid,
                'home_team_id': home_team_id,
                'visitor_team_id': visitor_team_id,
            },
            'team': {'abbreviation': team_abbrev},
        })
    return stats


class TestScenariosEndpoint:
    """Tests for GET /api/players/{name}/scenarios."""

    @patch('api.routers.players.get_prediction_service')
    def test_player_not_found_returns_404(self, mock_svc, client):
        mock_svc.return_value.get_player_info.return_value = None
        resp = client.get('/api/players/Nonexistent Player/scenarios')
        assert resp.status_code == 404

    @patch('api.routers.players.get_prediction_service')
    def test_empty_game_log_returns_empty(self, mock_svc, client):
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 100, 'id': 100,
            'team_abbrev': 'ATL', 'player_name': 'Test Player',
        }
        svc.scraper.get_player_game_log.return_value = pd.DataFrame()
        resp = client.get('/api/players/Test Player/scenarios')
        assert resp.status_code == 200
        data = resp.json()
        assert data['teammate_scenarios'] == []
        assert data['opponent_scenarios'] == []

    @patch('api.routers.players.get_player_mapper')
    @patch('api.routers.players.get_bdl_client')
    @patch('api.routers.players.get_prediction_service')
    def test_teammate_with_without_splits(self, mock_svc, mock_bdl,
                                          mock_pm, client):
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 100, 'id': 100,
            'team_abbrev': 'ATL', 'player_name': 'Star Player',
        }

        # 10 games total
        game_ids = list(range(1, 11))
        matchups = ['ATL vs. BOS'] * 10
        svc.scraper.get_player_game_log.return_value = _make_game_log_df(
            game_ids, matchups
        )

        # Teammate played in games 1-7, missed 8-10 (3 absences)
        teammate_stats = _make_bdl_stats(200, 'Teammate One',
                                          list(range(1, 8)), 'ATL')
        # Target player stats (all 10 games)
        target_stats = _make_bdl_stats(100, 'Star Player',
                                        game_ids, 'ATL')

        bdl_instance = mock_bdl.return_value
        bdl_instance.get_player_stats.return_value = teammate_stats + target_stats

        svc.get_injuries.return_value = {}
        svc.scraper.get_player_next_game.return_value = None
        mock_pm.return_value.nba_to_bdl.return_value = 100

        # Clear cache to avoid cross-test pollution
        from api.routers.players import _scenarios_cache
        _scenarios_cache.clear()

        resp = client.get('/api/players/Star Player/scenarios')

        assert resp.status_code == 200
        data = resp.json()
        assert len(data['teammate_scenarios']) >= 1
        scenario = data['teammate_scenarios'][0]
        assert scenario['player_name'] == 'Teammate One'
        assert scenario['with_splits']['games'] == 7
        assert scenario['without_splits']['games'] == 3

    @patch('api.routers.players.get_player_mapper')
    @patch('api.routers.players.get_bdl_client')
    @patch('api.routers.players.get_prediction_service')
    def test_trade_filter_excludes_recent_acquisition(self, mock_svc,
                                                       mock_bdl, mock_pm,
                                                       client):
        """Player traded TO the team mid-season (only 3 games together)
        should be excluded by the 5-game minimum 'with' filter."""
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 100, 'id': 100,
            'team_abbrev': 'ATL', 'player_name': 'Star Player',
        }

        game_ids = list(range(1, 11))
        matchups = ['ATL vs. BOS'] * 10
        svc.scraper.get_player_game_log.return_value = _make_game_log_df(
            game_ids, matchups
        )

        # New acquisition only played 3 games with the team
        new_player_stats = _make_bdl_stats(300, 'New Acquisition',
                                            [8, 9, 10], 'ATL')
        target_stats = _make_bdl_stats(100, 'Star Player',
                                        game_ids, 'ATL')

        bdl_instance = mock_bdl.return_value
        bdl_instance.get_player_stats.return_value = (
            new_player_stats + target_stats
        )

        svc.get_injuries.return_value = {}
        svc.scraper.get_player_next_game.return_value = None
        mock_pm.return_value.nba_to_bdl.return_value = 100

        from api.routers.players import _scenarios_cache
        _scenarios_cache.clear()

        resp = client.get('/api/players/Star Player/scenarios')

        data = resp.json()
        names = [s['player_name'] for s in data['teammate_scenarios']]
        assert 'New Acquisition' not in names

    @patch('api.routers.players.get_bdl_client')
    @patch('api.routers.players.get_prediction_service')
    def test_bdl_failure_returns_empty(self, mock_svc, mock_bdl, client):
        """BDL API failure should return 200 with empty lists."""
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 100, 'id': 100,
            'team_abbrev': 'ATL', 'player_name': 'Star Player',
        }
        svc.scraper.get_player_game_log.return_value = _make_game_log_df(
            [1, 2, 3], ['ATL vs. BOS'] * 3
        )

        bdl_instance = mock_bdl.return_value
        bdl_instance.get_player_stats.side_effect = Exception("API down")

        from api.routers.players import _scenarios_cache
        _scenarios_cache.clear()

        resp = client.get('/api/players/Star Player/scenarios')
        assert resp.status_code == 200
        data = resp.json()
        assert data['teammate_scenarios'] == []

    @patch('api.routers.players.get_player_mapper')
    @patch('api.routers.players.get_bdl_client')
    @patch('api.routers.players.get_prediction_service')
    def test_currently_out_flag(self, mock_svc, mock_bdl, mock_pm, client):
        """Teammates on injury report should have currently_out=True."""
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 100, 'id': 100,
            'team_abbrev': 'ATL', 'player_name': 'Star Player',
        }

        game_ids = list(range(1, 11))
        matchups = ['ATL vs. BOS'] * 10
        svc.scraper.get_player_game_log.return_value = _make_game_log_df(
            game_ids, matchups
        )

        teammate_stats = _make_bdl_stats(200, 'Injured Teammate',
                                          list(range(1, 8)), 'ATL')
        target_stats = _make_bdl_stats(100, 'Star Player',
                                        game_ids, 'ATL')

        bdl_instance = mock_bdl.return_value
        bdl_instance.get_player_stats.return_value = (
            teammate_stats + target_stats
        )

        svc.get_injuries.return_value = {
            'ATL': {
                'out': 1, 'questionable': 0, 'doubtful': 0,
                'players': [{'name': 'Injured Teammate', 'status': 'out'}],
            }
        }
        svc.scraper.get_player_next_game.return_value = None
        mock_pm.return_value.nba_to_bdl.return_value = 100

        from api.routers.players import _scenarios_cache
        _scenarios_cache.clear()

        resp = client.get('/api/players/Star Player/scenarios')

        data = resp.json()
        assert len(data['teammate_scenarios']) >= 1
        assert data['teammate_scenarios'][0]['currently_out'] is True

    @patch('api.routers.players.get_player_mapper')
    @patch('api.routers.players.get_bdl_client')
    @patch('api.routers.players.get_prediction_service')
    def test_opponent_scenarios(self, mock_svc, mock_bdl, mock_pm, client):
        """Opponent players with H2H present+absent games should appear."""
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 100, 'id': 100,
            'team_abbrev': 'ATL', 'player_name': 'Star Player',
        }

        # 4 games vs BOS (games 1-4), 6 vs other teams
        game_ids = list(range(1, 11))
        matchups = (['ATL vs. BOS'] * 4
                    + ['ATL vs. MIA'] * 6)
        svc.scraper.get_player_game_log.return_value = _make_game_log_df(
            game_ids, matchups
        )

        # BOS player played in games 1-2, missed 3-4
        opp_stats = _make_bdl_stats(500, 'Opp Star',
                                     [1, 2], 'BOS')
        target_stats = _make_bdl_stats(100, 'Star Player',
                                        game_ids, 'ATL')

        bdl_instance = mock_bdl.return_value
        bdl_instance.get_player_stats.return_value = opp_stats + target_stats

        svc.get_injuries.return_value = {
            'BOS': {
                'out': 1, 'questionable': 0, 'doubtful': 0,
                'players': [{'name': 'Opp Star', 'status': 'out'}],
            }
        }
        svc.scraper.get_player_next_game.return_value = {
            'opponent': 'BOS', 'matchup': 'ATL vs. BOS',
            'is_home': True, 'game_date': '2026-03-20',
        }
        mock_pm.return_value.nba_to_bdl.return_value = 100

        from api.routers.players import _scenarios_cache
        _scenarios_cache.clear()

        resp = client.get('/api/players/Star Player/scenarios')

        data = resp.json()
        assert len(data['opponent_scenarios']) >= 1
        opp = data['opponent_scenarios'][0]
        assert opp['player_name'] == 'Opp Star'
        assert opp['currently_out'] is True
        assert opp['with_splits']['games'] == 2
        assert opp['without_splits']['games'] == 2

    @patch('api.routers.players.get_player_mapper')
    @patch('api.routers.players.get_bdl_client')
    @patch('api.routers.players.get_prediction_service')
    def test_cache_prevents_refetch(self, mock_svc, mock_bdl, mock_pm,
                                     client):
        """Second call within TTL should return cached result."""
        svc = mock_svc.return_value
        svc.get_player_info.return_value = {
            'player_id': 999, 'id': 999,
            'team_abbrev': 'ATL', 'player_name': 'Cached Player',
        }
        svc.scraper.get_player_game_log.return_value = _make_game_log_df(
            [1, 2, 3], ['ATL vs. BOS'] * 3
        )

        bdl_instance = mock_bdl.return_value
        bdl_instance.get_player_stats.return_value = _make_bdl_stats(
            999, 'Cached Player', [1, 2, 3], 'ATL'
        )
        svc.get_injuries.return_value = {}
        svc.scraper.get_player_next_game.return_value = None
        mock_pm.return_value.nba_to_bdl.return_value = 999

        from api.routers.players import _scenarios_cache
        _scenarios_cache.clear()

        # First call
        resp1 = client.get('/api/players/Cached Player/scenarios')
        assert resp1.status_code == 200
        call_count_1 = bdl_instance.get_player_stats.call_count

        # Second call — should hit cache, no additional BDL calls
        resp2 = client.get('/api/players/Cached Player/scenarios')
        assert resp2.status_code == 200
        assert bdl_instance.get_player_stats.call_count == call_count_1
