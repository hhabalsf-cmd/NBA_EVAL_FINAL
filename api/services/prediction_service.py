"""Service layer wrapping existing ML prediction classes."""
import fcntl
import json
import logging
import sys
import time
import unicodedata

logger = logging.getLogger(__name__)
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Generator
import asyncio
import pandas as pd
import statistics

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sleeper_client import get_headshot_url as get_sleeper_headshot
from season_utils import get_recent_seasons

# Lazy import cache — nba_evaluator (and TensorFlow) only loads on first prediction
_nba_ev = None

def _load_nba_evaluator():
    """Lazy-load nba_evaluator so TensorFlow only loads on first prediction request."""
    global _nba_ev
    if _nba_ev is None:
        import nba_evaluator as _mod
        _nba_ev = _mod
    return _nba_ev


# BDL prop_type value -> our stat abbreviation
_BDL_PROP_TYPE_MAP: Dict[str, str] = {
    "points": "PTS",
    "rebounds": "REB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "turnovers": "TOV",
    "three_point_field_goals_made": "FG3M",
    "pts_reb_ast": "PRA",
    "pts_reb": "PR",
    "pts_ast": "PA",
    "reb_ast": "RA",
    "blocks_steals": "BS",
    "minutes": "MIN",
}


def _fetch_todays_props() -> list:
    """Fetch today's player props from the configured line sources.

    Delegates to line_sources.fetch_todays_props(): Odds API first, then
    manually entered lines (manual_lines table). Returns a list of dicts:
        {player, stat, consensus_line, home_team, away_team}
    """
    from line_sources import fetch_todays_props

    return fetch_todays_props()

def _prediction_cache_path(player_name: str) -> Path:
    from zoneinfo import ZoneInfo
    key = player_name.replace(" ", "_")
    date_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    return PRED_CACHE_DIR / f"{key}_{date_str}.json"


def _load_prediction_cache(player_name: str) -> Optional[Dict]:
    """Return today's cached prediction data, or None if absent/stale."""
    path = _prediction_cache_path(player_name)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _save_prediction_cache(player_name: str, data: Dict) -> None:
    """Write prediction data to today's cache file."""
    PRED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _prediction_cache_path(player_name)
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # Cache write failure is non-fatal


@contextmanager
def _player_model_lock(player_name: str):
    """Exclusive per-player file lock to prevent concurrent model overwrites."""
    ev = _load_nba_evaluator()
    ev.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = ev.MODEL_DIR / f"{player_name.replace(' ', '_')}.lock"
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


