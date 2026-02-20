"""
Shared utilities for backtest scripts.
"""

import time
import pandas as pd

# High-volume players for backtesting
DEFAULT_PLAYERS = [
    "Nikola Jokic",
    "Luka Doncic",
    "Jayson Tatum",
    "Anthony Edwards",
    "Shai Gilgeous-Alexander",
    "LeBron James",
    "Giannis Antetokounmpo",
    "Kevin Durant",
    "Tyrese Haliburton",
    "De'Aaron Fox",
    "Donovan Mitchell",
    "Trae Young",
    "Karl-Anthony Towns",
    "Paolo Banchero",
    "Devin Booker",
]

STATS_TO_TEST = ['PTS', 'REB', 'AST', 'PRA']


def fetch_full_game_log(scraper, player_id):
    """Fetch current + last season game logs for a player."""
    from nba_api.stats.endpoints import playergamelog

    all_games = []
    for season in ['2025-26', '2024-25']:
        try:
            log = playergamelog.PlayerGameLog(player_id=player_id, season=season)
            time.sleep(0.7)
            df = log.get_data_frames()[0]
            df['SEASON'] = season
            all_games.append(df)
        except Exception as e:
            print(f"    Warning: Could not fetch {season}: {e}")

    if not all_games:
        return pd.DataFrame()

    combined = pd.concat(all_games, ignore_index=True)
    combined['GAME_DATE'] = pd.to_datetime(combined['GAME_DATE'])
    return combined.sort_values('GAME_DATE').reset_index(drop=True)


def parse_minutes(val):
    """Parse minutes from various formats (e.g. '32:15' or 32.5)."""
    try:
        if ':' in str(val):
            return float(str(val).split(':')[0])
        return float(val) if pd.notna(val) else 0
    except (ValueError, TypeError):
        return 0


def build_result_row(player_name, test_date, stat, pred, actual, proxy_line,
                     opponent, is_home, minutes, games_trained_on=None):
    """Build a standardized result dict for one stat prediction."""
    edge_pct = ((pred - proxy_line) / proxy_line * 100) if proxy_line > 0 else 0
    direction = 'OVER' if pred > proxy_line else 'UNDER'
    hit = (actual > proxy_line) if direction == 'OVER' else (actual < proxy_line)

    row = {
        'player': player_name,
        'game_date': test_date.strftime('%Y-%m-%d'),
        'stat': stat,
        'prediction': round(pred, 1),
        'actual': actual,
        'proxy_line': round(proxy_line, 1),
        'error': round(pred - actual, 1),
        'abs_error': round(abs(pred - actual), 1),
        'edge_pct': round(edge_pct, 1),
        'abs_edge': round(abs(edge_pct), 1),
        'direction': direction,
        'hit': hit,
        'opponent': opponent,
        'is_home': is_home,
        'minutes': minutes,
    }
    if games_trained_on is not None:
        row['games_trained_on'] = games_trained_on
    return row


def compute_proxy_lines(current_season, test_date):
    """Compute season-average proxy lines from games before test_date."""
    season_before = current_season[current_season['GAME_DATE'] < test_date]
    proxy = {}
    for stat in ['PTS', 'REB', 'AST']:
        proxy[stat] = float(season_before[stat].mean()) if len(season_before) > 0 else 0
    proxy['PRA'] = proxy['PTS'] + proxy['REB'] + proxy['AST']
    return proxy
