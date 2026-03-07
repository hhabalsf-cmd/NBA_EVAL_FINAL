"""Game prediction endpoints."""
import json
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from ..limiter import limiter
from ..routers.auth import get_current_user, verify_service_key

from ..schemas.prediction import (
    TodaysGamesResponse,
    GamePredictionHistoryItem,
    GameAccuracyStats,
)
from ..services.game_service import GamePredictionService

_NBA_TEAM_ABBREVS = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
}


class GradeBody(BaseModel):
    actual_winner: str = Field(..., min_length=2, max_length=10)

    @field_validator("actual_winner")
    @classmethod
    def validate_team(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _NBA_TEAM_ABBREVS:
            raise ValueError(f"Invalid team abbreviation: {v}")
        return upper

router = APIRouter(prefix="/api/games", tags=["games"])

# Singleton service instance
_game_service: Optional[GamePredictionService] = None


def get_game_service() -> GamePredictionService:
    global _game_service
    if _game_service is None:
        _game_service = GamePredictionService()
    return _game_service


@router.get("/today", response_model=TodaysGamesResponse)
@limiter.limit("60/minute")
def get_todays_games(request: Request):
    """Get today's games with win predictions."""
    service = get_game_service()
    return service.get_todays_games()


@router.post("/predict")
@limiter.limit("10/minute")
async def predict_todays_games(request: Request):
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
@limiter.limit("60/minute")
def get_prediction_history(request: Request, limit: int = Query(default=40, ge=1, le=40)):
    """Get past game predictions with results."""
    service = get_game_service()
    return service.get_prediction_history(limit)


@router.post("/auto-grade")
@limiter.limit("10/minute")
def auto_grade_predictions(request: Request, _: None = Depends(verify_service_key)):
    """Auto-grade pending game predictions using final scores."""
    service = get_game_service()
    return service.auto_grade()


@router.put("/{prediction_id}/grade")
@limiter.limit("20/minute")
def grade_prediction(
    request: Request,
    prediction_id: int,
    body: GradeBody,
    current_user: dict = Depends(get_current_user),
):
    """Manually grade a game prediction with the actual winner."""
    service = get_game_service()
    return service.grade_prediction(prediction_id, body.actual_winner)


@router.get("/stats/accuracy", response_model=GameAccuracyStats)
@limiter.limit("60/minute")
def get_accuracy_stats(request: Request):
    """Get prediction accuracy statistics."""
    service = get_game_service()
    return service.get_accuracy_stats()