class PredictionService:
    """Wraps MLPredictor and FeatureEngineer for API use."""

    def __init__(self):
        self._scraper = None
        self._evaluator = None
        self._team_stats_cache = None
        self._team_stats_cache_time: float = 0
        self._injuries_cache = None
        self._injuries_cache_time: float = 0
        self._odds_cache: Optional[Dict] = None
        self._odds_cache_time: float = 0
        self._CACHE_TTL = 60 * 60       # 1 hour for stats/injuries
        self._ODDS_CACHE_TTL = 30 * 60  # 30 minutes

    @property
    def scraper(self):
        if self._scraper is None:
            ev = _load_nba_evaluator()
            self._scraper = ev.NBADataScraper()
        return self._scraper

    @property
    def evaluator(self):
        if self._evaluator is None:
            ev = _load_nba_evaluator()
            self._evaluator = ev.LineEvaluator()
        return self._evaluator

    def get_team_stats(self) -> Dict:
        """Get cached team defensive stats. Refreshes every hour."""
        now = time.time()
        if self._team_stats_cache is None or (now - self._team_stats_cache_time) >= self._CACHE_TTL:
            self._team_stats_cache = self.scraper.get_team_defensive_stats()
            self._team_stats_cache_time = now
        return self._team_stats_cache

    def get_injuries(self) -> Dict:
        """Get cached injury report. Refreshes every hour."""
        now = time.time()
        if self._injuries_cache is None or (now - self._injuries_cache_time) >= self._CACHE_TTL:
            self._injuries_cache = self.scraper.get_injury_report()
            self._injuries_cache_time = now
        return self._injuries_cache

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a player name: strip accents, lowercase, strip whitespace."""
        nfkd = unicodedata.normalize('NFKD', name)
        ascii_name = ''.join(c for c in nfkd if not unicodedata.combining(c))
        return ascii_name.lower().strip()

    def get_player_odds(self, player_name: str) -> Dict:
        """Return today's consensus prop lines for *player_name* (30-min cache)."""
        now = time.time()

        # Refresh cache if stale
        if self._odds_cache is None or (now - self._odds_cache_time) > self._ODDS_CACHE_TTL:
            try:
                props = _fetch_todays_props()
            except Exception:
                props = []
            # Build lookup: normalized_name -> {stat -> line}
            lookup: Dict[str, Dict[str, float]] = {}
            for prop in props:
                norm = self._normalize_name(prop.get('player', ''))
                stat = prop.get('stat')
                line = prop.get('consensus_line')
                if norm and stat and line is not None:
                    lookup.setdefault(norm, {})[stat] = line
            self._odds_cache = lookup
            self._odds_cache_time = now

        target = self._normalize_name(player_name)
        # Exact match first
        if target in self._odds_cache:
            lines = self._odds_cache[target]
            return {**lines, 'found': True}

        # Partial / fuzzy match: check if target words are a subset of any key
        for norm_key, lines in self._odds_cache.items():
            if target in norm_key or norm_key in target:
                return {**lines, 'found': True}

        return {'found': False}

    def _augment_with_nba_api_players(self, player_list: list) -> list:
        """Merge all active players from nba_api into the given list (deduplicated)."""
        try:
            from nba_api.stats.static import players as nba_players
            active_list = nba_players.get_active_players()
            before = len(player_list)
            # Deduplicate by normalized name to handle accents vs plain ascii
            seen_normalized = {p['normalized_full_name'] for p in player_list}
            
            for p in active_list:
                full_name = p['full_name']
                norm = self._normalize_name(full_name)
                if norm not in seen_normalized:
                    parts = full_name.split(' ', 1)
                    player_list.append({
                        'id': p['id'], # Use real NBA ID instead of 0
                        'full_name': full_name,
                        'normalized_full_name': norm,
                        'first_name': parts[0] if parts else '',
                        'last_name': parts[1] if len(parts) > 1 else '',
                        'is_active': True,
                    })
                    seen_normalized.add(norm)
            logger.info("nba_api augmented %d additional players", len(player_list) - before)
        except ImportError:
            logger.debug("nba_api not installed — using BDL player list only")
        except Exception as exc:
            logger.warning("Failed to inject nba_api players: %s", exc)
        return player_list

    # Class-level cache for current season players
    _current_season_players: list = None
    _current_season_players_time: float = 0
    _PLAYERS_CACHE_TTL = 60 * 60 * 6  # 6 hours

    def _refresh_players_sync(self) -> None:
        """Refresh player list from Supabase current-season game logs. Run via executor only.

        Uses the same current-season query as _get_current_season_players so the
        cache always contains only players who have actually logged stats this season
        (i.e. no historical/inactive players from old BDL data).
        """
        try:
            import db as _db
            conn = _db.get_connection()
            try:
                with conn.cursor() as cur:
                    seasons = tuple(get_recent_seasons(2))
                    cur.execute(
                        """
                        SELECT DISTINCT player_id AS id,
                               MAX(player_name) AS full_name
                        FROM player_game_logs
                        WHERE season = ANY(%s) AND player_name IS NOT NULL
                        GROUP BY player_id
                        """,
                        (list(seasons),),
                    )
                    rows = cur.fetchall()
            finally:
                _db.put_connection(conn)

            player_list = []
            for row in rows:
                full_name = str(row['full_name'] or '')
                if not full_name:
                    continue
                parts = full_name.split(' ', 1)
                player_list.append({
                    'id': int(row['id']),
                    'full_name': full_name,
                    'normalized_full_name': self._normalize_name(full_name),
                    'first_name': parts[0] if parts else '',
                    'last_name': parts[1] if len(parts) > 1 else '',
                    'is_active': True,
                })

            if player_list:
                player_list = self._augment_with_nba_api_players(player_list)
                PredictionService._current_season_players = player_list
                PredictionService._current_season_players_time = time.time()
        except Exception:
            pass  # Keep existing cache; _get_current_season_players handles fallback

    def _get_current_season_players(self) -> list:
        """Get current season players (cached 6 hours). Never blocks — returns stale/static if cold."""
        now = time.time()
        if (PredictionService._current_season_players is not None
                and now - PredictionService._current_season_players_time < self._PLAYERS_CACHE_TTL):
            return PredictionService._current_season_players
        # Cache cold: return fast static list immediately so search doesn't block
        try:
            import db as _db
            conn = _db.get_connection()
            try:
                with conn.cursor() as cur:
                    # Include current season AND most recent historical season so
                    # the list is populated even before current-season data accumulates
                    seasons = tuple(get_recent_seasons(2))
                    cur.execute(
                        """
                        SELECT DISTINCT player_id AS id,
                               MAX(player_name) AS full_name
                        FROM player_game_logs
                        WHERE season = ANY(%s) AND player_name IS NOT NULL
                        GROUP BY player_id
                        """,
                        (list(seasons),),
                    )
                    rows = cur.fetchall()
            finally:
                _db.put_connection(conn)

            static = []
            for row in rows:
                full_name = str(row['full_name'] or '')
                parts = full_name.split(' ', 1)
                static.append({
                    'id': int(row['id']),
                    'full_name': full_name,
                    'normalized_full_name': self._normalize_name(full_name),
                    'first_name': parts[0] if parts else '',
                    'last_name': parts[1] if len(parts) > 1 else '',
                    'is_active': True,
                })
        except Exception:
            static = []
            
        static = self._augment_with_nba_api_players(static)
            
        if PredictionService._current_season_players is None:
            # Seed cache with static list so concurrent requests don't all try to refresh
            PredictionService._current_season_players = static
            PredictionService._current_season_players_time = 0  # still expired — executor will refresh
        return static

    def search_players(self, query: str) -> list:
        """Search for players by name.

        Uses solely the local game_logs cache (augmented with nba_api active players)
        to ensure zero latency and only surface players we have data for.
        """
        if not query or not query.strip():
            return []

        return self._search_players_local(query)

    def _search_players_local(self, query: str) -> list:
        """Search local game_logs cache — fallback when BDL is unavailable."""
        active_players = self._get_current_season_players()
        results = []
        normalized_query = self._normalize_name(query)
        search_terms = normalized_query.split()

        for p in active_players:
            norm_name = p.get('normalized_full_name') or self._normalize_name(p['full_name'])
            if all(term in norm_name for term in search_terms):
                results.append({
                    'id': p.get('bdl_id', p['id']),
                    'full_name': p['full_name'],
                    'first_name': p.get('first_name', ''),
                    'last_name': p.get('last_name', ''),
                    'team_id': None,
                    'team_abbreviation': '',
                    'team_name': '',
                    'headshot_url': get_sleeper_headshot(p['full_name']),
                })
                if len(results) >= 10:
                    break

        return results

    def get_player_info(self, player_name: str) -> Optional[Dict]:
        """Get player info by name."""
        return self.scraper.get_player_info(player_name)

    async def predict_with_progress(
        self,
        player_name: str,
        model_type: str = "gradient_boost",
        use_ensemble: bool = False,
        retrain: bool = False
    ) -> Generator[Dict[str, Any], None, None]:
        """Generate predictions with progress updates for SSE."""
        ev = _load_nba_evaluator()

        # Stage 1: Fetching player data
        yield {
            "stage": "fetching_data",
            "progress": 10,
            "message": f"Looking up {player_name}..."
        }

        player_info = self.scraper.get_player_info(player_name)
        if not player_info:
            yield {
                "stage": "error",
                "progress": 100,
                "message": f"Player '{player_name}' not found",
                "data": None
            }
            return

        # Check prediction cache — skip on explicit retrain
        canonical_name = player_info['player_name']
        if not retrain:
            cached = _load_prediction_cache(canonical_name)
            if cached is not None:
                yield {
                    "stage": "fetching_data",
                    "progress": 50,
                    "message": "Loading today's cached prediction..."
                }
                yield {
                    "stage": "complete",
                    "progress": 100,
                    "message": "Predictions complete",
                    "data": cached,
                    "from_cache": True,
                }
                return

        yield {
            "stage": "fetching_data",
            "progress": 20,
            "message": "Fetching player data..."
        }

        # Fetch game log, next game, team stats, and injuries in parallel
        # All four are independent after player_info is resolved
        loop = asyncio.get_event_loop()
        game_log, game_info, team_stats, injuries = await asyncio.gather(
            loop.run_in_executor(None, self.scraper.get_player_game_log, player_info['player_id']),
            loop.run_in_executor(None, self.scraper.get_player_next_game, player_info),
            loop.run_in_executor(None, self.get_team_stats),
            loop.run_in_executor(None, self.get_injuries),
        )

        if game_log is None or game_log.empty:
            yield {
                "stage": "error",
                "progress": 100,
                "message": "Could not fetch game log",
                "data": None
            }
            return

        yield {
            "stage": "training_model",
            "progress": 45,
            "message": "Engineering features..."
        }

        # Create features (CPU-bound, offload to thread pool)
        df_features = await loop.run_in_executor(
            None,
            lambda: ev.FeatureEngineer.create_features(
                game_log,
                player_info=player_info,
                game_info=game_info,
                injuries=injuries,
                team_stats=team_stats
            )
        )

        # df_features ends in a synthetic row for the UPCOMING game (create_features
        # was given game_info), which is what makes the served vector describe the
        # next game instead of the last one played. Everything that SUMMARISES
        # completed games — L10 averages, the game-log table, minutes — must use
        # this frame instead, or it silently picks up a stat-less future row.
        completed_features = ev.drop_upcoming_rows(df_features)

        # Stage 3: Training/loading model
        yield {
            "stage": "training_model",
            "progress": 55,
            "message": "Loading or training model..."
        }

        predictor = ev.MLPredictor(model_type=model_type, use_ensemble=use_ensemble)

        # Enforce once-per-night retrain policy
        retrain_skipped = False
        if retrain and not ev.should_retrain(player_info['player_name']):
            retrain = False
            retrain_skipped = True

        # Offload blocking model load/train/save to thread pool so the
        # event loop stays responsive for SSE and other requests.
        def _load_or_train():
            with _player_model_lock(player_info['player_name']):
                loaded = not retrain and predictor.load(player_info['player_name'])
                if loaded:
                    predictor.update(df_features)
                else:
                    if not predictor.train(df_features):
                        return False, False  # train_failed, loaded
                predictor.save(player_info['player_name'])
            return True, loaded  # success, loaded

        success, loaded = await loop.run_in_executor(None, _load_or_train)

        if not success:
            yield {
                "stage": "error",
                "progress": 100,
                "message": "Insufficient data for training",
                "data": None
            }
            return

        yield {
            "stage": "training_model",
            "progress": 70,
            "message": "Model already retrained tonight — using latest data..." if retrain_skipped else (
                "Updating model with recent games..." if loaded else "Training new model..."
            )
        }

        # Stage 4: Making predictions
        yield {
            "stage": "predicting",
            "progress": 80,
            "message": "Generating predictions..."
        }

        # Get opponent context
        opponent = game_info.get('opponent', '') if game_info else ''
        is_home = game_info.get('is_home', 0) if game_info else 0
        opp_ctx = ev.FeatureEngineer.extract_opp_stats(team_stats, opponent)

        # Get injuries context
        team_abbrev = player_info.get('team_abbrev', '')
        injuries_team = injuries.get(team_abbrev, {}).get('out', 0) if injuries else 0
        injuries_opp = injuries.get(opponent, {}).get('out', 0) if injuries else 0

        # Get vs stats
        vs_stats = self.scraper.get_vs_team_stats(player_info['player_id'], opponent) if opponent else None

        # Days rest before the UPCOMING game. df_features carries the synthetic
        # next-game row (create_features was given game_info), so iloc[-1] is a
        # future date -- serve_days_rest reads that row's own schedule-derived
        # DAYS_REST and only falls back to the wall-clock formula without one.
        days_rest = ev.FeatureEngineer.serve_days_rest(df_features, default=2)

        # Check if the player themselves is DTD/questionable
        player_injury_status = self.scraper.get_player_injury_status(
            player_info['player_name'], injuries
        ) if injuries else {'is_injured': False}
        player_is_questionable = (
            player_injury_status.get('is_injured', False)
            and player_injury_status.get('status') in ('questionable', 'doubtful')
        )

        # Compute schedule density & travel context for Phase 3 features
        schedule_ctx = {}
        try:
            # Schedule density and the travel origin are both properties of games
            # already PLAYED, so the synthetic next-game row must be excluded --
            # otherwise the upcoming game counts itself in games_in_last_7 and
            # the travel origin becomes the destination.
            completed = completed_features
            game_dates = pd.to_datetime(completed['GAME_DATE'])
            now = datetime.now()
            recent_7 = game_dates[game_dates >= (now - timedelta(days=7))]
            recent_4 = game_dates[game_dates >= (now - timedelta(days=4))]
            schedule_ctx['games_in_last_7'] = len(recent_7)
            schedule_ctx['games_in_last_4'] = len(recent_4)

            # Travel: last COMPLETED game location → next game location
            team_abbrev = player_info.get('team_abbrev', '')
            last_opp = completed['MATCHUP'].iloc[-1]
            last_is_home = 'vs.' in str(last_opp)
            last_loc = team_abbrev if last_is_home else str(last_opp).split(' ')[-1]
            next_loc = team_abbrev if is_home else opponent
            schedule_ctx['travel_miles'] = ev._travel_miles(last_loc, next_loc)
            schedule_ctx['timezone_shift'] = ev._timezone_shift(last_loc, next_loc)
            schedule_ctx['is_altitude'] = 1 if (not is_home and opponent in ev.HIGH_ALTITUDE_TEAMS) else 0
        except Exception:
            pass  # Defaults in get_prediction_features handle missing values

        # The BDL odds fetch that used to live here fed VEGAS_GAME_TOTAL_NORM /
        # VEGAS_SPREAD_NORM / VEGAS_IMPLIED_TEAM_TOTAL_NORM. Those three were
        # declared in FEATURE_COLS but never built by create_features, so no
        # model was ever trained on them and predict() zero-filled them anyway.
        # They were removed 2026-08-22 along with this request.

        # Offload prediction to thread pool (matrix operations)
        def _run_prediction():
            pred_features = ev.FeatureEngineer.get_prediction_features(
                df_features,
                is_home=is_home,
                opponent=opponent,
                days_rest=days_rest,
                vs_stats=vs_stats,
                player_info=player_info,
                **opp_ctx,
                **schedule_ctx,
            )
            estimated_minutes = ev.FeatureEngineer.estimate_minutes(
                df_features, is_home, days_rest, injuries_team,
                games_in_last_7=schedule_ctx.get('games_in_last_7', 2),
                travel_miles=schedule_ctx.get('travel_miles', 0),
                is_altitude=schedule_ctx.get('is_altitude', 0),
                opp_net_rating=opp_ctx.get('opp_net_rating', 0),
            )
            predictor._update_recent_averages(df_features)
            preds = predictor.predict(pred_features, estimated_minutes=estimated_minutes)
            preds = predictor.apply_injury_boost(preds, injuries_team, injuries_opp)
            preds = predictor.apply_blowout_discount(
                preds,
                opp_net_rating=opp_ctx.get('opp_net_rating', 0),
                avg_min_l10=estimated_minutes,
            )

            # DTD / questionable self-injury dampener — player returning
            # from injury or listed as questionable gets predictions reduced.
            # They typically play fewer minutes or on a minutes restriction.
            if player_is_questionable:
                dampening = 0.88  # 12% reduction
                preds = {
                    stat: val * dampening for stat, val in preds.items()
                }
                # PRA needs no re-reconciliation here: the dampening is
                # uniform across stats, so the scaled PRA is exactly the
                # 85/15 blend of the scaled components (see pra_utils).
                # The old pure-sum overwrite silently discarded the blend.

            return pred_features, preds

        pred_features, predictions = await loop.run_in_executor(None, _run_prediction)

        yield {
            "stage": "predicting",
            "progress": 90,
            "message": "Calculating confidence intervals..."
        }

        # Pre-compute L10 averages once instead of per-stat
        l10 = completed_features.tail(10)
        l10_avgs = {col: round(l10[col].mean(), 1) for col in ['PTS', 'REB', 'AST'] if col in l10.columns}
        if all(c in l10.columns for c in ['PTS', 'REB', 'AST']):
            l10_avgs['PRA'] = round((l10['PTS'] + l10['REB'] + l10['AST']).mean(), 1)

        # Build response
        stat_predictions = {}
        for stat, pred in predictions.items():
            # Pass the serve-time feature row so get_confidence can reach the
            # quantile/CQR band. Without it the `features_df is not None` guard
            # fails and every API prediction silently falls back to historical
            # variance, bypassing the calibrated interval entirely.
            confidence_info = predictor.get_confidence(
                df_features, stat, pred, pred_features
            )
            uncertainty = predictor.get_prediction_uncertainty(pred_features, stat)

            stat_predictions[stat] = {
                "stat": stat,
                "prediction": round(pred, 1),
                "confidence": confidence_info.get('confidence', 70),
                "range_low": round(confidence_info.get('low', pred * 0.8), 1),
                "range_high": round(confidence_info.get('high', pred * 1.2), 1),
                "uncertainty_std": round(uncertainty['std'], 1) if uncertainty else None,
                "recent_avg": l10_avgs.get(stat),
            }

        # Build opponent context
        opponent_context = None
        if opponent and team_stats:
            opp_def_rating = opp_ctx.get('opp_def_rating', 110)
            opp_pace = opp_ctx.get('opp_pace', 100)
            def_rank = "Elite" if opp_def_rating < 108 else "Good" if opp_def_rating < 112 else "Average" if opp_def_rating < 116 else "Poor"
            pace_desc = "Fast" if opp_pace > 102 else "Slow" if opp_pace < 98 else "Average"
            opponent_context = {
                "def_rating": opp_def_rating,
                "pace": opp_pace,
                "def_rank": def_rank,
                "pace_desc": pace_desc
            }

        # Build game info
        game_info_response = None
        if game_info:
            game_info_response = {
                "matchup": game_info.get('matchup', ''),
                "game_date": str(game_info.get('game_date', '')),
                "is_home": bool(game_info.get('is_home', 0)),
                "opponent": game_info.get('opponent', ''),
                "opponent_name": game_info.get('opponent_name', '')
            }

        # Build vs stats
        vs_stats_response = None
        if vs_stats:
            vs_stats_response = {
                "games": vs_stats.get('games', 0),
                "avg_pts": round(vs_stats.get('avg_pts', 0), 1),
                "avg_reb": round(vs_stats.get('avg_reb', 0), 1),
                "avg_ast": round(vs_stats.get('avg_ast', 0), 1)
            }

        # Build game log (last 20 games)
        game_log_data = None
        avg_min_l10 = None
        try:
            log_df = completed_features[
                ['GAME_DATE', 'MATCHUP', 'MIN_NUMERIC', 'PTS', 'REB', 'AST']
            ].tail(20).copy()
            game_log_data = []
            for _, row in log_df.iterrows():
                matchup = str(row['MATCHUP'])
                is_home = 'vs.' in matchup
                opp = matchup.split('vs.')[-1].strip() if is_home else matchup.split('@')[-1].strip()
                game_log_data.append({
                    "game_date": pd.to_datetime(row['GAME_DATE']).strftime('%b %d'),
                    "opponent": f"vs {opp}" if is_home else f"@ {opp}",
                    "min": round(float(row['MIN_NUMERIC']), 1),
                    "pts": round(float(row['PTS']), 1),
                    "reb": round(float(row['REB']), 1),
                    "ast": round(float(row['AST']), 1),
                })
            avg_min_l10 = round(float(completed_features['MIN_NUMERIC'].tail(10).mean()), 1)
        except Exception:
            pass  # Non-critical — omit if any issue

        # Final result
        result_data = {
            "player_name": player_info['player_name'],
            "player_id": player_info['player_id'],
            "team_abbrev": player_info.get('team_abbrev'),
            "headshot_url": get_sleeper_headshot(player_info['player_name']),
            "predictions": stat_predictions,
            "game_info": game_info_response,
            "opponent_context": opponent_context,
            "vs_stats": vs_stats_response,
            "model_type": model_type,
            "games_trained_on": predictor.games_trained_on,
            "game_log": game_log_data,
            "avg_min_l10": avg_min_l10,
            "games_this_season": predictor._current_season_games(df_features),
        }
        _save_prediction_cache(canonical_name, result_data)

        yield {
            "stage": "complete",
            "progress": 100,
            "message": "Predictions complete",
            "data": result_data,
        }

    def evaluate_line(
        self,
        prediction: float,
        line: float,
        stat: str,
        confidence_info: Optional[Dict] = None,
        predictor=None
    ) -> Dict:
        """Evaluate a betting line against a prediction."""
        return self.evaluator.evaluate(prediction, line, stat, confidence_info, predictor=predictor)


