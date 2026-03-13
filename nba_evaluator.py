#!/usr/bin/env python3
"""
NBA Line Evaluator - ML-Powered Player Prop Analysis
=====================================================
Evaluates player prop lines using Random Forest or Neural Network models.
Scrapes live data for injuries, schedules, and historical performance.

Usage:
    python nba_evaluator.py --player "Nikola Jokic" --stat PTS --line 26.5
    python nba_evaluator.py --player "LeBron James" --stat PRA --line 45.5 --model neural
    python nba_evaluator.py --interactive
"""

import argparse
import json
import os
import pickle
import sys
import time
import threading
import warnings
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

# BallDontLie API client and ID mappers
from bdl_client import get_bdl_client
from bdl_id_mapper import get_team_mapper, get_player_mapper

# ML Libraries
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.linear_model import BayesianRidge
from sklearn.isotonic import IsotonicRegression
from sklearn.base import clone as sklearn_clone
from scipy import stats as scipy_stats
import joblib

# Optional: Optuna for hyperparameter optimization
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False

# Neural Network (TensorFlow/Keras)
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
warnings.filterwarnings("ignore", module="sklearn")

import model_storage

# === CONFIGURATION ===
DATA_DIR = Path("./data")
MODEL_DIR = Path("./models")
HISTORY_DIR = Path("./history")
CACHE_DIR = Path("./cache")

for d in [DATA_DIR, MODEL_DIR, HISTORY_DIR, CACHE_DIR]:
    d.mkdir(exist_ok=True)

# ── In-memory model cache (avoids repeated pickle.load from disk) ──
_MODEL_CACHE: dict = {}          # player_name -> (data_dict, loaded_at)
_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE_MAX = 30            # keep at most 30 players in memory
_MODEL_CACHE_TTL = 3600          # 1 hour before re-reading from disk


def _model_cache_get(player_name: str) -> 'dict | None':
    """Return cached model data dict if fresh, or None."""
    with _MODEL_CACHE_LOCK:
        entry = _MODEL_CACHE.get(player_name)
        if entry is None:
            return None
        data, loaded_at = entry
        if time.time() - loaded_at > _MODEL_CACHE_TTL:
            del _MODEL_CACHE[player_name]
            return None
        return data


def _model_cache_put(player_name: str, data: dict) -> None:
    """Store model data dict in the in-memory cache, evicting oldest if full."""
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE[player_name] = (data, time.time())
        if len(_MODEL_CACHE) > _MODEL_CACHE_MAX:
            oldest_key = min(_MODEL_CACHE, key=lambda k: _MODEL_CACHE[k][1])
            del _MODEL_CACHE[oldest_key]


# Timezone for NBA game completion check
_ET = ZoneInfo('America/New_York')
# Games are reliably done by 11:30pm ET
_GAMES_DONE_HOUR = 23
_GAMES_DONE_MINUTE = 30


def should_retrain(player_name: str) -> bool:
    """Return True if a retrain is permitted for this player.

    Only the first retrain after 11:30pm ET each night is allowed — once all
    NBA games are complete. Subsequent retrain requests that same night are
    blocked so no one can overwrite a fresh model with stale mid-day data.
    """
    model_path = MODEL_DIR / f"{player_name.replace(' ', '_')}_model.pkl"
    if not model_path.exists():
        model_storage.download_player_model(player_name, model_path)
    if not model_path.exists():
        return True

    now = datetime.now(_ET)
    cutoff_today = now.replace(
        hour=_GAMES_DONE_HOUR, minute=_GAMES_DONE_MINUTE,
        second=0, microsecond=0
    )
    # Before tonight's cutoff → the valid window opened at 11:30pm last night
    cutoff = cutoff_today if now >= cutoff_today else cutoff_today - timedelta(days=1)

    last_modified = datetime.fromtimestamp(model_path.stat().st_mtime, tz=_ET)
    return last_modified < cutoff


CURRENT_SEASON = '2025-26'
HISTORICAL_SEASONS = ['2024-25', '2023-24']

# Cache expiration times (in seconds)
CACHE_EXPIRY = {
    'player_info': 86400,      # 24 hours
    'game_log': 3600,          # 1 hour
    'team_stats': 3600,        # 1 hour
    'injury_report': 1800,     # 30 minutes
    'schedule': 3600,          # 1 hour
    'league_avg': 3600,        # 1 hour
}

# Team name mappings
TEAM_ABBREV_TO_NAME = {
    'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
    'LAC': 'LA Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
    'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards'
}

TEAM_NAME_TO_ABBREV = {v: k for k, v in TEAM_ABBREV_TO_NAME.items()}


class CacheManager:
    """Manages caching of API responses to reduce rate limiting.

    Uses an in-memory L1 dict to avoid pickle I/O on every cache hit.
    Falls back to the file-based L2 cache on memory miss.
    """
    _mem: dict = {}          # cache_key -> (data, timestamp)
    _MEM_MAX = 100           # max entries in L1

    @staticmethod
    def get_cache_key(prefix, *args):
        """Generate a unique cache key"""
        key_str = f"{prefix}_{'_'.join(str(a) for a in args)}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    @staticmethod
    def get(prefix, *args, expiry_type='game_log'):
        """Get cached data if valid (memory L1 → file L2)."""
        cache_key = CacheManager.get_cache_key(prefix, *args)
        ttl = CACHE_EXPIRY.get(expiry_type, 3600)

        # L1: in-memory check
        mem_entry = CacheManager._mem.get(cache_key)
        if mem_entry is not None:
            data, ts = mem_entry
            if (datetime.now() - ts).total_seconds() < ttl:
                return data
            else:
                del CacheManager._mem[cache_key]

        # L2: file-based check
        cache_file = CACHE_DIR / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    cached = pickle.load(f)

                age = (datetime.now() - cached['timestamp']).total_seconds()
                if age < ttl:
                    # Promote to L1
                    CacheManager._mem[cache_key] = (cached['data'], cached['timestamp'])
                    if len(CacheManager._mem) > CacheManager._MEM_MAX:
                        oldest = min(CacheManager._mem, key=lambda k: CacheManager._mem[k][1])
                        del CacheManager._mem[oldest]
                    return cached['data']
            except Exception:
                pass
        return None

    @staticmethod
    def set(prefix, data, *args):
        """Cache data with timestamp (writes to both L1 memory and L2 file)."""
        cache_key = CacheManager.get_cache_key(prefix, *args)
        now = datetime.now()

        # L1: in-memory
        CacheManager._mem[cache_key] = (data, now)
        if len(CacheManager._mem) > CacheManager._MEM_MAX:
            oldest = min(CacheManager._mem, key=lambda k: CacheManager._mem[k][1])
            del CacheManager._mem[oldest]

        # L2: file-based
        cache_file = CACHE_DIR / f"{cache_key}.pkl"
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({'timestamp': now, 'data': data}, f)
        except Exception:
            pass


def _safe_float(val, default: float) -> float:
    """Convert val to float, returning default on None or non-numeric input."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int) -> int:
    """Convert val to int, returning default on None or non-numeric input.

    Uses int(float(val)) so decimal strings like "14.0" are handled correctly.
    """
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


class NBADataScraper:
    """Handles all data collection from NBA API and web scraping"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    @staticmethod
    def _bdl_last_name(player_name: str) -> str:
        """Extract the searchable last name from a full name, stripping Jr./Sr./II/III suffixes."""
        _SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}
        parts = player_name.strip().split()
        for part in reversed(parts):
            if part.lower().rstrip('.') not in _SUFFIXES:
                return part
        return parts[-1] if parts else player_name

    def get_player_info(self, player_name):
        """Get player ID and team info via BallDontLie API (FREE tier).

        BDL's ``search`` param filters by *last name* only — so we first try
        the full name string (in case BDL ever supports it), then fall back to
        last-name extraction so "Jaylen Brown" → search "Brown".
        """
        print(f"🔍 Looking up player: {player_name}")
        try:
            bdl = get_bdl_client()
            results = bdl.get_players(search=player_name)
            if not results:
                # BDL search is last-name based — retry with extracted last name
                last_name = self._bdl_last_name(player_name)
                if last_name.lower() != player_name.lower().strip():
                    print(f"🔄 Retrying BDL search with last name: {last_name}")
                    results = bdl.get_players(search=last_name)
            if not results:
                print(f"⚠️ No BDL results for: {player_name}")
                return None

            # Find best match: prefer exact full-name match, fall back to first result
            name_lower = player_name.lower().strip()
            match = None
            for p in results:
                first = (p.get('first_name') or '').strip()
                last = (p.get('last_name') or '').strip()
                full = f"{first} {last}".strip()
                if full.lower() == name_lower:
                    match = p
                    break
            if match is None:
                # Partial match: any result whose full name contains the search term
                for p in results:
                    first = (p.get('first_name') or '').strip()
                    last = (p.get('last_name') or '').strip()
                    full = f"{first} {last}".strip()
                    if name_lower in full.lower() or full.lower() in name_lower:
                        match = p
                        break
            if match is None:
                match = results[0]

            bdl_id = int(match['id'])
            first = (match.get('first_name') or '').strip()
            last = (match.get('last_name') or '').strip()
            full_name = f"{first} {last}".strip()

            team_obj = match.get('team') or {}
            team_abbrev = str(team_obj.get('abbreviation') or '').upper()
            team_name = str(team_obj.get('full_name') or team_obj.get('name') or '')
            position = str(match.get('position') or '')

            # Resolve BDL team ID from abbreviation
            team_mapper = get_team_mapper()
            bdl_team_id = team_mapper.abbrev_to_bdl_id(team_abbrev) if team_abbrev else None

            # Map BDL player ID → nba.com player ID
            player_mapper = get_player_mapper()
            nba_id = player_mapper.bdl_to_nba(bdl_id, full_name)
            # Fallback to BDL id if no nba.com mapping exists (new players)
            player_id = nba_id if nba_id is not None else bdl_id

            return {
                'player_id': player_id,
                'player_name': full_name,
                'team_id': bdl_team_id,
                'team_abbrev': team_abbrev,
                'team_name': team_name,
                'position': position,
            }
        except Exception as e:
            print(f"⚠️ Error getting player info: {e}")
            return None
    
    def get_todays_games(self):
        """Get today's NBA games via BallDontLie API (FREE tier)."""
        print("📅 Fetching today's schedule...")
        try:
            today_str = datetime.now().date().strftime('%Y-%m-%d')
            bdl = get_bdl_client()
            raw_games = bdl.get_games(dates=[today_str])

            if not raw_games:
                return pd.DataFrame()

            team_mapper = get_team_mapper()

            # BDL status → GAME_STATUS_ID mapping
            status_map = {'scheduled': 1, 'in progress': 2, 'final': 3}

            rows = []
            for g in raw_games:
                home = g.get('home_team') or {}
                visitor = g.get('visitor_team') or {}
                home_bdl_id = home.get('id')
                visitor_bdl_id = visitor.get('id')
                home_abbrev = str(home.get('abbreviation') or '').upper()
                visitor_abbrev = str(visitor.get('abbreviation') or '').upper()
                raw_status = str(g.get('status') or 'scheduled').lower().strip()
                game_status_id = status_map.get(raw_status, 1)
                game_date_raw = g.get('date') or ''
                # Normalise to "YYYY-MM-DD" — BDL may include time component
                game_date_est = game_date_raw[:10] if game_date_raw else today_str

                rows.append({
                    'GAME_ID': g.get('id'),
                    'GAME_DATE_EST': game_date_est,
                    'GAME_STATUS_ID': game_status_id,
                    'HOME_TEAM_ID': home_bdl_id,
                    'VISITOR_TEAM_ID': visitor_bdl_id,
                    'HOME_TEAM_ABBREV': home_abbrev,
                    'VISITOR_TEAM_ABBREV': visitor_abbrev,
                })

            return pd.DataFrame(rows)
        except Exception as e:
            print(f"⚠️ Error fetching games: {e}")
            return pd.DataFrame()
    
    def get_player_next_game(self, player_info):
        """Find the player's next game via BallDontLie API (FREE tier).

        Uses a single date-range query covering today through today+7 days,
        filtered by the player's BDL team ID.
        """
        print(f"📆 Finding next game for {player_info['player_name']}...")
        try:
            team_abbrev = player_info.get('team_abbrev', '')
            if not team_abbrev:
                return None

            team_mapper = get_team_mapper()
            bdl_team_id = team_mapper.abbrev_to_bdl_id(team_abbrev)
            if bdl_team_id is None:
                print(f"⚠️ No BDL team ID for abbreviation: {team_abbrev}")
                return None

            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("America/New_York")).date()
            end_date = today + timedelta(days=7)
            start_str = today.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            bdl = get_bdl_client()
            raw_games = bdl.get_games(
                team_ids=[bdl_team_id],
                start_date=start_str,
                end_date=end_str,
            )

            if not raw_games:
                return None

            # Sort by date ascending and find first non-final game
            def _game_date_key(g):
                d = g.get('date') or ''
                return d[:10] if d else ''

            raw_games_sorted = sorted(raw_games, key=_game_date_key)

            for g in raw_games_sorted:
                raw_status = str(g.get('status') or 'scheduled').lower().strip()
                if raw_status == 'final':
                    continue  # Skip completed games

                home = g.get('home_team') or {}
                visitor = g.get('visitor_team') or {}
                home_bdl_id = home.get('id')
                visitor_bdl_id = visitor.get('id')
                home_abbrev = str(home.get('abbreviation') or '').upper()
                visitor_abbrev = str(visitor.get('abbreviation') or '').upper()

                is_home = 1 if home_bdl_id == bdl_team_id else 0
                opp_abbrev = visitor_abbrev if is_home else home_abbrev

                matchup = (
                    f"{team_abbrev} vs. {opp_abbrev}"
                    if is_home
                    else f"{team_abbrev} @ {opp_abbrev}"
                )

                game_date_raw = g.get('date') or ''
                game_date_str = game_date_raw[:10] if game_date_raw else start_str

                return {
                    'matchup': matchup,
                    'game_date': pd.to_datetime(game_date_str),
                    'is_home': is_home,
                    'opponent': opp_abbrev,
                    'opponent_name': TEAM_ABBREV_TO_NAME.get(opp_abbrev, opp_abbrev),
                }

            return None
        except Exception as e:
            print(f"⚠️ Error finding next game: {e}")
            return None
    
    def get_player_game_log(self, player_id, seasons=None):
        """Get player's game log for specified seasons via BallDontLie API (ALL-STAR tier).

        Cache hierarchy:
          - Historical seasons: Supabase (permanent) → BDL API
          - Current season: local file cache (1h TTL) → BDL API
        """
        import db as _db

        if player_id is None:
            return pd.DataFrame()

        if seasons is None:
            seasons = [CURRENT_SEASON, '2024-25', '2023-24']

        # Resolve BDL player ID. player_id is normally an nba.com ID, but
        # search_players falls back to using the BDL ID directly when no NBA
        # mapping exists — in that case nba_to_bdl returns None and we use
        # player_id itself as the BDL ID.
        player_mapper = get_player_mapper()
        bdl_id = player_mapper.nba_to_bdl(int(player_id))
        if bdl_id is None:
            bdl_id = int(player_id)

        all_games = []

        for season in seasons:
            season_int = int(season.split('-')[0])

            if season != CURRENT_SEASON:
                # Historical: check Supabase first
                cached_df = _db.get_game_logs_from_supabase(str(player_id), season)
                if cached_df is not None and not cached_df.empty:
                    print(f"📦 Loaded {season} from Supabase ({len(cached_df)} games)")
                    all_games.append(cached_df)
                    continue

                # Miss: fetch from BDL API and store permanently
                print(f"📊 Fetching {season} game log from BDL (first time)...")
                try:
                    df = self._fetch_bdl_game_log(player_id, bdl_id, season_int, season)
                    if df is not None and not df.empty:
                        _db.insert_game_logs_to_supabase(df, str(player_id), season)
                        print(f"  ✅ Stored {len(df)} rows to Supabase")
                        all_games.append(df)
                except Exception as e:
                    print(f"⚠️ Could not fetch {season}: {e}")

            else:
                # Current season: local file cache first
                cached = CacheManager.get('game_log', player_id, season, expiry_type='game_log')
                if cached is not None:
                    print(f"📦 Loaded {season} from local cache")
                    all_games.append(cached)
                    continue

                print(f"📊 Fetching {season} game log from BDL...")
                try:
                    df = self._fetch_bdl_game_log(player_id, bdl_id, season_int, season)
                    if df is not None and not df.empty:
                        CacheManager.set('game_log', df, player_id, season)
                        all_games.append(df)
                except Exception as e:
                    print(f"⚠️ Could not fetch {season}: {e}")

        if all_games:
            combined = pd.concat(all_games, ignore_index=True)
            # Sort ascending so tail() = most recent games
            combined['_sort_date'] = pd.to_datetime(combined['GAME_DATE'], format='mixed')
            combined = combined.sort_values('_sort_date', ascending=True).drop(columns=['_sort_date']).reset_index(drop=True)
            return combined
        return pd.DataFrame()

    def _fetch_bdl_game_log(self, nba_player_id, bdl_id, season_int, season_str):
        """Internal helper: fetch per-game stats from BDL and return a DataFrame
        with UPPERCASE column names identical to the former PlayerGameLog output.
        """
        if bdl_id is None:
            print(f"  ⚠️ No BDL ID mapping for nba_id={nba_player_id} — cannot fetch game log")
            return pd.DataFrame()

        bdl = get_bdl_client()
        team_mapper = get_team_mapper()
        raw_stats = bdl.get_player_stats(player_ids=[bdl_id], seasons=[season_int])

        if not raw_stats:
            return pd.DataFrame()

        rename_map = {
            'pts': 'PTS', 'reb': 'REB', 'ast': 'AST', 'min': 'MIN',
            'fgm': 'FGM', 'fga': 'FGA', 'fg_pct': 'FG_PCT',
            'fg3m': 'FG3M', 'fg3a': 'FG3A', 'fg3_pct': 'FG3_PCT',
            'ftm': 'FTM', 'fta': 'FTA', 'ft_pct': 'FT_PCT',
            'oreb': 'OREB', 'dreb': 'DREB', 'stl': 'STL', 'blk': 'BLK',
            'turnover': 'TOV', 'pf': 'PF', 'plus_minus': 'PLUS_MINUS',
        }

        rows = []
        for stat in raw_stats:
            game_obj = stat.get('game') or {}
            player_obj = stat.get('player') or {}
            # Use stat-level team for MATCHUP accuracy (correct for mid-season trades).
            # BDL includes 'team' at the stat level when available; fall back to player.team.
            stat_team_obj = stat.get('team') or {}
            player_team_obj = player_obj.get('team') or {}
            stat_team_abbrev = str(stat_team_obj.get('abbreviation') or '').upper()
            player_team_obj_abbrev = str(player_team_obj.get('abbreviation') or '').upper()
            player_team_abbrev = stat_team_abbrev or player_team_obj_abbrev

            # /v1/stats game objects have home_team_id/visitor_team_id (integers),
            # not nested team objects — use team_mapper to resolve abbreviations.
            home_team_id = game_obj.get('home_team_id')
            visitor_team_id = game_obj.get('visitor_team_id')
            home_abbrev = (team_mapper.bdl_id_to_abbrev(int(home_team_id)) or '') if home_team_id is not None else ''
            visitor_abbrev = (team_mapper.bdl_id_to_abbrev(int(visitor_team_id)) or '') if visitor_team_id is not None else ''

            # Derive GAME_DATE from game.date
            game_date_raw = game_obj.get('date') or ''
            game_date = game_date_raw[:10] if game_date_raw else ''

            # Derive MATCHUP
            if player_team_abbrev == home_abbrev:
                matchup = f"{player_team_abbrev} vs. {visitor_abbrev}"
                opp_abbrev = visitor_abbrev
            else:
                matchup = f"{player_team_abbrev} @ {home_abbrev}"
                opp_abbrev = home_abbrev

            # Derive WL
            home_score = game_obj.get('home_team_score')
            visitor_score = game_obj.get('visitor_team_score')
            game_status = str(game_obj.get('status') or '').lower()
            if game_status == 'final' and home_score is not None and visitor_score is not None:
                if player_team_abbrev == home_abbrev:
                    wl = 'W' if home_score > visitor_score else 'L'
                else:
                    wl = 'W' if visitor_score > home_score else 'L'
            else:
                wl = ''

            p_first = (player_obj.get('first_name') or '').strip()
            p_last = (player_obj.get('last_name') or '').strip()
            player_name_str = f"{p_first} {p_last}".strip() or None

            row = {
                'Player_ID': nba_player_id,
                'Game_ID': game_obj.get('id'),
                'GAME_DATE': game_date,
                'MATCHUP': matchup,
                'WL': wl,
                'SEASON': season_str,
                'SEASON_ID': season_int,
                'VIDEO_AVAILABLE': 0,
                'PLAYER_NAME': player_name_str,
            }

            # Map stat fields
            for bdl_field, upper_col in rename_map.items():
                row[upper_col] = stat.get(bdl_field)

            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df
    
    def get_injury_report(self):
        """Fetch current NBA injury report via BallDontLie API (ALL-STAR tier)."""
        cached = CacheManager.get('injuries', 'report', expiry_type='injury_report')
        if cached is not None:
            return cached

        print("🏥 Fetching injury report...")
        injuries = {abbrev: {'out': 0, 'questionable': 0, 'doubtful': 0, 'players': []}
                    for abbrev in TEAM_ABBREV_TO_NAME}

        # BDL status → internal status mapping (case-insensitive)
        # BDL uses: "Out", "Out For Season", "Doubtful", "Questionable", "Day-To-Day", "Probable"
        status_map = {
            'out': 'out',
            'out for season': 'out',
            'suspension': 'out',
            'doubtful': 'doubtful',
            'questionable': 'questionable',
            'day-to-day': 'questionable',
            'probable': 'questionable',
        }

        try:
            bdl = get_bdl_client()
            team_mapper = get_team_mapper()
            raw_injuries = bdl.get_injuries()

            for entry in raw_injuries:
                player_obj = entry.get('player') or {}
                # BDL injury entries: player has team_id (int) but not a full team object
                # Try team dict first; fall back to team_id lookup
                team_obj = player_obj.get('team') or {}
                team_abbrev = str(team_obj.get('abbreviation') or '').upper()
                if not team_abbrev:
                    bdl_team_id = player_obj.get('team_id')
                    if bdl_team_id is not None:
                        team_abbrev = team_mapper.bdl_id_to_abbrev(int(bdl_team_id)) or ''

                if team_abbrev not in injuries:
                    continue

                first = (player_obj.get('first_name') or '').strip()
                last = (player_obj.get('last_name') or '').strip()
                player_name = f"{first} {last}".strip()

                raw_status = str(entry.get('status') or '').lower().strip()
                mapped_status = status_map.get(raw_status, 'questionable')
                note = str(entry.get('description') or entry.get('return_date') or '')

                injuries[team_abbrev][mapped_status] += 1
                injuries[team_abbrev]['players'].append(
                    {'name': player_name, 'status': mapped_status, 'note': note}
                )

            print(f"  ✅ Loaded injury report ({sum(t['out'] for t in injuries.values())} players out across all teams)")
            CacheManager.set('injuries', injuries, 'report')
            return injuries

        except Exception as e:
            print(f"  ⚠️ BDL injury source failed: {e}")

        return injuries

    def get_player_injury_status(self, player_name, injuries_data):
        """Check if a specific player is on the injury report"""
        player_lower = player_name.lower()

        for team, data in injuries_data.items():
            for player in data.get('players', []):
                if player_lower in player.get('name', '').lower():
                    return {
                        'team': team,
                        'status': player.get('status', 'unknown'),
                        'is_injured': True
                    }

        return {'is_injured': False, 'status': 'healthy'}
    
    def get_vs_team_stats(self, player_id, opponent_abbrev):
        """Get player's historical stats against specific opponent"""
        print(f"📈 Analyzing performance vs {opponent_abbrev}...")
        try:
            # Get multi-season game log
            all_games = self.get_player_game_log(player_id)

            if all_games.empty:
                return None

            # Filter for games against opponent
            vs_games = all_games[all_games['MATCHUP'].str.contains(opponent_abbrev)]

            if vs_games.empty:
                return None

            return {
                'games': len(vs_games),
                'avg_pts': vs_games['PTS'].mean(),
                'avg_reb': vs_games['REB'].mean(),
                'avg_ast': vs_games['AST'].mean(),
                'avg_min': vs_games['MIN'].apply(lambda x: float(str(x).split(':')[0]) if ':' in str(x) else float(x)).mean(),
                'pts_std': vs_games['PTS'].std(),
                'reb_std': vs_games['REB'].std(),
                'ast_std': vs_games['AST'].std(),
            }
        except Exception as e:
            print(f"⚠️ Error getting vs stats: {e}")
            return None

    def get_team_defensive_stats(self, season='2025-26'):
        """Get team defensive ratings and pace for all teams via BallDontLie (GOAT tier).
        Cache hierarchy: local file (1h) → Supabase (24h) → BDL API.
        Two BDL calls are issued in parallel to halve network wait time.
        """
        import db as _db
        import concurrent.futures

        # 1. Local file cache (fastest, 1h TTL)
        cached = CacheManager.get('team_stats', season, expiry_type='team_stats')
        if cached is not None:
            return cached

        # 2. Supabase cache (shared across restarts, 24h TTL)
        supabase_data = _db.get_team_stats_from_supabase(season)
        if supabase_data:
            print(f"📦 Loaded team stats from Supabase ({len(supabase_data)} teams)")
            CacheManager.set('team_stats', supabase_data, season)
            return supabase_data

        # 3. Fetch from BDL API — two calls in parallel
        print("🛡️ Fetching team defensive statistics from BDL...")
        season_int = int(season.split('-')[0])

        try:
            bdl = get_bdl_client()
            team_mapper = get_team_mapper()

            def fetch_advanced():
                return bdl.get_team_season_averages("general", "advanced", season_int)

            def fetch_base():
                return bdl.get_team_season_averages("general", "base", season_int)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f_advanced = pool.submit(fetch_advanced)
                f_base = pool.submit(fetch_base)
                advanced_list = f_advanced.result()
                base_list = f_base.result()

            if not advanced_list or not base_list:
                raise ValueError("BDL API returned empty stats for team defensive averages")

            team_data = {}

            # BDL response structure: {team: {..., abbreviation}, season, season_type, stats: {...}}
            # Advanced stats contain: def_rating, pace, def_rating_rank, pace_rank
            for entry in (advanced_list or []):
                team_obj = entry.get('team') or {}
                team_abbrev = str(team_obj.get('abbreviation') or '').upper()
                if not team_abbrev:
                    bdl_team_id = team_obj.get('id')
                    if bdl_team_id is not None:
                        team_abbrev = team_mapper.bdl_id_to_abbrev(int(bdl_team_id)) or ''
                if not team_abbrev:
                    continue

                stats = entry.get('stats') or {}
                def_rating = _safe_float(stats.get('def_rating'), 110)
                pace = _safe_float(stats.get('pace'), 100)
                # opp_pts not available in BDL; approximate from def_rating (pts allowed per 100 poss)
                # Use def_rating as proxy: points allowed ≈ def_rating * pace / 100
                opp_pts = round(def_rating * pace / 100, 1)

                team_data[team_abbrev] = {
                    'def_rating': def_rating,
                    'opp_pts': opp_pts,
                    'pace': pace,
                    'pts_rank': _safe_int(stats.get('def_rating_rank'), 15),
                    'opp_ast': 25,    # Overridden by base stats if available
                    # Enhanced opponent context (from BDL advanced stats)
                    'off_rating': _safe_float(stats.get('off_rating'), 110),
                    'net_rating': _safe_float(stats.get('net_rating'), 0),
                    'efg_pct': _safe_float(stats.get('efg_pct'), 0.50),
                    'ts_pct': _safe_float(stats.get('ts_pct'), 0.56),
                    'ast_pct': _safe_float(stats.get('ast_pct'), 0.60),
                    'tov_pct': _safe_float(stats.get('tov_pct'), 14.0),
                    'oreb_pct': _safe_float(stats.get('oreb_pct'), 0.27),
                    'dreb_pct': _safe_float(stats.get('dreb_pct'), 0.73),
                }

            # Process base stats — enrich with pts_rank (opponent points allowed rank)
            # Base stats contain pts_rank (own scoring rank), ast (own assists)
            # Use own pts_rank as a fallback signal for defensive quality ranking
            for entry in (base_list or []):
                team_obj = entry.get('team') or {}
                team_abbrev = str(team_obj.get('abbreviation') or '').upper()
                if not team_abbrev:
                    bdl_team_id = team_obj.get('id')
                    if bdl_team_id is not None:
                        team_abbrev = team_mapper.bdl_id_to_abbrev(int(bdl_team_id)) or ''
                if not team_abbrev:
                    continue

                stats = entry.get('stats') or {}

                if team_abbrev not in team_data:
                    # Bootstrap entry from base stats if advanced was empty
                    team_data[team_abbrev] = {
                        'def_rating': 110, 'opp_pts': 110, 'pace': 100,
                        'pts_rank': 15, 'opp_ast': 25,
                        'off_rating': 110, 'net_rating': 0,
                        'efg_pct': 0.50, 'ts_pct': 0.56, 'ast_pct': 0.60,
                        'tov_pct': 14.0, 'oreb_pct': 0.27, 'dreb_pct': 0.73,
                    }

                # Derive opp_ast from team's actual assists per game (better than hardcoded 25)
                team_ast = _safe_float(stats.get('ast'), None)
                if team_ast is not None:
                    team_data[team_abbrev]['opp_ast'] = team_ast

                # If def_rating_rank was not in advanced, fall back to pts_rank from base
                if team_data[team_abbrev].get('pts_rank', 15) == 15:
                    pts_rank = stats.get('pts_rank')
                    if pts_rank is not None:
                        team_data[team_abbrev]['pts_rank'] = _safe_int(pts_rank, 15)

            if team_data:
                _db.upsert_team_stats_to_supabase(team_data, season)
                CacheManager.set('team_stats', team_data, season)
                return team_data

            # Empty result — fall through to defaults
            raise ValueError("BDL returned no team season averages")

        except Exception as e:
            print(f"⚠️ Error fetching team defensive stats: {e}")
            return {abbrev: {
                'def_rating': 110, 'pace': 100, 'opp_pts': 110, 'pts_rank': 15, 'opp_ast': 25,
                'off_rating': 110, 'net_rating': 0, 'efg_pct': 0.50, 'ts_pct': 0.56,
                'ast_pct': 0.60, 'tov_pct': 14.0, 'oreb_pct': 0.27, 'dreb_pct': 0.73,
            } for abbrev in TEAM_ABBREV_TO_NAME}

    def get_league_averages(self, season='2025-26'):
        """Get league average stats for normalization.

        Queries Supabase player_game_logs directly — zero external API calls.
        """
        import db as _db

        cached = CacheManager.get('league_avg', season, expiry_type='league_avg')
        if cached is not None:
            return cached

        print("📊 Fetching league averages from Supabase...")
        try:
            averages = _db.get_league_averages_from_supabase(season)
            if averages:
                result = {**averages, 'PACE': averages.get('PACE', 100)}
                CacheManager.set('league_avg', result, season)
                return result
        except Exception as e:
            print(f"⚠️ Error fetching league averages from Supabase: {e}")

        return {'PTS': 11.5, 'REB': 4.2, 'AST': 2.4, 'MIN': 24, 'PACE': 100}


