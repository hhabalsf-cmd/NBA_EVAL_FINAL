"""Player search and prediction endpoints."""
import json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from ..schemas.prediction import (
    PlayerSearchResult,
    PlayerInfo,
    PredictionRequest,
    PredictionResponse,
    LineEvaluationRequest,
    LineEvaluation,
)
from ..services.prediction_service import PredictionService

router = APIRouter(prefix="/api/players", tags=["players"])

# Singleton service instance
_prediction_service: Optional[PredictionService] = None


def get_prediction_service() -> PredictionService:
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = PredictionService()
    return _prediction_service


@router.get("/search", response_model=PlayerSearchResult)
async def search_players(q: str = Query(..., min_length=2, description="Search query")):
    """Search for players by name."""
    service = get_prediction_service()
    players = service.search_players(q)

    return PlayerSearchResult(
        players=[
            PlayerInfo(
                player_id=p['id'],
                player_name=p['full_name'],
                team_id=p.get('team_id'),
                team_abbrev=p.get('team_abbreviation'),
                team_name=p.get('team_name')
            )
            for p in players
        ]
    )


@router.post("/predict")
async def predict_player_stats(request: PredictionRequest):
    """
    Get ML predictions for a player's stats.
    Returns Server-Sent Events for progress updates.
    """
    service = get_prediction_service()

    async def event_generator():
        async for event in service.predict_with_progress(
            player_name=request.player_name,
            model_type=request.model_type,
            use_ensemble=request.use_ensemble,
            retrain=request.retrain
        ):
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


@router.post("/predict/sync", response_model=PredictionResponse)
async def predict_player_stats_sync(request: PredictionRequest):
    """
    Get ML predictions for a player's stats (non-streaming).
    Useful for programmatic access.
    """
    service = get_prediction_service()

    result = None
    error = None

    async for event in service.predict_with_progress(
        player_name=request.player_name,
        model_type=request.model_type,
        use_ensemble=request.use_ensemble,
        retrain=request.retrain
    ):
        if event['stage'] == 'complete':
            result = event['data']
        elif event['stage'] == 'error':
            error = event['message']

    if error:
        raise HTTPException(status_code=404, detail=error)

    if not result:
        raise HTTPException(status_code=500, detail="Prediction failed")

    return PredictionResponse(**result)


@router.get("/{player_name}/odds")
async def get_player_odds(player_name: str):
    """Get today's consensus prop lines for a player (30-min cached)."""
    service = get_prediction_service()
    result = service.get_player_odds(player_name)
    return result


@router.post("/evaluate-line", response_model=LineEvaluation)
async def evaluate_line(request: LineEvaluationRequest):
    """Evaluate a betting line against a prediction."""
    service = get_prediction_service()

    # If prediction not provided, we need to fetch it
    prediction = request.prediction
    if prediction is None:
        # Get prediction from model
        result = None
        async for event in service.predict_with_progress(request.player_name):
            if event['stage'] == 'complete':
                result = event['data']
            elif event['stage'] == 'error':
                raise HTTPException(status_code=404, detail=event['message'])

        if not result or request.stat not in result['predictions']:
            raise HTTPException(status_code=404, detail=f"Could not get prediction for {request.stat}")

        prediction = result['predictions'][request.stat]['prediction']

    # Evaluate the line
    confidence_info = {
        'confidence': 75,
        'low': prediction * 0.85,
        'high': prediction * 1.15
    }

    evaluation = service.evaluate_line(prediction, request.line, request.stat, confidence_info)

    return LineEvaluation(**evaluation)
