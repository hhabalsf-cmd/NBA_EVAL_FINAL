#!/usr/bin/env python3
"""
NBA Game Winner Predictor V2 - ML-Powered Game Outcome Prediction
==================================================================
Predicts which team will win each NBA game using:
- Elo ratings (self-computed, margin-of-victory adjusted)
- Four Factors of basketball (eFG%, TOV%, OREB%, FT rate)
- Multi-window rolling features with EMA
- Stacking ensemble (XGBoost + LightGBM + RF + HistGB)
- Isotonic probability calibration
- Recency-weighted training
- Travel/timezone effects
- Strength of schedule
"""

import concurrent.futures
import json
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import joblib

from bdl_client import get_bdl_client
from bdl_id_mapper import get_team_mapper, get_player_mapper

from sklearn.preprocessing import RobustScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, log_loss
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.base import clone as sklearn_clone

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except (ImportError, OSError, Exception):
    XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except (ImportError, OSError, Exception):
    LGB_AVAILABLE = False

try:
    from sklearn.ensemble import HistGradientBoostingClassifier
    HISTGB_AVAILABLE = True
except ImportError:
    HISTGB_AVAILABLE = False

# Reuse from existing evaluator
from nba_evaluator import (
    CacheManager,
    NBADataScraper,
    TEAM_ABBREV_TO_NAME,
    TEAM_NAME_TO_ABBREV,
    MODEL_DIR,
    CACHE_DIR,
    _safe_float,
    _safe_int,
)

import model_storage

warnings.filterwarnings("ignore")

# Model path
GAME_MODEL_DIR = MODEL_DIR / "games"
GAME_MODEL_DIR.mkdir(exist_ok=True)

# Team timezone offsets (UTC) for travel effects
TEAM_TIMEZONE = {
    'BOS': -5, 'BKN': -5, 'NYK': -5, 'PHI': -5, 'TOR': -5,
    'CHI': -6, 'CLE': -5, 'DET': -5, 'IND': -5, 'MIL': -6,
    'ATL': -5, 'CHA': -5, 'MIA': -5, 'ORL': -5, 'WAS': -5,
    'DEN': -7, 'MIN': -6, 'OKC': -6, 'POR': -8, 'UTA': -7,
    'GSW': -8, 'LAC': -8, 'LAL': -8, 'PHX': -7, 'SAC': -8,
    'DAL': -6, 'HOU': -6, 'MEM': -6, 'NOP': -6, 'SAS': -6,
}


# ── Elo Rating System ──────────────────────────────────────────

class EloTracker:
    """Dual-track Elo ratings from game results (FiveThirtyEight-style).

    Maintains two parallel rating tracks per team:
    - 'fast' track (K=20): reacts quickly to recent form, best for regular season
    - 'slow' track (K=10): captures longer-term team quality, better for playoffs

    The blended rating uses 70% fast + 30% slow during regular season,
    shifting to 50/50 in playoffs where long-term quality matters more.
    """

    K_FACTOR = 20         # Fast track
    K_FACTOR_SLOW = 10    # Slow track (more stable)
    HOME_ADVANTAGE = 100
    INITIAL_ELO = 1500
    SEASON_REVERSION = 0.75

    def __init__(self):
        self.ratings = {}       # Fast track (default, backwards compatible)
        self.ratings_slow = {}  # Slow track (new)

    def initialize(self, team_list):
        for t in team_list:
            self.ratings[t] = self.INITIAL_ELO
            self.ratings_slow[t] = self.INITIAL_ELO

    def expected_score(self, elo_a, elo_b):
        return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))

    def update(self, home_team, away_team, home_won, margin=None):
        home_elo = self.ratings.get(home_team, self.INITIAL_ELO) + self.HOME_ADVANTAGE
        away_elo = self.ratings.get(away_team, self.INITIAL_ELO)

        expected_home = self.expected_score(home_elo, away_elo)
        actual_home = 1.0 if home_won else 0.0

        # Margin-of-victory multiplier (FiveThirtyEight formula)
        if margin is not None:
            elo_diff = home_elo - away_elo
            mov_mult = np.log(abs(margin) + 1) * (2.2 / (elo_diff * 0.001 + 2.2))
        else:
            mov_mult = 1.0

        # Fast track (K=20)
        k_fast = self.K_FACTOR * mov_mult
        self.ratings[home_team] = self.ratings.get(home_team, self.INITIAL_ELO) + k_fast * (actual_home - expected_home)
        self.ratings[away_team] = self.ratings.get(away_team, self.INITIAL_ELO) + k_fast * (expected_home - actual_home)

        # Slow track (K=10) — captures longer-term quality
        k_slow = self.K_FACTOR_SLOW * mov_mult
        home_elo_slow = self.ratings_slow.get(home_team, self.INITIAL_ELO) + self.HOME_ADVANTAGE
        away_elo_slow = self.ratings_slow.get(away_team, self.INITIAL_ELO)
        expected_slow = self.expected_score(home_elo_slow, away_elo_slow)
        self.ratings_slow[home_team] = self.ratings_slow.get(home_team, self.INITIAL_ELO) + k_slow * (actual_home - expected_slow)
        self.ratings_slow[away_team] = self.ratings_slow.get(away_team, self.INITIAL_ELO) + k_slow * (expected_slow - actual_home)

    def new_season(self):
        """Revert ratings toward mean between seasons."""
        mean_elo = np.mean(list(self.ratings.values())) if self.ratings else self.INITIAL_ELO
        for team in self.ratings:
            self.ratings[team] = self.SEASON_REVERSION * self.ratings[team] + (1 - self.SEASON_REVERSION) * mean_elo
        # Slow track reverts less (more stable across seasons)
        mean_slow = np.mean(list(self.ratings_slow.values())) if self.ratings_slow else self.INITIAL_ELO
        slow_reversion = 0.85  # Carry 85% forward (more stable than fast track)
        for team in self.ratings_slow:
            self.ratings_slow[team] = slow_reversion * self.ratings_slow[team] + (1 - slow_reversion) * mean_slow

    def get_rating(self, team):
        return self.ratings.get(team, self.INITIAL_ELO)

    def get_rating_slow(self, team):
        return self.ratings_slow.get(team, self.INITIAL_ELO)

    def get_blended_rating(self, team, is_playoff=False):
        """Blend fast and slow ratings. Regular season favors fast (recent form),
        playoffs favor slow (long-term quality)."""
        fast = self.get_rating(team)
        slow = self.get_rating_slow(team)
        if is_playoff:
            return 0.5 * fast + 0.5 * slow
        return 0.7 * fast + 0.3 * slow

    def get_diff(self, home_team, away_team):
        return self.get_rating(home_team) - self.get_rating(away_team)

    def get_blended_diff(self, home_team, away_team, is_playoff=False):
        return self.get_blended_rating(home_team, is_playoff) - self.get_blended_rating(away_team, is_playoff)

    def get_expected(self, home_team, away_team):
        home_elo = self.get_rating(home_team) + self.HOME_ADVANTAGE
        away_elo = self.get_rating(away_team)
        return self.expected_score(home_elo, away_elo)

    def compute_from_games(self, games_df):
        """Process a full DataFrame of games chronologically to build ratings."""
        games_df = games_df.copy()
        games_df['GAME_DATE'] = pd.to_datetime(games_df['GAME_DATE'])
        games_df = games_df.sort_values('GAME_DATE')

        current_season = None
        seen_game_ids = set()

        for _, row in games_df.iterrows():
            game_id = row.get('GAME_ID', '')
            if game_id in seen_game_ids:
                continue

            matchup = str(row.get('MATCHUP', ''))
            if 'vs.' not in matchup:
                continue

            seen_game_ids.add(game_id)

            # Find both sides of this game
            game_rows = games_df[games_df['GAME_ID'] == game_id]
            if len(game_rows) != 2:
                continue

            home = game_rows[game_rows['MATCHUP'].str.contains('vs.')]
            away = game_rows[game_rows['MATCHUP'].str.contains('@')]
            if home.empty or away.empty:
                continue

            home = home.iloc[0]
            away = away.iloc[0]

            season = home.get('SEASON', '')
            if current_season and season != current_season:
                self.new_season()
            current_season = season

            home_won = home['WL'] == 'W'
            margin = home.get('PLUS_MINUS', None)
            if pd.isna(margin):
                margin = None

            home_abbrev = home['TEAM_ABBREVIATION']
            away_abbrev = away['TEAM_ABBREVIATION']

            if home_abbrev not in self.ratings:
                self.ratings[home_abbrev] = self.INITIAL_ELO
            if away_abbrev not in self.ratings:
                self.ratings[away_abbrev] = self.INITIAL_ELO

            self.update(home_abbrev, away_abbrev, home_won, margin)

    def copy(self):
        """Return a copy of this tracker."""
        new = EloTracker()
        new.ratings = dict(self.ratings)
        return new


# ── Stacking Model Wrapper ─────────────────────────────────────

class GameStackingModel:
    """Lightweight wrapper that chains base models -> meta-learner."""

    def __init__(self, base_models, meta_learner):
        self.base_models_ = base_models
        self.meta_learner_ = meta_learner

    def predict_proba(self, X):
        base_probas = []
        for _, model in self.base_models_:
            proba = model.predict_proba(X)
            base_probas.append(proba[:, 1])
        meta_X = np.column_stack(base_probas)
        return self.meta_learner_.predict_proba(meta_X)

    def predict(self, X):
        probas = self.predict_proba(X)
        return (probas[:, 1] > 0.5).astype(int)


# ── Main Predictor ─────────────────────────────────────────────