class OddsAPI:
    """Fetches player props from The Odds API (free tier: 500 requests/month)"""

    BASE_URL = "https://api.the-odds-api.com/v4"
    SPORT = "basketball_nba"

    # Map Odds API market keys to our stat names
    MARKET_MAP = {
        'player_points': 'PTS',
        'player_rebounds': 'REB',
        'player_assists': 'AST',
        'player_points_rebounds_assists': 'PRA',
    }

    def __init__(self, api_key=None):
        """Initialize with API key from param, env var, or config file"""
        self.api_key = api_key or os.environ.get('ODDS_API_KEY')

        if not self.api_key:
            print("⚠️  No Odds API key found. Set ODDS_API_KEY env var or add to config.json")
            print("    Get a free key at: https://the-odds-api.com/")

    def get_todays_events(self):
        """Get today's NBA games (games starting within the next 24 hours)"""
        if not self.api_key:
            return []

        try:
            url = f"{self.BASE_URL}/sports/{self.SPORT}/events"
            params = {
                'apiKey': self.api_key,
                'dateFormat': 'iso',
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            events = response.json()
            now = datetime.now(tz=ZoneInfo('US/Eastern'))

            # Filter to games starting within the next 24 hours
            todays_events = []
            for event in events:
                # Parse UTC time and convert to Eastern
                event_time_utc = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
                event_time_local = event_time_utc.astimezone(ZoneInfo('US/Eastern'))

                hours_until = (event_time_local - now).total_seconds() / 3600

                # Include games starting in the next 24 hours that haven't started yet
                if -2 < hours_until < 24:  # -2 allows for games that just started
                    todays_events.append(event)

            return todays_events

        except Exception as e:
            print(f"⚠️ Error fetching events: {e}")
            return []

    def get_player_props(self, event_id, markets=None):
        """Get player props for a specific game"""
        if not self.api_key:
            return []

        if markets is None:
            markets = ['player_points', 'player_rebounds', 'player_assists', 'player_points_rebounds_assists']

        try:
            url = f"{self.BASE_URL}/sports/{self.SPORT}/events/{event_id}/odds"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': ','.join(markets),
                'oddsFormat': 'american',
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            print(f"⚠️ Error fetching props for event {event_id}: {e}")
            return {}

    def get_all_todays_props(self):
        """Get all player props for today's games"""
        if not self.api_key:
            return []

        print("🎰 Fetching today's player props from The Odds API...")
        events = self.get_todays_events()

        if not events:
            print("   No games found for today")
            return []

        print(f"   Found {len(events)} games today")

        all_props = []
        for event in events:
            event_id = event['id']
            home_team = event['home_team']
            away_team = event['away_team']
            game_time = event['commence_time']

            print(f"   Fetching props: {away_team} @ {home_team}")
            time.sleep(0.3)

            props_data = self.get_player_props(event_id)
            if not props_data or 'bookmakers' not in props_data:
                continue

            # Parse props from all bookmakers, find consensus/best lines
            player_lines = {}

            for bookmaker in props_data.get('bookmakers', []):
                book_name = bookmaker['key']

                for market in bookmaker.get('markets', []):
                    market_key = market['key']
                    stat_type = self.MARKET_MAP.get(market_key)
                    if not stat_type:
                        continue

                    for outcome in market.get('outcomes', []):
                        player_name = outcome.get('description', '')
                        point = outcome.get('point')
                        price = outcome.get('price')
                        name = outcome.get('name', '')  # Over/Under

                        if not player_name or point is None:
                            continue

                        key = (player_name, stat_type)
                        if key not in player_lines:
                            player_lines[key] = {
                                'player': player_name,
                                'stat': stat_type,
                                'home_team': home_team,
                                'away_team': away_team,
                                'game_time': game_time,
                                'lines': [],
                            }

                        player_lines[key]['lines'].append({
                            'book': book_name,
                            'line': point,
                            'over_odds': price if name == 'Over' else None,
                            'under_odds': price if name == 'Under' else None,
                        })

            # Consolidate lines per player/stat
            for key, data in player_lines.items():
                lines = data['lines']
                if not lines:
                    continue

                # Use consensus line (most common) or average
                line_values = [l['line'] for l in lines if l['line']]
                if line_values:
                    consensus_line = max(set(line_values), key=line_values.count)
                    data['consensus_line'] = consensus_line
                    all_props.append(data)

        print(f"   Found {len(all_props)} player props total")
        return all_props

    def check_remaining_requests(self):
        """Check how many API requests remain this month"""
        if not self.api_key:
            return None

        try:
            url = f"{self.BASE_URL}/sports"
            params = {'apiKey': self.api_key}
            response = requests.get(url, params=params, timeout=10)

            remaining = response.headers.get('x-requests-remaining')
            used = response.headers.get('x-requests-used')

            return {
                'remaining': int(remaining) if remaining else None,
                'used': int(used) if used else None,
            }
        except Exception:
            return None


class FeatureEngineer:
    """Creates features for ML models"""

    @staticmethod
    def extract_opp_stats(team_stats, opponent):
        """Extract all opponent context stats from team_stats dict.

        Returns a dict of keyword arguments suitable for passing to
        ``get_prediction_features(**opp_ctx)``.
        """
        opp = (team_stats or {}).get(opponent, {})
        return {
            'opp_def_rating': opp.get('def_rating', 110),
            'opp_pace': opp.get('pace', 100),
            'opp_ast_allowed': opp.get('opp_ast', 25),
            'opp_off_rating': opp.get('off_rating', 110),
            'opp_net_rating': opp.get('net_rating', 0),
            'opp_efg_pct': opp.get('efg_pct', 0.50),
            'opp_tov_pct': opp.get('tov_pct', 14.0),
            'opp_oreb_pct': opp.get('oreb_pct', 0.27),
            'opp_dreb_pct': opp.get('dreb_pct', 0.73),
        }

    @staticmethod
    def create_features(game_log, player_info=None, game_info=None, injuries=None, team_stats=None):
        """Create comprehensive feature set from game log"""
        df = game_log.copy()
        df = df.sort_values('GAME_DATE', key=lambda x: pd.to_datetime(x, format='mixed'))

        # Parse minutes
        df['MIN_NUMERIC'] = df['MIN'].apply(
            lambda x: float(str(x).split(':')[0]) + float(str(x).split(':')[1])/60
            if ':' in str(x) else float(x) if pd.notna(x) else 0
        )

        # Drop games where the player did not play (DNP) or played 0 minutes
        # so these games do not drag down rolling averages or feature calculations.
        df = df[df['MIN_NUMERIC'] > 0].copy()

        # =====================
        # ADVANCED STATS
        # =====================

        # True Shooting % (TS%) - accounts for 3PT and FT efficiency
        # Formula: PTS / (2 * (FGA + 0.44 * FTA))
        df['TSA'] = df['FGA'] + 0.44 * df['FTA']  # True Shooting Attempts
        df['TS_PCT'] = df.apply(
            lambda x: x['PTS'] / (2 * x['TSA']) if x['TSA'] > 0 else 0.5, axis=1
        )

        # Effective Field Goal % (eFG%) - weights 3PT makes
        # Formula: (FGM + 0.5 * FG3M) / FGA
        df['EFG_PCT'] = df.apply(
            lambda x: (x['FGM'] + 0.5 * x['FG3M']) / x['FGA'] if x['FGA'] > 0 else 0.5, axis=1
        )

        # Points per shot attempt (efficiency)
        df['PTS_PER_FGA'] = df.apply(
            lambda x: x['PTS'] / x['FGA'] if x['FGA'] > 0 else 0, axis=1
        )

        # Assist to Turnover ratio — use floor of 2 on TOV denominator to prevent
        # ratio explosion when TOV is 0-1 (which causes extreme model overfit on this feature)
        df['AST_TOV_RATIO'] = df.apply(
            lambda x: min(x['AST'] / max(x['TOV'], 2), 6.0), axis=1
        )

        # Stock stats (Steals + Blocks)
        df['STOCKS'] = df['STL'] + df['BLK']

        # Fantasy-style scoring (common weighting)
        df['FANTASY_PTS'] = (df['PTS'] + 1.2 * df['REB'] + 1.5 * df['AST'] +
                            3 * df['STL'] + 3 * df['BLK'] - df['TOV'])

        # =====================
        # REBOUND SPLIT FEATURES
        # =====================
        if 'OREB' in df.columns and 'DREB' in df.columns:
            df['OREB_RATE'] = df.apply(
                lambda x: x['OREB'] / x['REB'] if x['REB'] > 0 else 0.0, axis=1
            )

        # =====================
        # THREE-POINT SHOOTING RATE
        # =====================
        if 'FG3A' in df.columns and 'FGA' in df.columns:
            df['FG3_RATE'] = df.apply(
                lambda x: x['FG3A'] / x['FGA'] if x['FGA'] > 0 else 0.0, axis=1
            )

        # =====================
        # FREE THROW RATE (foul-drawing ability)
        # =====================
        if 'FTA' in df.columns and 'FGA' in df.columns:
            df['FT_RATE'] = df.apply(
                lambda x: x['FTA'] / x['FGA'] if x['FGA'] > 0 else 0.0, axis=1
            )

        # =====================
        # FOULS PER MINUTE (foul trouble risk)
        # =====================
        if 'PF' in df.columns:
            df['PF_PER_MIN'] = df.apply(
                lambda x: x['PF'] / x['MIN_NUMERIC'] if x['MIN_NUMERIC'] > 5 else 0.0, axis=1
            )

        # Home/Away indicator
        df['IS_HOME'] = df['MATCHUP'].apply(lambda x: 1 if 'vs.' in str(x) else 0)

        # Extract opponent
        df['OPPONENT'] = df['MATCHUP'].apply(lambda x: str(x).split(' ')[-1])

        # Rolling averages (multiple windows) with exponential weighting for recent form
        # Include new advanced stats in rolling calculations
        stats_for_rolling = ['PTS', 'REB', 'AST', 'MIN_NUMERIC', 'FGA', 'FG_PCT', 'FTA',
                             'TS_PCT', 'EFG_PCT', 'PTS_PER_FGA', 'STOCKS', 'FANTASY_PTS',
                             # New: rebound splits, 3PT, FT, fouls, rates
                             'OREB', 'DREB', 'FG3M', 'FG3A', 'FTM', 'PF',
                             'FG3_RATE', 'FT_RATE']
        for stat in stats_for_rolling:
            if stat in df.columns:
                # Standard rolling averages
                df[f'ROLL_5_{stat}'] = df[stat].rolling(5, min_periods=1).mean().shift(1)
                df[f'ROLL_10_{stat}'] = df[stat].rolling(10, min_periods=1).mean().shift(1)
                df[f'ROLL_20_{stat}'] = df[stat].rolling(20, min_periods=1).mean().shift(1)
                df[f'STD_10_{stat}'] = df[stat].rolling(10, min_periods=1).std().shift(1)

                # Exponentially weighted moving average (more weight on recent games)
                df[f'EMA_5_{stat}'] = df[stat].ewm(span=5, min_periods=1).mean().shift(1)
                df[f'EMA_10_{stat}'] = df[stat].ewm(span=10, min_periods=1).mean().shift(1)

        # =====================
        # PER-36-MINUTE NORMALIZATION
        # =====================
        # Normalize stats to per-36-minute basis to account for minutes variation
        for stat in ['PTS', 'REB', 'AST', 'OREB', 'DREB']:
            if stat not in df.columns:
                continue
            df[f'{stat}_PER36'] = df.apply(
                lambda x, s=stat: (x[s] / x['MIN_NUMERIC'] * 36) if x['MIN_NUMERIC'] > 10 else 0, axis=1
            )
            df[f'ROLL_5_{stat}_PER36'] = df[f'{stat}_PER36'].rolling(5, min_periods=1).mean().shift(1)
            df[f'ROLL_10_{stat}_PER36'] = df[f'{stat}_PER36'].rolling(10, min_periods=1).mean().shift(1)

        # =====================
        # BLOWOUT GAME INDICATOR
        # =====================
        # Flag games with large point differentials where starters may have rested
        if 'PLUS_MINUS' in df.columns:
            df['BLOWOUT'] = (df['PLUS_MINUS'].abs() > 20).astype(int)
            # Blowout-adjusted rolling averages (downweight blowout games)
            for stat in ['PTS', 'REB', 'AST']:
                # Weight: 1.0 for normal games, 0.5 for blowouts
                blowout_weight = df['BLOWOUT'].apply(lambda x: 0.5 if x == 1 else 1.0)
                weighted_vals = df[stat] * blowout_weight
                weighted_sum = weighted_vals.rolling(10, min_periods=1).sum().shift(1)
                weight_sum = blowout_weight.rolling(10, min_periods=1).sum().shift(1)
                df[f'ROLL_10_{stat}_BLOWOUT_ADJ'] = weighted_sum / weight_sum.replace(0, 1)

        # Combined stats
        df['PRA'] = df['PTS'] + df['REB'] + df['AST']
        df['ROLL_5_PRA'] = df['PRA'].rolling(5, min_periods=1).mean().shift(1)
        df['ROLL_10_PRA'] = df['PRA'].rolling(10, min_periods=1).mean().shift(1)
        df['EMA_5_PRA'] = df['PRA'].ewm(span=5, min_periods=1).mean().shift(1)

        # Trend (recent vs longer term)
        df['PTS_TREND'] = df['ROLL_5_PTS'] - df['ROLL_20_PTS']
        df['REB_TREND'] = df['ROLL_5_REB'] - df['ROLL_20_REB']
        df['AST_TREND'] = df['ROLL_5_AST'] - df['ROLL_20_AST']
        df['MIN_TREND'] = df['ROLL_5_MIN_NUMERIC'] - df['ROLL_20_MIN_NUMERIC']

        # Three-point trend (recent 3PT form vs longer term)
        if 'ROLL_5_FG3M' in df.columns and 'ROLL_20_FG3M' in df.columns:
            df['FG3_TREND'] = df['ROLL_5_FG3M'] - df['ROLL_20_FG3M']

        # Days rest (if we have date info)
        df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
        df['DAYS_REST'] = df['GAME_DATE'].diff().dt.days.fillna(3)
        df['DAYS_REST'] = df['DAYS_REST'].clip(0, 7)  # Cap at 7

        # Back-to-back indicator
        df['B2B'] = (df['DAYS_REST'] == 1).astype(int)

        # Extended rest indicator (3+ days off)
        df['EXTENDED_REST'] = (df['DAYS_REST'] >= 3).astype(int)

        # Game number in season
        df['GAME_NUM'] = range(1, len(df) + 1)

        # Season phase (early=1, mid=2, late=3, playoffs=4)
        df['SEASON_PHASE'] = pd.cut(df['GAME_NUM'],
                                     bins=[0, 25, 55, 82, 110],
                                     labels=[1, 2, 3, 4]).astype(float).fillna(2)

        # Win/Loss momentum
        df['WL_NUM'] = df['WL'].apply(lambda x: 1 if x == 'W' else 0)
        df['WIN_STREAK'] = df['WL_NUM'].rolling(5, min_periods=1).sum().shift(1)
        df['LOSS_STREAK'] = (1 - df['WL_NUM']).rolling(5, min_periods=1).sum().shift(1)

        # Usage rate proxy (FGA as percentage of team attempts)
        if 'FGA' in df.columns:
            df['USAGE_PROXY'] = df['FGA'].rolling(10, min_periods=1).mean().shift(1)

        # Minutes consistency (lower std = more consistent role)
        df['MIN_CONSISTENCY'] = df['MIN_NUMERIC'].rolling(10, min_periods=3).std().shift(1)
        df['MIN_CONSISTENCY'] = df['MIN_CONSISTENCY'].fillna(5)  # Default moderate variance

        # Hot/Cold streak detection
        df['RECENT_PERFORMANCE'] = (df['EMA_5_PTS'] - df['ROLL_20_PTS']).fillna(0)
        df['IS_HOT'] = (df['RECENT_PERFORMANCE'] > df['STD_10_PTS'].fillna(5)).astype(int)
        df['IS_COLD'] = (df['RECENT_PERFORMANCE'] < -df['STD_10_PTS'].fillna(5)).astype(int)

        # Add opponent defensive rating if team stats available
        if team_stats:
            df['OPP_DEF_RATING'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('def_rating', 110)
            )
            df['OPP_PACE'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('pace', 100)
            )
            # Normalize to league average (100 is average)
            df['OPP_DEF_RATING_NORM'] = (df['OPP_DEF_RATING'] - 110) / 5  # Centered around 0
            df['OPP_PACE_NORM'] = (df['OPP_PACE'] - 100) / 5

            # Opponent assists allowed (higher = weaker at defending assists)
            df['OPP_AST_ALLOWED'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('opp_ast', 25)
            )
            df['OPP_AST_ALLOWED_NORM'] = (df['OPP_AST_ALLOWED'] - 25) / 3

            # =====================
            # ROLLING OPPONENT DEFENSIVE CONTEXT
            # =====================
            # Use rolling 10-game average of opponent def rating to capture recent defense form
            df['OPP_DEF_RATING_ROLL10'] = df['OPP_DEF_RATING'].rolling(10, min_periods=3).mean().shift(1)
            df['OPP_PACE_ROLL10'] = df['OPP_PACE'].rolling(10, min_periods=3).mean().shift(1)

            # =====================
            # ENHANCED OPPONENT CONTEXT (from BDL advanced stats)
            # =====================
            # Opponent offensive rating (scoring environment context)
            df['OPP_OFF_RATING'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('off_rating', 110)
            )
            df['OPP_OFF_RATING_NORM'] = (df['OPP_OFF_RATING'] - 110) / 5

            # Opponent net rating (overall team quality)
            df['OPP_NET_RATING'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('net_rating', 0)
            )
            df['OPP_NET_RATING_NORM'] = df['OPP_NET_RATING'] / 5

            # Opponent eFG% (scoring efficiency context)
            df['OPP_EFG_PCT'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('efg_pct', 0.50)
            )
            df['OPP_EFG_PCT_NORM'] = (df['OPP_EFG_PCT'] - 0.50) / 0.03

            # Opponent turnover rate (transition opportunity indicator)
            df['OPP_TOV_PCT'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('tov_pct', 14.0)
            )
            df['OPP_TOV_PCT_NORM'] = (df['OPP_TOV_PCT'] - 14.0) / 2.0

            # Opponent offensive rebound rate (second chance pts context)
            df['OPP_OREB_PCT'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('oreb_pct', 0.27)
            )
            df['OPP_OREB_PCT_NORM'] = (df['OPP_OREB_PCT'] - 0.27) / 0.05

            # Opponent defensive rebound rate (rebound availability for player)
            df['OPP_DREB_PCT'] = df['OPPONENT'].map(
                lambda x: team_stats.get(x, {}).get('dreb_pct', 0.73)
            )
            df['OPP_DREB_PCT_NORM'] = (df['OPP_DREB_PCT'] - 0.73) / 0.05

            # =====================
            # PACE-ADJUSTED STATS
            # =====================
            # Normalize stats to per-100-possessions equivalent
            # League average pace is ~100, so we scale by (100 / opponent_pace)
            pace_factor = 100 / df['OPP_PACE'].replace(0, 100)

            df['PTS_PACE_ADJ'] = df['PTS'] * pace_factor
            df['REB_PACE_ADJ'] = df['REB'] * pace_factor
            df['AST_PACE_ADJ'] = df['AST'] * pace_factor

            # Rolling averages for pace-adjusted stats
            for stat in ['PTS_PACE_ADJ', 'REB_PACE_ADJ', 'AST_PACE_ADJ']:
                df[f'ROLL_5_{stat}'] = df[stat].rolling(5, min_periods=1).mean().shift(1)
                df[f'ROLL_10_{stat}'] = df[stat].rolling(10, min_periods=1).mean().shift(1)

            # =====================
            # USAGE RATE ESTIMATION
            # =====================
            # Approximate USG% based on shot attempts and touches per minute
            # Formula: USG% ≈ (FGA + 0.44*FTA + TOV) / (MIN * team_pace_factor)
            # Since we don't have team possessions, use minutes-adjusted proxy
            df['POSS_USED'] = df['FGA'] + 0.44 * df['FTA'] + df['TOV']
            df['USG_PROXY'] = df.apply(
                lambda x: (x['POSS_USED'] / x['MIN_NUMERIC'] * 48) if x['MIN_NUMERIC'] > 0 else 0,
                axis=1
            )
            # Rolling usage
            df['ROLL_5_USG'] = df['USG_PROXY'].rolling(5, min_periods=1).mean().shift(1)
            df['ROLL_10_USG'] = df['USG_PROXY'].rolling(10, min_periods=1).mean().shift(1)

        # =====================
        # ROLLING AST/TOV RATIO
        # =====================
        if 'AST_TOV_RATIO' in df.columns:
            df['ROLL_5_AST_TOV'] = df['AST_TOV_RATIO'].rolling(5, min_periods=1).mean().shift(1)

        # =====================
        # INTERACTION FEATURES
        # =====================
        # Back-to-back vs elite defense (< 108 DEF RTG)
        if 'B2B' in df.columns and 'OPP_DEF_RATING_NORM' in df.columns:
            df['B2B_VS_ELITE'] = df['B2B'] * (df['OPP_DEF_RATING_NORM'] < -0.4).astype(int)

        # Hot streak vs weak defense (> 116 DEF RTG)
        if 'IS_HOT' in df.columns and 'OPP_DEF_RATING_NORM' in df.columns:
            df['HOT_VS_WEAK'] = df['IS_HOT'] * (df['OPP_DEF_RATING_NORM'] > 1.2).astype(int)

        # Rested and at home
        if 'EXTENDED_REST' in df.columns and 'IS_HOME' in df.columns:
            df['RESTED_HOME'] = df['EXTENDED_REST'] * df['IS_HOME']

        # =====================
        # REBOUND SPLIT INTERACTION
        # =====================
        if 'OREB_RATE' in df.columns and 'OPP_OREB_PCT_NORM' in df.columns:
            df['OREB_RATE_x_OPP_OREB'] = df['OREB_RATE'] * df['OPP_OREB_PCT_NORM']

        # =====================
        # PACE BUCKET FLAGS
        # =====================
        if 'OPP_PACE' in df.columns:
            df['HIGH_PACE_GAME'] = (df['OPP_PACE'] > 103).astype(int)
            df['LOW_PACE_GAME'] = (df['OPP_PACE'] < 97).astype(int)

        # =====================
        # ELITE OPPONENT FLAG
        # =====================
        if 'OPP_NET_RATING' in df.columns:
            df['ELITE_OPP'] = (df['OPP_NET_RATING'] > 5.0).astype(int)

        # =====================
        # POSITION FEATURES
        # =====================
        _POSITION_ORD = {
            'Guard': 0, 'Guard-Forward': 1, 'Forward-Guard': 1,
            'Forward': 2, 'Forward-Center': 3, 'Center-Forward': 3, 'Center': 4,
        }
        position_str = player_info.get('position', '') if player_info else ''
        pos_ord = _POSITION_ORD.get(position_str, 2)  # Default: Forward
        df['POSITION_ORD'] = pos_ord
        if 'OPP_DEF_RATING_NORM' in df.columns:
            df['POSITION_x_OPP_DEF'] = df['POSITION_ORD'] * df['OPP_DEF_RATING_NORM']
            df['POSITION_x_OPP_PACE'] = df['POSITION_ORD'] * df['OPP_PACE_NORM']
        else:
            df['POSITION_x_OPP_DEF'] = 0.0
            df['POSITION_x_OPP_PACE'] = 0.0

        # --- VS_OPP head-to-head features (leak-free expanding window) ---
        if 'OPPONENT' in df.columns:
            for stat in ['PTS', 'REB', 'AST']:
                df[f'VS_OPP_AVG_{stat}'] = (
                    df.groupby('OPPONENT')[stat]
                    .apply(lambda x: x.expanding().mean().shift(1))
                    .reset_index(level=0, drop=True)
                )
            df['VS_OPP_GAMES'] = (
                df.groupby('OPPONENT')['PTS']
                .apply(lambda x: x.expanding().count().shift(1))
                .reset_index(level=0, drop=True)
            ).clip(upper=10)
            for stat in ['PTS', 'REB', 'AST']:
                roll_col = f'ROLL_10_{stat}'
                if roll_col in df.columns:
                    df[f'VS_OPP_{stat}_DIFF'] = df[f'VS_OPP_AVG_{stat}'] - df[roll_col]
                else:
                    df[f'VS_OPP_{stat}_DIFF'] = 0
            vs_opp_cols = [c for c in df.columns if c.startswith('VS_OPP_')]
            df[vs_opp_cols] = df[vs_opp_cols].fillna(0)

        # Defragment the DataFrame after all column additions
        df = df.copy()

        return df
    
    @staticmethod
    def get_prediction_features(df, is_home, opponent, injuries_team=0, injuries_opp=0,
                                 opp_def_rating=110, opp_pace=100, opp_ast_allowed=25, days_rest=2, vs_stats=None,
                                 player_info=None,
                                 # Enhanced opponent context (from BDL advanced stats)
                                 opp_off_rating=110, opp_net_rating=0,
                                 opp_efg_pct=0.50, opp_tov_pct=14.0,
                                 opp_oreb_pct=0.27, opp_dreb_pct=0.73):
        """Get feature vector for prediction

        Args:
            vs_stats: Dict with head-to-head stats (avg_pts, avg_reb, avg_ast, games)
            player_info: Dict with player metadata including 'position'
            opp_off_rating: Opponent offensive rating (pts per 100 poss)
            opp_net_rating: Opponent net rating (off - def)
            opp_efg_pct: Opponent effective FG%
            opp_tov_pct: Opponent turnover percentage
            opp_oreb_pct: Opponent offensive rebound percentage
            opp_dreb_pct: Opponent defensive rebound percentage
        """
        latest = df.iloc[-1]

        features = {
            'IS_HOME': is_home,
            # Standard rolling averages
            'ROLL_5_PTS': latest.get('ROLL_5_PTS', 0),
            'ROLL_10_PTS': latest.get('ROLL_10_PTS', 0),
            'ROLL_5_REB': latest.get('ROLL_5_REB', 0),
            'ROLL_10_REB': latest.get('ROLL_10_REB', 0),
            'ROLL_5_AST': latest.get('ROLL_5_AST', 0),
            'ROLL_10_AST': latest.get('ROLL_10_AST', 0),
            'ROLL_5_MIN_NUMERIC': latest.get('ROLL_5_MIN_NUMERIC', 30),
            'ROLL_10_MIN_NUMERIC': latest.get('ROLL_10_MIN_NUMERIC', 30),
            # Exponential moving averages (better captures recent form)
            'EMA_5_PTS': latest.get('EMA_5_PTS', latest.get('ROLL_5_PTS', 0)),
            'EMA_5_REB': latest.get('EMA_5_REB', latest.get('ROLL_5_REB', 0)),
            'EMA_5_AST': latest.get('EMA_5_AST', latest.get('ROLL_5_AST', 0)),
            'EMA_5_MIN_NUMERIC': latest.get('EMA_5_MIN_NUMERIC', latest.get('ROLL_5_MIN_NUMERIC', 30)),
            # Variance measures
            'STD_10_PTS': latest.get('STD_10_PTS', 5),
            'STD_10_REB': latest.get('STD_10_REB', 2),
            'STD_10_AST': latest.get('STD_10_AST', 2),
            # Trends
            'PTS_TREND': latest.get('PTS_TREND', 0),
            'REB_TREND': latest.get('REB_TREND', 0),
            'AST_TREND': latest.get('AST_TREND', 0),
            'MIN_TREND': latest.get('MIN_TREND', 0),
            # Rest and schedule
            'DAYS_REST': days_rest,
            'B2B': 1 if days_rest == 1 else 0,
            'EXTENDED_REST': 1 if days_rest >= 3 else 0,
            # Team momentum
            'WIN_STREAK': latest.get('WIN_STREAK', 2.5),
            'LOSS_STREAK': latest.get('LOSS_STREAK', 2.5),
            # Injuries
            'INJURIES_TEAM': injuries_team,
            'INJURIES_OPP': injuries_opp,
            # Opponent context (normalized)
            'OPP_DEF_RATING_NORM': (opp_def_rating - 110) / 5,
            'OPP_PACE_NORM': (opp_pace - 100) / 5,
            'OPP_AST_ALLOWED_NORM': (opp_ast_allowed - 25) / 3,
            # Role stability
            'MIN_CONSISTENCY': latest.get('MIN_CONSISTENCY', 5),
            'USAGE_PROXY': latest.get('USAGE_PROXY', 15),
            # Hot/Cold indicators
            'IS_HOT': latest.get('IS_HOT', 0),
            'IS_COLD': latest.get('IS_COLD', 0),
            # Season phase
            'SEASON_PHASE': latest.get('SEASON_PHASE', 2),

            # =====================
            # ADVANCED STATS
            # =====================
            # Efficiency metrics
            'ROLL_5_TS_PCT': latest.get('ROLL_5_TS_PCT', 0.55),
            'ROLL_10_TS_PCT': latest.get('ROLL_10_TS_PCT', 0.55),
            'ROLL_5_EFG_PCT': latest.get('ROLL_5_EFG_PCT', 0.50),
            'ROLL_5_PTS_PER_FGA': latest.get('ROLL_5_PTS_PER_FGA', 1.1),

            # Usage rate proxy
            'ROLL_5_USG': latest.get('ROLL_5_USG', 20),
            'ROLL_10_USG': latest.get('ROLL_10_USG', 20),

            # Pace-adjusted stats
            'ROLL_5_PTS_PACE_ADJ': latest.get('ROLL_5_PTS_PACE_ADJ', latest.get('ROLL_5_PTS', 0)),
            'ROLL_5_REB_PACE_ADJ': latest.get('ROLL_5_REB_PACE_ADJ', latest.get('ROLL_5_REB', 0)),
            'ROLL_5_AST_PACE_ADJ': latest.get('ROLL_5_AST_PACE_ADJ', latest.get('ROLL_5_AST', 0)),

            # Stocks (steals + blocks) and fantasy
            'ROLL_5_STOCKS': latest.get('ROLL_5_STOCKS', 1.5),
            'ROLL_5_FANTASY_PTS': latest.get('ROLL_5_FANTASY_PTS', 30),

            # Assist/Turnover trends
            'AST_TOV_RATIO': latest.get('AST_TOV_RATIO', 2.0),
            'ROLL_5_AST_TOV': latest.get('ROLL_5_AST_TOV', 2.0),

            # Per-36-minute normalized stats
            'ROLL_5_PTS_PER36': latest.get('ROLL_5_PTS_PER36', 0),
            'ROLL_10_PTS_PER36': latest.get('ROLL_10_PTS_PER36', 0),
            'ROLL_5_REB_PER36': latest.get('ROLL_5_REB_PER36', 0),
            'ROLL_10_REB_PER36': latest.get('ROLL_10_REB_PER36', 0),
            'ROLL_5_AST_PER36': latest.get('ROLL_5_AST_PER36', 0),
            'ROLL_10_AST_PER36': latest.get('ROLL_10_AST_PER36', 0),

            # Blowout-adjusted rolling averages
            'ROLL_10_PTS_BLOWOUT_ADJ': latest.get('ROLL_10_PTS_BLOWOUT_ADJ', latest.get('ROLL_10_PTS', 0)),
            'ROLL_10_REB_BLOWOUT_ADJ': latest.get('ROLL_10_REB_BLOWOUT_ADJ', latest.get('ROLL_10_REB', 0)),
            'ROLL_10_AST_BLOWOUT_ADJ': latest.get('ROLL_10_AST_BLOWOUT_ADJ', latest.get('ROLL_10_AST', 0)),

            # Rolling opponent defensive context (recent form, not just season-long)
            'OPP_DEF_RATING_ROLL10': latest.get('OPP_DEF_RATING_ROLL10', (opp_def_rating - 110) / 5),
            'OPP_PACE_ROLL10': latest.get('OPP_PACE_ROLL10', (opp_pace - 100) / 5),

            # Interaction features
            'B2B_VS_ELITE': (1 if days_rest == 1 else 0) * (1 if (opp_def_rating - 110) / 5 < -0.4 else 0),
            'HOT_VS_WEAK': latest.get('IS_HOT', 0) * (1 if (opp_def_rating - 110) / 5 > 1.2 else 0),
            'RESTED_HOME': (1 if days_rest >= 3 else 0) * is_home,

            # =====================
            # HEAD-TO-HEAD MATCHUP STATS
            # =====================
            # How this player performs vs this specific opponent
            'VS_OPP_AVG_PTS': 0,
            'VS_OPP_AVG_REB': 0,
            'VS_OPP_AVG_AST': 0,
            'VS_OPP_GAMES': 0,
            # Difference from overall average (positive = performs better vs this opponent)
            'VS_OPP_PTS_DIFF': 0,
            'VS_OPP_REB_DIFF': 0,
            'VS_OPP_AST_DIFF': 0,

            # =====================
            # POSITION FEATURES
            # =====================
            'POSITION_ORD': latest.get('POSITION_ORD', 2),
            'POSITION_x_OPP_DEF': latest.get('POSITION_x_OPP_DEF', 0),
            'POSITION_x_OPP_PACE': latest.get('POSITION_x_OPP_PACE', 0),

            # =====================
            # ENHANCED OPPONENT CONTEXT (from BDL advanced stats)
            # =====================
            'OPP_OFF_RATING_NORM': (opp_off_rating - 110) / 5,
            'OPP_NET_RATING_NORM': opp_net_rating / 5,
            'OPP_EFG_PCT_NORM': (opp_efg_pct - 0.50) / 0.03,
            'OPP_TOV_PCT_NORM': (opp_tov_pct - 14.0) / 2.0,
            'OPP_OREB_PCT_NORM': (opp_oreb_pct - 0.27) / 0.05,
            'OPP_DREB_PCT_NORM': (opp_dreb_pct - 0.73) / 0.05,

            # =====================
            # REBOUND SPLIT FEATURES
            # =====================
            'OREB_RATE': latest.get('OREB_RATE', 0.25),
            'ROLL_5_OREB': latest.get('ROLL_5_OREB', 1.0),
            'ROLL_10_OREB': latest.get('ROLL_10_OREB', 1.0),
            'ROLL_5_DREB': latest.get('ROLL_5_DREB', 3.0),
            'ROLL_10_DREB': latest.get('ROLL_10_DREB', 3.0),

            # =====================
            # THREE-POINT SHOOTING FEATURES
            # =====================
            'FG3_RATE': latest.get('FG3_RATE', 0.35),
            'ROLL_5_FG3M': latest.get('ROLL_5_FG3M', 1.5),
            'ROLL_10_FG3M': latest.get('ROLL_10_FG3M', 1.5),
            'ROLL_5_FG3A': latest.get('ROLL_5_FG3A', 4.0),
            'FG3_TREND': latest.get('FG3_TREND', 0),
            'ROLL_5_FG3_RATE': latest.get('ROLL_5_FG3_RATE', 0.35),

            # =====================
            # FREE THROW FEATURES
            # =====================
            'FT_RATE': latest.get('FT_RATE', 0.25),
            'ROLL_5_FT_RATE': latest.get('ROLL_5_FT_RATE', 0.25),
            'ROLL_5_FTM': latest.get('ROLL_5_FTM', 2.0),

            # =====================
            # FOUL TROUBLE / GAME FLOW
            # =====================
            'ROLL_5_PF': latest.get('ROLL_5_PF', 2.5),
            'PF_PER_MIN': latest.get('PF_PER_MIN', 0.08),

            # =====================
            # ENHANCED INTERACTION FEATURES
            # =====================
            'OREB_RATE_x_OPP_OREB': latest.get('OREB_RATE', 0.25) * ((opp_oreb_pct - 0.27) / 0.05),
            'HIGH_PACE_GAME': 1 if opp_pace > 103 else 0,
            'LOW_PACE_GAME': 1 if opp_pace < 97 else 0,
            'ELITE_OPP': 1 if opp_net_rating > 5.0 else 0,

            # Per-36 rebound splits
            'ROLL_5_OREB_PER36': latest.get('ROLL_5_OREB_PER36', 0),
            'ROLL_5_DREB_PER36': latest.get('ROLL_5_DREB_PER36', 0),
        }

        # Add head-to-head stats if available
        if vs_stats and vs_stats.get('games', 0) >= 1:
            features['VS_OPP_AVG_PTS'] = vs_stats.get('avg_pts', 0)
            features['VS_OPP_AVG_REB'] = vs_stats.get('avg_reb', 0)
            features['VS_OPP_AVG_AST'] = vs_stats.get('avg_ast', 0)
            features['VS_OPP_GAMES'] = min(vs_stats.get('games', 0), 10)  # Cap at 10 for normalization

            # Calculate difference from player's overall rolling average
            overall_pts = latest.get('ROLL_10_PTS', latest.get('ROLL_5_PTS', 0))
            overall_reb = latest.get('ROLL_10_REB', latest.get('ROLL_5_REB', 0))
            overall_ast = latest.get('ROLL_10_AST', latest.get('ROLL_5_AST', 0))

            features['VS_OPP_PTS_DIFF'] = vs_stats.get('avg_pts', overall_pts) - overall_pts
            features['VS_OPP_REB_DIFF'] = vs_stats.get('avg_reb', overall_reb) - overall_reb
            features['VS_OPP_AST_DIFF'] = vs_stats.get('avg_ast', overall_ast) - overall_ast

        return pd.DataFrame([features])

    @staticmethod
    def estimate_minutes(df, is_home, days_rest, injuries_team=0):
        """Estimate expected minutes based on context"""
        latest = df.iloc[-1]

        # Base minutes from recent average
        base_min = latest.get('EMA_5_MIN_NUMERIC', latest.get('ROLL_5_MIN_NUMERIC', 30))

        # Adjustments
        adj = 0

        # Home games typically have slightly more minutes for starters
        if is_home:
            adj += 0.5

        # Back-to-back usually means fewer minutes
        if days_rest == 1:
            adj -= 2.0

        # Extended rest can mean fresh legs, more minutes
        if days_rest >= 3:
            adj += 1.0

        # More team injuries might mean more minutes
        if injuries_team >= 2:
            adj += 1.5

        # Cap adjustments
        estimated = base_min + adj
        return max(20, min(42, estimated))  # Reasonable bounds


class MLPredictor:
    """Machine Learning prediction models with ensemble support"""

    def __init__(self, model_type='random_forest', use_ensemble=False):
        self.model_type = model_type
        self.use_ensemble = use_ensemble
        self.models = {}
        self.ensemble_models = {}  # For ensemble predictions
        self.scalers = {}
        self.feature_names = None
        self.training_history = []
        self.feature_importance = {}
        self.recent_averages = {}  # Store recent averages for bias correction
        self.last_game_date = None  # Track last game date in training data
        self.trained_at = None      # Track when model was actually saved/trained
        self.games_trained_on = 0   # Track how many games model has seen
        self.selected_features = None  # Feature selection mask after importance pruning
        self.quantile_models = {}  # Quantile regression models (q10, q90)
        self.residual_models = {}  # Learned bias correction models
        self.probability_calibrator = {}  # Isotonic regression for probability calibration
        self.optimized_params = {}  # Per-player optimized hyperparameters
        self.performance_history = []  # Rolling performance tracking

    # Canonical feature list — used for training and feature mismatch detection
    FEATURE_COLS = [
        # Core features
        'IS_HOME',
        # Rolling averages
        'ROLL_5_PTS', 'ROLL_10_PTS', 'ROLL_5_REB', 'ROLL_10_REB',
        'ROLL_5_AST', 'ROLL_10_AST', 'ROLL_5_MIN_NUMERIC', 'ROLL_10_MIN_NUMERIC',
        # Exponential moving averages
        'EMA_5_PTS', 'EMA_5_REB', 'EMA_5_AST', 'EMA_5_MIN_NUMERIC',
        # Variance
        'STD_10_PTS', 'STD_10_REB', 'STD_10_AST',
        # Trends
        'PTS_TREND', 'REB_TREND', 'AST_TREND', 'MIN_TREND',
        # Schedule context
        'DAYS_REST', 'B2B', 'EXTENDED_REST',
        # Team momentum
        'WIN_STREAK', 'LOSS_STREAK',
        # Role indicators
        'MIN_CONSISTENCY', 'USAGE_PROXY',
        # Hot/cold
        'IS_HOT', 'IS_COLD',
        # Season phase
        'SEASON_PHASE',
        # Opponent context
        'OPP_DEF_RATING_NORM', 'OPP_PACE_NORM', 'OPP_AST_ALLOWED_NORM',
        # Efficiency metrics
        'ROLL_5_TS_PCT', 'ROLL_10_TS_PCT',
        'ROLL_5_EFG_PCT',
        'ROLL_5_PTS_PER_FGA',
        # Usage rate
        'ROLL_5_USG', 'ROLL_10_USG',
        # Pace-adjusted stats
        'ROLL_5_PTS_PACE_ADJ', 'ROLL_5_REB_PACE_ADJ', 'ROLL_5_AST_PACE_ADJ',
        # Defensive contribution
        'ROLL_5_STOCKS',
        # Fantasy (composite metric)
        'ROLL_5_FANTASY_PTS',
        # Assist efficiency
        'AST_TOV_RATIO', 'ROLL_5_AST_TOV',
        # Per-36-minute normalized stats
        'ROLL_5_PTS_PER36', 'ROLL_10_PTS_PER36',
        'ROLL_5_REB_PER36', 'ROLL_10_REB_PER36',
        'ROLL_5_AST_PER36', 'ROLL_10_AST_PER36',
        # Blowout-adjusted rolling averages
        'ROLL_10_PTS_BLOWOUT_ADJ', 'ROLL_10_REB_BLOWOUT_ADJ', 'ROLL_10_AST_BLOWOUT_ADJ',
        # Rolling opponent context
        'OPP_DEF_RATING_ROLL10', 'OPP_PACE_ROLL10',
        # Head-to-head matchup stats
        'VS_OPP_AVG_PTS', 'VS_OPP_AVG_REB', 'VS_OPP_AVG_AST', 'VS_OPP_GAMES',
        'VS_OPP_PTS_DIFF', 'VS_OPP_REB_DIFF', 'VS_OPP_AST_DIFF',
        # Interaction features
        'B2B_VS_ELITE', 'HOT_VS_WEAK', 'RESTED_HOME',
        # Injury context (0 in training data; non-zero at prediction time via apply_injury_boost)
        'INJURIES_TEAM', 'INJURIES_OPP',
        # Position features
        'POSITION_ORD', 'POSITION_x_OPP_DEF', 'POSITION_x_OPP_PACE',

        # =====================
        # NEW FEATURES (BDL advanced stats integration)
        # =====================

        # Enhanced Opponent Context (from team advanced stats)
        'OPP_OFF_RATING_NORM', 'OPP_NET_RATING_NORM', 'OPP_EFG_PCT_NORM',
        'OPP_TOV_PCT_NORM', 'OPP_OREB_PCT_NORM', 'OPP_DREB_PCT_NORM',

        # Rebound Split Features
        'OREB_RATE',
        'ROLL_5_OREB', 'ROLL_10_OREB',
        'ROLL_5_DREB', 'ROLL_10_DREB',

        # Three-Point Shooting Features
        'FG3_RATE',
        'ROLL_5_FG3M', 'ROLL_10_FG3M',
        'ROLL_5_FG3A',
        'FG3_TREND',
        'ROLL_5_FG3_RATE',

        # Free Throw Features
        'FT_RATE',
        'ROLL_5_FT_RATE',
        'ROLL_5_FTM',

        # Foul Trouble / Game Flow
        'ROLL_5_PF',
        'PF_PER_MIN',

        # Enhanced Interaction Features
        'OREB_RATE_x_OPP_OREB',
        'HIGH_PACE_GAME', 'LOW_PACE_GAME',
        'ELITE_OPP',

        # Per-36 Rebound Splits
        'ROLL_5_OREB_PER36', 'ROLL_5_DREB_PER36',
    ]

    # Per-stat optimized hyperparameters for Gradient Boosting
    GB_STAT_PARAMS = {
        'PTS': {
            'n_estimators': 300,
            'max_depth': 5,
            'learning_rate': 0.03,
            'min_samples_leaf': 4,
            'min_samples_split': 8,
            'subsample': 0.8,
            'max_features': 0.7,
            'validation_fraction': 0.15,
            'n_iter_no_change': 20,
            'tol': 1e-4,
        },
        'REB': {
            'n_estimators': 250,
            'max_depth': 4,
            'learning_rate': 0.04,
            'min_samples_leaf': 5,
            'min_samples_split': 10,
            'subsample': 0.75,
            'max_features': 0.6,
            'validation_fraction': 0.15,
            'n_iter_no_change': 15,
            'tol': 1e-4,
        },
        'AST': {
            'n_estimators': 300,
            'max_depth': 5,
            'learning_rate': 0.03,
            'min_samples_leaf': 5,
            'min_samples_split': 8,
            'subsample': 0.8,
            'max_features': 0.7,
            'validation_fraction': 0.15,
            'n_iter_no_change': 20,
            'tol': 1e-4,
        },
        'PRA': {
            'n_estimators': 350,
            'max_depth': 5,
            'learning_rate': 0.025,
            'min_samples_leaf': 4,
            'min_samples_split': 8,
            'subsample': 0.8,
            'max_features': 0.75,
            'validation_fraction': 0.15,
            'n_iter_no_change': 25,
            'tol': 1e-4,
        },
    }

    def _create_model(self, stat):
        """Create a new model instance with stat-specific optimization"""
        if self.model_type == 'random_forest':
            return RandomForestRegressor(
                n_estimators=200,
                max_depth=12,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features='sqrt',
                random_state=42,
                n_jobs=-1
            )
        elif self.model_type == 'gradient_boost':
            # Use stat-specific optimized parameters
            params = self.GB_STAT_PARAMS.get(stat, self.GB_STAT_PARAMS['PTS'])
            return GradientBoostingRegressor(
                n_estimators=params['n_estimators'],
                max_depth=params['max_depth'],
                learning_rate=params['learning_rate'],
                min_samples_leaf=params['min_samples_leaf'],
                min_samples_split=params['min_samples_split'],
                subsample=params['subsample'],
                max_features=params['max_features'],
                validation_fraction=params['validation_fraction'],
                n_iter_no_change=params['n_iter_no_change'],
                tol=params['tol'],
                loss='huber',  # Robust to outliers
                alpha=0.9,     # Huber quantile parameter
                random_state=42
            )
        elif self.model_type == 'neural' and TF_AVAILABLE:
            return self._create_neural_network()
        else:
            return RandomForestRegressor(n_estimators=100, random_state=42)

    def _create_neural_network(self):
        """Create neural network model with improved architecture"""
        model = keras.Sequential([
            layers.Dense(128, activation='relu'),
            layers.BatchNormalization(),
            layers.Dropout(0.3),
            layers.Dense(64, activation='relu'),
            layers.BatchNormalization(),
            layers.Dropout(0.2),
            layers.Dense(32, activation='relu'),
            layers.Dropout(0.1),
            layers.Dense(16, activation='relu'),
            layers.Dense(1)
        ])
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss='huber',  # More robust to outliers
            metrics=['mae']
        )
        return model

    def _create_ensemble_models(self, stat):
        """Create ensemble of different model types with stat-specific GB tuning"""
        params = self.GB_STAT_PARAMS.get(stat, self.GB_STAT_PARAMS['PTS'])
        return {
            'rf': RandomForestRegressor(
                n_estimators=200, max_depth=10, min_samples_leaf=3,
                max_features='sqrt', random_state=42, n_jobs=-1
            ),
            'gb': GradientBoostingRegressor(
                n_estimators=params['n_estimators'],
                max_depth=params['max_depth'],
                learning_rate=params['learning_rate'],
                min_samples_leaf=params['min_samples_leaf'],
                subsample=params['subsample'],
                max_features=params['max_features'],
                loss='huber',
                alpha=0.9,
                random_state=42
            ),
        }

    @staticmethod
    def _weighted_cv_mae(model_or_factory, X, y, weights, tscv):
        """Manual cross-validation with sample_weight support (works on all sklearn versions)."""
        scores = []
        for train_idx, val_idx in tscv.split(X):
            m = sklearn_clone(model_or_factory) if hasattr(model_or_factory, 'get_params') else model_or_factory
            m.fit(X[train_idx], y[train_idx], sample_weight=weights[train_idx])
            pred = m.predict(X[val_idx])
            mae = np.mean(np.abs(y[val_idx] - pred))
            scores.append(mae)
        return np.array(scores)

    def _optimize_hyperparameters(self, X, y, weights, stat):
        """Use Optuna to find optimal hyperparameters for a stat (Improvement #10)."""
        if not OPTUNA_AVAILABLE:
            return self.GB_STAT_PARAMS.get(stat, self.GB_STAT_PARAMS['PTS'])

        # Return cached params if available
        if stat in self.optimized_params:
            return self.optimized_params[stat]

        def objective(trial):
            params = {
                'n_estimators': trial.suggest_int('n_estimators', 100, 500),
                'max_depth': trial.suggest_int('max_depth', 3, 8),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15, log=True),
                'subsample': trial.suggest_float('subsample', 0.6, 0.95),
                'min_samples_leaf': trial.suggest_int('min_samples_leaf', 2, 10),
                'min_samples_split': trial.suggest_int('min_samples_split', 4, 15),
                'max_features': trial.suggest_float('max_features', 0.4, 0.9),
            }
            model = GradientBoostingRegressor(
                **params, loss='huber', alpha=0.9, random_state=42,
                validation_fraction=0.15, n_iter_no_change=15, tol=1e-4,
            )
            tscv = TimeSeriesSplit(n_splits=5)
            scores = self._weighted_cv_mae(model, X, y, weights, tscv)
            # Prioritize last fold (most recent data)
            return scores[-1]

        study = optuna.create_study(direction='minimize')
        study.optimize(objective, n_trials=40, timeout=60, show_progress_bar=False)

        best = study.best_params
        best['validation_fraction'] = 0.15
        best['n_iter_no_change'] = 20
        best['tol'] = 1e-4
        self.optimized_params[stat] = best
        print(f"    Optuna best MAE: {study.best_value:.2f} (params: depth={best['max_depth']}, lr={best['learning_rate']:.3f}, n={best['n_estimators']})")
        return best

    # Features that are stat-specific and should NOT be used to predict other stats.
    # Shared features (MIN, schedule, opponent, efficiency, usage) are allowed everywhere.
    STAT_SPECIFIC_FEATURES = {
        'PTS': {
            'ROLL_5_REB', 'ROLL_10_REB', 'EMA_5_REB', 'STD_10_REB',
            'REB_TREND', 'ROLL_5_REB_PACE_ADJ', 'ROLL_5_REB_PER36', 'ROLL_10_REB_PER36',
            'ROLL_10_REB_BLOWOUT_ADJ', 'VS_OPP_AVG_REB', 'VS_OPP_REB_DIFF',
            'ROLL_5_AST', 'ROLL_10_AST', 'EMA_5_AST', 'STD_10_AST',
            'AST_TREND', 'ROLL_5_AST_PACE_ADJ', 'ROLL_5_AST_PER36', 'ROLL_10_AST_PER36',
            'ROLL_10_AST_BLOWOUT_ADJ', 'VS_OPP_AVG_AST', 'VS_OPP_AST_DIFF',
            'AST_TOV_RATIO', 'ROLL_5_AST_TOV',
        },
        'REB': {
            'ROLL_5_PTS', 'ROLL_10_PTS', 'EMA_5_PTS', 'STD_10_PTS',
            'PTS_TREND', 'ROLL_5_PTS_PACE_ADJ', 'ROLL_5_PTS_PER36', 'ROLL_10_PTS_PER36',
            'ROLL_10_PTS_BLOWOUT_ADJ', 'VS_OPP_AVG_PTS', 'VS_OPP_PTS_DIFF',
            'ROLL_5_AST', 'ROLL_10_AST', 'EMA_5_AST', 'STD_10_AST',
            'AST_TREND', 'ROLL_5_AST_PACE_ADJ', 'ROLL_5_AST_PER36', 'ROLL_10_AST_PER36',
            'ROLL_10_AST_BLOWOUT_ADJ', 'VS_OPP_AVG_AST', 'VS_OPP_AST_DIFF',
            'AST_TOV_RATIO', 'ROLL_5_AST_TOV',
            'ROLL_5_TS_PCT', 'ROLL_10_TS_PCT', 'ROLL_5_EFG_PCT', 'ROLL_5_PTS_PER_FGA',
        },
        'AST': {
            'ROLL_5_PTS', 'ROLL_10_PTS', 'EMA_5_PTS', 'STD_10_PTS',
            'PTS_TREND', 'ROLL_5_PTS_PACE_ADJ', 'ROLL_5_PTS_PER36', 'ROLL_10_PTS_PER36',
            'ROLL_10_PTS_BLOWOUT_ADJ', 'VS_OPP_AVG_PTS', 'VS_OPP_PTS_DIFF',
            'ROLL_5_REB', 'ROLL_10_REB', 'EMA_5_REB', 'STD_10_REB',
            'REB_TREND', 'ROLL_5_REB_PACE_ADJ', 'ROLL_5_REB_PER36', 'ROLL_10_REB_PER36',
            'ROLL_10_REB_BLOWOUT_ADJ', 'VS_OPP_AVG_REB', 'VS_OPP_REB_DIFF',
            'ROLL_5_TS_PCT', 'ROLL_10_TS_PCT', 'ROLL_5_EFG_PCT', 'ROLL_5_PTS_PER_FGA',
        },
        # PRA uses all features since it's a composite stat
        'PRA': set(),
    }

    def _select_features(self, model, X, feature_names, cumulative_threshold=0.95, stat=None):
        """Select features by cumulative importance with cross-stat pruning.

        When training a stat-specific model (PTS/REB/AST), zero out importance of
        features that belong to other stat categories to prevent cross-stat
        contamination (e.g., AST features dominating a PTS model).
        """
        if not hasattr(model, 'feature_importances_'):
            return np.arange(X.shape[1]), feature_names

        importances = model.feature_importances_.copy()

        # Zero out cross-stat features so they are pruned first
        if stat and stat in self.STAT_SPECIFIC_FEATURES:
            excluded = self.STAT_SPECIFIC_FEATURES[stat]
            for i, fname in enumerate(feature_names):
                if fname in excluded:
                    importances[i] = 0.0
            # Renormalize remaining importances
            total = importances.sum()
            if total > 0:
                importances = importances / total

        sorted_idx = np.argsort(importances)[::-1]
        cumsum = np.cumsum(importances[sorted_idx])
        # Keep features explaining cumulative_threshold of importance
        n_keep = np.searchsorted(cumsum, cumulative_threshold) + 1
        # Keep at least 15 features to avoid over-pruning
        n_keep = max(n_keep, min(15, len(feature_names)))
        selected_idx = sorted_idx[:n_keep]
        selected_idx = np.sort(selected_idx)  # Restore original order
        selected_names = [feature_names[i] for i in selected_idx]
        return selected_idx, selected_names

    def _train_quantile_models(self, X, y, weights, stat, params):
        """Train quantile regression models for uncertainty bounds (Improvement #4)."""
        q_params = {k: v for k, v in params.items()
                    if k not in ('validation_fraction', 'n_iter_no_change', 'tol')}
        q_params['n_estimators'] = max(100, q_params.get('n_estimators', 200) // 2)
        q_params['learning_rate'] = q_params.get('learning_rate', 0.05) * 1.5
        q_params['random_state'] = 42

        for alpha, label in [(0.1, 'q10'), (0.9, 'q90')]:
            qmodel = GradientBoostingRegressor(loss='quantile', alpha=alpha, **q_params)
            qmodel.fit(X, y, sample_weight=weights)
            self.quantile_models[f'{stat}_{label}'] = qmodel

    def _train_residual_model(self, X, y, weights, stat, tscv):
        """Train a residual correction model from OOF predictions (Improvement #6)."""
        oof_preds = np.full(len(y), np.nan)
        for train_idx, val_idx in tscv.split(X):
            fold_model = sklearn_clone(self.models[stat])
            fold_model.fit(X[train_idx], y[train_idx], sample_weight=weights[train_idx])
            oof_preds[val_idx] = fold_model.predict(X[val_idx])

        valid_mask = ~np.isnan(oof_preds)
        if valid_mask.sum() < 15:
            return

        residuals = y[valid_mask] - oof_preds[valid_mask]
        # Build residual features: [raw_pred, recent_5g_rolling_mean_approx, std_proxy]
        residual_X = np.column_stack([
            oof_preds[valid_mask],
            np.convolve(y, np.ones(5)/5, mode='same')[valid_mask],
            np.convolve(y, np.ones(10)/10, mode='same')[valid_mask],
            pd.Series(y).rolling(10, min_periods=3).std().fillna(3).values[valid_mask],
        ])
        residual_model = BayesianRidge()
        residual_model.fit(residual_X, residuals)
        self.residual_models[stat] = residual_model

    def _train_probability_calibrator(self, X, y, weights, stat, tscv):
        """Train isotonic regression for probability calibration (Improvement #5)."""
        oof_preds = np.full(len(y), np.nan)
        for train_idx, val_idx in tscv.split(X):
            fold_model = sklearn_clone(self.models[stat])
            fold_model.fit(X[train_idx], y[train_idx], sample_weight=weights[train_idx])
            oof_preds[val_idx] = fold_model.predict(X[val_idx])

        valid_mask = ~np.isnan(oof_preds)
        if valid_mask.sum() < 30:
            return

        preds = oof_preds[valid_mask]
        actuals = y[valid_mask]
        std_estimate = np.std(actuals - preds) or 1.0

        # Generate calibration data across hypothetical lines
        z_scores = []
        outcomes = []
        for i in range(len(preds)):
            # Test multiple line offsets around the prediction
            for offset in np.linspace(-2 * std_estimate, 2 * std_estimate, 9):
                hypothetical_line = preds[i] + offset
                z = (hypothetical_line - preds[i]) / (std_estimate + 0.1)
                went_over = 1 if actuals[i] > hypothetical_line else 0
                z_scores.append(z)
                outcomes.append(went_over)

        z_scores = np.array(z_scores)
        outcomes = np.array(outcomes)

        # Bin z-scores and compute actual over rates
        calibrator = IsotonicRegression(y_min=0.02, y_max=0.98, out_of_bounds='clip')
        # Map z-score to raw CDF-based probability, then calibrate
        raw_prob_over = 1 - scipy_stats.norm.cdf(z_scores)
        calibrator.fit(raw_prob_over, outcomes)
        self.probability_calibrator[stat] = {
            'calibrator': calibrator,
            'std_estimate': std_estimate,
        }

    def train(self, df, stats=None):
        """Train models for specified stats with feature selection, quantile regression,
        residual correction, probability calibration, and optional Optuna HPO."""
        if stats is None:
            stats = ['PTS', 'REB', 'AST']
        feature_cols = self.FEATURE_COLS

        # Filter to available features
        available_features = [f for f in feature_cols if f in df.columns]
        self.feature_names = available_features

        # Prepare data - filter out low-minute games (likely injury/rest games)
        df_clean = df.dropna(subset=available_features + stats)

        # Filter out games with very low minutes (likely not representative)
        if 'MIN_NUMERIC' in df_clean.columns:
            avg_min = df_clean['MIN_NUMERIC'].mean()
            min_threshold = max(15, avg_min * 0.5)  # At least 50% of average or 15 min
            df_clean = df_clean[df_clean['MIN_NUMERIC'] >= min_threshold]

        if len(df_clean) < 20:
            print("⚠️ Insufficient data for training (need at least 20 games)")
            return False

        # Apply exponential recency weighting.
        # Exponent scales with dataset size so recent games carry proportionally more weight
        # for large (multi-season) datasets without over-reacting to the last few games:
        # - 50 games  → span -1.5  (recent 10 = ~28% of weight, 7x oldest→newest)
        # - 100 games → span -1.9  (recent 10 = ~18% of weight, 7x oldest→newest)
        # - 200 games → span -2.5  (recent 10 = ~13% of weight, 12x oldest→newest)
        n_games = len(df_clean)
        exponent_span = -max(1.5, min(2.5, n_games / 80))
        recency_weights = np.exp(np.linspace(exponent_span, 0, n_games))
        recency_weights = recency_weights / recency_weights.sum() * n_games

        X = df_clean[available_features].values

        # Scale features
        self.scalers['features'] = StandardScaler()
        X_scaled = self.scalers['features'].fit_transform(X)

        print(f"\n🤖 Training {self.model_type} models on {len(df_clean)} games with {len(available_features)} features...")

        # Store recent averages for bias correction fallback
        self.recent_averages = {}
        for stat in stats + ['PRA']:
            if stat == 'PRA':
                recent_vals = (df_clean['PTS'] + df_clean['REB'] + df_clean['AST']).tail(10)
            elif stat in df_clean.columns:
                recent_vals = df_clean[stat].tail(10)
            else:
                continue
            self.recent_averages[stat] = recent_vals.mean()

        tscv = TimeSeriesSplit(n_splits=5)

        for stat in stats:
            y = df_clean[stat].values

            # --- Optuna HPO (Improvement #10) ---
            if self.model_type == 'gradient_boost' and OPTUNA_AVAILABLE and n_games >= 40:
                print(f"  {stat}: Running hyperparameter optimization...")
                best_params = self._optimize_hyperparameters(X_scaled, y, recency_weights, stat)
                model = GradientBoostingRegressor(
                    **best_params, loss='huber', alpha=0.9, random_state=42,
                )
            else:
                model = self._create_model(stat)

            if self.model_type == 'neural' and TF_AVAILABLE:
                # Neural network training with early stopping
                early_stop = keras.callbacks.EarlyStopping(
                    monitor='val_loss', patience=10, restore_best_weights=True
                )
                model.fit(X_scaled, y, epochs=100, batch_size=16, verbose=0,
                         validation_split=0.2, callbacks=[early_stop],
                         sample_weight=recency_weights)
            else:
                # Sklearn model training with weighted CV
                scores = self._weighted_cv_mae(model, X_scaled, y, recency_weights, tscv)
                print(f"  {stat}: CV MAE = {scores.mean():.2f} (±{scores.std():.2f})")
                model.fit(X_scaled, y, sample_weight=recency_weights)

                # --- Feature Selection (Improvement #1) ---
                if hasattr(model, 'feature_importances_') and len(available_features) > 20:
                    sel_idx, sel_names = self._select_features(model, X_scaled, available_features, stat=stat)
                    if len(sel_names) < len(available_features):
                        X_sel = X_scaled[:, sel_idx]
                        # Retrain on selected features
                        model_sel = sklearn_clone(model)
                        model_sel.fit(X_sel, y, sample_weight=recency_weights)
                        scores_sel = self._weighted_cv_mae(model_sel, X_sel, y, recency_weights, tscv)
                        new_mae = scores_sel.mean()
                        old_mae = scores.mean()
                        if new_mae <= old_mae * 1.02:  # Accept if not worse by >2%
                            model = model_sel
                            print(f"    Feature selection: {len(available_features)} → {len(sel_names)} features (MAE {old_mae:.2f} → {new_mae:.2f})")
                            if self.selected_features is None:
                                self.selected_features = {}
                            self.selected_features[stat] = sel_idx
                        else:
                            print(f"    Feature selection skipped (would increase MAE: {old_mae:.2f} → {new_mae:.2f})")

                # Store feature importance for tree-based models
                if hasattr(model, 'feature_importances_'):
                    feat_names = available_features
                    if self.selected_features and stat in self.selected_features:
                        feat_names = [available_features[i] for i in self.selected_features[stat]]
                    self.feature_importance[stat] = dict(
                        zip(feat_names, model.feature_importances_)
                    )

                    # Log new feature usage after selection
                    _new_feats = {
                        'OPP_OFF_RATING_NORM', 'OPP_NET_RATING_NORM', 'OPP_EFG_PCT_NORM',
                        'OPP_TOV_PCT_NORM', 'OPP_OREB_PCT_NORM', 'OPP_DREB_PCT_NORM',
                        'OREB_RATE', 'ROLL_5_OREB', 'ROLL_10_OREB', 'ROLL_5_DREB', 'ROLL_10_DREB',
                        'FG3_RATE', 'ROLL_5_FG3M', 'ROLL_10_FG3M', 'ROLL_5_FG3A', 'FG3_TREND',
                        'FT_RATE', 'ROLL_5_FT_RATE', 'ROLL_5_FTM',
                        'ROLL_5_PF', 'PF_PER_MIN',
                        'OREB_RATE_x_OPP_OREB', 'HIGH_PACE_GAME', 'LOW_PACE_GAME', 'ELITE_OPP',
                        'ROLL_5_OREB_PER36', 'ROLL_5_DREB_PER36', 'ROLL_5_FG3_RATE',
                    }
                    _kept = {n: v for n, v in self.feature_importance[stat].items() if n in _new_feats}
                    if _kept:
                        _top = sorted(_kept.items(), key=lambda x: x[1], reverse=True)[:5]
                        print(f"    📊 New features in {stat}: {len(_kept)} kept, top: {', '.join(f'{n}={v:.3f}' for n, v in _top)}")

            self.models[stat] = model

            # --- Quantile Regression (Improvement #4) ---
            if self.model_type in ('gradient_boost',) and self.model_type != 'neural':
                params = self.optimized_params.get(stat, self.GB_STAT_PARAMS.get(stat, self.GB_STAT_PARAMS['PTS']))
                X_for_quantile = X_scaled
                if self.selected_features and stat in self.selected_features:
                    X_for_quantile = X_scaled[:, self.selected_features[stat]]
                self._train_quantile_models(X_for_quantile, y, recency_weights, stat, params)

            # --- Residual Correction Model (Improvement #6) ---
            if self.model_type != 'neural':
                X_for_residual = X_scaled
                if self.selected_features and stat in self.selected_features:
                    X_for_residual = X_scaled[:, self.selected_features[stat]]
                self._train_residual_model(X_for_residual, y, recency_weights, stat, tscv)

            # --- Probability Calibration (Improvement #5) ---
            if self.model_type != 'neural':
                X_for_calib = X_scaled
                if self.selected_features and stat in self.selected_features:
                    X_for_calib = X_scaled[:, self.selected_features[stat]]
                self._train_probability_calibrator(X_for_calib, y, recency_weights, stat, tscv)

            # Train ensemble if enabled
            if self.use_ensemble and self.model_type != 'neural':
                print(f"  Training ensemble for {stat}...")
                self.ensemble_models[stat] = self._create_ensemble_models(stat)
                for name, ens_model in self.ensemble_models[stat].items():
                    ens_model.fit(X_scaled, y, sample_weight=recency_weights)

        # Train PRA model
        if all(s in df_clean.columns for s in ['PTS', 'REB', 'AST']):
            y_pra = (df_clean['PTS'] + df_clean['REB'] + df_clean['AST']).values
            stat = 'PRA'

            if self.model_type == 'gradient_boost' and OPTUNA_AVAILABLE and n_games >= 40:
                print(f"  PRA: Running hyperparameter optimization...")
                best_params = self._optimize_hyperparameters(X_scaled, y_pra, recency_weights, 'PRA')
                model_pra = GradientBoostingRegressor(
                    **best_params, loss='huber', alpha=0.9, random_state=42,
                )
            else:
                model_pra = self._create_model('PRA')

            if self.model_type == 'neural' and TF_AVAILABLE:
                model_pra.fit(X_scaled, y_pra, epochs=100, batch_size=16, verbose=0,
                             sample_weight=recency_weights)
            else:
                scores = self._weighted_cv_mae(model_pra, X_scaled, y_pra, recency_weights, tscv)
                print(f"  PRA: CV MAE = {scores.mean():.2f} (±{scores.std():.2f})")
                model_pra.fit(X_scaled, y_pra, sample_weight=recency_weights)
            self.models['PRA'] = model_pra

            # Quantile + residual + calibration for PRA
            if self.model_type in ('gradient_boost',) and self.model_type != 'neural':
                pra_params = self.optimized_params.get('PRA', self.GB_STAT_PARAMS.get('PRA', self.GB_STAT_PARAMS['PTS']))
                self._train_quantile_models(X_scaled, y_pra, recency_weights, 'PRA', pra_params)
                self._train_residual_model(X_scaled, y_pra, recency_weights, 'PRA', tscv)
                self._train_probability_calibrator(X_scaled, y_pra, recency_weights, 'PRA', tscv)

            if self.use_ensemble and self.model_type != 'neural':
                self.ensemble_models['PRA'] = self._create_ensemble_models('PRA')
                for name, ens_model in self.ensemble_models['PRA'].items():
                    ens_model.fit(X_scaled, y_pra, sample_weight=recency_weights)

        # Track training metadata
        self.last_game_date = df_clean['GAME_DATE'].max().strftime('%Y-%m-%d')
        self.games_trained_on = len(df_clean)

        return True

    # Maximum estimator growth before forcing a full retrain
    MAX_ESTIMATOR_GROWTH = 80  # After 4 warm-start updates, retrain from scratch
    # Maximum model age (in days) before forcing a full retrain
    MAX_MODEL_AGE_DAYS = 7

    def _needs_full_retrain(self):
        """Check if the model has grown too large or is too old and needs a full retrain."""
        # Check estimator bloat
        for stat, model in self.models.items():
            if hasattr(model, 'n_estimators'):
                original = self.GB_STAT_PARAMS.get(stat, self.GB_STAT_PARAMS['PTS'])['n_estimators']
                if model.n_estimators >= original + self.MAX_ESTIMATOR_GROWTH:
                    print(f"  ⚠️ {stat} model has {model.n_estimators} estimators (started at {original}) — triggering full retrain")
                    return True

        # Check model age (use trained_at wall-clock date, not last game date)
        trained_at = getattr(self, 'trained_at', None)
        if trained_at:
            saved_date = datetime.strptime(trained_at, '%Y-%m-%d')
            age_days = (datetime.now() - saved_date).days
            if age_days >= self.MAX_MODEL_AGE_DAYS:
                print(f"  ⚠️ Model was saved {age_days} days ago ({trained_at}) — triggering full retrain")
                return True

        # Check feature set mismatch — only retrain if features the model was
        # trained on have been REMOVED from FEATURE_COLS. Features in FEATURE_COLS
        # but absent from training data (e.g. INJURIES_TEAM/OPP, VS_OPP_* before
        # backfill) are expected and not a mismatch.
        if self.feature_names:
            saved_set = set(self.feature_names)
            declared_set = set(self.FEATURE_COLS)
            removed_features = saved_set - declared_set
            if removed_features:
                print(f"  ⚠️ Features removed from FEATURE_COLS: {removed_features} — triggering full retrain")
                return True

        return False

    def update(self, df, stats=None):
        """Incrementally update model with new games (warm start).

        Automatically triggers a full retrain when:
        - Estimator count has grown too high (80+ above original)
        - Model is older than 7 days
        """
        if stats is None:
            stats = ['PTS', 'REB', 'AST']
        if not self.models or not self.last_game_date:
            print("  ⚠️ No existing model to update, training from scratch...")
            return self.train(df, stats)

        # Check if model needs a full retrain instead of warm-start
        if self._needs_full_retrain():
            print("\n♻️ Auto-retraining from scratch for better accuracy...")
            return self.train(df, stats)

        # Check for genuinely new features in data that model wasn't trained on
        available_now = [f for f in self.FEATURE_COLS if f in df.columns]
        new_data_features = set(available_now) - set(self.feature_names)
        if new_data_features:
            print(f"  ⚠️ New features available in data: {new_data_features} — triggering full retrain")
            return self.train(df, stats)

        # Filter to only new games since last training
        df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
        last_date = pd.to_datetime(self.last_game_date)
        new_games = df[df['GAME_DATE'] > last_date]

        if len(new_games) == 0:
            print(f"  ℹ️ No new games since {self.last_game_date} - model is up to date")
            # Still update recent averages for better predictions
            self._update_recent_averages(df, stats)
            return True

        print(f"\n🔄 Updating model with {len(new_games)} new game(s) since {self.last_game_date}...")

        # For tree-based models, we can do warm_start updates
        feature_cols = self.feature_names

        # Filter out low-minute games
        df_clean = df.dropna(subset=feature_cols + stats)
        if 'MIN_NUMERIC' in df_clean.columns:
            avg_min = df_clean['MIN_NUMERIC'].mean()
            min_threshold = max(15, avg_min * 0.5)
            df_clean = df_clean[df_clean['MIN_NUMERIC'] >= min_threshold]

        if len(df_clean) < 20:
            print("  ⚠️ Insufficient data for update")
            return False

        # Apply stronger recency weighting for updates (same adaptive formula as full train)
        n_games = len(df_clean)
        exponent_span = -max(1.5, min(2.5, n_games / 80))
        recency_weights = np.exp(np.linspace(exponent_span, 0, n_games))
        recency_weights = recency_weights / recency_weights.sum() * n_games

        X = df_clean[feature_cols].values
        X_scaled = self.scalers['features'].transform(X)

        for stat in stats:
            if stat not in self.models:
                continue

            y = df_clean[stat].values
            model = self.models[stat]

            # --- Smart Warm-Start with Shift Detection (Improvement #8) ---
            n_add = 20  # Default
            if hasattr(model, 'warm_start') and len(new_games) > 0:
                old_mean = df_clean[stat].iloc[:-len(new_games)].tail(20).mean() if len(df_clean) > len(new_games) else df_clean[stat].mean()
                old_std = df_clean[stat].iloc[:-len(new_games)].tail(20).std() if len(df_clean) > len(new_games) else df_clean[stat].std()
                new_mean = new_games[stat].mean() if stat in new_games.columns else old_mean
                shift_z = abs(new_mean - old_mean) / (old_std + 0.1)

                if shift_z > 1.5:
                    n_add = 40
                    print(f"  {stat}: Major distribution shift detected (z={shift_z:.1f}) — aggressive update (+{n_add})")
                elif shift_z > 0.7:
                    n_add = 30
                    print(f"  {stat}: Moderate shift (z={shift_z:.1f}) — aggressive update (+{n_add})")
                elif len(new_games) < 2:
                    n_add = 10
                else:
                    n_add = 20

            # Match feature count to what the model expects
            X_update = X_scaled
            use_warm_start = hasattr(model, 'warm_start')

            if self.selected_features and stat in self.selected_features:
                expected = getattr(model, 'n_features_in_', X_scaled.shape[1])
                if len(self.selected_features[stat]) == expected:
                    X_update = X_scaled[:, self.selected_features[stat]]
                else:
                    # Model and selection are out of sync — cold retrain
                    del self.selected_features[stat]
                    use_warm_start = False

            if use_warm_start:
                model.set_params(warm_start=True, n_estimators=model.n_estimators + n_add)
                model.fit(X_update, y, sample_weight=recency_weights)
                print(f"  {stat}: Updated (+{n_add} estimators, now {model.n_estimators} total)")
            else:
                model.fit(X_update, y, sample_weight=recency_weights)
                print(f"  {stat}: Retrained with {len(df_clean)} games")

            # Update feature importance
            if hasattr(model, 'feature_importances_'):
                self.feature_importance[stat] = dict(
                    zip(feature_cols, model.feature_importances_)
                )

        # Update PRA model
        if 'PRA' in self.models:
            y_pra = df_clean['PTS'] + df_clean['REB'] + df_clean['AST']
            model_pra = self.models['PRA']
            X_update_pra = X_scaled
            use_warm_pra = hasattr(model_pra, 'warm_start')

            if self.selected_features and 'PRA' in self.selected_features:
                expected = getattr(model_pra, 'n_features_in_', X_scaled.shape[1])
                if len(self.selected_features['PRA']) == expected:
                    X_update_pra = X_scaled[:, self.selected_features['PRA']]
                else:
                    del self.selected_features['PRA']
                    use_warm_pra = False

            if use_warm_pra:
                model_pra.set_params(warm_start=True, n_estimators=model_pra.n_estimators + 20)
                model_pra.fit(X_update_pra, y_pra.values, sample_weight=recency_weights)
            else:
                model_pra.fit(X_update_pra, y_pra.values, sample_weight=recency_weights)

        # Update recent averages
        self._update_recent_averages(df_clean, stats)

        # Update tracking
        self.last_game_date = df_clean['GAME_DATE'].max().strftime('%Y-%m-%d')
        self.games_trained_on = len(df_clean)

        return True

    def _update_recent_averages(self, df, stats=None):
        """Update recent averages from latest data"""
        if stats is None:
            stats = ['PTS', 'REB', 'AST']
        for stat in stats + ['PRA']:
            if stat == 'PRA':
                if all(s in df.columns for s in ['PTS', 'REB', 'AST']):
                    recent_vals = (df['PTS'] + df['REB'] + df['AST']).tail(10)
                else:
                    continue
            elif stat in df.columns:
                recent_vals = df[stat].tail(10)
            else:
                continue
            self.recent_averages[stat] = recent_vals.mean()
    
    # Per-stat bias correction weights — lower = trust the ML model more
    # Increased from original values to combat systematic over-prediction bias
    # (OVER picks hitting 47.1% vs UNDER 62.2%)
    BIAS_CORRECTION_BY_STAT = {
        'PTS': 0.15,
        'REB': 0.20,   # increased from 0.15 — corrects +0.99 systematic over-prediction
        'AST': 0.25,   # increased from 0.20 — corrects +0.96 systematic over-prediction
        'PRA': 0.12,
    }

    # Regression-to-mean dampening — pulls predictions toward recent avg.
    # Slightly asymmetric: stronger when prediction is ABOVE avg (over-prediction bias).
    OVER_DAMPENING_BY_STAT = {
        'PTS': 0.08,
        'REB': 0.18,   # increased from 0.10
        'AST': 0.16,   # increased from 0.10
        'PRA': 0.08,
    }

    def predict(self, features_df, bias_correction=None, estimated_minutes=None):
        """Make predictions for all trained stats with learned residual correction.

        Args:
            features_df: DataFrame with features for prediction
            bias_correction: Legacy param — ignored, uses learned residual model or per-stat weights.
            estimated_minutes: Expected minutes for this game (from estimate_minutes).
                               If provided, scales predictions based on minutes ratio.
        """
        if not self.models:
            return {}

        # Ensure features match training - handle missing features
        feature_values = []
        for f in self.feature_names:
            if f in features_df.columns:
                feature_values.append(features_df[f].values[0])
            else:
                feature_values.append(0)  # Default for missing features

        X = np.array([feature_values])
        X_scaled = self.scalers['features'].transform(X)

        # Get baseline minutes for minutes-based scaling
        baseline_minutes = None
        if estimated_minutes is not None:
            # Use the rolling average minutes as baseline
            for fname in ['EMA_5_MIN_NUMERIC', 'ROLL_5_MIN_NUMERIC', 'ROLL_10_MIN_NUMERIC']:
                if fname in features_df.columns:
                    val = features_df[fname].values[0]
                    if val > 0:
                        baseline_minutes = val
                        break

        predictions = {}
        for stat, model in self.models.items():
            # Apply feature selection if active and consistent with model
            X_pred = X_scaled
            if self.selected_features and stat in self.selected_features:
                expected = getattr(model, 'n_features_in_', X_scaled.shape[1])
                if len(self.selected_features[stat]) == expected:
                    X_pred = X_scaled[:, self.selected_features[stat]]
                else:
                    del self.selected_features[stat]

            if self.model_type == 'neural' and TF_AVAILABLE:
                pred = model.predict(X_pred, verbose=0)[0][0]
            else:
                pred = model.predict(X_pred)[0]

            # Ensemble predictions if enabled
            if self.use_ensemble and stat in self.ensemble_models:
                ensemble_preds = [pred]  # Include main model
                for name, ens_model in self.ensemble_models[stat].items():
                    ens_pred = ens_model.predict(X_scaled)[0]
                    ensemble_preds.append(ens_pred)
                # Weighted average (main model gets more weight)
                pred = 0.5 * pred + 0.5 * np.mean(ensemble_preds[1:])

            # --- Minutes-Based Scaling ---
            # Scale prediction proportionally if expected minutes differ from baseline
            if estimated_minutes is not None and baseline_minutes and baseline_minutes > 15 and stat != 'PRA':
                minutes_ratio = estimated_minutes / baseline_minutes
                # Dampen the ratio to avoid extreme swings (e.g., 0.85 - 1.15 range)
                minutes_ratio = 0.5 + 0.5 * minutes_ratio  # Blend toward 1.0
                minutes_ratio = max(0.85, min(1.15, minutes_ratio))
                pred = pred * minutes_ratio

            # --- Learned Residual Correction (Improvement #6) ---
            if stat in self.residual_models and hasattr(self, 'recent_averages') and stat in self.recent_averages:
                recent_avg = self.recent_averages[stat]
                residual_X = np.array([[
                    pred,
                    recent_avg,
                    recent_avg,  # 10g proxy (same as recent avg if we only have it)
                    3.0,  # std proxy fallback
                ]])
                predicted_residual = self.residual_models[stat].predict(residual_X)[0]
                # Clip residual correction to avoid wild swings
                max_correction = abs(pred) * 0.15
                predicted_residual = np.clip(predicted_residual, -max_correction, max_correction)
                pred = pred + predicted_residual
            elif hasattr(self, 'recent_averages') and stat in self.recent_averages:
                # Fallback: symmetric bias correction
                recent_avg = self.recent_averages[stat]
                bc = self.BIAS_CORRECTION_BY_STAT.get(stat, 0.15)
                pred = (1 - bc) * pred + bc * recent_avg

            # --- Regression-to-Mean Dampening ---
            # Pull predictions toward recent avg. Slightly stronger when ABOVE avg
            # to combat the model's systematic over-prediction bias.
            if hasattr(self, 'recent_averages') and stat in self.recent_averages:
                recent_avg = self.recent_averages[stat]
                dampening = self.OVER_DAMPENING_BY_STAT.get(stat, 0.08)
                diff = pred - recent_avg
                # Asymmetric: 50% stronger pull when over-predicting (above avg)
                if diff > 0:
                    dampening = dampening * 1.5
                pred = pred - (diff * dampening)

            # --- Rolling Performance Feedback (Improvement #9) ---
            rolling_bias = self.get_rolling_bias(stat)
            if abs(rolling_bias) > 0.3:  # Only correct if meaningful bias detected
                correction = rolling_bias * 0.5  # Apply 50% of detected bias
                pred = pred - correction

            # --- Hard Deviation Cap ---
            # Prevents runaway EMA-driven predictions when one outlier game dominates
            # recent features (e.g., EMA_5_AST at 52%+ importance). Cap only fires
            # when prediction is far above recent average; has zero effect on normal cases.
            if hasattr(self, 'recent_averages') and stat in self.recent_averages:
                recent_avg = self.recent_averages[stat]
                if recent_avg > 0:
                    stat_upside_caps = {
                        'AST': 1.40,  # max 40% above recent L10 avg
                        'REB': 1.55,  # max 55% above
                        'PTS': 1.60,  # max 60% above
                        'PRA': 1.50,  # max 50% above
                    }
                    upside_mult = stat_upside_caps.get(stat, 1.50)
                    upper_cap = recent_avg * upside_mult
                    if pred > upper_cap:
                        pred = upper_cap

            predictions[stat] = pred

        # Reconcile PRA with component predictions to avoid inconsistency.
        # Heavily weight component sum (85%) since the independent PRA model's
        # composite predictions compound errors (PRA picks are 0-3 all-time).
        if 'PRA' in predictions and all(s in predictions for s in ['PTS', 'REB', 'AST']):
            component_sum = predictions['PTS'] + predictions['REB'] + predictions['AST']
            predictions['PRA'] = 0.85 * component_sum + 0.15 * predictions['PRA']

        return predictions

    def apply_injury_boost(self, predictions, injuries_team=0, injuries_opp=0):
        """Apply post-prediction usage adjustment based on injury counts.

        Each teammate OUT redistributes their minutes/usage to remaining players.
        Each opponent OUT slightly eases the defensive matchup for scoring.

        Args:
            predictions: dict of {stat: predicted_value} from predict()
            injuries_team: number of the player's own teammates ruled OUT
            injuries_opp: number of opponent players ruled OUT

        Returns:
            New predictions dict with injury adjustments applied.
        """
        if injuries_team == 0 and injuries_opp == 0:
            return predictions

        result = dict(predictions)

        # Teammate OUT → usage redistribution: +2.5% per player, capped at +10%
        if injuries_team > 0:
            boost = min(injuries_team * 0.025, 0.10)
            for stat in ('PTS', 'REB', 'AST'):
                if stat in result:
                    result[stat] = result[stat] * (1 + boost)

        # Opponent OUT → easier scoring: +1% per player, capped at +4%, PTS only
        if injuries_opp > 0:
            pts_boost = min(injuries_opp * 0.010, 0.04)
            if 'PTS' in result:
                result['PTS'] = result['PTS'] * (1 + pts_boost)

        # Reconcile PRA with adjusted components
        if all(s in result for s in ('PTS', 'REB', 'AST')):
            result['PRA'] = result['PTS'] + result['REB'] + result['AST']

        return result

    def get_prediction_uncertainty(self, features_df, stat):
        """Get prediction uncertainty using model-specific methods"""
        if stat not in self.models:
            return None

        # Handle missing features
        feature_values = []
        for f in self.feature_names:
            if f in features_df.columns:
                feature_values.append(features_df[f].values[0])
            else:
                feature_values.append(0)

        X = np.array([feature_values])
        X_scaled = self.scalers['features'].transform(X)

        model = self.models[stat]

        if isinstance(model, RandomForestRegressor):
            # Apply feature selection mask if it was used during training
            X_pred = X_scaled
            if self.selected_features and stat in self.selected_features:
                expected = getattr(model, 'n_features_in_', X_scaled.shape[1])
                if len(self.selected_features[stat]) == expected:
                    X_pred = X_scaled[:, self.selected_features[stat]]
            # Get predictions from all trees
            tree_preds = np.array([tree.predict(X_pred)[0]
                                   for tree in model.estimators_])
            return {
                'mean': np.mean(tree_preds),
                'std': np.std(tree_preds),
                'quantile_25': np.percentile(tree_preds, 25),
                'quantile_75': np.percentile(tree_preds, 75),
            }

        return None

    def get_feature_importance(self, stat, top_n=10):
        """Get top N most important features for a stat"""
        if stat not in self.feature_importance:
            return None

        importance = self.feature_importance[stat]
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        return sorted_features[:top_n]
    
    # Per-stat confidence caps — prevents overconfidence on harder-to-predict stats
    CONFIDENCE_CAPS = {
        'PTS': 88,
        'REB': 82,
        'AST': 78,  # Hardest to predict — was showing 93% but hitting 38%
        'PRA': 80,
    }

    # Scale factor per stat — normalizes std impact across different stat magnitudes
    CONFIDENCE_STD_SCALE = {
        'PTS': 3.0,
        'REB': 5.0,   # REB std is smaller in absolute terms, scale up
        'AST': 6.0,   # AST std is smallest, scale up most
        'PRA': 2.5,
    }

    def _sample_size_penalty(self):
        """Reduce confidence for models trained on few games.

        Returns a multiplier (0-1) that scales down confidence for small samples.
        Players with <75 games get up to 15% penalty, <100 gets 5%.
        """
        n = getattr(self, 'games_trained_on', 200)
        if n >= 100:
            return 1.0
        elif n >= 75:
            # Linear interpolation: 75 games → 0.95, 100 games → 1.0
            return 0.95 + 0.05 * (n - 75) / 25
        else:
            # Linear interpolation: 30 games → 0.80, 75 games → 0.95
            return max(0.80, 0.80 + 0.15 * (n - 30) / 45)

    def get_confidence(self, df, stat, prediction, features_df=None):
        """Calculate confidence interval using quantile regression when available,
        falling back to historical variance with per-stat calibration.

        Applies a sample-size penalty for players with limited training data."""

        sample_penalty = self._sample_size_penalty()

        # --- Quantile Regression bounds (Improvement #4) ---
        q10_key, q90_key = f'{stat}_q10', f'{stat}_q90'
        if q10_key in self.quantile_models and q90_key in self.quantile_models and features_df is not None:
            try:
                feature_values = []
                for f in self.feature_names:
                    if f in features_df.columns:
                        feature_values.append(features_df[f].values[0])
                    else:
                        feature_values.append(0)
                X = np.array([feature_values])
                X_scaled = self.scalers['features'].transform(X)
                X_pred = X_scaled

                # Apply feature selection to match what the quantile models were trained on
                if self.selected_features and stat in self.selected_features:
                    q_expected = getattr(self.quantile_models[q10_key], 'n_features_in_', None)
                    sel_count = len(self.selected_features[stat])
                    if q_expected is not None and sel_count == q_expected:
                        X_pred = X_scaled[:, self.selected_features[stat]]
                    elif q_expected is not None and q_expected != X_scaled.shape[1]:
                        # Quantile model feature count doesn't match either option — skip to fallback
                        raise ValueError(f"Quantile model expects {q_expected} features, have {X_scaled.shape[1]} (selected {sel_count})")

                q10 = self.quantile_models[q10_key].predict(X_pred)[0]
                q90 = self.quantile_models[q90_key].predict(X_pred)[0]
                quantile_std = (q90 - q10) / 2.56  # Convert 80% interval to approx std

                scale = self.CONFIDENCE_STD_SCALE.get(stat, 3.0)
                cap = self.CONFIDENCE_CAPS.get(stat, 85)
                raw_confidence = 100 - quantile_std * scale
                confidence = min(cap, max(55, raw_confidence))
                confidence = confidence * sample_penalty  # Apply sample-size discount

                return {
                    'low': round(q10, 1),
                    'high': round(q90, 1),
                    'confidence': round(confidence, 0),
                    'std': round(quantile_std, 2),
                }
            except Exception:
                pass  # Fall through to historical variance fallback

        # Fallback: historical variance
        if stat in df.columns:
            std = df[stat].std()
            recent_std = df[stat].tail(10).std()
            combined_std = 0.4 * std + 0.6 * recent_std

            scale = self.CONFIDENCE_STD_SCALE.get(stat, 3.0)
            cap = self.CONFIDENCE_CAPS.get(stat, 85)
            raw_confidence = 100 - combined_std * scale
            confidence = min(cap, max(55, raw_confidence))
            confidence = confidence * sample_penalty  # Apply sample-size discount

            return {
                'low': round(prediction - 1.5 * combined_std, 1),
                'high': round(prediction + 1.5 * combined_std, 1),
                'confidence': round(confidence, 0),
                'std': round(combined_std, 2),
            }
        return {'low': prediction * 0.8, 'high': prediction * 1.2, 'confidence': 65, 'std': 5.0}

    def update_performance_feedback(self, predicted, actual, stat, date=None):
        """Record a prediction result for rolling performance tracking (Improvement #9)."""
        self.performance_history.append({
            'predicted': predicted,
            'actual': actual,
            'stat': stat,
            'date': date or datetime.now().isoformat(),
        })
        # Keep last 100 entries
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]

    def get_rolling_bias(self, stat, window=20):
        """Get rolling prediction bias for a stat (positive = over-predicting)."""
        relevant = [h for h in self.performance_history if h['stat'] == stat]
        if len(relevant) < 5:
            return 0.0
        recent = relevant[-window:]
        bias = np.mean([h['predicted'] - h['actual'] for h in recent])
        return bias

    def get_rolling_mae(self, stat, window=20):
        """Get rolling MAE for a stat."""
        relevant = [h for h in self.performance_history if h['stat'] == stat]
        if len(relevant) < 5:
            return None
        recent = relevant[-window:]
        return np.mean([abs(h['predicted'] - h['actual']) for h in recent])

    def save(self, player_name):
        """Save model to disk"""
        filename = MODEL_DIR / f"{player_name.replace(' ', '_')}_model.pkl"
        data = {
            'models': self.models if self.model_type != 'neural' else None,
            'ensemble_models': self.ensemble_models if self.use_ensemble else None,
            'scalers': self.scalers,
            'feature_names': self.feature_names,
            'model_type': self.model_type,
            'use_ensemble': self.use_ensemble,
            'training_history': self.training_history,
            'feature_importance': self.feature_importance,
            'recent_averages': getattr(self, 'recent_averages', {}),
            'last_game_date': getattr(self, 'last_game_date', None),
            'trained_at': datetime.now().strftime('%Y-%m-%d'),
            'games_trained_on': getattr(self, 'games_trained_on', 0),
            'version': '3.0',  # Version tracking for compatibility
            # New v3.0 artifacts
            'selected_features': getattr(self, 'selected_features', None),
            'quantile_models': getattr(self, 'quantile_models', {}),
            'residual_models': getattr(self, 'residual_models', {}),
            'probability_calibrator': getattr(self, 'probability_calibrator', {}),
            'optimized_params': getattr(self, 'optimized_params', {}),
            'performance_history': getattr(self, 'performance_history', []),
        }

        if self.model_type == 'neural' and TF_AVAILABLE:
            # Save neural networks separately
            for stat, model in self.models.items():
                model.save(MODEL_DIR / f"{player_name.replace(' ', '_')}_{stat}_nn")

        with open(filename, 'wb') as f:
            pickle.dump(data, f)

        # Update in-memory cache so the next load() skips disk I/O
        _model_cache_put(player_name, data)

        # L3: upload to Supabase Storage
        model_storage.upload_player_model(player_name, filename)

        print(f"💾 Model saved to {filename}")

    def _restore_from_dict(self, data: dict, player_name: str) -> bool:
        """Restore model state from a data dict (shared by load and cache hit)."""
        self.scalers = data['scalers']
        self.feature_names = data['feature_names']
        self.model_type = data['model_type']
        self.use_ensemble = data.get('use_ensemble', False)
        self.training_history = data.get('training_history', [])
        self.feature_importance = data.get('feature_importance', {})
        self.recent_averages = data.get('recent_averages', {})
        self.last_game_date = data.get('last_game_date', None)
        self.trained_at = data.get('trained_at', None)
        self.games_trained_on = data.get('games_trained_on', 0)

        # Load v3.0 artifacts (backward compatible)
        self.selected_features = data.get('selected_features', None)
        self.quantile_models = data.get('quantile_models', {})
        self.residual_models = data.get('residual_models', {})
        self.probability_calibrator = data.get('probability_calibrator', {})
        self.optimized_params = data.get('optimized_params', {})
        self.performance_history = data.get('performance_history', [])

        if data['models']:
            self.models = data['models']
        elif self.model_type == 'neural' and TF_AVAILABLE:
            for stat in ['PTS', 'REB', 'AST', 'PRA']:
                nn_path = MODEL_DIR / f"{player_name.replace(' ', '_')}_{stat}_nn"
                if nn_path.exists():
                    self.models[stat] = keras.models.load_model(nn_path)

        if data.get('ensemble_models'):
            self.ensemble_models = data['ensemble_models']

        # Check version compatibility
        version = data.get('version', '1.0')
        if version not in ['2.0', '2.1', '3.0']:
            print(f"  ⚠️ Model version {version} - consider retraining with --retrain for improved accuracy")

        return True

    def load(self, player_name):
        """Load model from L1 memory -> L2 disk -> L3 Supabase Storage."""
        # L1: in-memory cache (avoids pickle I/O)
        cached = _model_cache_get(player_name)
        if cached is not None:
            self._restore_from_dict(cached, player_name)
            print(f"⚡ Loaded model from memory cache")
            return True

        # L2: disk
        filename = MODEL_DIR / f"{player_name.replace(' ', '_')}_model.pkl"
        if filename.exists():
            try:
                with open(filename, 'rb') as f:
                    data = pickle.load(f)

                self._restore_from_dict(data, player_name)

                # Promote to L1 cache
                _model_cache_put(player_name, data)
                print(f"📂 Loaded model from {filename}")
                return True
            except Exception as e:
                print(f"⚠️ Error loading model from disk: {e}")

        # L3: Supabase Storage -> download to L2, then load
        if model_storage.download_player_model(player_name, filename):
            try:
                with open(filename, 'rb') as f:
                    data = pickle.load(f)

                self._restore_from_dict(data, player_name)
                _model_cache_put(player_name, data)
                print(f"☁️ Loaded model from Supabase Storage")
                return True
            except Exception as e:
                print(f"⚠️ Error loading model after Supabase download: {e}")

        return False


