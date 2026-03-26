"""Service layer wrapping GamePredictor for API use."""
import logging
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Generator
from datetime import datetime

logger = logging.getLogger(__name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from game_predictor import GamePredictor
import db


class GamePredictionService:
    """Wraps GamePredictor for API use with SSE progress support."""

    def __init__(self):
        self._predictor: "GamePredictor | None" = None
        self._model_loaded = False

    @property
    def predictor(self) -> "GamePredictor":
        """Lazy-init GamePredictor so DB-only endpoints don't depend on BDL API."""
        if self._predictor is None:
            self._predictor = GamePredictor()
        return self._predictor

    def _ensure_model(self):
        """Ensure model is loaded or trained."""
        if not self._model_loaded:
            if not self.predictor.load_model():
                logger.warning("Game model not found on disk/Supabase, training from scratch")
                self.predictor.train_model()
                self.predictor.save_model()
            self._model_loaded = True
            logger.info("Game prediction model ready")

    def get_todays_games(self) -> Dict:
        """Return today's stored game predictions from DB (no NBA API call)."""
        predictions = db.get_todays_stored_predictions()
        return {
            'predictions': predictions,
            'generated_at': datetime.now().isoformat(),
            'games_count': len(predictions),
        }

    async def predict_with_progress(self) -> Generator[Dict[str, Any], None, None]:
        """Generate predictions with progress updates for SSE."""

        # Stage 1: Fetching games
        yield {
            'stage': 'fetching_games',
            'progress': 10,
            'message': "Fetching today's NBA games...",
        }

        games = self.predictor.get_todays_games()
        await asyncio.sleep(0.1)

        if not games:
            yield {
                'stage': 'complete',
                'progress': 100,
                'message': 'No games scheduled today',
                'data': {
                    'predictions': [],
                    'generated_at': datetime.now().isoformat(),
                    'games_count': 0,
                },
            }
            return

        yield {
            'stage': 'loading_stats',
            'progress': 20,
            'message': f'Found {len(games)} games. Loading team stats...',
        }

        # Stage 2: Load team stats, injuries, etc.
        self._ensure_model()
        self.predictor.get_team_stats()
        self.predictor.get_injuries()
        self.predictor.get_top_scorers()

        await asyncio.sleep(0.1)

        # Stage 3: Build features and predict per game
        predictions = []
        for i, game in enumerate(games):
            progress = 30 + int((i / len(games)) * 50)
            yield {
                'stage': 'predicting',
                'progress': progress,
                'message': f"Predicting {game['home_team']} vs {game['away_team']}...",
            }

            pred = self.predictor.predict_game(
                game['home_team'],
                game['away_team'],
                game.get('game_date'),
            )

            if pred:
                pred['matchup']['game_time'] = game.get('game_time', '')
                predictions.append(pred)

                # Save to DB including full extended_data for fast GET /today
                matchup = pred['matchup']
                home = matchup['home_team']
                away = matchup['away_team']
                db.save_game_prediction({
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
                    'matchup': matchup,  # triggers extended_data storage
                })

            await asyncio.sleep(0.1)

        # Stage 4: Complete
        yield {
            'stage': 'complete',
            'progress': 100,
            'message': f'Predictions complete for {len(predictions)} games',
            'data': {
                'predictions': predictions,
                'generated_at': datetime.now().isoformat(),
                'games_count': len(predictions),
            },
        }

    def predict_all_sync(self) -> dict:
        """Run predictions for all today's games synchronously (for cron use)."""
        try:
            games = self.predictor.get_todays_games()

            if not games:
                logger.info("predict_all_sync: no games scheduled today")
                return {
                    'predictions': [],
                    'generated_at': datetime.now().isoformat(),
                    'games_count': 0,
                    'message': 'No games scheduled today',
                }

            logger.info("predict_all_sync: found %d games, loading model/stats", len(games))
            self._ensure_model()
            self.predictor.get_team_stats()
            self.predictor.get_injuries()
            self.predictor.get_top_scorers()

            predictions = []
            for game in games:
                pred = self.predictor.predict_game(
                    game['home_team'],
                    game['away_team'],
                    game.get('game_date'),
                )

                if pred:
                    pred['matchup']['game_time'] = game.get('game_time', '')
                    predictions.append(pred)

                    matchup = pred['matchup']
                    home = matchup['home_team']
                    away = matchup['away_team']
                    db.save_game_prediction({
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
                        'matchup': matchup,
                    })

            logger.info("predict_all_sync: predicted %d of %d games", len(predictions), len(games))
            return {
                'predictions_count': len(predictions),
                'generated_at': datetime.now().isoformat(),
                'games_count': len(games),
                'message': f'Predicted {len(predictions)} of {len(games)} games',
            }
        except Exception:
            logger.exception("predict_all_sync failed")
            raise

    def get_prediction_history(self, limit: int = 40) -> list:
        """Get past predictions."""
        return db.get_game_predictions(limit=limit)

    def auto_grade(self) -> dict:
        """Auto-grade pending predictions."""
        return db.auto_grade_game_predictions()

    def grade_prediction(self, prediction_id: int, actual_winner: str) -> dict:
        """Manually grade a game prediction."""
        db.grade_game_prediction(prediction_id, actual_winner)
        return {"success": True}

    def get_accuracy_stats(self) -> dict:
        """Get accuracy statistics."""
        return db.get_game_accuracy_stats()