class GamePredictor:
    """ML-powered NBA game winner prediction (V2 — stacking ensemble)."""

    def __init__(self):
        self.scraper = NBADataScraper()
        self.model = None
        self.scaler = RobustScaler()
        self.feature_names = []
        self.selected_feature_idx = None
        self.calibrator = None
        self.elo_tracker = EloTracker()
        self._team_stats_cache = None
        self._team_stats_cache_time: float = 0
        self._team_game_logs_cache: dict = {}
        self._team_game_logs_cache_times: dict = {}
        self._injuries_cache = None
        self._injuries_cache_time: float = 0
        self._top_scorers_cache = None
        self._top_scorers_cache_time: float = 0

        # Cache config
        self._CACHE_TTL = 60 * 60          # 1 hour for all caches
        self._GAME_LOGS_MAX_ENTRIES = 15   # Max team/season combos to keep

        # Build team lookup using BDL team mapper (BDL team IDs)
        team_mapper = get_team_mapper()
        self.team_abbrev_to_id = {}
        self.team_id_to_abbrev = {}
        for abbrev in TEAM_ABBREV_TO_NAME:
            bdl_id = team_mapper.abbrev_to_bdl_id(abbrev)
            if bdl_id is not None:
                self.team_abbrev_to_id[abbrev] = bdl_id
                self.team_id_to_abbrev[bdl_id] = abbrev
        self.team_id_to_name = {}  # Not used for critical logic

    # ── Data Fetching ──────────────────────────────────────────

    def get_todays_games(self):
        """Fetch today's NBA games via BallDontLie API (FREE tier)."""
        cached = CacheManager.get('game_pred', 'todays_games', expiry_type='schedule')
        if cached is not None:
            return cached

        try:
            today_str = datetime.now(ZoneInfo("America/New_York")).date().strftime('%Y-%m-%d')
            bdl = get_bdl_client()
            raw_games = bdl.get_games(dates=[today_str])

            if not raw_games:
                return []

            status_map = {'scheduled': 1, 'in progress': 2, 'final': 3}
            games = []
            seen_games = set()

            for g in raw_games:
                home = g.get('home_team') or {}
                visitor = g.get('visitor_team') or {}
                home_id = home.get('id')
                visitor_id = visitor.get('id')
                home_abbrev = str(home.get('abbreviation') or '').upper()
                visitor_abbrev = str(visitor.get('abbreviation') or '').upper()
                game_id = g.get('id')
                raw_status = str(g.get('status') or 'scheduled').lower().strip()
                status = status_map.get(raw_status, 1)

                if status == 3:  # Final — skip
                    continue

                dedup_key = game_id if game_id else (home_abbrev, visitor_abbrev)
                if dedup_key in seen_games:
                    continue
                seen_games.add(dedup_key)

                game_date_raw = g.get('date') or ''
                game_date = game_date_raw[:10] if game_date_raw else today_str

                games.append({
                    'game_id': game_id,
                    'home_team_id': home_id,
                    'away_team_id': visitor_id,
                    'home_team': home_abbrev,
                    'away_team': visitor_abbrev,
                    'home_team_name': TEAM_ABBREV_TO_NAME.get(home_abbrev, home_abbrev),
                    'away_team_name': TEAM_ABBREV_TO_NAME.get(visitor_abbrev, visitor_abbrev),
                    'game_date': game_date,
                    'game_time': str(g.get('time') or ''),
                    'status': status,
                })

            CacheManager.set('game_pred', games, 'todays_games')
            return games

        except Exception as e:
            print(f"Error fetching today's games: {e}")
            return []

    def get_team_stats(self, season='2025-26'):
        """Get advanced team stats via BallDontLie API."""
        if not season or '-' not in season:
            print(f"  ⚠️ Invalid season format '{season}', expected 'YYYY-YY'")
            return {}

        now = time.time()
        if self._team_stats_cache is not None and (now - self._team_stats_cache_time) < self._CACHE_TTL:
            return self._team_stats_cache

        cached = CacheManager.get('game_pred_team', season, expiry_type='team_stats')
        if cached is not None:
            self._team_stats_cache = cached
            self._team_stats_cache_time = now
            return cached

        try:
            season_int = int(season.split('-')[0])
            bdl = get_bdl_client()
            team_mapper = get_team_mapper()

            def fetch_advanced():
                return bdl.get_team_season_averages("general", "advanced", season_int)

            def fetch_base():
                return bdl.get_team_season_averages("general", "base", season_int)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f_adv = pool.submit(fetch_advanced)
                f_base = pool.submit(fetch_base)
                exc_adv = f_adv.exception()
                if exc_adv is not None:
                    print(f"  ⚠️ Advanced team stats fetch failed: {exc_adv}")
                adv_list = f_adv.result() if exc_adv is None else []

                exc_base = f_base.exception()
                if exc_base is not None:
                    print(f"  ⚠️ Base team stats fetch failed: {exc_base}")
                base_list = f_base.result() if exc_base is None else []

            team_data = {}

            for entry in (adv_list or []):
                team_obj = entry.get('team') or {}
                abbrev = str(team_obj.get('abbreviation') or '').upper()
                if not abbrev:
                    bdl_tid = team_obj.get('id')
                    if bdl_tid is not None:
                        abbrev = team_mapper.bdl_id_to_abbrev(int(bdl_tid)) or ''
                if not abbrev:
                    continue

                stats = entry.get('stats') or {}
                off_rating = _safe_float(stats.get('off_rating'), 110)
                def_rating = _safe_float(stats.get('def_rating'), 110)
                net_rating = _safe_float(stats.get('net_rating'), 0)
                pace = _safe_float(stats.get('pace'), 100)
                opp_pts = round(def_rating * pace / 100, 1)

                team_data[abbrev] = {
                    'off_rating': off_rating,
                    'def_rating': def_rating,
                    'net_rating': net_rating,
                    'pace': pace,
                    'opp_pts': opp_pts,
                    # Four Factors from BDL advanced stats
                    'efg_pct': _safe_float(stats.get('efg_pct'), 0.50),
                    'ts_pct': _safe_float(stats.get('ts_pct'), 0.56),
                    'ast_pct': _safe_float(stats.get('ast_pct'), 0.60),
                    'tov_pct': _safe_float(stats.get('tov_pct'), 14.0),
                    'oreb_pct': _safe_float(stats.get('oreb_pct'), 0.27),
                    'dreb_pct': _safe_float(stats.get('dreb_pct'), 0.73),
                }

            for entry in (base_list or []):
                team_obj = entry.get('team') or {}
                abbrev = str(team_obj.get('abbreviation') or '').upper()
                if not abbrev:
                    bdl_tid = team_obj.get('id')
                    if bdl_tid is not None:
                        abbrev = team_mapper.bdl_id_to_abbrev(int(bdl_tid)) or ''
                if not abbrev:
                    continue

                stats = entry.get('stats') or {}

                if abbrev not in team_data:
                    team_data[abbrev] = {
                        'off_rating': 110, 'def_rating': 110, 'net_rating': 0,
                        'pace': 100, 'opp_pts': 110,
                    }

                team_data[abbrev].update({
                    'w': _safe_int(stats.get('w') or stats.get('wins'), 0),
                    'l': _safe_int(stats.get('l') or stats.get('losses'), 0),
                    'pts': _safe_float(stats.get('pts'), 110),
                    'reb': _safe_float(stats.get('reb'), 44),
                    'ast': _safe_float(stats.get('ast'), 24),
                    'stl': _safe_float(stats.get('stl'), 7),
                    'blk': _safe_float(stats.get('blk'), 5),
                    'tov': _safe_float(stats.get('tov'), 14),
                    'fg_pct': _safe_float(stats.get('fg_pct'), 0.46),
                    'fg3_pct': _safe_float(stats.get('fg3_pct'), 0.36),
                    'ft_pct': _safe_float(stats.get('ft_pct'), 0.78),
                })
                # opp_pts from advanced stats; if not available use pts as proxy
                if 'opp_pts' not in team_data[abbrev]:
                    team_data[abbrev]['opp_pts'] = team_data[abbrev].get('pts', 110)

            # Enrich with standings data (win%, conference rank, win streak)
            try:
                standings_list = bdl.get_standings(season_int)
                for entry in (standings_list or []):
                    team_obj = entry.get('team') or {}
                    abbrev = str(team_obj.get('abbreviation') or '').upper()
                    if not abbrev:
                        bdl_tid = team_obj.get('id')
                        if bdl_tid is not None:
                            abbrev = team_mapper.bdl_id_to_abbrev(int(bdl_tid)) or ''
                    if not abbrev or abbrev not in team_data:
                        continue
                    wins = _safe_float(entry.get('wins'), 0)
                    losses = _safe_float(entry.get('losses'), 1)
                    streak_raw = entry.get('streak') or 0
                    # streak may be dict {'streak_type': 'W', 'streak': 5} or just int
                    if isinstance(streak_raw, dict):
                        streak_val = _safe_int(streak_raw.get('streak'), 0)
                        if str(streak_raw.get('streak_type', 'W')).upper() == 'L':
                            streak_val = -streak_val
                    else:
                        streak_val = _safe_int(streak_raw, 0)
                    team_data[abbrev].update({
                        'standings_win_pct': wins / max(wins + losses, 1),
                        'conf_rank': _safe_int(entry.get('conference_rank') or entry.get('rank'), 15),
                        'win_streak': streak_val,
                    })
            except Exception as e:
                print(f"  ⚠️ Standings fetch failed (non-fatal): {e}")

            CacheManager.set('game_pred_team', team_data, season)
            self._team_stats_cache = team_data
            self._team_stats_cache_time = time.time()
            return team_data

        except Exception as e:
            print(f"Error fetching team stats: {e}")
            return {}

    def get_team_game_log(self, team_id, season='2025-26'):
        """Get a team's game log via BallDontLie API.

        team_id is a BDL team ID (as returned by get_todays_games / team_abbrev_to_id).
        Returns DataFrame with PTS, WL, MATCHUP, PLUS_MINUS, TEAM_ABBREVIATION, GAME_DATE, GAME_ID.
        """
        if team_id is None:
            return pd.DataFrame()

        if not season or '-' not in season:
            print(f"  ⚠️ Invalid season format '{season}', expected 'YYYY-YY'")
            return pd.DataFrame()

        cache_key = f"{team_id}_{season}"
        now = time.time()
        if cache_key in self._team_game_logs_cache:
            if (now - self._team_game_logs_cache_times.get(cache_key, 0)) < self._CACHE_TTL:
                return self._team_game_logs_cache[cache_key]
            del self._team_game_logs_cache[cache_key]
            self._team_game_logs_cache_times.pop(cache_key, None)

        cached = CacheManager.get('game_pred_log', team_id, season, expiry_type='game_log')
        if cached is not None:
            self._team_game_logs_cache[cache_key] = cached
            self._team_game_logs_cache_times[cache_key] = now
            return cached

        try:
            season_int = int(season.split('-')[0])
            bdl = get_bdl_client()
            team_mapper = get_team_mapper()
            team_abbrev = team_mapper.bdl_id_to_abbrev(int(team_id)) or ''

            raw_games = bdl.get_games(team_ids=[int(team_id)], seasons=[season_int])

            if not raw_games:
                return pd.DataFrame()

            rows = []
            for g in raw_games:
                game_status = str(g.get('status') or '').lower()
                if game_status != 'final':
                    continue  # Skip non-final games

                home = g.get('home_team') or {}
                visitor = g.get('visitor_team') or {}
                home_bdl_id = home.get('id')
                visitor_bdl_id = visitor.get('id')
                if home_bdl_id is None or visitor_bdl_id is None:
                    continue
                home_abbrev = str(home.get('abbreviation') or '').upper()
                visitor_abbrev = str(visitor.get('abbreviation') or '').upper()
                home_score = g.get('home_team_score')
                visitor_score = g.get('visitor_team_score')

                is_home = (home_bdl_id == int(team_id))
                team_pts = home_score if is_home else visitor_score
                opp_pts = visitor_score if is_home else home_score

                if team_pts is None or opp_pts is None:
                    continue

                team_pts = _safe_int(team_pts, None)
                opp_pts = _safe_int(opp_pts, None)
                if team_pts is None or opp_pts is None:
                    continue

                if is_home:
                    matchup = f"{team_abbrev} vs. {visitor_abbrev}"
                    wl = 'W' if team_pts > opp_pts else 'L'
                else:
                    matchup = f"{team_abbrev} @ {home_abbrev}"
                    wl = 'W' if team_pts > opp_pts else 'L'

                game_date_raw = g.get('date') or ''
                game_date = game_date_raw[:10] if game_date_raw else ''

                rows.append({
                    'GAME_ID': g.get('id'),
                    'GAME_DATE': game_date,
                    'TEAM_ABBREVIATION': team_abbrev,
                    'MATCHUP': matchup,
                    'WL': wl,
                    'PTS': team_pts,
                    'PLUS_MINUS': team_pts - opp_pts,
                })

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
            df = df.sort_values('GAME_DATE')

            CacheManager.set('game_pred_log', df, team_id, season)
            # Evict oldest entries if at capacity
            if len(self._team_game_logs_cache) >= self._GAME_LOGS_MAX_ENTRIES:
                oldest_key = min(self._team_game_logs_cache_times, key=self._team_game_logs_cache_times.get)
                del self._team_game_logs_cache[oldest_key]
                del self._team_game_logs_cache_times[oldest_key]
            self._team_game_logs_cache[cache_key] = df
            self._team_game_logs_cache_times[cache_key] = time.time()
            return df

        except Exception as e:
            print(f"Error fetching team game log: {e}")
            return pd.DataFrame()

    def get_injuries(self):
        """Get injury report (reuses existing scraper). Refreshes every hour."""
        now = time.time()
        if self._injuries_cache is not None and (now - self._injuries_cache_time) < self._CACHE_TTL:
            return self._injuries_cache
        self._injuries_cache = self.scraper.get_injury_report()
        self._injuries_cache_time = now
        return self._injuries_cache

    def get_top_scorers(self, season='2025-26'):
        """Get top 2 scorers per team via BallDontLie season averages."""
        if not season or '-' not in season:
            print(f"  ⚠️ Invalid season format '{season}', expected 'YYYY-YY'")
            return {}

        now = time.time()
        if self._top_scorers_cache is not None and (now - self._top_scorers_cache_time) < self._CACHE_TTL:
            return self._top_scorers_cache

        cached = CacheManager.get('game_pred_scorers', season, expiry_type='team_stats')
        if cached is not None:
            self._top_scorers_cache = cached
            self._top_scorers_cache_time = now
            return cached

        try:
            season_int = int(season.split('-')[0])
            bdl = get_bdl_client()
            team_mapper = get_team_mapper()

            # BDL /v1/season_averages returns player season averages
            raw_avgs = bdl.get_season_averages("general", "base", season_int)

            # raw_avgs is a list of {player: {..., team: {abbreviation}}, stats: {pts, ...}}
            # Build per-team player list
            team_players: dict = {}
            for entry in (raw_avgs or []):
                player_obj = entry.get('player') or {}
                team_obj = player_obj.get('team') or entry.get('team') or {}
                abbrev = str(team_obj.get('abbreviation') or '').upper()
                if not abbrev:
                    continue
                stats = entry.get('stats') or {}
                pts = _safe_float(stats.get('pts'), 0)
                player_name = f"{(player_obj.get('first_name') or '').strip()} {(player_obj.get('last_name') or '').strip()}".strip()
                bdl_pid = player_obj.get('id')

                if abbrev not in team_players:
                    team_players[abbrev] = []
                team_players[abbrev].append({
                    'name': player_name,
                    'pts': pts,
                    'player_id': bdl_pid,
                })

            top_scorers = {}
            for abbrev in TEAM_ABBREV_TO_NAME:
                players = team_players.get(abbrev, [])
                sorted_players = sorted(players, key=lambda x: x['pts'], reverse=True)
                top_scorers[abbrev] = sorted_players[:2]

            CacheManager.set('game_pred_scorers', top_scorers, season)
            self._top_scorers_cache = top_scorers
            self._top_scorers_cache_time = time.time()
            return top_scorers

        except Exception as e:
            print(f"Error fetching top scorers: {e}")
            return {}

    # ── Feature Engineering (Advanced) ─────────────────────────

    @staticmethod
    def _compute_four_factors(games, n_games=10):
        """Compute Dean Oliver's Four Factors from game logs."""
        recent = games.tail(n_games)
        if len(recent) < 3:
            return {'efg_pct': 0.50, 'tov_pct': 14.0, 'oreb_rate': 10.0, 'ft_rate': 0.20}

        fgm = recent['FGM'].sum() if 'FGM' in recent.columns else 0
        fga = recent['FGA'].sum() if 'FGA' in recent.columns else 1
        fg3m = recent['FG3M'].sum() if 'FG3M' in recent.columns else 0
        fta = recent['FTA'].sum() if 'FTA' in recent.columns else 0
        oreb = recent['OREB'].sum() if 'OREB' in recent.columns else 0
        tov = recent['TOV'].sum() if 'TOV' in recent.columns else 0

        efg_pct = (fgm + 0.5 * fg3m) / max(fga, 1)
        possessions = fga + 0.44 * fta + tov
        tov_pct = (tov / max(possessions, 1)) * 100
        oreb_rate = oreb / max(len(recent), 1)
        ft_rate = fta / max(fga, 1)

        return {'efg_pct': efg_pct, 'tov_pct': tov_pct, 'oreb_rate': oreb_rate, 'ft_rate': ft_rate}

    @staticmethod
    def _compute_rolling_features(games):
        """Compute multi-window rolling metrics from game logs."""
        if len(games) < 5:
            return {}

        features = {}
        pts = games['PTS'].values
        margins = games['PLUS_MINUS'].values if 'PLUS_MINUS' in games.columns else np.zeros(len(games))
        wl = (games['WL'] == 'W').astype(float).values

        for window in [3, 5, 10, 15, 20]:
            if len(games) >= window:
                features[f'wp_l{window}'] = wl[-window:].mean()
                features[f'margin_l{window}'] = margins[-window:].mean()
                features[f'pts_l{window}'] = pts[-window:].mean()
                features[f'pts_std_l{window}'] = pts[-window:].std() if len(pts[-window:]) > 1 else 0
                features[f'margin_std_l{window}'] = np.std(margins[-window:]) if len(margins[-window:]) > 1 else 0

        # EMA (more responsive to recent form)
        for span in [3, 5, 10]:
            if len(games) >= span:
                features[f'ema_margin_{span}'] = pd.Series(margins).ewm(span=span).mean().iloc[-1]
                features[f'ema_pts_{span}'] = pd.Series(pts).ewm(span=span).mean().iloc[-1]
                features[f'ema_wp_{span}'] = pd.Series(wl).ewm(span=span).mean().iloc[-1]

        # Trends (short vs long)
        if len(games) >= 20:
            features['margin_trend'] = features.get('margin_l5', 0) - features.get('margin_l20', 0)
            features['wp_trend'] = features.get('wp_l5', 0.5) - features.get('wp_l20', 0.5)
            features['pts_trend'] = features.get('pts_l5', 100) - features.get('pts_l20', 100)

        # Scoring consistency (coefficient of variation)
        if len(games) >= 10:
            mean_pts = pts[-10:].mean()
            features['pts_cv'] = (pts[-10:].std() / max(mean_pts, 1)) if mean_pts > 0 else 0
            features['margin_range_10'] = margins[-10:].max() - margins[-10:].min()

        return features

    @staticmethod
    def _schedule_features(games, game_date, team_abbrev):
        """Compute rest, B2B, 3-in-4, travel, fatigue features."""
        if games.empty:
            return {'rest': 2, 'b2b': 0, 'three_in_four': 0, 'tz_change': 0, 'games_in_7': 3}

        dates = games['GAME_DATE'].sort_values()
        past = dates[dates < game_date]

        rest = (game_date - past.max()).days if not past.empty else 2
        rest = min(rest, 5)
        b2b = 1 if rest <= 1 else 0

        # 3 games in 4 nights
        four_days_ago = game_date - pd.Timedelta(days=4)
        games_in_4 = ((dates >= four_days_ago) & (dates < game_date)).sum()
        three_in_four = 1 if games_in_4 >= 2 else 0

        # Games in last 7 days (fatigue proxy)
        seven_ago = game_date - pd.Timedelta(days=7)
        games_in_7 = ((dates >= seven_ago) & (dates < game_date)).sum()

        # Timezone change from last game
        tz_change = 0
        if not past.empty:
            last_game = games[games['GAME_DATE'] == past.max()]
            if not last_game.empty:
                matchup = str(last_game.iloc[-1].get('MATCHUP', ''))
                if '@' in matchup:
                    opp = matchup.split()[-1]
                    tz_change = abs(TEAM_TIMEZONE.get(team_abbrev, -5) - TEAM_TIMEZONE.get(opp, -5))

        return {'rest': rest, 'b2b': b2b, 'three_in_four': three_in_four,
                'tz_change': tz_change, 'games_in_7': games_in_7}

    @staticmethod
    def _compute_sos(team_games, all_games_df):
        """Compute strength of schedule from opponents' win percentages."""
        if team_games.empty or all_games_df.empty:
            return 0.5

        opponents = []
        for _, g in team_games.iterrows():
            matchup = str(g.get('MATCHUP', ''))
            parts = matchup.replace('vs.', '@').split('@')
            if len(parts) == 2:
                opp = parts[1].strip().split()[-1] if parts[1].strip() else ''
                if opp:
                    opponents.append(opp)

        if not opponents:
            return 0.5

        opp_wps = []
        for opp in set(opponents):
            opp_games = all_games_df[all_games_df['TEAM_ABBREVIATION'] == opp]
            if len(opp_games) >= 5:
                opp_wps.append((opp_games['WL'] == 'W').mean())

        return np.mean(opp_wps) if opp_wps else 0.5

    @staticmethod
    def _clutch_and_mov_features(games, n=15):
        """Close game record and margin-of-victory indicators."""
        if len(games) < 5:
            return {'close_wp': 0.5, 'blowout_pct': 0.0, 'avg_close_margin': 0}

        recent = games.tail(n)
        if 'PLUS_MINUS' not in recent.columns:
            return {'close_wp': 0.5, 'blowout_pct': 0.0, 'avg_close_margin': 0}

        margins = recent['PLUS_MINUS'].abs()

        close = recent[recent['PLUS_MINUS'].abs() <= 5]
        close_wp = (close['WL'] == 'W').mean() if len(close) > 0 else 0.5

        blowout_pct = (margins >= 15).mean()

        avg_close_margin = close['PLUS_MINUS'].mean() if len(close) > 0 else 0

        return {'close_wp': close_wp, 'blowout_pct': blowout_pct, 'avg_close_margin': avg_close_margin}

    @staticmethod
    def _home_away_splits(games, is_home=True, n_recent=10):
        """Home/away win% with recency."""
        pattern = 'vs.' if is_home else '@'
        if 'MATCHUP' not in games.columns or games.empty:
            return {'ha_wp': 0.5, 'ha_margin': 0, 'ha_recent_wp': 0.5}

        filtered = games[games['MATCHUP'].str.contains(pattern)]
        if filtered.empty:
            return {'ha_wp': 0.5, 'ha_margin': 0, 'ha_recent_wp': 0.5}

        overall_wp = (filtered['WL'] == 'W').mean()
        overall_margin = filtered['PLUS_MINUS'].mean() if 'PLUS_MINUS' in filtered.columns else 0

        recent = filtered.tail(n_recent)
        recent_wp = (recent['WL'] == 'W').mean()

        return {'ha_wp': overall_wp, 'ha_margin': overall_margin, 'ha_recent_wp': recent_wp}

    def _get_streak(self, game_log):
        """Get current win/loss streak."""
        if game_log.empty:
            return 0

        streak = 0
        last_result = game_log.iloc[-1].get('WL', 'L')

        for i in range(len(game_log) - 1, -1, -1):
            if game_log.iloc[i].get('WL', '') == last_result:
                streak += 1
            else:
                break

        return streak if last_result == 'W' else -streak

    def _head_to_head(self, game_log, opponent_abbrev):
        """Get head-to-head record this season."""
        if game_log.empty:
            return {'wins': 0, 'losses': 0, 'avg_margin': 0}

        h2h = game_log[game_log['MATCHUP'].str.contains(opponent_abbrev)]
        if h2h.empty:
            return {'wins': 0, 'losses': 0, 'avg_margin': 0}

        wins = (h2h['WL'] == 'W').sum()
        losses = len(h2h) - wins
        avg_margin = h2h['PLUS_MINUS'].mean() if 'PLUS_MINUS' in h2h.columns else 0

        return {'wins': wins, 'losses': losses, 'avg_margin': avg_margin}

    def _injury_impact(self, team_abbrev, injuries, top_scorers):
        """Assess injury impact for a team."""
        team_injuries = injuries.get(team_abbrev, {})
        out_count = team_injuries.get('out', 0)
        questionable_count = team_injuries.get('questionable', 0)

        star_out = 0
        injured_players = [p.get('name', '').lower() for p in team_injuries.get('players', [])]
        team_stars = top_scorers.get(team_abbrev, [])

        for star in team_stars:
            star_name = star.get('name', '').lower()
            for injured in injured_players:
                if star_name in injured or injured in star_name:
                    star_out += 1
                    break

        return {
            'out': out_count,
            'questionable': questionable_count,
            'star_out': star_out,
            'star_pts_lost': sum(
                s['pts'] for i, s in enumerate(team_stars)
                if i < star_out
            ) if star_out > 0 else 0,
        }

    # ── Feature Building ───────────────────────────────────────

    def _build_historical_features(self, home_games, away_games, home_abbrev, away_abbrev,
                                    all_games_df=None, elo_tracker=None, game_date=None):
        """Build comprehensive feature vector from historical game logs (~120 features)."""

        def safe_val(d, key, default=0):
            v = d.get(key, default)
            return default if pd.isna(v) else v

        # === Rolling features ===
        home_roll = self._compute_rolling_features(home_games)
        away_roll = self._compute_rolling_features(away_games)

        # === Four Factors ===
        home_ff = self._compute_four_factors(home_games, 10)
        away_ff = self._compute_four_factors(away_games, 10)

        # === Schedule features ===
        if game_date is not None:
            home_sched = self._schedule_features(home_games, game_date, home_abbrev)
            away_sched = self._schedule_features(away_games, game_date, away_abbrev)
        else:
            home_sched = {'rest': 2, 'b2b': 0, 'three_in_four': 0, 'tz_change': 0, 'games_in_7': 3}
            away_sched = {'rest': 2, 'b2b': 0, 'three_in_four': 0, 'tz_change': 0, 'games_in_7': 3}

        # === Clutch & MOV ===
        home_clutch = self._clutch_and_mov_features(home_games)
        away_clutch = self._clutch_and_mov_features(away_games)

        # === Home/Away splits ===
        home_ha = self._home_away_splits(home_games, is_home=True)
        away_ha = self._home_away_splits(away_games, is_home=False)

        # === Win pct, streaks, H2H ===
        def win_pct(games):
            if games.empty:
                return 0.5
            return (games['WL'] == 'W').sum() / len(games)

        home_wp = win_pct(home_games)
        away_wp = win_pct(away_games)
        home_streak = self._get_streak(home_games)
        away_streak = self._get_streak(away_games)

        h2h = self._head_to_head(home_games, away_abbrev)

        # === Approximate ratings from game data ===
        home_avg_pts = home_games['PTS'].tail(15).mean() if len(home_games) >= 5 else 110
        away_avg_pts = away_games['PTS'].tail(15).mean() if len(away_games) >= 5 else 110
        home_avg_opp = (home_games['PTS'] - home_games['PLUS_MINUS']).tail(15).mean() if ('PLUS_MINUS' in home_games.columns and len(home_games) >= 5) else 110
        away_avg_opp = (away_games['PTS'] - away_games['PLUS_MINUS']).tail(15).mean() if ('PLUS_MINUS' in away_games.columns and len(away_games) >= 5) else 110

        home_net = home_avg_pts - home_avg_opp
        away_net = away_avg_pts - away_avg_opp

        # === Shooting stats ===
        home_fg_pct = home_games['FG_PCT'].tail(10).mean() if 'FG_PCT' in home_games.columns else 0.46
        away_fg_pct = away_games['FG_PCT'].tail(10).mean() if 'FG_PCT' in away_games.columns else 0.46
        home_fg3_pct = home_games['FG3_PCT'].tail(10).mean() if 'FG3_PCT' in home_games.columns else 0.36
        away_fg3_pct = away_games['FG3_PCT'].tail(10).mean() if 'FG3_PCT' in away_games.columns else 0.36
        home_tov = home_games['TOV'].tail(10).mean() if 'TOV' in home_games.columns else 14
        away_tov = away_games['TOV'].tail(10).mean() if 'TOV' in away_games.columns else 14
        home_reb = home_games['REB'].tail(10).mean() if 'REB' in home_games.columns else 44
        away_reb = away_games['REB'].tail(10).mean() if 'REB' in away_games.columns else 44

        # === SOS ===
        if all_games_df is not None and not all_games_df.empty:
            home_sos = self._compute_sos(home_games, all_games_df)
            away_sos = self._compute_sos(away_games, all_games_df)
        else:
            home_sos = 0.5
            away_sos = 0.5

        # === Elo ===
        if elo_tracker is not None:
            elo_diff = elo_tracker.get_diff(home_abbrev, away_abbrev)
            home_elo = elo_tracker.get_rating(home_abbrev)
            away_elo = elo_tracker.get_rating(away_abbrev)
            elo_expected = elo_tracker.get_expected(home_abbrev, away_abbrev)
        else:
            elo_diff = 0
            home_elo = 1500
            away_elo = 1500
            elo_expected = 0.5

        # ── Build feature dict ──

        features = {
            # === Elo ===
            'elo_diff': elo_diff,
            'home_elo': home_elo,
            'away_elo': away_elo,
            'elo_expected': elo_expected,

            # === Team ratings (approximate) ===
            'off_rating_diff': home_avg_pts - away_avg_pts,
            'def_rating_diff': home_avg_opp - away_avg_opp,
            'net_rating_diff': home_net - away_net,

            'home_off_rating': home_avg_pts,
            'home_def_rating': home_avg_opp,
            'home_net_rating': home_net,
            'away_off_rating': away_avg_pts,
            'away_def_rating': away_avg_opp,
            'away_net_rating': away_net,

            # === Win percentages ===
            'home_win_pct': home_wp,
            'away_win_pct': away_wp,
            'win_pct_diff': home_wp - away_wp,

            # === Four Factors ===
            'home_efg_pct': home_ff['efg_pct'],
            'away_efg_pct': away_ff['efg_pct'],
            'efg_pct_diff': home_ff['efg_pct'] - away_ff['efg_pct'],
            'home_tov_pct': home_ff['tov_pct'],
            'away_tov_pct': away_ff['tov_pct'],
            'tov_pct_diff': home_ff['tov_pct'] - away_ff['tov_pct'],
            'home_oreb_rate': home_ff['oreb_rate'],
            'away_oreb_rate': away_ff['oreb_rate'],
            'oreb_rate_diff': home_ff['oreb_rate'] - away_ff['oreb_rate'],
            'home_ft_rate': home_ff['ft_rate'],
            'away_ft_rate': away_ff['ft_rate'],
            'ft_rate_diff': home_ff['ft_rate'] - away_ff['ft_rate'],

            # === Rolling win% (multi-window) ===
            'home_wp_l5': safe_val(home_roll, 'wp_l5', 0.5),
            'away_wp_l5': safe_val(away_roll, 'wp_l5', 0.5),
            'wp_l5_diff': safe_val(home_roll, 'wp_l5', 0.5) - safe_val(away_roll, 'wp_l5', 0.5),
            'home_wp_l10': safe_val(home_roll, 'wp_l10', 0.5),
            'away_wp_l10': safe_val(away_roll, 'wp_l10', 0.5),
            'wp_l10_diff': safe_val(home_roll, 'wp_l10', 0.5) - safe_val(away_roll, 'wp_l10', 0.5),
            'home_wp_l15': safe_val(home_roll, 'wp_l15', 0.5),
            'away_wp_l15': safe_val(away_roll, 'wp_l15', 0.5),
            'wp_l15_diff': safe_val(home_roll, 'wp_l15', 0.5) - safe_val(away_roll, 'wp_l15', 0.5),

            # === Rolling margin ===
            'home_margin_l5': safe_val(home_roll, 'margin_l5', 0),
            'away_margin_l5': safe_val(away_roll, 'margin_l5', 0),
            'margin_l5_diff': safe_val(home_roll, 'margin_l5', 0) - safe_val(away_roll, 'margin_l5', 0),
            'home_margin_l10': safe_val(home_roll, 'margin_l10', 0),
            'away_margin_l10': safe_val(away_roll, 'margin_l10', 0),
            'margin_l10_diff': safe_val(home_roll, 'margin_l10', 0) - safe_val(away_roll, 'margin_l10', 0),

            # === Rolling points ===
            'home_pts_l5': safe_val(home_roll, 'pts_l5', 110),
            'away_pts_l5': safe_val(away_roll, 'pts_l5', 110),

            # === EMA features ===
            'home_ema_margin_3': safe_val(home_roll, 'ema_margin_3', 0),
            'away_ema_margin_3': safe_val(away_roll, 'ema_margin_3', 0),
            'ema_margin_3_diff': safe_val(home_roll, 'ema_margin_3', 0) - safe_val(away_roll, 'ema_margin_3', 0),
            'home_ema_margin_5': safe_val(home_roll, 'ema_margin_5', 0),
            'away_ema_margin_5': safe_val(away_roll, 'ema_margin_5', 0),
            'ema_margin_5_diff': safe_val(home_roll, 'ema_margin_5', 0) - safe_val(away_roll, 'ema_margin_5', 0),
            'home_ema_wp_5': safe_val(home_roll, 'ema_wp_5', 0.5),
            'away_ema_wp_5': safe_val(away_roll, 'ema_wp_5', 0.5),
            'ema_wp_5_diff': safe_val(home_roll, 'ema_wp_5', 0.5) - safe_val(away_roll, 'ema_wp_5', 0.5),

            # === Trends ===
            'home_margin_trend': safe_val(home_roll, 'margin_trend', 0),
            'away_margin_trend': safe_val(away_roll, 'margin_trend', 0),
            'margin_trend_diff': safe_val(home_roll, 'margin_trend', 0) - safe_val(away_roll, 'margin_trend', 0),
            'home_wp_trend': safe_val(home_roll, 'wp_trend', 0),
            'away_wp_trend': safe_val(away_roll, 'wp_trend', 0),
            'wp_trend_diff': safe_val(home_roll, 'wp_trend', 0) - safe_val(away_roll, 'wp_trend', 0),

            # === Consistency / Variance ===
            'home_pts_cv': safe_val(home_roll, 'pts_cv', 0.1),
            'away_pts_cv': safe_val(away_roll, 'pts_cv', 0.1),
            'home_pts_std_l10': safe_val(home_roll, 'pts_std_l10', 10),
            'away_pts_std_l10': safe_val(away_roll, 'pts_std_l10', 10),
            'home_margin_range_10': safe_val(home_roll, 'margin_range_10', 20),
            'away_margin_range_10': safe_val(away_roll, 'margin_range_10', 20),

            # === Streaks ===
            'home_streak': home_streak,
            'away_streak': away_streak,
            'streak_diff': home_streak - away_streak,

            # === Schedule / Rest ===
            'home_rest_days': home_sched['rest'],
            'away_rest_days': away_sched['rest'],
            'rest_diff': home_sched['rest'] - away_sched['rest'],
            'home_b2b': home_sched['b2b'],
            'away_b2b': away_sched['b2b'],
            'home_3in4': home_sched['three_in_four'],
            'away_3in4': away_sched['three_in_four'],
            'home_games_in_7': home_sched['games_in_7'],
            'away_games_in_7': away_sched['games_in_7'],
            'games_in_7_diff': home_sched['games_in_7'] - away_sched['games_in_7'],
            'home_tz_change': home_sched['tz_change'],
            'away_tz_change': away_sched['tz_change'],
            'tz_change_diff': home_sched['tz_change'] - away_sched['tz_change'],

            # === Head-to-head ===
            'h2h_home_wins': h2h['wins'],
            'h2h_avg_margin': h2h['avg_margin'],

            # === Injuries (zeros for historical) ===
            'home_injuries_out': 0,
            'away_injuries_out': 0,
            'injury_diff': 0,
            'home_star_out': 0,
            'away_star_out': 0,
            'home_star_pts_lost': 0,
            'away_star_pts_lost': 0,

            # === Scoring stats ===
            'pts_diff': home_avg_pts - away_avg_pts,
            'fg_pct_diff': home_fg_pct - away_fg_pct,
            'fg3_pct_diff': home_fg3_pct - away_fg3_pct,
            'tov_diff': home_tov - away_tov,
            'reb_diff': home_reb - away_reb,

            # === SOS ===
            'home_sos': home_sos,
            'away_sos': away_sos,
            'sos_diff': home_sos - away_sos,

            # === Clutch / MOV ===
            'home_close_wp': home_clutch['close_wp'],
            'away_close_wp': away_clutch['close_wp'],
            'close_wp_diff': home_clutch['close_wp'] - away_clutch['close_wp'],
            'home_blowout_pct': home_clutch['blowout_pct'],
            'away_blowout_pct': away_clutch['blowout_pct'],

            # === Home/Away splits ===
            'home_ha_wp': home_ha['ha_wp'],
            'home_ha_margin': home_ha['ha_margin'],
            'home_ha_recent_wp': home_ha['ha_recent_wp'],
            'away_ha_wp': away_ha['ha_wp'],
            'away_ha_margin': away_ha['ha_margin'],
            'away_ha_recent_wp': away_ha['ha_recent_wp'],

            # === Interaction features ===
            'elo_x_form': elo_diff * safe_val(home_roll, 'wp_l5', 0.5) / 100,
            'rest_x_b2b': (home_sched['rest'] - away_sched['rest']) * (home_sched['b2b'] - away_sched['b2b']),
            'rating_x_streak': (home_net - away_net) * (home_streak - away_streak),
            'elo_x_sos': elo_diff * (home_sos - away_sos),
        }

        return features

    def build_game_features(self, home_team_abbrev, away_team_abbrev, game_date=None):
        """Build feature vector for a single game matchup (live prediction path)."""
        if game_date is None:
            game_date = pd.Timestamp(datetime.now())
        elif isinstance(game_date, str):
            game_date = pd.Timestamp(game_date)

        team_stats = self.get_team_stats()
        injuries = self.get_injuries()
        top_scorers = self.get_top_scorers()

        home_stats = team_stats.get(home_team_abbrev, {})
        away_stats = team_stats.get(away_team_abbrev, {})

        home_id = self.team_abbrev_to_id.get(home_team_abbrev)
        away_id = self.team_abbrev_to_id.get(away_team_abbrev)

        home_log = self.get_team_game_log(home_id) if home_id else pd.DataFrame()
        away_log = self.get_team_game_log(away_id) if away_id else pd.DataFrame()

        # Build features using the same method as training
        features = self._build_historical_features(
            home_log, away_log, home_team_abbrev, away_team_abbrev,
            all_games_df=None, elo_tracker=self.elo_tracker, game_date=game_date
        )

        # Override ratings with real API data if available
        if home_stats and away_stats:
            features['home_off_rating'] = home_stats.get('off_rating', features['home_off_rating'])
            features['home_def_rating'] = home_stats.get('def_rating', features['home_def_rating'])
            features['home_net_rating'] = home_stats.get('net_rating', features['home_net_rating'])
            features['away_off_rating'] = away_stats.get('off_rating', features['away_off_rating'])
            features['away_def_rating'] = away_stats.get('def_rating', features['away_def_rating'])
            features['away_net_rating'] = away_stats.get('net_rating', features['away_net_rating'])
            features['off_rating_diff'] = features['home_off_rating'] - features['away_off_rating']
            features['def_rating_diff'] = features['home_def_rating'] - features['away_def_rating']
            features['net_rating_diff'] = features['home_net_rating'] - features['away_net_rating']

        # Inject new API-sourced features (Four Factors + Standings)
        for prefix, stats in [('home', home_stats), ('away', away_stats)]:
            features[f'{prefix}_api_efg_pct'] = stats.get('efg_pct', 0.50)
            features[f'{prefix}_api_tov_pct'] = stats.get('tov_pct', 14.0)
            features[f'{prefix}_api_oreb_pct'] = stats.get('oreb_pct', 0.27)
            features[f'{prefix}_api_ts_pct'] = stats.get('ts_pct', 0.56)
            features[f'{prefix}_standings_win_pct'] = stats.get('standings_win_pct', 0.50)
            features[f'{prefix}_conf_rank'] = stats.get('conf_rank', 15)
            features[f'{prefix}_win_streak'] = stats.get('win_streak', 0)

        features['api_efg_diff'] = features.get('home_api_efg_pct', 0.50) - features.get('away_api_efg_pct', 0.50)
        features['api_tov_diff'] = features.get('home_api_tov_pct', 14.0) - features.get('away_api_tov_pct', 14.0)
        features['standings_win_pct_diff'] = features.get('home_standings_win_pct', 0.5) - features.get('away_standings_win_pct', 0.5)
        features['conf_rank_diff'] = features.get('home_conf_rank', 15) - features.get('away_conf_rank', 15)
        features['win_streak_diff'] = features.get('home_win_streak', 0) - features.get('away_win_streak', 0)

        # Override injury features with live data
        home_inj = self._injury_impact(home_team_abbrev, injuries, top_scorers)
        away_inj = self._injury_impact(away_team_abbrev, injuries, top_scorers)

        features['home_injuries_out'] = home_inj['out']
        features['away_injuries_out'] = away_inj['out']
        features['injury_diff'] = away_inj['out'] - home_inj['out']
        features['home_star_out'] = home_inj['star_out']
        features['away_star_out'] = away_inj['star_out']
        features['home_star_pts_lost'] = home_inj['star_pts_lost']
        features['away_star_pts_lost'] = away_inj['star_pts_lost']

        # === Player-level team strength adjustment ===
        # When stars are out, adjust team ratings proportionally to their scoring impact.
        # A team losing 25+ ppg player drops ~3-5 net rating points (research-based).
        # This bridges the gap between team-level-only and lineup-aware models.
        home_pts_lost = home_inj['star_pts_lost']
        away_pts_lost = away_inj['star_pts_lost']

        # Approximate net rating impact: ~0.15 net rating per point of star scoring lost
        home_adj = -home_pts_lost * 0.15
        away_adj = -away_pts_lost * 0.15

        features['home_lineup_adj_net'] = features.get('home_net_rating', 0) + home_adj
        features['away_lineup_adj_net'] = features.get('away_net_rating', 0) + away_adj
        features['lineup_adj_net_diff'] = features['home_lineup_adj_net'] - features['away_lineup_adj_net']

        # Lineup-adjusted Elo: shift Elo by star impact (scale: ~5 Elo pts per scoring point)
        features['lineup_adj_elo_diff'] = features.get('elo_diff', 0) + (away_pts_lost - home_pts_lost) * 5

        return features

    def _generate_key_factors(self, features):
        """Generate human-readable key factors from features."""
        factors = []

        # Elo advantage
        elo_diff = features.get('elo_diff', 0)
        if abs(elo_diff) > 50:
            side = 'Home' if elo_diff > 0 else 'Away'
            factors.append({
                'factor': 'Elo Rating',
                'impact': 'MAJOR' if abs(elo_diff) > 100 else 'MODERATE',
                'description': f"{side} team has a {abs(elo_diff):.0f}-point Elo advantage",
                'favors': 'HOME' if elo_diff > 0 else 'AWAY',
            })

        # Home court
        factors.append({
            'factor': 'Home Court',
            'impact': 'MODERATE',
            'description': 'Home team has home court advantage',
            'favors': 'HOME',
        })

        # Net rating
        nrd = features.get('net_rating_diff', 0)
        if abs(nrd) > 3:
            factors.append({
                'factor': 'Net Rating',
                'impact': 'MAJOR' if abs(nrd) > 6 else 'MODERATE',
                'description': f"{'Home' if nrd > 0 else 'Away'} team has a {abs(nrd):.1f} better net rating",
                'favors': 'HOME' if nrd > 0 else 'AWAY',
            })

        # Recent form (EMA)
        ema_diff = features.get('ema_margin_5_diff', 0)
        if abs(ema_diff) > 3:
            better = 'Home' if ema_diff > 0 else 'Away'
            factors.append({
                'factor': 'Recent Form',
                'impact': 'MODERATE',
                'description': f"{better} team has stronger recent momentum (EMA margin {ema_diff:+.1f})",
                'favors': 'HOME' if ema_diff > 0 else 'AWAY',
            })

        # Back-to-back
        if features.get('home_b2b') or features.get('away_b2b'):
            tired = 'Home' if features.get('home_b2b') else 'Away'
            factors.append({
                'factor': 'Back-to-Back',
                'impact': 'MODERATE',
                'description': f"{tired} team is on a back-to-back",
                'favors': 'AWAY' if features.get('home_b2b') else 'HOME',
            })

        # 3-in-4
        if features.get('home_3in4') or features.get('away_3in4'):
            tired = 'Home' if features.get('home_3in4') else 'Away'
            factors.append({
                'factor': 'Fatigue (3-in-4)',
                'impact': 'MODERATE',
                'description': f"{tired} team playing 3rd game in 4 nights",
                'favors': 'AWAY' if features.get('home_3in4') else 'HOME',
            })

        # Travel
        tz_diff = features.get('tz_change_diff', 0)
        if abs(tz_diff) >= 2:
            traveled = 'Home' if tz_diff > 0 else 'Away'
            factors.append({
                'factor': 'Travel',
                'impact': 'MINOR',
                'description': f"{traveled} team has more timezone travel",
                'favors': 'AWAY' if tz_diff > 0 else 'HOME',
            })

        # Injuries
        if features.get('home_star_out', 0) > 0:
            factors.append({
                'factor': 'Home Star Injured',
                'impact': 'MAJOR',
                'description': f"Home team missing {features['home_star_out']} star(s) ({features.get('home_star_pts_lost', 0):.1f} PPG lost)",
                'favors': 'AWAY',
            })
        if features.get('away_star_out', 0) > 0:
            factors.append({
                'factor': 'Away Star Injured',
                'impact': 'MAJOR',
                'description': f"Away team missing {features['away_star_out']} star(s) ({features.get('away_star_pts_lost', 0):.1f} PPG lost)",
                'favors': 'HOME',
            })

        # Four Factors edge
        efg_diff = features.get('efg_pct_diff', 0)
        if abs(efg_diff) > 0.02:
            better = 'Home' if efg_diff > 0 else 'Away'
            factors.append({
                'factor': 'Shooting Efficiency',
                'impact': 'MODERATE' if abs(efg_diff) > 0.04 else 'MINOR',
                'description': f"{better} team has {abs(efg_diff):.1%} better eFG%",
                'favors': 'HOME' if efg_diff > 0 else 'AWAY',
            })

        # SOS
        sos_diff = features.get('sos_diff', 0)
        if abs(sos_diff) > 0.03:
            harder = 'Home' if sos_diff > 0 else 'Away'
            factors.append({
                'factor': 'Strength of Schedule',
                'impact': 'MINOR',
                'description': f"{harder} team has faced tougher opponents",
                'favors': 'HOME' if sos_diff > 0 else 'AWAY',
            })

        # Sort by impact
        impact_order = {'MAJOR': 0, 'MODERATE': 1, 'MINOR': 2}
        factors.sort(key=lambda f: impact_order.get(f['impact'], 3))

        return factors[:6]

    # ── Model Architecture ─────────────────────────────────────

    def _create_base_models_list(self):
        """Create list of base classifiers for stacking."""
        models = []

        models.append(('rf', RandomForestClassifier(
            n_estimators=200, max_depth=10, min_samples_split=5,
            min_samples_leaf=3, max_features='sqrt', random_state=42, n_jobs=-1
        )))

        if XGBOOST_AVAILABLE:
            models.append(('xgb', XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.05,
                min_child_weight=3, subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=1.0, random_state=42,
                eval_metric='logloss', use_label_encoder=False,
            )))

        if LGB_AVAILABLE:
            models.append(('lgb', lgb.LGBMClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=1.0, random_state=42, verbose=-1,
            )))

        if HISTGB_AVAILABLE:
            models.append(('histgb', HistGradientBoostingClassifier(
                max_iter=200, max_depth=6, learning_rate=0.05,
                l2_regularization=1.0, random_state=42,
            )))

        if len(models) < 2:
            models.append(('gb', GradientBoostingClassifier(
                n_estimators=200, max_depth=5, learning_rate=0.05,
                min_samples_split=5, min_samples_leaf=3, subsample=0.8,
                random_state=42,
            )))

        return models

    def _fit_stacking_with_weights(self, X, y, sample_weights):
        """Custom stacking that passes sample_weight through CV folds."""
        base_models = self._create_base_models_list()
        meta_learner = LogisticRegression(C=1.0, max_iter=1000)

        tscv = TimeSeriesSplit(n_splits=5)
        meta_features = np.full((len(y), len(base_models)), np.nan)

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, w_train = y.iloc[train_idx], sample_weights[train_idx]

            for i, (name, model) in enumerate(base_models):
                cloned = sklearn_clone(model)
                try:
                    cloned.fit(X_train, y_train, sample_weight=w_train)
                except TypeError:
                    cloned.fit(X_train, y_train)
                probas = cloned.predict_proba(X_val)
                meta_features[val_idx, i] = probas[:, 1]

        # Only use rows with all predictions
        valid = ~np.isnan(meta_features).any(axis=1)
        if valid.sum() < 30:
            # Fallback: train best single model
            print("  Stacking fallback: not enough OOF samples, using single model")
            best = base_models[1] if len(base_models) > 1 else base_models[0]
            cloned = sklearn_clone(best[1])
            try:
                cloned.fit(X, y, sample_weight=sample_weights)
            except TypeError:
                cloned.fit(X, y)
            return cloned

        # Fit meta-learner on OOF predictions only (standard stacking, no passthrough)
        meta_X = meta_features[valid]
        meta_learner.fit(meta_X, y.iloc[valid.nonzero()[0]], sample_weight=sample_weights[valid])

        # Refit all base models on full data
        fitted = []
        for name, model in base_models:
            cloned = sklearn_clone(model)
            try:
                cloned.fit(X, y, sample_weight=sample_weights)
            except TypeError:
                cloned.fit(X, y)
            fitted.append((name, cloned))

        return GameStackingModel(fitted, meta_learner)

    def _select_features(self, X, y, feature_names):
        """Select top features explaining 95% cumulative importance."""
        rf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
        rf.fit(X, y)

        importances = rf.feature_importances_
        sorted_idx = np.argsort(importances)[::-1]

        cumulative = np.cumsum(importances[sorted_idx])
        n_keep = np.searchsorted(cumulative, 0.95) + 1
        n_keep = max(n_keep, 30)  # Keep at least 30 features
        n_keep = min(n_keep, len(feature_names))

        selected_idx = sorted_idx[:n_keep]
        selected_names = [feature_names[i] for i in selected_idx]

        print(f"  Feature selection: {len(feature_names)} -> {n_keep} features (95% cumulative importance)")

        return selected_idx, selected_names

    def _calibrate_probabilities(self, X_scaled, y, sample_weights):
        """Train isotonic regression calibrator on OOF predictions."""
        tscv = TimeSeriesSplit(n_splits=5)
        oof_probas = np.full(len(y), np.nan)

        base_model = self._create_base_models_list()[0][1]

        for train_idx, val_idx in tscv.split(X_scaled):
            fold_model = sklearn_clone(base_model)
            try:
                fold_model.fit(X_scaled[train_idx], y.iloc[train_idx],
                               sample_weight=sample_weights[train_idx])
            except TypeError:
                fold_model.fit(X_scaled[train_idx], y.iloc[train_idx])
            oof_probas[val_idx] = fold_model.predict_proba(X_scaled[val_idx])[:, 1]

        valid = ~np.isnan(oof_probas)
        if valid.sum() < 50:
            print("  Calibration: not enough OOF samples, skipping")
            return

        self.calibrator = IsotonicRegression(y_min=0.15, y_max=0.85, out_of_bounds='clip')
        self.calibrator.fit(oof_probas[valid], y.values[valid])
        print("  Probability calibrator trained (isotonic regression)")

    # ── Model Training ─────────────────────────────────────────

    def _get_historical_games(self, seasons=None):
        """Fetch historical game data via BallDontLie API."""
        if seasons is None:
            seasons = ['2024-25', '2023-24', '2022-23']

        all_games = []

        for season in seasons:
            if not season or '-' not in season:
                print(f"  ⚠️ Invalid season format '{season}', skipping")
                continue
            print(f"  Fetching {season} games...")
            try:
                season_int = int(season.split('-')[0])
                bdl = get_bdl_client()

                raw_games = bdl.get_games(seasons=[season_int])

                if not raw_games:
                    continue

                rows = []
                for g in raw_games:
                    game_status = str(g.get('status') or '').lower()
                    if game_status != 'final':
                        continue

                    home = g.get('home_team') or {}
                    visitor = g.get('visitor_team') or {}
                    home_abbrev = str(home.get('abbreviation') or '').upper()
                    visitor_abbrev = str(visitor.get('abbreviation') or '').upper()
                    home_score = g.get('home_team_score')
                    visitor_score = g.get('visitor_team_score')

                    if not home_abbrev or not visitor_abbrev:
                        continue
                    if home_score is None or visitor_score is None:
                        continue

                    home_score = _safe_int(home_score, None)
                    visitor_score = _safe_int(visitor_score, None)
                    if home_score is None or visitor_score is None:
                        continue
                    game_id = g.get('id')
                    game_date_raw = g.get('date') or ''
                    game_date = game_date_raw[:10] if game_date_raw else ''

                    # Home team row
                    rows.append({
                        'GAME_ID': game_id,
                        'GAME_DATE': game_date,
                        'TEAM_ABBREVIATION': home_abbrev,
                        'MATCHUP': f"{home_abbrev} vs. {visitor_abbrev}",
                        'WL': 'W' if home_score > visitor_score else 'L',
                        'PTS': home_score,
                        'PLUS_MINUS': home_score - visitor_score,
                        'SEASON': season,
                    })
                    # Away team row
                    rows.append({
                        'GAME_ID': game_id,
                        'GAME_DATE': game_date,
                        'TEAM_ABBREVIATION': visitor_abbrev,
                        'MATCHUP': f"{visitor_abbrev} @ {home_abbrev}",
                        'WL': 'W' if visitor_score > home_score else 'L',
                        'PTS': visitor_score,
                        'PLUS_MINUS': visitor_score - home_score,
                        'SEASON': season,
                    })

                if rows:
                    df = pd.DataFrame(rows)
                    all_games.append(df)
                    print(f"  {season}: {len(rows)//2} games")

            except Exception as e:
                print(f"  Error fetching {season}: {e}")

        if not all_games:
            return pd.DataFrame()

        return pd.concat(all_games, ignore_index=True)

    def _build_training_data(self, games_df, elo_tracker=None):
        """Build training dataset from historical games with advanced features."""
        if games_df.empty:
            return pd.DataFrame(), pd.Series(dtype='int')

        games_df = games_df.copy()
        games_df['GAME_DATE'] = pd.to_datetime(games_df['GAME_DATE'])
        games_df = games_df.sort_values('GAME_DATE')

        # Build Elo if not provided
        if elo_tracker is None:
            elo_tracker = EloTracker()
            elo_tracker.initialize(list(TEAM_ABBREV_TO_NAME.keys()))

        # We need to process games chronologically and track Elo
        # First, build the matchup list
        matchup_list = []
        seen_ids = set()
        for game_id, group in games_df.groupby('GAME_ID'):
            if len(group) != 2:
                continue

            home = group[group['MATCHUP'].str.contains('vs.')]
            away = group[group['MATCHUP'].str.contains('@')]

            if home.empty or away.empty:
                continue

            home = home.iloc[0]
            away = away.iloc[0]

            matchup_list.append({
                'game_id': game_id,
                'game_date': home['GAME_DATE'],
                'home_abbrev': home['TEAM_ABBREVIATION'],
                'away_abbrev': away['TEAM_ABBREVIATION'],
                'home_won': 1 if home['WL'] == 'W' else 0,
                'margin': home.get('PLUS_MINUS', 0),
                'season': home.get('SEASON', ''),
            })

        matchup_list.sort(key=lambda x: x['game_date'])

        # Process chronologically: compute features then update Elo
        elo_copy = elo_tracker.copy()
        current_season = None
        matchups = []

        for m in matchup_list:
            game_date = m['game_date']
            home_abbrev = m['home_abbrev']
            away_abbrev = m['away_abbrev']

            # Season boundary
            if current_season and m['season'] != current_season:
                elo_copy.new_season()
            current_season = m['season']

            # Get pre-game data
            home_games = games_df[
                (games_df['TEAM_ABBREVIATION'] == home_abbrev) &
                (games_df['GAME_DATE'] < game_date)
            ].sort_values('GAME_DATE')

            away_games = games_df[
                (games_df['TEAM_ABBREVIATION'] == away_abbrev) &
                (games_df['GAME_DATE'] < game_date)
            ].sort_values('GAME_DATE')

            # Need minimum games
            if len(home_games) < 10 or len(away_games) < 10:
                # Still update Elo
                margin = m['margin'] if not pd.isna(m['margin']) else None
                elo_copy.update(home_abbrev, away_abbrev, m['home_won'] == 1, margin)
                continue

            try:
                pre_game_df = games_df[games_df['GAME_DATE'] < game_date]
                features = self._build_historical_features(
                    home_games, away_games, home_abbrev, away_abbrev,
                    all_games_df=pre_game_df, elo_tracker=elo_copy, game_date=game_date
                )
                features['home_won'] = m['home_won']
                matchups.append(features)
            except Exception:
                pass

            # Update Elo with actual result
            margin = m['margin'] if not pd.isna(m['margin']) else None
            elo_copy.update(home_abbrev, away_abbrev, m['home_won'] == 1, margin)

        if not matchups:
            return pd.DataFrame(), pd.Series(dtype='int')

        df = pd.DataFrame(matchups)
        y = df.pop('home_won')

        # Replace NaN/inf
        df = df.replace([np.inf, -np.inf], np.nan).fillna(0)

        return df, y

    def train_model(self, seasons=None):
        """Train the game prediction model (V2 pipeline)."""
        print("Training game prediction model (V2)...")
        print("  Fetching historical games...")

        games_df = self._get_historical_games(seasons)
        if games_df.empty:
            print("  No historical data available")
            return False

        print(f"  Found {len(games_df)} game entries")

        # Build Elo from scratch
        print("  Computing Elo ratings...")
        self.elo_tracker = EloTracker()
        self.elo_tracker.initialize(list(TEAM_ABBREV_TO_NAME.keys()))

        print("  Building training features...")
        X, y = self._build_training_data(games_df, self.elo_tracker)
        if X.empty:
            print("  Could not build training data")
            return False

        # Update Elo tracker to final state
        self.elo_tracker.compute_from_games(games_df)

        print(f"  Training on {len(X)} matchups with {len(X.columns)} features")

        self.feature_names = list(X.columns)

        # Feature selection
        selected_idx, selected_names = self._select_features(X.values, y, self.feature_names)
        self.selected_feature_idx = selected_idx
        X_selected = X.values[:, selected_idx]
        self.feature_names = selected_names

        # Scale features
        X_scaled = self.scaler.fit_transform(X_selected)

        # Recency weights (more aggressive decay for game-level trends)
        n_samples = len(X)
        recency_weights = np.exp(np.linspace(-2.0, 0, n_samples))
        recency_weights = recency_weights / recency_weights.sum() * n_samples

        # Cross-validate first
        print("  Cross-validating...")
        tscv = TimeSeriesSplit(n_splits=5)
        scores = []
        for train_idx, val_idx in tscv.split(X_scaled):
            X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
            w_train = recency_weights[train_idx]

            base_model = self._create_base_models_list()[0][1]
            fold_model = sklearn_clone(base_model)
            try:
                fold_model.fit(X_train, y_train, sample_weight=w_train)
            except TypeError:
                fold_model.fit(X_train, y_train)
            acc = accuracy_score(y_val, fold_model.predict(X_val))
            scores.append(acc)

        print(f"  Cross-validation accuracy: {np.mean(scores):.3f} (+/- {np.std(scores):.3f})")

        # Train stacking ensemble with weights
        print("  Training stacking ensemble...")
        self.model = self._fit_stacking_with_weights(X_scaled, y, recency_weights)

        # Train probability calibrator
        print("  Training calibrator...")
        self._calibrate_probabilities(X_scaled, y, recency_weights)

        # Show top features
        try:
            rf_temp = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42, n_jobs=-1)
            rf_temp.fit(X_scaled, y)
            importances = list(zip(self.feature_names, rf_temp.feature_importances_))
            importances.sort(key=lambda x: x[1], reverse=True)
            print()
            print("  Top 15 features:")
            for name, imp in importances[:15]:
                bar = '█' * int(imp * 200)
                print(f"    {name:<30} {bar} {imp:.4f}")
        except Exception:
            pass

        print()
        print("  Model trained successfully (V2)")
        return True

    def retrain_model(self):
        """Retrain model with current-season data included."""
        print("Retraining model with latest data (V2)...")
        print()

        current_season = '2025-26'
        seasons = [current_season, '2024-25', '2023-24']

        success = self.train_model(seasons=seasons)
        if success:
            self.save_model()
            print()
            print("  Model retrained with current-season data.")

            model_path = GAME_MODEL_DIR / 'game_predictor.pkl'
            data = joblib.load(model_path)
            print(f"  Last trained: {data.get('trained_at', 'unknown')}")
            print(f"  Model version: {data.get('model_version', 'v1.0')}")
        else:
            print("  Retrain failed.")

        return success

    def should_retrain(self, graded_since_train=20):
        """Check if the model should be retrained."""
        model_path = GAME_MODEL_DIR / 'game_predictor.pkl'
        if not model_path.exists():
            model_storage.download_game_model(model_path)
        if not model_path.exists():
            return True

        try:
            data = joblib.load(model_path)
            trained_at = data.get('trained_at')
            if not trained_at:
                return True

            trained_date = datetime.fromisoformat(trained_at)
            days_since = (datetime.now() - trained_date).days

            if days_since >= 7:
                return True

            import db
            stats = db.get_game_accuracy_stats()
            graded = stats.get('graded_predictions', 0)
            last_graded_count = data.get('graded_count_at_train', 0)

            if graded - last_graded_count >= graded_since_train:
                return True

        except Exception:
            return True

        return False

    def save_model(self):
        """Save model, scaler, calibrator, Elo tracker, and feature info."""
        model_path = GAME_MODEL_DIR / 'game_predictor.pkl'

        graded_count = 0
        try:
            import db
            stats = db.get_game_accuracy_stats()
            graded_count = stats.get('graded_predictions', 0)
        except Exception:
            pass

        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'selected_feature_idx': self.selected_feature_idx,
            'calibrator': self.calibrator,
            'elo_tracker': self.elo_tracker,
            'trained_at': datetime.now().isoformat(),
            'graded_count_at_train': graded_count,
            'model_version': 'v2.0',
        }, model_path)

        # L3: upload to Supabase Storage
        model_storage.upload_game_model(model_path)

        print(f"  Model saved to {model_path}")

    def load_model(self):
        """Load saved model from disk or Supabase Storage."""
        model_path = GAME_MODEL_DIR / 'game_predictor.pkl'
        if not model_path.exists():
            model_storage.download_game_model(model_path)
        if not model_path.exists():
            return False

        try:
            data = joblib.load(model_path)
            loaded_model = data['model']
            # Reject stale pkl files that used a different architecture
            if not isinstance(loaded_model, GameStackingModel):
                print(f"Stale model architecture ({type(loaded_model).__name__}); retraining...")
                return False
            # Also validate internal consistency: meta_learner must expect exactly
            # len(base_models_) features (one per base model's OOF probability)
            n_base = len(loaded_model.base_models_)
            n_meta = getattr(loaded_model.meta_learner_, 'n_features_in_', n_base)
            if n_meta != n_base:
                print(f"Stale stacking model: {n_base} base models but meta_learner "
                      f"expects {n_meta} features; retraining...")
                return False
            self.model = loaded_model
            self.scaler = data['scaler']
            self.feature_names = data['feature_names']
            self.selected_feature_idx = data.get('selected_feature_idx')
            self.calibrator = data.get('calibrator')
            self.elo_tracker = data.get('elo_tracker', EloTracker())
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False

    def get_model_info(self):
        """Get info about the current saved model."""
        model_path = GAME_MODEL_DIR / 'game_predictor.pkl'
        if not model_path.exists():
            model_storage.download_game_model(model_path)
        if not model_path.exists():
            return None

        try:
            data = joblib.load(model_path)
            trained_at = data.get('trained_at', 'unknown')
            graded_at_train = data.get('graded_count_at_train', 0)

            age_str = 'unknown'
            if trained_at != 'unknown':
                days = (datetime.now() - datetime.fromisoformat(trained_at)).days
                age_str = f"{days} day(s) ago"

            model_type = type(data.get('model')).__name__
            if model_type == 'GameStackingModel':
                n_base = len(data['model'].base_models_)
                model_type = f"Stacking ({n_base} base models)"

            return {
                'trained_at': trained_at,
                'age': age_str,
                'features': len(data.get('feature_names', [])),
                'graded_at_train': graded_at_train,
                'model_type': model_type,
                'model_version': data.get('model_version', 'v1.0'),
                'has_calibrator': data.get('calibrator') is not None,
                'has_elo': data.get('elo_tracker') is not None,
            }
        except Exception:
            return None

    # ── Prediction ─────────────────────────────────────────────

    def predict_game(self, home_team, away_team, game_date=None):
        """Predict a single game."""
        if self.model is None:
            if not self.load_model():
                self.train_model()
                if self.model is None:
                    return None

        features = self.build_game_features(home_team, away_team, game_date)
        key_factors = self._generate_key_factors(features)

        # Ensure feature alignment
        feature_vector = [features.get(f, 0) for f in self.feature_names]
        X = np.array([feature_vector])
        X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)
        X_scaled = self.scaler.transform(X)

        # Predict
        proba = self.model.predict_proba(X_scaled)[0]
        home_win_prob = float(proba[1])
        away_win_prob = float(proba[0])

        # Apply calibration
        if self.calibrator is not None:
            home_win_prob = float(self.calibrator.predict([home_win_prob])[0])
            away_win_prob = 1.0 - home_win_prob

        # Hard cap: NBA games are rarely more predictable than 85/15
        home_win_prob = float(np.clip(home_win_prob, 0.15, 0.85))
        away_win_prob = 1.0 - home_win_prob

        predicted_winner = home_team if home_win_prob > 0.5 else away_team
        confidence = max(home_win_prob, away_win_prob)

        # Edge analysis
        edge = abs(home_win_prob - 0.5) * 2
        if edge < 0.05:
            bet_quality = 'NO_BET'
        elif edge < 0.10:
            bet_quality = 'LEAN'
        elif edge < 0.20:
            bet_quality = 'BET'
        else:
            bet_quality = 'STRONG_BET'

        # Get team info
        team_stats = self.get_team_stats()
        home_stats = team_stats.get(home_team, {})
        away_stats = team_stats.get(away_team, {})

        home_w = home_stats.get('w', 0)
        home_l = home_stats.get('l', 0)
        away_w = away_stats.get('w', 0)
        away_l = away_stats.get('l', 0)

        return {
            'matchup': {
                'home_team': {
                    'team_id': self.team_abbrev_to_id.get(home_team, 0),
                    'team_abbrev': home_team,
                    'team_name': TEAM_ABBREV_TO_NAME.get(home_team, home_team),
                    'record': f"{home_w}-{home_l}",
                    'off_rating': home_stats.get('off_rating', 110),
                    'def_rating': home_stats.get('def_rating', 110),
                    'net_rating': home_stats.get('net_rating', 0),
                    'pace': home_stats.get('pace', 100),
                },
                'away_team': {
                    'team_id': self.team_abbrev_to_id.get(away_team, 0),
                    'team_abbrev': away_team,
                    'team_name': TEAM_ABBREV_TO_NAME.get(away_team, away_team),
                    'record': f"{away_w}-{away_l}",
                    'off_rating': away_stats.get('off_rating', 110),
                    'def_rating': away_stats.get('def_rating', 110),
                    'net_rating': away_stats.get('net_rating', 0),
                    'pace': away_stats.get('pace', 100),
                },
                'game_date': str(game_date or datetime.now().strftime('%Y-%m-%d'))[:10],
            },
            'predicted_winner': predicted_winner,
            'home_win_prob': round(home_win_prob * 100, 1),
            'away_win_prob': round(away_win_prob * 100, 1),
            'confidence': round(confidence * 100, 1),
            'edge': round(edge * 100, 1),
            'bet_quality': bet_quality,
            'calibrated': self.calibrator is not None,
            'key_factors': key_factors,
        }

    def predict_all_today(self):
        """Predict all of today's games."""
        games = self.get_todays_games()
        if not games:
            return []

        predictions = []
        for game in games:
            pred = self.predict_game(
                game['home_team'],
                game['away_team'],
                game.get('game_date'),
            )
            if pred:
                pred['matchup']['game_time'] = game.get('game_time', '')
                predictions.append(pred)

        return predictions