class ProbabilityCalculator:
    """Unified probability calculation used by both LineEvaluator and EnhancedMLPredictor (Improvement #3)."""

    @staticmethod
    def calculate(prediction, line, std, calibrator_data=None):
        """Calculate calibrated probability of going OVER the line.

        Args:
            prediction: Model's point prediction
            line: The betting line
            std: Standard deviation / uncertainty estimate
            calibrator_data: Optional dict with 'calibrator' (IsotonicRegression) and 'std_estimate'
        Returns:
            Probability of going over (0-100)
        """
        z = (line - prediction) / (std + 0.1)
        raw_prob_over = 1 - scipy_stats.norm.cdf(z)

        if calibrator_data and 'calibrator' in calibrator_data:
            try:
                calibrated = calibrator_data['calibrator'].predict([raw_prob_over])[0]
                return round(calibrated * 100, 1)
            except Exception:
                pass

        return round(raw_prob_over * 100, 1)


class LineEvaluator:
    """Evaluates betting lines against predictions"""

    def __init__(self):
        self.history = []

    def evaluate(self, prediction, line, stat, confidence_info=None, predictor=None):
        """Evaluate a betting line against prediction with unified probability calculation."""
        diff = prediction - line
        diff_pct = (diff / line) * 100

        # Determine recommendation
        if abs(diff_pct) < 3:
            recommendation = "LEAN OVER" if diff > 0 else "LEAN UNDER"
            strength = "SLIGHT"
        elif abs(diff_pct) < 8:
            recommendation = "OVER" if diff > 0 else "UNDER"
            strength = "MODERATE"
        else:
            recommendation = "STRONG OVER" if diff > 0 else "STRONG UNDER"
            strength = "HIGH"

        result = {
            'stat': stat,
            'line': line,
            'prediction': prediction,
            'difference': diff,
            'diff_pct': diff_pct,
            'recommendation': recommendation,
            'strength': strength,
            'high_edge_warning': abs(diff_pct) > 50,  # picks >50% edge hit <27% historically
        }

        if confidence_info:
            result['confidence'] = confidence_info['confidence']
            result['range_low'] = confidence_info['low']
            result['range_high'] = confidence_info['high']

            # --- Unified Probability (Improvement #3) ---
            std = confidence_info.get('std', None)
            if std is not None:
                calibrator_data = None
                if predictor and hasattr(predictor, 'probability_calibrator') and stat in predictor.probability_calibrator:
                    calibrator_data = predictor.probability_calibrator[stat]
                result['prob_over'] = ProbabilityCalculator.calculate(
                    prediction, line, std, calibrator_data
                )
            elif confidence_info['high'] != confidence_info['low']:
                # Fallback: position-based for legacy models without std
                range_size = confidence_info['high'] - confidence_info['low']
                position = (line - confidence_info['low']) / range_size
                prob_over = max(0, min(100, (1 - position) * 100))
                result['prob_over'] = prob_over
            else:
                # high == low: no spread info, default to coin flip
                result['prob_over'] = 50.0

        return result
    
    def log_prediction(self, player_name, evaluation, actual=None):
        """Log prediction for tracking accuracy"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'player': player_name,
            **evaluation
        }
        if actual is not None:
            entry['actual'] = actual
            entry['hit'] = (actual > evaluation['line']) == ('OVER' in evaluation['recommendation'])
        
        self.history.append(entry)
        
        # Save to file
        history_file = HISTORY_DIR / "predictions.json"
        try:
            if history_file.exists():
                with open(history_file, 'r') as f:
                    all_history = json.load(f)
            else:
                all_history = []
            all_history.append(entry)
            with open(history_file, 'w') as f:
                json.dump(all_history, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save prediction history: {e}")


def print_banner():
    """Print application banner"""
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                    🏀 NBA LINE EVALUATOR 🏀                       ║
║              ML-Powered Player Prop Analysis                      ║
╚═══════════════════════════════════════════════════════════════════╝
    """)


