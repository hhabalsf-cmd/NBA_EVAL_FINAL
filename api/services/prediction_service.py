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
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any, Generator
import asyncio
import pandas as pd
import statistics

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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


def _fetch_bdl_todays_props() -> list:
    """Fetch today's player props from BDL odds endpoint.

    Returns a list of dicts with keys:
        player, stat, consensus_line, home_team, away_team
    Drop-in replacement for the old OddsAPI.get_all_todays_props().
    """
    import db as _db
    from bdl_client import get_bdl_client

    today = date.today().strftime("%Y-%m-%d")
    bdl = get_bdl_client()

    try:
        games = bdl.get_games(dates=[today])
    except Exception:
        return []

    if not games:
        return []

    # Build game_id -> {home_team, away_team} lookup
    game_info: Dict[int, Dict[str, str]] = {}
    for g in games:
        gid = g.get("id")
        if not gid:
            continue
        home = (g.get("home_team") or {}).get("abbreviation", "")
        away = (g.get("visitor_team") or {}).get("abbreviation", "")
        game_info[gid] = {"home_team": home, "away_team": away}

    # Fetch raw props for every game
    raw_props: list = []
    for gid in game_info:
        try:
            raw_props.extend(bdl.get_player_props(gid))
        except Exception:
            pass

    if not raw_props:
        return []

    # Resolve player_id -> player_name from our local db
    try:
        conn = _db.get_connection()
        pid_to_name: Dict[str, str] = {}
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT player_id, player_name FROM player_game_logs "
                    "WHERE player_name IS NOT NULL AND player_id IS NOT NULL"
                )
                for row in cur.fetchall():
                    pid_to_name[str(row["player_id"])] = row["player_name"]
        finally:
            conn.close()
    except Exception:
        pid_to_name = {}

    # Group lines by (player_id, stat, game_id) across vendors
    grouped: Dict[tuple, list] = defaultdict(list)
    for prop in raw_props:
        # Filter out alternative milestone lines (e.g. 30+ points)
        if prop.get("market", {}).get("type") != "over_under":
            continue

        pid = str(prop.get("player_id") or "")
        ptype = prop.get("prop_type", "")
        stat = _BDL_PROP_TYPE_MAP.get(ptype)
        gid = prop.get("game_id")
        line_val = prop.get("line_value")
        if not pid or not stat or line_val is None:
            continue
        try:
            grouped[(pid, stat, gid)].append(float(line_val))
        except (ValueError, TypeError):
            pass

    result: list = []
    seen: set = set()  # deduplicate (player, stat) — keep first game encountered
    for (pid, stat, gid), lines in grouped.items():
        key = (pid, stat)
        if key in seen:
            continue
        name = pid_to_name.get(pid)
        if not name:
            continue
        
        # Use median to resist extreme outliers if heavy juicing occurs
        consensus_line = statistics.median(lines)
        
        info = game_info.get(gid or 0, {})
        result.append({
            "player": name,
            "stat": stat,
            "consensus_line": consensus_line,
            "home_team": info.get("home_team", ""),
            "away_team": info.get("away_team", ""),
        })
        seen.add(key)

    return result


PRED_CACHE_DIR = Path("./cache/predictions")