# ── CLI ────────────────────────────────────────────────────────

def _print_header():
    print()
    print("=" * 60)
    print("  NBA GAME WINNER PREDICTOR V2")
    print("  Stacking Ensemble + Elo + Calibration")
    print("=" * 60)
    print()


def _print_prediction(pred):
    matchup = pred['matchup']
    home = matchup['home_team']
    away = matchup['away_team']
    winner = pred['predicted_winner']
    home_prob = pred['home_win_prob']
    away_prob = pred['away_win_prob']
    confidence = pred['confidence']
    edge = pred.get('edge', 0)
    bet_quality = pred.get('bet_quality', '')

    print(f"  {away['team_abbrev']} ({away['record']})  @  {home['team_abbrev']} ({home['record']})")
    if matchup.get('game_time'):
        print(f"  {matchup['game_time']}")
    print()

    # Probability bar
    bar_width = 40
    home_blocks = round(home_prob / 100 * bar_width)
    away_blocks = bar_width - home_blocks
    bar = f"  {'█' * away_blocks}{'░' * home_blocks}"
    print(f"  {away['team_abbrev']} {away_prob:.1f}%{bar}{home_prob:.1f}% {home['team_abbrev']}")
    print()

    quality_label = f"  [{bet_quality}]" if bet_quality else ""
    calibrated_label = " (calibrated)" if pred.get('calibrated') else ""
    print(f"  PREDICTION: {winner} WINS  (Confidence: {confidence:.1f}%, Edge: {edge:.1f}%){quality_label}{calibrated_label}")
    print()

    # Key factors
    if pred.get('key_factors'):
        print("  Key Factors:")
        for f in pred['key_factors']:
            impact_icon = "!!!" if f['impact'] == 'MAJOR' else "!! " if f['impact'] == 'MODERATE' else "!  "
            favors_team = home['team_abbrev'] if f['favors'] == 'HOME' else away['team_abbrev']
            print(f"    [{impact_icon}] {f['description']}  -> {favors_team}")
        print()

    # Team stats
    print(f"  {'':>12} {'OFF RTG':>8} {'DEF RTG':>8} {'NET RTG':>8} {'PACE':>6}")
    print(f"  {away['team_abbrev']:>12} {away['off_rating']:>8.1f} {away['def_rating']:>8.1f} {away['net_rating']:>+8.1f} {away['pace']:>6.1f}")
    print(f"  {home['team_abbrev']:>12} {home['off_rating']:>8.1f} {home['def_rating']:>8.1f} {home['net_rating']:>+8.1f} {home['pace']:>6.1f}")