def print_results(player_name, game_info, predictions, evaluations, vs_stats=None,
                  feature_importance=None, uncertainty=None, team_stats=None, recent_averages=None):
    """Print formatted results"""
    print("\n" + "=" * 65)
    print(f"  📊 ANALYSIS: {player_name.upper()}")
    print("=" * 65)

    if game_info:
        print(f"  🎮 Matchup: {game_info.get('matchup', 'N/A')}")
        print(f"  📍 Location: {'HOME' if game_info.get('is_home') else 'AWAY'}")
        opp = game_info.get('opponent', '')
        opp_name = game_info.get('opponent_name', 'N/A')
        print(f"  🆚 Opponent: {opp_name}")

        # Show opponent defensive context if available
        if team_stats and opp in team_stats:
            opp_stats = team_stats[opp]
            def_rating = opp_stats.get('def_rating', 110)
            pace = opp_stats.get('pace', 100)
            def_rank = "Elite" if def_rating < 108 else "Good" if def_rating < 112 else "Average" if def_rating < 116 else "Poor"
            pace_desc = "Fast" if pace > 102 else "Slow" if pace < 98 else "Average"
            print(f"  🛡️ Opponent Defense: {def_rank} ({def_rating:.1f} DEF RTG)")
            print(f"  ⚡ Opponent Pace: {pace_desc} ({pace:.1f})")

    # Show recent averages (last 10 games)
    if recent_averages:
        pts_avg = recent_averages.get('PTS', 0)
        reb_avg = recent_averages.get('REB', 0)
        ast_avg = recent_averages.get('AST', 0)
        print(f"\n  📊 Last 10 Games Avg: {pts_avg:.1f} PTS | {reb_avg:.1f} REB | {ast_avg:.1f} AST")

    if vs_stats:
        print(f"\n  📈 vs {game_info.get('opponent', 'OPP')} History ({vs_stats['games']} games):")
        print(f"      Avg: {vs_stats['avg_pts']:.1f} PTS | {vs_stats['avg_reb']:.1f} REB | {vs_stats['avg_ast']:.1f} AST")

    print("\n" + "-" * 65)
    print("  🤖 ML PREDICTIONS:")
    print("-" * 65)

    for stat, pred in predictions.items():
        uncertainty_str = ""
        if uncertainty and stat in uncertainty:
            u = uncertainty[stat]
            uncertainty_str = f" (±{u['std']:.1f})"
        # Show comparison to recent average
        recent_str = ""
        if recent_averages and stat in recent_averages:
            diff = pred - recent_averages[stat]
            recent_str = f" [L10 avg: {recent_averages[stat]:.1f}]"
        print(f"      {stat}: {pred:.1f}{uncertainty_str}{recent_str}")

    if evaluations:
        print("\n" + "-" * 65)
        print("  📋 LINE EVALUATIONS:")
        print("-" * 65)

        for eval_result in evaluations:
            stat = eval_result['stat']
            icon = "🟢" if "OVER" in eval_result['recommendation'] else "🔴"

            print(f"\n  {icon} {stat} Line: {eval_result['line']}")
            print(f"      Prediction: {eval_result['prediction']:.1f} ({eval_result['diff_pct']:+.1f}%)")
            print(f"      ➤ {eval_result['recommendation']} ({eval_result['strength']} confidence)")

            if 'prob_over' in eval_result:
                prob = eval_result['prob_over']
                bar_filled = int(prob / 5)
                bar_empty = 20 - bar_filled
                bar = "█" * bar_filled + "░" * bar_empty
                print(f"      Prob Over: [{bar}] {prob:.0f}%")
            if 'range_low' in eval_result:
                print(f"      Range: {eval_result['range_low']:.1f} - {eval_result['range_high']:.1f}")

    # Show feature importance if available
    if feature_importance:
        print("\n" + "-" * 65)
        print("  🔬 KEY FACTORS (Feature Importance):")
        print("-" * 65)
        for stat, importance in feature_importance.items():
            if importance:
                print(f"\n      {stat}:")
                for feat, imp in importance[:5]:  # Top 5
                    bar_len = int(imp * 50)
                    bar = "▓" * bar_len
                    print(f"        {feat:<25} {bar} {imp:.1%}")

    print("\n" + "=" * 65)