def _prediction_cache_path(player_name: str) -> Path:
    key = player_name.replace(" ", "_")
    date_str = datetime.now().strftime("%Y-%m-%d")
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
        self._injuries_cache = None
        self._odds_cache: Optional[Dict] = None
        self._odds_cache_time: float = 0
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
        """Get cached team defensive stats."""
        if self._team_stats_cache is None:
            self._team_stats_cache = self.scraper.get_team_defensive_stats()
        return self._team_stats_cache

    def get_injuries(self) -> Dict:
        """Get cached injury report."""
        if self._injuries_cache is None:
            self._injuries_cache = self.scraper.get_injury_report()
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
                props = _fetch_bdl_todays_props()
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
                    seasons = ('2025-26', '2024-25')
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
                    seasons = ('2025-26', '2024-25')
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
                    'headshot_url': None,
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

        await asyncio.sleep(0.1)  # Yield control

        yield {
            "stage": "fetching_data",
            "progress": 20,
            "message": "Fetching game log..."
        }

        # Get game log
        game_log = self.scraper.get_player_game_log(player_info['player_id'])
        if game_log is None or game_log.empty:
            yield {
                "stage": "error",
                "progress": 100,
                "message": "Could not fetch game log",
                "data": None
            }
            return

        await asyncio.sleep(0.1)

        yield {
            "stage": "fetching_data",
            "progress": 30,
            "message": "Fetching game schedule..."
        }

        # Get game info
        game_info = self.scraper.get_player_next_game(player_info)

        await asyncio.sleep(0.1)

        yield {
            "stage": "fetching_data",
            "progress": 40,
            "message": "Fetching team stats and injuries..."
        }

        # Get context data — fetch in parallel (independent calls)
        loop = asyncio.get_event_loop()
        team_stats, injuries = await asyncio.gather(
            loop.run_in_executor(None, self.get_team_stats),
            loop.run_in_executor(None, self.get_injuries),
        )

        await asyncio.sleep(0.1)

        # Stage 2: Creating features
        yield {
            "stage": "training_model",
            "progress": 50,
            "message": "Engineering features..."
        }

        # Create features
        df_features = ev.FeatureEngineer.create_features(
            game_log,
            player_info=player_info,
            game_info=game_info,
            injuries=injuries,
            team_stats=team_stats
        )

        await asyncio.sleep(0.1)

        # Stage 3: Training/loading model
        yield {
            "stage": "training_model",
            "progress": 60,
            "message": "Loading or training model..."
        }

        predictor = ev.MLPredictor(model_type=model_type, use_ensemble=use_ensemble)

        # Enforce once-per-night retrain policy
        retrain_skipped = False
        if retrain and not ev.should_retrain(player_info['player_name']):
            retrain = False
            retrain_skipped = True

        # Acquire an exclusive per-player file lock so concurrent worker
        # processes can't overwrite each other's trained model.
        train_failed = False
        with _player_model_lock(player_info['player_name']):
            loaded = not retrain and predictor.load(player_info['player_name'])
            if loaded:
                predictor.update(df_features)
            else:
                if not predictor.train(df_features):
                    train_failed = True
            if not train_failed:
                predictor.save(player_info['player_name'])

        if train_failed:
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

        await asyncio.sleep(0.1)

        # Stage 4: Making predictions
        yield {
            "stage": "predicting",
            "progress": 80,
            "message": "Generating predictions..."
        }

        # Get opponent context
        opponent = game_info.get('opponent', '') if game_info else ''
        is_home = game_info.get('is_home', 0) if game_info else 0
        opp_stats = team_stats.get(opponent, {}) if team_stats else {}
        opp_def_rating = opp_stats.get('def_rating', 110)
        opp_pace = opp_stats.get('pace', 100)
        opp_ast_allowed = opp_stats.get('opp_ast', 25)

        # Get injuries context
        team_abbrev = player_info.get('team_abbrev', '')
        injuries_team = injuries.get(team_abbrev, {}).get('out', 0) if injuries else 0
        injuries_opp = injuries.get(opponent, {}).get('out', 0) if injuries else 0

        # Get vs stats
        vs_stats = self.scraper.get_vs_team_stats(player_info['player_id'], opponent) if opponent else None

        # Calculate actual days rest from last game date
        try:
            import pandas as pd
            last_game = pd.to_datetime(df_features['GAME_DATE'].iloc[-1])
            days_rest = min((datetime.now() - last_game).days, 7)
        except Exception:
            days_rest = 2  # Fallback if date parsing fails

        # Create prediction features
        pred_features = ev.FeatureEngineer.get_prediction_features(
            df_features,
            is_home=is_home,
            opponent=opponent,
            injuries_team=injuries_team,
            injuries_opp=injuries_opp,
            opp_def_rating=opp_def_rating,
            opp_pace=opp_pace,
            opp_ast_allowed=opp_ast_allowed,
            days_rest=days_rest,
            vs_stats=vs_stats,
            player_info=player_info,
        )

        # Estimate minutes for this game context
        estimated_minutes = ev.FeatureEngineer.estimate_minutes(
            df_features, is_home, days_rest, injuries_team
        )

        # Refresh recent_averages from live game log so bias correction and L10 display are always current
        predictor._update_recent_averages(df_features)

        # Make predictions with minutes-based scaling
        predictions = predictor.predict(pred_features, estimated_minutes=estimated_minutes)
        predictions = predictor.apply_injury_boost(predictions, injuries_team, injuries_opp)

        await asyncio.sleep(0.1)

        yield {
            "stage": "predicting",
            "progress": 90,
            "message": "Calculating confidence intervals..."
        }

        # Build response
        stat_predictions = {}
        for stat, pred in predictions.items():
            confidence_info = predictor.get_confidence(df_features, stat, pred)
            uncertainty = predictor.get_prediction_uncertainty(pred_features, stat)

            stat_predictions[stat] = {
                "stat": stat,
                "prediction": round(pred, 1),
                "confidence": confidence_info.get('confidence', 70),
                "range_low": round(confidence_info.get('low', pred * 0.8), 1),
                "range_high": round(confidence_info.get('high', pred * 1.2), 1),
                "uncertainty_std": round(uncertainty['std'], 1) if uncertainty else None,
                "recent_avg": round(
                    (df_features['PTS'] + df_features['REB'] + df_features['AST']).tail(10).mean()
                    if stat == 'PRA'
                    else df_features[stat].tail(10).mean()
                , 1) if stat in df_features.columns or stat == 'PRA' else None
            }

        # Build opponent context
        opponent_context = None
        if opponent and team_stats:
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
            log_df = df_features[['GAME_DATE', 'MATCHUP', 'MIN_NUMERIC', 'PTS', 'REB', 'AST']].tail(20).copy()
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
            avg_min_l10 = round(float(df_features['MIN_NUMERIC'].tail(10).mean()), 1)
        except Exception:
            pass  # Non-critical — omit if any issue

        # Final result
        result_data = {
            "player_name": player_info['player_name'],
            "player_id": player_info['player_id'],
            "team_abbrev": player_info.get('team_abbrev'),
            "predictions": stat_predictions,
            "game_info": game_info_response,
            "opponent_context": opponent_context,
            "vs_stats": vs_stats_response,
            "model_type": model_type,
            "games_trained_on": predictor.games_trained_on,
            "game_log": game_log_data,
            "avg_min_l10": avg_min_l10,
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
        """Find the best betting opportunities for today's games."""
        # Get today's props from BDL odds
        props = _fetch_bdl_todays_props()

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

                            # Calculate edge
                            edge = prediction - line
                            edge_pct = (edge / line) * 100

                            # Only include if edge is within the reliable range (>50% edge picks hit <27% historically)
                            if abs(edge_pct) >= min_edge and abs(edge_pct) <= 50.0:
                                direction = "OVER" if edge > 0 else "UNDER"
                                strength = "STRONG" if abs(edge_pct) >= 8 else "MODERATE" if abs(edge_pct) >= 5 else "SLIGHT"

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
                                    "prob_over": pred_data.get('prob_over'),
                                    "game_info": data.get('game_info'),
                                    "home_team": prop['home_team'],
                                    "away_team": prop['away_team'],
                                    "confidence": pred_data.get('confidence')
                                })
                    elif event['stage'] == 'error':
                        break
            except Exception as e:
                print(f"Error processing {player_name}: {e}")
                continue

        # Sort by absolute edge percentage
        best_bets.sort(key=lambda x: abs(x['edge_pct']), reverse=True)

        return {
            "bets": best_bets[:limit],
            "generated_at": datetime.now().isoformat(),
            "games_count": len(games_seen)
        }