def _print_accuracy_stats(stats):
    """Print accuracy statistics."""
    print("  PREDICTION ACCURACY")
    print("=" * 60)
    print()

    graded = stats['graded_predictions']
    if graded == 0:
        print("  No graded predictions yet.")
        print("  Run with --grade to grade completed games.")
        print()
        return

    correct = stats['correct']
    incorrect = stats['incorrect']
    accuracy = stats['accuracy']

    print(f"  Record:     {correct}W - {incorrect}L")
    print(f"  Accuracy:   {accuracy:.1f}%")
    print(f"  Recent:     {stats['recent_streak']}")
    print(f"  Total:      {stats['total_predictions']} predictions ({graded} graded)")
    print()

    by_conf = stats.get('by_confidence_range', {})
    if by_conf:
        print("  BY CONFIDENCE RANGE")
        print(f"  {'Range':<12} {'Record':>10} {'Accuracy':>10}")
        print(f"  {'-'*12} {'-'*10} {'-'*10}")
        for range_label, data in sorted(by_conf.items()):
            wrong = data['total'] - data['correct']
            print(f"  {range_label:<12} {data['correct']}W-{wrong}L{' ':>{7 - len(str(data['correct'])) - len(str(wrong))}} {data['accuracy']:>9.1f}%")
        print()