def find_best_bets(min_edge=5.0, max_edge=55.0, max_results=20, select_games=False):
    """
    Analyze all today's player props and find the best betting opportunities.

    Args:
        min_edge: Minimum edge percentage to include (default 5%)
        max_edge: Maximum edge percentage to include (default 55%) - filters out unreliable extreme predictions.
                  Reduced from 50% to exclude 60%+ edge picks which historically hit only 45.8%.
        max_results: Maximum number of results to show (default 20)
        select_games: If True, prompt user to select specific games to analyze

    Returns:
        List of best bets sorted by edge
    """
    print("=" * 65)
    print("🎯 NBA BEST BETS FINDER")
    print("=" * 65)

    # Initialize components
    odds_api = OddsAPI()
    scraper = NBADataScraper()
    evaluator = LineEvaluator()

    # Check API status
    api_status = odds_api.check_remaining_requests()
    if api_status and api_status.get('remaining'):
        print(f"📊 API Requests: {api_status['remaining']} remaining this month")

    # Game selection mode
    if select_games:
        events = odds_api.get_todays_events()
        if not events:
            print("\n❌ No games found for today.")
            return []

        # Display games for selection
        print(f"\n📅 Today's Games ({len(events)} total):")
        print("-" * 50)
        for i, event in enumerate(events, 1):
            home_team = event['home_team']
            away_team = event['away_team']
            game_time = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
            game_time_local = game_time.astimezone(ZoneInfo('US/Eastern'))
            time_str = game_time_local.strftime('%I:%M %p ET')
            print(f"  {i}. {away_team} @ {home_team} ({time_str})")

        print("-" * 50)
        print("\n🎮 Select games to analyze:")
        print("   Enter numbers separated by commas (e.g., 1,3,5)")
        print("   Or 'all' for all games, 'q' to quit")

        selection = input(">>> ").strip().lower()

        if selection in ['q', 'quit', 'exit']:
            print("👋 Goodbye!")
            return []

        if selection == 'all' or selection == '':
            selected_events = events
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                selected_events = [events[i] for i in indices if 0 <= i < len(events)]
                if not selected_events:
                    print("❌ No valid games selected.")
                    return []
            except (ValueError, IndexError):
                print("❌ Invalid selection. Please enter numbers like: 1,2,3")
                return []

        # Get props only for selected games
        selected_teams = set()
        for event in selected_events:
            selected_teams.add(event['home_team'])
            selected_teams.add(event['away_team'])

        print(f"\n🔍 Analyzing {len(selected_events)} selected game(s)...")
        all_props = odds_api.get_all_todays_props()
        # Filter to only selected games
        all_props = [p for p in all_props if p['home_team'] in selected_teams or p['away_team'] in selected_teams]
    else:
        # Get all today's props
        all_props = odds_api.get_all_todays_props()

    if not all_props:
        print("\n❌ No player props available for today.")
        print("   This could mean:")
        print("   - No games scheduled today")
        print("   - Props not yet posted (check closer to game time)")
        print("   - API key issue (check ODDS_API_KEY env var)")
        return []

    # Pre-fetch team stats
    print("\n🔄 Loading team statistics...")
    team_stats = scraper.get_team_defensive_stats()
    injuries = scraper.get_injury_report()

    # Analyze each prop
    print(f"\n🔍 Analyzing {len(all_props)} player props...")
    results = []
    processed = 0
    errors = 0

    # Group by player to reduce API calls
    player_info_cache = {}
    game_log_cache = {}

    for prop in all_props:
        player_name = prop['player']
        stat = prop['stat']
        line = prop['consensus_line']

        # Progress indicator
        processed += 1
        if processed % 10 == 0:
            print(f"   Processed {processed}/{len(all_props)} props...")

        try:
            # Get player info (cached after first call)
            if player_name not in player_info_cache:
                player_info = scraper.get_player_info(player_name)
                if not player_info:
                    player_info_cache[player_name] = None
                    continue
                player_info_cache[player_name] = player_info
            else:
                player_info = player_info_cache[player_name]
                if not player_info:
                    continue

            player_id = player_info['player_id']
            team_abbrev = player_info.get('team_abbrev', '')

            # Get game log (cached per player)
            if player_id not in game_log_cache:
                game_log_cache[player_id] = scraper.get_player_game_log(player_id)
            game_log = game_log_cache[player_id]
            if game_log is None or len(game_log) < 10:
                continue

            # Get next game info
            game_info = scraper.get_player_next_game(player_info)
            opponent = game_info.get('opponent', '') if game_info else ''
            is_home = game_info.get('is_home', 0) if game_info else 0

            # Feature engineering
            df = FeatureEngineer.create_features(game_log, player_info, game_info, injuries, team_stats)

            # Get opponent stats
            opp_ctx = FeatureEngineer.extract_opp_stats(team_stats, opponent)

            # Calculate days rest
            last_game = pd.to_datetime(df['GAME_DATE'].iloc[-1])
            days_rest = min((datetime.now() - last_game).days, 7)

            # Get injury counts
            injuries_team = injuries.get(team_abbrev, {}).get('out', 0)
            injuries_opp = injuries.get(opponent, {}).get('out', 0)

            # Get head-to-head stats
            vs_stats = scraper.get_vs_team_stats(player_id, opponent) if opponent else None

            # Generate features for prediction
            features_df = FeatureEngineer.get_prediction_features(
                df, is_home, opponent,
                injuries_team=injuries_team, injuries_opp=injuries_opp,
                days_rest=days_rest, vs_stats=vs_stats,
                **opp_ctx,
            )

            # Load or train model
            predictor = MLPredictor(model_type='gradient_boost')
            model_path = Path('models') / f"{player_name.replace(' ', '_').lower()}_model.pkl"

            if predictor.load(player_name):
                predictor.update(df, stats=[stat])
            else:
                # Quick train if no model exists
                predictor.train(df, stats=[stat])

            # Make prediction with minutes estimation
            if stat not in predictor.models:
                continue

            estimated_minutes = FeatureEngineer.estimate_minutes(
                df, is_home, days_rest, injuries_team
            )
            all_predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)
            all_predictions = predictor.apply_injury_boost(all_predictions, injuries_team, injuries_opp)
            if not all_predictions or stat not in all_predictions:
                continue
            prediction = all_predictions[stat]

            # Calculate edge
            edge_pct = ((prediction - line) / line) * 100
            direction = "OVER" if prediction > line else "UNDER"
            abs_edge = abs(edge_pct)

            # Get confidence info
            confidence_info = predictor.get_confidence(df, stat, prediction, features_df=features_df)

            # Only include if edge is within threshold range
            if abs_edge >= min_edge and abs_edge <= max_edge:
                results.append({
                    'player': player_name,
                    'stat': stat,
                    'line': line,
                    'prediction': round(prediction, 1),
                    'edge': round(edge_pct, 1),
                    'abs_edge': round(abs_edge, 1),
                    'direction': direction,
                    'confidence': confidence_info.get('confidence', 70),
                    'opponent': opponent,
                    'is_home': is_home,
                    'recent_avg': round(df[stat].tail(5).mean(), 1) if stat in df.columns else None,
                })

        except Exception as e:
            errors += 1
            continue

    # Sort by absolute edge (highest first)
    results.sort(key=lambda x: x['abs_edge'], reverse=True)
    results = results[:max_results]

    # Display results
    print("\n" + "=" * 65)
    print(f"🏆 TOP {len(results)} BEST BETS (Edge: {min_edge}%-{max_edge}%)")
    print("=" * 65)

    if not results:
        print("\n❌ No bets found meeting the edge threshold.")
        print(f"   Try lowering --min-edge below {min_edge}% or raising --max-edge above {max_edge}%")
        return []

    for i, bet in enumerate(results, 1):
        home_away = "🏠" if bet['is_home'] else "✈️"
        direction_color = "🟢" if bet['direction'] == "OVER" else "🔴"

        print(f"\n{i}. {bet['player']} - {bet['stat']}")
        print(f"   {direction_color} {bet['direction']} {bet['line']} {home_away} vs {bet['opponent']}")
        print(f"   📈 Prediction: {bet['prediction']} | Edge: {bet['edge']:+.1f}%")
        print(f"   📊 Recent Avg: {bet['recent_avg']} | Confidence: {bet['confidence']:.0f}%")

    print("\n" + "=" * 65)
    print(f"✅ Found {len(results)} opportunities with {min_edge}%-{max_edge}% edge")
    if errors > 0:
        print(f"⚠️  Skipped {errors} props due to data issues")

    # Show API usage
    api_status = odds_api.check_remaining_requests()
    if api_status and api_status.get('remaining'):
        print(f"📊 API Requests remaining: {api_status['remaining']}")

    print("=" * 65)

    return results


