"""Service layer wrapping existing ML prediction classes."""
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Generator
import asyncio

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nba_evaluator import (
    NBADataScraper,
    FeatureEngineer,
    MLPredictor,
    LineEvaluator,
    OddsAPI,
)


class PredictionService:
    """Wraps MLPredictor and FeatureEngineer for API use."""

    def __init__(self):
        self.scraper = NBADataScraper()
        self.evaluator = LineEvaluator()
        self._team_stats_cache = None
        self._injuries_cache = None
        self._odds_cache: Optional[Dict] = None
        self._odds_cache_time: float = 0
        self._ODDS_CACHE_TTL = 30 * 60  # 30 minutes

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
                props = OddsAPI().get_all_todays_props()
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

    def search_players(self, query: str) -> list:
        """Search for players by name."""
        from nba_api.stats.static import players

        all_players = players.get_players()
        query_lower = query.lower()

        # First try exact matches
        exact_matches = [p for p in all_players if query_lower == p['full_name'].lower()]
        if exact_matches:
            return exact_matches[:10]

        # Then try partial matches
        matches = [p for p in all_players if query_lower in p['full_name'].lower()]

        # Sort by relevance (starts with query first)
        matches.sort(key=lambda p: (
            0 if p['full_name'].lower().startswith(query_lower) else 1,
            p['full_name']
        ))

        return matches[:10]

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

        # Get context data
        team_stats = self.get_team_stats()
        injuries = self.get_injuries()

        await asyncio.sleep(0.1)

        # Stage 2: Creating features
        yield {
            "stage": "training_model",
            "progress": 50,
            "message": "Engineering features..."
        }

        # Create features
        df_features = FeatureEngineer.create_features(
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

        predictor = MLPredictor(model_type=model_type, use_ensemble=use_ensemble)

        # Try to load existing model
        if not retrain and predictor.load(player_info['player_name']):
            yield {
                "stage": "training_model",
                "progress": 70,
                "message": "Updating model with recent games..."
            }
            predictor.update(df_features)
        else:
            yield {
                "stage": "training_model",
                "progress": 70,
                "message": "Training new model..."
            }
            if not predictor.train(df_features):
                yield {
                    "stage": "error",
                    "progress": 100,
                    "message": "Insufficient data for training",
                    "data": None
                }
                return

        # Save model
        predictor.save(player_info['player_name'])

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
        pred_features = FeatureEngineer.get_prediction_features(
            df_features,
            is_home=is_home,
            opponent=opponent,
            injuries_team=injuries_team,
            injuries_opp=injuries_opp,
            opp_def_rating=opp_def_rating,
            opp_pace=opp_pace,
            opp_ast_allowed=opp_ast_allowed,
            days_rest=days_rest,
            vs_stats=vs_stats
        )

        # Estimate minutes for this game context
        estimated_minutes = FeatureEngineer.estimate_minutes(
            df_features, is_home, days_rest, injuries_team
        )

        # Make predictions with minutes-based scaling
        predictions = predictor.predict(pred_features, estimated_minutes=estimated_minutes)

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
                "recent_avg": round(predictor.recent_averages.get(stat, 0), 1) if predictor.recent_averages else None
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

        # Final result
        yield {
            "stage": "complete",
            "progress": 100,
            "message": "Predictions complete",
            "data": {
                "player_name": player_info['player_name'],
                "player_id": player_info['player_id'],
                "team_abbrev": player_info.get('team_abbrev'),
                "predictions": stat_predictions,
                "game_info": game_info_response,
                "opponent_context": opponent_context,
                "vs_stats": vs_stats_response,
                "model_type": model_type,
                "games_trained_on": predictor.games_trained_on
            }
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
        self.odds_api = OddsAPI()
        self.prediction_service = PredictionService()

    async def get_todays_best_bets(self, min_edge: float = 5.0, limit: int = 10) -> Dict:
        """Find the best betting opportunities for today's games."""
        from datetime import datetime

        # Get today's props from Odds API
        props = self.odds_api.get_all_todays_props()

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

                            # Only include if edge is significant
                            if abs(edge_pct) >= min_edge:
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
