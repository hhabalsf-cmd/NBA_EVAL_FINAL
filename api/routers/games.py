"""Game prediction endpoints."""
import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List

from ..routers.auth import get_current_user

from ..schemas.prediction import (
    TodaysGamesResponse,
    GamePredictionHistoryItem,
    GameAccuracyStats,
)
from ..services.game_service import GamePredictionService


class GradeBody(BaseModel):
    actual_winner: str = Field(..., min_length=2, max_length=10)

router = APIRouter(prefix="/api/games", tags=["games"])

# Singleton service instance
_game_service: Optional[GamePredictionService] = None


def get_game_service() -> GamePredictionService:
    global _game_service
    if _game_service is None:
        _game_service = GamePredictionService()
    return _game_service


@router.get("/today", response_model=TodaysGamesResponse)
def get_todays_games():
    """Get today's games with win predictions."""
    service = get_game_service()
    return service.get_todays_games()


@router.post("/predict")
async def predict_todays_games():
    """
    Predict today's games with SSE progress updates.
    Returns Server-Sent Events for real-time progress.
    """
    service = get_game_service()

    async def event_generator():
        async for event in service.predict_with_progress():
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/history")
def get_prediction_history(days: int = Query(default=7, ge=1, le=90)):
    """Get past game predictions with results."""
    service = get_game_service()
    return service.get_prediction_history(days)


@router.post("/auto-grade")
def auto_grade_predictions(current_user: dict = Depends(get_current_user)):
    """Auto-grade pending game predictions using final scores."""
    service = get_game_service()
    return service.auto_grade()


@router.put("/{prediction_id}/grade")
def grade_prediction(
    prediction_id: int,
    body: GradeBody,
    current_user: dict = Depends(get_current_user),
):
    """Manually grade a game prediction with the actual winner."""
    service = get_game_service()
    return service.grade_prediction(prediction_id, body.actual_winner)


@router.get("/stats/accuracy", response_model=GameAccuracyStats)
def get_accuracy_stats():
    """Get prediction accuracy statistics."""
    service = get_game_service()
    return service.get_accuracy_stats()