def track_picks_interactive(results, model_type='random_forest'):
    """
    Interactive mode to select and track picks from best bets results.

    Args:
        results: List of bet dictionaries from find_best_bets
        model_type: Model type to record with the picks
    """
    import db

    if not results:
        print("❌ No results to track.")
        return

    print("\n" + "=" * 65)
    print("📝 TRACK PICKS")
    print("=" * 65)
    print("Enter pick numbers to track (e.g., 1,3,5), 'all', or 'q' to quit:")

    selection = input(">>> ").strip().lower()

    if selection in ['q', 'quit', 'exit']:
        return

    if selection == 'all':
        indices = list(range(len(results)))
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
            indices = [i for i in indices if 0 <= i < len(results)]
        except ValueError:
            print("❌ Invalid selection.")
            return

    if not indices:
        print("❌ No valid picks selected.")
        return

    tracked = 0
    for i in indices:
        bet = results[i]
        pick_data = {
            'player': bet['player'],
            'stat': bet['stat'],
            'line': bet['line'],
            'prediction': bet['prediction'],
            'direction': bet['direction'],
            'edge': bet['edge'],
            'confidence': bet['confidence'],
            'opponent': bet['opponent'],
            'is_home': bet['is_home'],
            'model_type': model_type,
            'game_date': datetime.now().strftime('%Y-%m-%d'),
            'player_id': bet.get('player_id'),
            'team_abbrev': bet.get('team_abbrev')
        }
        db.save_pick(pick_data)
        tracked += 1
        print(f"  ✅ Tracked: {bet['player']} {bet['stat']} {bet['direction']} {bet['line']}")

    print(f"\n🎯 Tracked {tracked} pick(s)!")