class BestBetsService:
    """Service for finding best betting opportunities."""

    def __init__(self):
        self.prediction_service = PredictionService()

    async def get_todays_best_bets(self, min_edge: float = 5.0, limit: int = 10) -> Dict:
        # NOTE: ``min_edge`` is retained for API/CLI compatibility but is no
        # longer used. Phase B2 selection filters on calibrated prob_pick_wins
        # band (70-80) instead. See backtest in docs/backtest_pick_rules.md.
        """Find the best betting opportunities for today's games."""
        # Get today's props from BDL odds
        props = _fetch_todays_props()

        if not props:
            return {
                "bets": [],
                "generated_at": datetime.now().isoformat(),
                "games_count": 0
            }

        best_bets = []
        games_seen = set()

        for prop in props:
            player_name = prop['player']
            stat = prop['stat']
            line = prop.get('consensus_line')

            if not line:
                continue

            # Track unique games
            game_key = f"{prop['away_team']}@{prop['home_team']}"
            games_seen.add(game_key)

            try:
                # Get prediction (simplified - just use the final result)
                async for event in self.prediction_service.predict_with_progress(player_name):
                    if event['stage'] == 'complete' and event.get('data'):
                        data = event['data']
                        if stat in data['predictions']:
                            pred_data = data['predictions'][stat]
                            prediction = pred_data['prediction']

                            # Calculate edge (informational only — no longer the filter)
                            edge = prediction - line
                            edge_pct = (edge / line) * 100
                            direction = "OVER" if edge > 0 else "UNDER"

                            # Phase B2 selection rule: filter on calibrated
                            # prob_pick_wins, not on raw edge magnitude.
                            # Backtest of 106 graded picks (docs/backtest_pick_rules.md)
                            # showed edge-based selection was anti-correlated with
                            # success — large-edge picks landed in the
                            # "overconfident tail" (prob_over ≥ 80) bucket which
                            # hit at 30%. The 70 ≤ prob_pick_wins < 80 band hit
                            # at 53.7% and is the only profitable zone.
                            prob_over = pred_data.get('prob_over')
                            if prob_over is None:
                                continue
                            prob_pick_wins = (
                                prob_over if direction == "OVER" else 100.0 - prob_over
                            )
                            if not (70.0 <= prob_pick_wins < 80.0):
                                continue
                            strength = "TARGET"

                            best_bets.append({
                                "player": player_name,
                                "player_id": data.get('player_id'),
                                "team_abbrev": data.get('team_abbrev'),
                                "stat": stat,
                                "line": line,
                                "prediction": prediction,
                                "edge": round(edge, 1),
                                "edge_pct": round(edge_pct, 1),
                                "direction": direction,
                                "recommendation": f"{strength} {direction}",
                                "prob_over": prob_over,
                                "prob_pick_wins": round(prob_pick_wins, 1),
                                "game_info": data.get('game_info'),
                                "home_team": prop['home_team'],
                                "away_team": prop['away_team'],
                                "confidence": pred_data.get('confidence'),
                            })
                    elif event['stage'] == 'error':
                        break
            except Exception as e:
                print(f"Error processing {player_name}: {e}")
                continue

        # Sort by closeness to the calibrated centre (~75 prob_pick_wins).
        # The historical sweet spot was 70-75 → 64% WR; 75-80 → 37% WR. Sorting
        # by abs(prob_pick_wins - 73) puts the strongest historical zone first.
        best_bets.sort(
            key=lambda x: abs(x.get('prob_pick_wins', 50.0) - 73.0)
        )

        return {
            "bets": best_bets[:limit],
            "generated_at": datetime.now().isoformat(),
            "games_count": len(games_seen)
        }