def _print_history(predictions):
    """Print prediction history."""
    if not predictions:
        print("  No prediction history found.")
        print()
        return

    print(f"  PREDICTION HISTORY ({len(predictions)} games)")
    print("=" * 60)
    print()
    print(f"  {'Date':<12} {'Matchup':<18} {'Pick':<6} {'Result':<8} {'Prob':>6}")
    print(f"  {'-'*12} {'-'*18} {'-'*6} {'-'*8} {'-'*6}")

    for p in predictions:
        date = p.get('game_date', '')[:10]
        home = p.get('home_team', '???')
        away = p.get('away_team', '???')
        matchup = f"{away} @ {home}"
        pick = p.get('predicted_winner', '???')
        confidence = p.get('confidence') or p.get('home_win_prob', 50)

        actual = p.get('actual_winner')
        correct = p.get('correct')

        if correct is None:
            result = "PENDING"
        elif correct == 1:
            result = "  WIN"
        else:
            result = " LOSS"

        print(f"  {date:<12} {matchup:<18} {pick:<6} {result:<8} {confidence:>5.1f}%")

    print()


def main():
    import argparse
    import db

    parser = argparse.ArgumentParser(description="NBA Game Winner Predictor V2")
    parser.add_argument('--train', action='store_true', help='Train model on historical data')
    parser.add_argument('--retrain', action='store_true', help='Retrain model with current-season data')
    parser.add_argument('--home', type=str, help='Home team abbreviation (e.g., BOS)')
    parser.add_argument('--away', type=str, help='Away team abbreviation (e.g., LAL)')
    parser.add_argument('--today', action='store_true', help="Predict all of today's games")
    parser.add_argument('--grade', action='store_true', help='Auto-grade completed predictions')
    parser.add_argument('--stats', action='store_true', help='Show prediction accuracy stats')
    parser.add_argument('--history', type=int, nargs='?', const=7, metavar='DAYS',
                        help='Show prediction history (default: last 7 days)')
    parser.add_argument('--save', action='store_true', help='Save predictions to database')
    parser.add_argument('--model-info', action='store_true', help='Show current model info')
    args = parser.parse_args()

    _print_header()

    # Model info
    if args.model_info:
        predictor = GamePredictor()
        info = predictor.get_model_info()
        if info:
            print("  MODEL INFO")
            print("=" * 60)
            print(f"  Type:           {info['model_type']}")
            print(f"  Version:        {info['model_version']}")
            print(f"  Trained:        {info['trained_at']}")
            print(f"  Age:            {info['age']}")
            print(f"  Features:       {info['features']}")
            print(f"  Calibrated:     {info['has_calibrator']}")
            print(f"  Elo Ratings:    {info['has_elo']}")
            print(f"  Graded at train: {info['graded_at_train']} predictions")
            print()

            if predictor.should_retrain():
                print("  Model is due for retraining. Run: python3 game_predictor.py --retrain")
                print()
        else:
            print("  No model found. Run: python3 game_predictor.py --train")
            print()
        return

    # Stats mode
    if args.stats:
        stats = db.get_game_accuracy_stats()
        _print_accuracy_stats(stats)
        return

    # History mode
    if args.history is not None:
        predictions = db.get_game_predictions(args.history)
        _print_history(predictions)

        stats = db.get_game_accuracy_stats()
        if stats['graded_predictions'] > 0:
            print(f"  Overall: {stats['correct']}W-{stats['incorrect']}L ({stats['accuracy']:.1f}%)")
            print()
        return

    # Grade mode
    if args.grade:
        print("  Auto-grading completed predictions...")
        print()
        result = db.auto_grade_game_predictions()

        if result['graded_count'] == 0:
            print("  No predictions to grade (games may not be final yet).")
        else:
            print(f"  Graded {result['graded_count']} prediction(s):")
            print()
            for r in result.get('results', []):
                mark = "WIN" if r['correct'] else "LOSS"
                print(f"    [{mark}] {r['away_team']} @ {r['home_team']}  "
                      f"Pick: {r['predicted_winner']}  "
                      f"Actual: {r['actual_winner']} ({r['away_pts']}-{r['home_pts']})")
            print()

        if result.get('errors'):
            print(f"  Errors: {len(result['errors'])}")
            for err in result['errors']:
                print(f"    {err}")
            print()

        stats = db.get_game_accuracy_stats()
        if stats['graded_predictions'] > 0:
            print(f"  Overall: {stats['correct']}W-{stats['incorrect']}L ({stats['accuracy']:.1f}%)")
            print()

        predictor = GamePredictor()
        if predictor.should_retrain():
            print("  Model is due for retraining (new results available).")
            print("  Run: python3 game_predictor.py --retrain")
            print()
        return

    predictor = GamePredictor()

    # Retrain mode
    if args.retrain:
        predictor.retrain_model()
        return

    # Train mode
    if args.train:
        print("Training model on historical data...")
        print()
        if predictor.train_model():
            predictor.save_model()
            print()
            print("Model trained and saved successfully.")
        else:
            print("Training failed.")
        return

    # Single matchup
    if args.home and args.away:
        home = args.home.upper()
        away = args.away.upper()

        if home not in TEAM_ABBREV_TO_NAME:
            print(f"  Unknown team: {home}")
            return
        if away not in TEAM_ABBREV_TO_NAME:
            print(f"  Unknown team: {away}")
            return

        print(f"  Predicting: {away} @ {home}")
        print("-" * 60)

        pred = predictor.predict_game(home, away)
        if pred:
            _print_prediction(pred)

            if args.save:
                matchup = pred['matchup']
                db.save_game_prediction({
                    'game_date': matchup.get('game_date', datetime.now().strftime('%Y-%m-%d')),
                    'home_team': home,
                    'away_team': away,
                    'home_team_id': matchup['home_team'].get('team_id'),
                    'away_team_id': matchup['away_team'].get('team_id'),
                    'predicted_winner': pred['predicted_winner'],
                    'home_win_prob': pred['home_win_prob'],
                    'away_win_prob': pred['away_win_prob'],
                    'confidence': pred['confidence'],
                    'key_factors': pred.get('key_factors', []),
                })
                print("  Prediction saved to database.")
        else:
            print("  Could not generate prediction.")
        print("-" * 60)
        return

    # Today's games (default)
    print("  Fetching today's games...")
    print()

    predictions = predictor.predict_all_today()

    if not predictions:
        print("  No games scheduled for today.")
        return

    print(f"  Found {len(predictions)} game(s)")
    print()

    for i, pred in enumerate(predictions):
        print("-" * 60)
        _print_prediction(pred)

    print("-" * 60)
    print()

    # Auto-save
    if args.save:
        import db as _db
        for pred in predictions:
            matchup = pred['matchup']
            home = matchup['home_team']
            away = matchup['away_team']
            _db.save_game_prediction({
                'game_date': matchup.get('game_date', datetime.now().strftime('%Y-%m-%d')),
                'home_team': home['team_abbrev'],
                'away_team': away['team_abbrev'],
                'home_team_id': home.get('team_id'),
                'away_team_id': away.get('team_id'),
                'predicted_winner': pred['predicted_winner'],
                'home_win_prob': pred['home_win_prob'],
                'away_win_prob': pred['away_win_prob'],
                'confidence': pred['confidence'],
                'key_factors': pred.get('key_factors', []),
            })
        print(f"  {len(predictions)} prediction(s) saved to database.")

    print(f"  {len(predictions)} game(s) predicted.")
    print()


if __name__ == "__main__":
    main()