def show_history(days=30):
    """Show pick history in terminal."""
    import db

    print("\n" + "=" * 65)
    print(f"📜 PICK HISTORY (Last {days} days)")
    print("=" * 65)

    picks = db.get_picks_history(days)

    if not picks:
        print("\n❌ No picks found. Track some picks first!")
        return

    # Group by result (exclude voided picks from pending)
    pending = [p for p in picks if p['won'] is None and not p.get('voided')]
    wins = [p for p in picks if p['won'] == 1]
    losses = [p for p in picks if p['won'] == 0]
    voided = [p for p in picks if p.get('voided')]

    print(f"\n📊 Summary: {len(wins)}W - {len(losses)}L ({len(pending)} pending, {len(voided)} voided)")

    # Auto-void stale picks before display
    stale_voided = db.auto_void_stale_picks(days_threshold=3)
    if stale_voided > 0:
        print(f"\n🧹 Auto-voided {stale_voided} stale pick(s) (3+ days old, likely DNP)")
        # Re-fetch after voiding
        picks = db.get_picks_history(days)
        pending = [p for p in picks if p['won'] is None and not p.get('voided')]
        wins = [p for p in picks if p['won'] == 1]
        losses = [p for p in picks if p['won'] == 0]
        voided = [p for p in picks if p.get('voided')]
        print(f"📊 Updated: {len(wins)}W - {len(losses)}L ({len(pending)} pending, {len(voided)} voided)")

    # Show pending picks (ALL of them with edge info)
    if pending:
        print(f"\n⏳ PENDING PICKS ({len(pending)}):")
        print("-" * 65)
        # Sort by absolute edge descending
        pending_sorted = sorted(pending, key=lambda x: abs(x.get('edge', 0)), reverse=True)
        stale_count = 0
        for p in pending_sorted:
            model = (p.get('model_type') or 'unknown').replace('_', ' ').title()[:12]
            direction_icon = "🟢" if "OVER" in p['direction'].upper() else "🔴"
            edge = p.get('edge', 0)
            edge_str = f"{edge:+.1f}%" if edge else "N/A"
            game_date = p.get('game_date', '')[:10] if p.get('game_date') else ''
            print(f"   {direction_icon} {p['player']:<20} {p['stat']:<4} {p['direction']:<5} {p['line']:<6} | Edge: {edge_str:<8} | Pred: {p['prediction']:.1f} | vs {p.get('opponent', 'N/A'):<4} | {game_date}")
            # Check if stale
            if game_date:
                try:
                    pd_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                    if (datetime.now().date() - pd_date).days >= 2:
                        stale_count += 1
                except ValueError:
                    pass
        print("-" * 65)
        if stale_count > 0:
            print(f"   ⚠️ {stale_count} pick(s) are 2+ days old and likely DNP - run --grade to resolve")

    # Show recent results
    graded = [p for p in picks if p['won'] is not None]
    if graded:
        print(f"\n📋 GRADED RESULTS ({len(graded)}):")
        print("-" * 65)
        for p in graded[:20]:  # Show max 20
            emoji = "✅" if p['won'] == 1 else "❌"
            actual = p.get('actual_result', '?')
            if actual != '?':
                actual = f"{actual:.0f}"
            model = (p.get('model_type') or 'unknown').replace('_', ' ').title()[:12]
            edge = p.get('edge', 0)
            edge_str = f"{edge:+.1f}%" if edge else "N/A"
            print(f"   {emoji} {p['player']:<20} {p['stat']:<4} {p['direction']:<5} {p['line']:<6} | Edge: {edge_str:<8} | Pred: {p['prediction']:.1f} | Actual: {actual}")
        if len(graded) > 20:
            print(f"   ... and {len(graded) - 20} more")
        print("-" * 65)

    # Export to Excel
    print("\n📊 Updating Excel tracker...")
    excel_path = db.export_to_excel()
    if excel_path:
        print(f"   ✅ Saved to: {excel_path}")

    print("=" * 65)


def check_games_in_progress():
    """Check if any NBA games are currently in progress via BallDontLie API."""
    try:
        scraper = NBADataScraper()
        games = scraper.get_todays_games()

        if games is None or games.empty:
            return {'in_progress': False, 'games': []}

        # GAME_STATUS_ID: 1=scheduled, 2=in progress, 3=final
        in_progress = games[games['GAME_STATUS_ID'] == 2]
        scheduled = games[games['GAME_STATUS_ID'] == 1]

        in_progress_list = []
        for _, game in in_progress.iterrows():
            in_progress_list.append({
                'home': game.get('HOME_TEAM_ID'),
                'away': game.get('VISITOR_TEAM_ID'),
                'status': 'In Progress'
            })

        return {
            'in_progress': len(in_progress) > 0,
            'in_progress_count': len(in_progress),
            'scheduled_count': len(scheduled),
            'final_count': len(games) - len(in_progress) - len(scheduled),
            'games': in_progress_list
        }
    except Exception as e:
        return {'in_progress': False, 'error': str(e), 'games': []}


def auto_grade_cli():
    """Auto-grade pending picks via CLI."""
    import db

    print("\n" + "=" * 65)
    print("🔄 AUTO-GRADING PICKS")
    print("=" * 65)

    pending = db.get_pending_picks()
    if not pending:
        print("\n✅ No pending picks to grade!")
        return

    # Check if games are still in progress
    print("\n🏀 Checking game status...")
    game_status = check_games_in_progress()

    if game_status.get('in_progress'):
        print(f"\n⚠️  WARNING: {game_status['in_progress_count']} game(s) still IN PROGRESS!")
        print(f"   📊 Today's games: {game_status.get('final_count', 0)} final, {game_status['in_progress_count']} in progress, {game_status.get('scheduled_count', 0)} scheduled")
        print("\n   Grading now may result in incorrect stats from incomplete games.")
        print("   It's recommended to wait until all games are final.\n")

        try:
            choice = input("   Continue anyway? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return

        if choice != 'y':
            print("\n   Cancelled. Run again after games finish.")
            print("=" * 65)
            return
        print()
    else:
        final_count = game_status.get('final_count', 0)
        scheduled_count = game_status.get('scheduled_count', 0)
        if final_count > 0 or scheduled_count > 0:
            print(f"   ✅ No games in progress. ({final_count} final, {scheduled_count} scheduled)")
        else:
            print("   ✅ No games found for today.")

    print(f"\n📋 Found {len(pending)} pending pick(s). Fetching results...")

    result = db.auto_grade_picks()

    # Show stale auto-voided picks
    stale_voided = result.get('stale_voided', 0)
    if stale_voided > 0:
        print(f"\n🧹 Auto-voided {stale_voided} stale pick(s) (3+ days old, likely DNP)")

    # Show voided DNP picks
    voided_count = result.get('voided_count', 0)
    if voided_count > 0:
        print(f"\n🚫 Voided {voided_count} DNP pick(s):\n")
        for r in result['results']:
            if r.get('voided'):
                model = (r.get('model_type') or 'unknown').replace('_', ' ').title()
                print(f"   ⛔ {r['player']} {r['stat']} {r['direction']} {r['line']} - DNP [{model}]")

    if result['graded_count'] > 0:
        print(f"\n✅ Graded {result['graded_count']} pick(s):\n")
        for r in result['results']:
            if not r.get('voided'):
                emoji = "✅" if r['won'] else "❌"
                model = (r.get('model_type') or 'unknown').replace('_', ' ').title()
                print(f"   {emoji} {r['player']} {r['stat']}: {r['actual']} (Line: {r['line']}) [{model}]")
    elif voided_count == 0 and stale_voided == 0:
        print("\n⚠️ No picks could be graded. Games may not have finished yet.")

    if result['errors']:
        print(f"\n⚠️ Errors ({len(result['errors'])}):")
        for err in result['errors'][:5]:
            print(f"   - {err}")

    # Show remaining pending picks that are >1 day old
    remaining_pending = db.get_pending_picks()
    old_pending = []
    for p in remaining_pending:
        gd = p.get('game_date', '')
        if gd:
            try:
                pick_date = datetime.strptime(gd[:10], '%Y-%m-%d').date()
                days_old = (datetime.now().date() - pick_date).days
                if days_old >= 1:
                    old_pending.append((p, days_old))
            except ValueError:
                pass

    if old_pending:
        print(f"\n⏳ {len(old_pending)} pick(s) still pending (game was 1+ days ago, will retry next grade):")
        for p, days in old_pending[:5]:
            gd_str = p.get('game_date', '')[:10]
            print(f"   {p['player']} {p['stat']} {p['direction']} {p['line']} ({gd_str}, {days}d ago)")
        if len(old_pending) > 5:
            print(f"   ... and {len(old_pending) - 5} more")

    print("=" * 65)


def handle_reset_grades():
    """Interactive mode to reset graded picks back to pending for re-grading."""
    import db

    print("\n" + "=" * 65)
    print("🔄 RESET GRADED PICKS")
    print("=" * 65)

    # Get recently graded picks
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM picks
        WHERE won IS NOT NULL AND (voided IS NULL OR voided = 0)
        ORDER BY graded_at DESC, timestamp DESC
        LIMIT 30
    """)
    graded = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not graded:
        print("\n✅ No graded picks to reset!")
        return

    print(f"\n📋 Recently Graded Picks ({len(graded)}):")
    print("-" * 65)

    for i, p in enumerate(graded, 1):
        result_icon = "✅" if p['won'] == 1 else "❌"
        actual = f"{p['actual_result']:.0f}" if p.get('actual_result') is not None else "?"
        game_date = p.get('game_date', '')[:10] if p.get('game_date') else ''
        print(f"  {i:2}. [ID:{p['id']:3}] {result_icon} {p['player']:<18} {p['stat']:<4} {p['direction']:<5} {p['line']:<6} | Actual: {actual:<4} | {game_date}")

    print("-" * 65)
    print("\nOptions:")
    print("  - Enter pick numbers to reset (e.g., 1,3,5)")
    print("  - Enter 'date YYYY-MM-DD' to reset all picks for a date")
    print("  - Enter 'all' to reset all shown picks")
    print("  - Press Enter to cancel")

    try:
        choice = input("\n>>> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    if not choice:
        print("Cancelled.")
        return

    if choice.startswith('date '):
        date_str = choice[5:].strip()
        count = db.reset_all_graded_for_date(date_str)
        print(f"\n✅ Reset {count} pick(s) for {date_str} back to pending")
    elif choice == 'all':
        for p in graded:
            db.reset_pick_to_pending(p['id'])
        print(f"\n✅ Reset {len(graded)} pick(s) back to pending")
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            indices = [i for i in indices if 0 <= i < len(graded)]
        except ValueError:
            print("❌ Invalid input.")
            return

        if not indices:
            print("No valid picks selected.")
            return

        for i in indices:
            pick = graded[i]
            db.reset_pick_to_pending(pick['id'])
            print(f"  ✅ Reset: {pick['player']} {pick['stat']} {pick['direction']} {pick['line']}")

        print(f"\n✅ Reset {len(indices)} pick(s) back to pending")

    print("\nRun --grade again after games are final to re-grade.")
    print("=" * 65)


def handle_dnp_picks():
    """Interactive mode to void DNP (Did Not Play) picks."""
    import db

    print("\n" + "=" * 65)
    print("🚫 VOID DNP PICKS")
    print("=" * 65)

    pending = db.get_pending_picks()

    if not pending:
        print("\n✅ No pending picks to void!")
        return

    print(f"\n📋 Pending Picks ({len(pending)}):")
    print("-" * 65)

    for i, p in enumerate(pending, 1):
        direction_icon = "🟢" if "OVER" in p['direction'].upper() else "🔴"
        edge = p.get('edge', 0)
        edge_str = f"{edge:+.1f}%" if edge else "N/A"
        game_date = p.get('game_date', '')[:10] if p.get('game_date') else ''
        print(f"  {i:2}. [ID:{p['id']:3}] {p['player']:<20} {p['stat']:<4} {direction_icon} {p['direction']:<5} {p['line']:<6} | {game_date} vs {p.get('opponent', 'N/A')}")

    print("-" * 65)
    print("\nEnter pick numbers to void (e.g., 1,3,5), 'all' for all, or press Enter to cancel:")

    try:
        choice = input(">>> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    if not choice:
        print("Cancelled.")
        return

    if choice == 'all':
        indices = list(range(len(pending)))
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            indices = [i for i in indices if 0 <= i < len(pending)]
        except ValueError:
            print("❌ Invalid input.")
            return

    if not indices:
        print("No valid picks selected.")
        return

    # Ask for reason
    print("\nVoid reason? (1=DNP, 2=Injury, 3=Postponed, 4=Other, Enter=DNP)")
    try:
        reason_choice = input(">>> ").strip()
    except (EOFError, KeyboardInterrupt):
        reason_choice = ""

    reasons = {'1': 'DNP', '2': 'Injury', '3': 'Postponed', '4': 'Other', '': 'DNP'}
    reason = reasons.get(reason_choice, 'DNP')

    # Void the picks
    voided_count = 0
    for i in indices:
        pick = pending[i]
        db.void_pick(pick['id'], reason=reason)
        print(f"  ✅ Voided: {pick['player']} {pick['stat']} {pick['direction']} {pick['line']} ({reason})")
        voided_count += 1

    print(f"\n🚫 Voided {voided_count} pick(s) - removed from performance calculations")

    # Update Excel
    print("\n📊 Updating Excel tracker...")
    excel_path = db.export_to_excel()
    if excel_path:
        print(f"   ✅ Saved to: {excel_path}")

    print("=" * 65)


def show_performance():
    """Show performance analytics by model in terminal."""
    import db

    print("\n" + "=" * 65)
    print("📈 PERFORMANCE ANALYTICS")
    print("=" * 65)

    # Overall stats
    stats = db.get_performance_stats()

    print(f"\n📊 OVERALL:")
    print(f"   Total Picks: {stats['total_picks']}")
    print(f"   Graded: {stats['graded_picks']}")
    print(f"   Record: {stats['wins']}-{stats['losses']}" + (f"-{stats['pushes']}" if stats['pushes'] > 0 else ""))

    if stats['graded_picks'] > 0:
        print(f"   Win Rate: {stats['win_rate']:.1f}%")
        print(f"   ROI: {stats['roi']:+.1f}%")
        print(f"   Avg Edge (Winners): {stats['avg_edge_winners']:.1f}%")

        # Breakeven indicator
        if stats['win_rate'] >= 52.4:
            print(f"   📈 Above breakeven (52.4%)")
        else:
            print(f"   📉 Below breakeven (52.4%)")

    # Model-specific performance
    model_stats = db.get_performance_by_model()

    if model_stats:
        print(f"\n🤖 BY MODEL:")
        print("-" * 50)
        print(f"   {'Model':<20} {'Record':<10} {'Win%':<8} {'ROI':<10}")
        print("-" * 50)

        for model, data in sorted(model_stats.items(), key=lambda x: x[1]['win_rate'], reverse=True):
            model_name = model.replace('_', ' ').title()[:20]
            record = f"{data['wins']}-{data['losses']}"
            win_rate = f"{data['win_rate']:.1f}%"
            roi = f"{data['roi']:+.1f}%"
            print(f"   {model_name:<20} {record:<10} {win_rate:<8} {roi:<10}")

        print("-" * 50)

    # By stat type
    if stats['by_stat']:
        print(f"\n📊 BY STAT TYPE:")
        print("-" * 40)
        for stat, data in stats['by_stat'].items():
            print(f"   {stat}: {data['wins']}/{data['total']} ({data['win_rate']:.1f}%)")

    # Model + Stat breakdown
    model_stat_data = db.get_performance_by_model_and_stat()

    if model_stat_data and len(model_stat_data) > 0:
        print(f"\n🔬 DETAILED (Model + Stat):")
        for model, stat_data in model_stat_data.items():
            model_name = model.replace('_', ' ').title()
            print(f"\n   {model_name}:")
            for stat, data in stat_data.items():
                print(f"      {stat}: {data['wins']}/{data['total']} ({data['win_rate']:.1f}%)")

    # Export to Excel
    print("\n📊 Exporting to Excel...")
    excel_path = db.export_to_excel()
    if excel_path:
        print(f"   ✅ Saved to: {excel_path}")
    else:
        print("   ⚠️ Could not export to Excel (install openpyxl)")

    print("\n" + "=" * 65)


def interactive_mode():
    """Run in interactive mode"""
    print_banner()

    scraper = NBADataScraper()
    evaluator = LineEvaluator()

    # Pre-fetch team stats for the session
    print("🔄 Loading team statistics...")
    team_stats = scraper.get_team_defensive_stats()
    injuries = scraper.get_injury_report()

    while True:
        print("\n📝 Enter player name (or 'quit' to exit):")
        player_input = input(">>> ").strip()

        if player_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break

        if not player_input:
            continue

        # Get player info
        player_info = scraper.get_player_info(player_input)
        if not player_info:
            print(f"❌ Player '{player_input}' not found. Try again.")
            continue

        player_name = player_info['player_name']
        print(f"✅ Found: {player_name}")

        # Check player injury status
        injury_status = scraper.get_player_injury_status(player_name, injuries)
        if injury_status['is_injured']:
            print(f"  ⚠️ INJURY ALERT: {player_name} is {injury_status['status'].upper()}")

        # Get game info
        game_info = scraper.get_player_next_game(player_info)

        # Get game log and create features with team stats
        game_log = scraper.get_player_game_log(player_info['player_id'])
        if game_log.empty:
            print("❌ No game data available for this player.")
            continue

        # Feature engineering with opponent context
        df = FeatureEngineer.create_features(game_log, player_info=player_info, team_stats=team_stats)

        # Get vs team stats
        vs_stats = None
        if game_info:
            vs_stats = scraper.get_vs_team_stats(
                player_info['player_id'],
                game_info.get('opponent', '')
            )

        # Model selection
        print("\n🤖 Select model type:")
        print("  1. Random Forest (default)")
        print("  2. Gradient Boosting")
        print("  3. Ensemble (RF + GB combined)")
        if TF_AVAILABLE:
            print("  4. Neural Network")

        model_choice = input(">>> ").strip()
        use_ensemble = model_choice == '3'
        model_type = {
            '1': 'random_forest',
            '2': 'gradient_boost',
            '3': 'random_forest',  # Ensemble uses RF as base
            '4': 'neural' if TF_AVAILABLE else 'random_forest'
        }.get(model_choice, 'random_forest')

        # Initialize and train model
        predictor = MLPredictor(model_type=model_type, use_ensemble=use_ensemble)

        # Try to load and update existing model
        if predictor.load(player_name):
            if predictor.last_game_date:
                trained_at_str = f", saved {predictor.trained_at}" if getattr(predictor, 'trained_at', None) else ""
                print(f"📂 Model last game: {predictor.last_game_date}{trained_at_str} ({predictor.games_trained_on} games)")
            if predictor.update(df):
                predictor.save(player_name)
        else:
            print("🆕 No existing model found, training new model...")
            if not predictor.train(df):
                print("❌ Could not train model.")
                continue
            predictor.save(player_name)

        # Get opponent context
        is_home = game_info.get('is_home', 0) if game_info else 0
        opponent = game_info.get('opponent', '') if game_info else ''
        opp_ctx = FeatureEngineer.extract_opp_stats(team_stats, opponent)

        # Get injury counts for teams
        team_abbrev = player_info.get('team_abbrev', '')
        injuries_team = injuries.get(team_abbrev, {}).get('out', 0)
        injuries_opp = injuries.get(opponent, {}).get('out', 0)

        # Calculate days rest before prediction features
        days_rest_val = 2  # default
        if 'GAME_DATE' in df.columns and len(df) > 1:
            last_game = pd.to_datetime(df['GAME_DATE'].iloc[-1])
            days_rest_val = min((datetime.now() - last_game).days, 7)

        # Make predictions with full context
        features_df = FeatureEngineer.get_prediction_features(
            df, is_home, opponent,
            injuries_team=injuries_team,
            injuries_opp=injuries_opp,
            days_rest=days_rest_val,
            vs_stats=vs_stats,
            **opp_ctx,
        )

        estimated_minutes = FeatureEngineer.estimate_minutes(
            df, is_home, days_rest_val, injuries_team
        )
        # Refresh recent_averages from live game log before predicting
        predictor._update_recent_averages(df)
        predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)
        predictions = predictor.apply_injury_boost(predictions, injuries_team, injuries_opp)

        # Get uncertainty estimates
        uncertainty = {}
        for stat in predictions.keys():
            u = predictor.get_prediction_uncertainty(features_df, stat)
            if u:
                uncertainty[stat] = u

        # Get feature importance
        feature_importance = {}
        for stat in predictions.keys():
            fi = predictor.get_feature_importance(stat, top_n=5)
            if fi:
                feature_importance[stat] = fi

        # Get lines to evaluate
        evaluations = []
        trackable_picks = []  # Store picks that can be tracked
        print("\n📊 Enter lines to evaluate (or press Enter to skip):")
        for stat in ['PTS', 'REB', 'AST', 'PRA']:
            if stat in predictions:
                pred_str = f"{predictions[stat]:.1f}"
                line_input = input(f"  {stat} line (prediction: {pred_str}): ").strip()
                if line_input:
                    try:
                        line = float(line_input)
                    except ValueError:
                        print(f"  ⚠️ Invalid number, skipping {stat}")
                        continue
                    try:
                        confidence_info = predictor.get_confidence(df, stat, predictions[stat], features_df=features_df)
                        eval_result = evaluator.evaluate(predictions[stat], line, stat, confidence_info, predictor=predictor)
                        evaluations.append(eval_result)
                        evaluator.log_prediction(player_name, eval_result)

                        # Store for potential tracking
                        if eval_result.get('recommendation') != 'PASS':
                            trackable_picks.append({
                                'player': player_name,
                                'stat': stat,
                                'line': line,
                                'prediction': round(predictions[stat], 1),
                                'direction': 'OVER' if 'OVER' in eval_result.get('recommendation', '') else 'UNDER',
                                'edge': round(eval_result.get('diff_pct', 0), 1),
                                'confidence': confidence_info.get('confidence', 70),
                                'opponent': opponent,
                                'is_home': is_home,
                                'model_type': model_type,
                                'game_date': datetime.now().strftime('%Y-%m-%d'),
                                'player_id': player_info['player_id'],
                                'team_abbrev': team_abbrev
                            })
                    except Exception as e:
                        print(f"  ⚠️ Error evaluating {stat}: {e}")

        # Print results — compute L10 live from current game log (not frozen pkl value)
        live_l10 = {}
        for _s in ['PTS', 'REB', 'AST']:
            if _s in df.columns:
                live_l10[_s] = df[_s].tail(10).mean()
        if all(c in df.columns for c in ['PTS', 'REB', 'AST']):
            live_l10['PRA'] = (df['PTS'] + df['REB'] + df['AST']).tail(10).mean()
        print_results(
            player_name, game_info, predictions, evaluations, vs_stats,
            feature_importance=feature_importance,
            uncertainty=uncertainty,
            team_stats=team_stats,
            recent_averages=live_l10
        )

        print("\n💾 Model auto-saved with latest data.")

        # Offer to track picks
        if trackable_picks:
            print("\n" + "-" * 50)
            print("📝 TRACK PICKS")
            print("-" * 50)
            MAX_EDGE_THRESHOLD = 50.0
            for i, pick in enumerate(trackable_picks, 1):
                direction_emoji = "🟢" if pick['direction'] == "OVER" else "🔴"
                warning = " ⚠️  HIGH EDGE" if abs(pick['edge']) > MAX_EDGE_THRESHOLD else ""
                print(f"  {i}. {pick['stat']} {direction_emoji} {pick['direction']} {pick['line']} (Edge: {pick['edge']:+.1f}%){warning}")

            print("\nTrack these picks? Enter numbers (e.g., 1,2), 'all', or press Enter to skip:")
            track_input = input(">>> ").strip().lower()

            if track_input:
                import db

                if track_input == 'all':
                    indices = list(range(len(trackable_picks)))
                else:
                    try:
                        indices = [int(x.strip()) - 1 for x in track_input.split(',')]
                        indices = [i for i in indices if 0 <= i < len(trackable_picks)]
                    except ValueError:
                        indices = []

                if indices:
                    for i in indices:
                        db.save_pick(trackable_picks[i])
                        pick = trackable_picks[i]
                        print(f"  ✅ Tracked: {pick['stat']} {pick['direction']} {pick['line']}")
                    print(f"\n🎯 Tracked {len(indices)} pick(s)!")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='NBA Line Evaluator - ML-Powered Player Prop Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --player "Nikola Jokic" --stat PTS --line 26.5
  %(prog)s --player "LeBron James" --stat PRA --line 45.5 --model gradient_boost
  %(prog)s --interactive
  %(prog)s --player "Kevin Durant" --ensemble --pts-line 28.5
  %(prog)s --best-bets --min-edge 5
  %(prog)s --best-bets --select-games
  %(prog)s --best-bets --track
  %(prog)s --history
  %(prog)s --grade
  %(prog)s --performance
        """
    )

    # Best bets mode (no API cost for NBA data, uses free Odds API tier)
    parser.add_argument('--best-bets', '-b', action='store_true',
                       help='Find best betting opportunities for today (requires Odds API key)')
    parser.add_argument('--select-games', '-g', action='store_true',
                       help='Select specific games to analyze (use with --best-bets)')
    parser.add_argument('--min-edge', type=float, default=5.0,
                       help='Minimum edge %% to show in best bets (default: 5)')
    parser.add_argument('--max-edge', type=float, default=50.0,
                       help='Maximum edge %% to show in best bets (default: 50) - filters out unreliable extreme predictions')
    parser.add_argument('--max-results', type=int, default=20,
                       help='Maximum results to show in best bets (default: 20)')
    parser.add_argument('--track', '-t', action='store_true',
                       help='Enable tracking mode to save picks (use with --best-bets)')

    # Pick tracking and history
    parser.add_argument('--history', action='store_true',
                       help='Show pick history and results')
    parser.add_argument('--history-days', type=int, default=30,
                       help='Number of days to show in history (default: 30)')
    parser.add_argument('--grade', action='store_true',
                       help='Auto-grade pending picks using NBA API')
    parser.add_argument('--performance', action='store_true',
                       help='Show performance analytics by model')
    parser.add_argument('--dnp', action='store_true',
                       help='Mark picks as DNP (Did Not Play) - removes from performance')
    parser.add_argument('--void', type=int, metavar='PICK_ID',
                       help='Void a specific pick by ID (DNP, postponed, etc.)')
    parser.add_argument('--reset-grades', action='store_true',
                       help='Reset graded picks back to pending (for re-grading)')
    parser.add_argument('--reset-date', type=str, metavar='YYYY-MM-DD',
                       help='Reset all graded picks for a specific date')

    parser.add_argument('--player', '-p', type=str, help='Player name')
    parser.add_argument('--stat', '-s', type=str, choices=['PTS', 'REB', 'AST', 'PRA'],
                       help='Stat to predict')
    parser.add_argument('--line', '-l', type=float, help='Betting line to evaluate')
    parser.add_argument('--model', '-m', type=str, default='gradient_boost',
                       choices=['random_forest', 'gradient_boost', 'neural'],
                       help='ML model type')
    parser.add_argument('--ensemble', '-e', action='store_true',
                       help='Use ensemble of models for better predictions')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Run in interactive mode')
    parser.add_argument('--all-stats', action='store_true',
                       help='Predict all stats')
    parser.add_argument('--pts-line', type=float, help='Points line')
    parser.add_argument('--reb-line', type=float, help='Rebounds line')
    parser.add_argument('--ast-line', type=float, help='Assists line')
    parser.add_argument('--pra-line', type=float, help='PRA (PTS+REB+AST) line')
    parser.add_argument('--retrain', action='store_true',
                       help='Force retrain model from scratch')
    parser.add_argument('--update', '-u', action='store_true',
                       help='Update existing model with new games (default behavior)')
    parser.add_argument('--show-importance', action='store_true',
                       help='Show feature importance in output')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Clear cached data before running')

    args = parser.parse_args()

    # Clear cache if requested
    if args.clear_cache:
        import shutil
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
            CACHE_DIR.mkdir(exist_ok=True)
            print("🗑️ Cache cleared")

    # History mode
    if args.history:
        show_history(days=args.history_days)
        return

    # Auto-grade mode
    if args.grade:
        auto_grade_cli()
        return

    # Performance mode
    if args.performance:
        show_performance()
        return

    # Void specific pick
    if args.void:
        import db
        db.void_pick(args.void, reason="DNP")
        print(f"✅ Pick #{args.void} voided (DNP) - removed from performance calculations")
        return

    # DNP mode - interactive selection to void picks
    if args.dnp:
        handle_dnp_picks()
        return

    # Reset grades for a specific date
    if args.reset_date:
        import db
        count = db.reset_all_graded_for_date(args.reset_date)
        print(f"✅ Reset {count} pick(s) for {args.reset_date} back to pending")
        print("   Run --grade again after games are final to re-grade.")
        return

    # Reset grades interactively
    if args.reset_grades:
        handle_reset_grades()
        return

    # Best bets mode
    if args.best_bets:
        results = find_best_bets(min_edge=args.min_edge, max_edge=args.max_edge, max_results=args.max_results, select_games=args.select_games)
        # If tracking is enabled, prompt to track picks
        if args.track and results:
            track_picks_interactive(results, model_type=args.model)
        return

    if args.interactive or (not args.player):
        interactive_mode()
        return

    print_banner()

    # Initialize components
    scraper = NBADataScraper()
    evaluator = LineEvaluator()

    # Get team stats and injuries
    print("🔄 Loading contextual data...")
    team_stats = scraper.get_team_defensive_stats()
    injuries = scraper.get_injury_report()

    # Get player info
    player_info = scraper.get_player_info(args.player)
    if not player_info:
        print(f"❌ Player '{args.player}' not found.")
        sys.exit(1)

    player_name = player_info['player_name']

    # Check player injury status
    injury_status = scraper.get_player_injury_status(player_name, injuries)
    if injury_status['is_injured']:
        print(f"⚠️ INJURY ALERT: {player_name} is {injury_status['status'].upper()}")

    # Get game info
    game_info = scraper.get_player_next_game(player_info)

    # Get game log
    game_log = scraper.get_player_game_log(player_info['player_id'])
    if game_log.empty:
        print("❌ No game data available.")
        sys.exit(1)

    # Feature engineering with team stats
    df = FeatureEngineer.create_features(game_log, player_info=player_info, team_stats=team_stats)

    # Get vs team stats
    vs_stats = None
    if game_info:
        vs_stats = scraper.get_vs_team_stats(
            player_info['player_id'],
            game_info.get('opponent', '')
        )

    # Initialize model
    model_type = args.model
    if model_type == 'neural' and not TF_AVAILABLE:
        print("⚠️ TensorFlow not available, using Random Forest")
        model_type = 'random_forest'

    predictor = MLPredictor(model_type=model_type, use_ensemble=args.ensemble)

    # Load, update, or train model
    if args.retrain:
        # Force full retrain from scratch
        print("🔄 Retraining model from scratch...")
        if not predictor.train(df):
            print("❌ Could not train model.")
            sys.exit(1)
        predictor.save(player_name)
    elif predictor.load(player_name):
        # Model loaded - update with any new games
        if predictor.last_game_date:
            print(f"📂 Model last updated: {predictor.last_game_date} ({predictor.games_trained_on} games)")
        if predictor.update(df):
            predictor.save(player_name)  # Save the updated model
    else:
        # No existing model - train new one
        print("🆕 No existing model found, training new model...")
        if not predictor.train(df):
            print("❌ Could not train model.")
            sys.exit(1)
        predictor.save(player_name)

    # Get opponent context
    is_home = game_info.get('is_home', 0) if game_info else 0
    opponent = game_info.get('opponent', '') if game_info else ''
    opp_ctx = FeatureEngineer.extract_opp_stats(team_stats, opponent)

    # Get injury counts
    team_abbrev = player_info.get('team_abbrev', '')
    injuries_team = injuries.get(team_abbrev, {}).get('out', 0)
    injuries_opp = injuries.get(opponent, {}).get('out', 0)

    # Calculate days rest before prediction features
    days_rest_cli = 2
    if 'GAME_DATE' in df.columns and len(df) > 1:
        last_game = pd.to_datetime(df['GAME_DATE'].iloc[-1])
        days_rest_cli = min((datetime.now() - last_game).days, 7)

    # Make predictions with full context
    features_df = FeatureEngineer.get_prediction_features(
        df, is_home, opponent,
        injuries_team=injuries_team,
        injuries_opp=injuries_opp,
        days_rest=days_rest_cli,
        vs_stats=vs_stats,
        **opp_ctx,
    )

    estimated_minutes = FeatureEngineer.estimate_minutes(
        df, is_home, days_rest_cli, injuries_team
    )
    predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)
    predictions = predictor.apply_injury_boost(predictions, injuries_team, injuries_opp)

    # Get uncertainty estimates
    uncertainty = {}
    for stat in predictions.keys():
        u = predictor.get_prediction_uncertainty(features_df, stat)
        if u:
            uncertainty[stat] = u

    # Get feature importance if requested
    feature_importance = None
    if args.show_importance:
        feature_importance = {}
        for stat in predictions.keys():
            fi = predictor.get_feature_importance(stat, top_n=5)
            if fi:
                feature_importance[stat] = fi

    # Evaluate lines
    evaluations = []
    lines = {
        'PTS': args.pts_line or (args.line if args.stat == 'PTS' else None),
        'REB': args.reb_line or (args.line if args.stat == 'REB' else None),
        'AST': args.ast_line or (args.line if args.stat == 'AST' else None),
        'PRA': args.pra_line or (args.line if args.stat == 'PRA' else None),
    }

    for stat, line in lines.items():
        if line and stat in predictions:
            confidence_info = predictor.get_confidence(df, stat, predictions[stat], features_df=features_df)
            eval_result = evaluator.evaluate(predictions[stat], line, stat, confidence_info, predictor=predictor)
            evaluations.append(eval_result)
            evaluator.log_prediction(player_name, eval_result)

    # Print results — compute L10 live from current game log (not frozen pkl value)
    live_l10 = {}
    for _s in ['PTS', 'REB', 'AST']:
        if _s in df.columns:
            live_l10[_s] = df[_s].tail(10).mean()
    if all(c in df.columns for c in ['PTS', 'REB', 'AST']):
        live_l10['PRA'] = (df['PTS'] + df['REB'] + df['AST']).tail(10).mean()
    print_results(
        player_name, game_info, predictions, evaluations, vs_stats,
        feature_importance=feature_importance,
        uncertainty=uncertainty,
        team_stats=team_stats,
        recent_averages=live_l10
    )


if __name__ == "__main__":
    main()
