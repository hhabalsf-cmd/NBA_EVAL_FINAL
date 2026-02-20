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


@router.get("/{player_name}/team-injuries")
async def get_team_injuries(player_name: str):
    """Get injury report for a player's team and their next opponent (30-min cached)."""
    service = get_prediction_service()

    player_info = service.get_player_info(player_name)
    if not player_info:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")

    team_abbrev = player_info.get('team_abbrev', '')
    game_info = service.scraper.get_player_next_game(player_info)
    opponent = game_info.get('opponent', '') if game_info else ''

    injuries = service.get_injuries()

    def extract_team(abbrev: str):
        if not abbrev:
            return None
        team_data = injuries.get(abbrev, {})
        players = team_data.get('players', [])
        return {
            "abbrev": abbrev,
            "out": [p for p in players if p.get('status') == 'out'],
            "questionable": [p for p in players if p.get('status') == 'questionable'],
        }

    return {
        "team": extract_team(team_abbrev),
        "opponent": extract_team(opponent) if opponent else None,
    }


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
    # Use per-stat CV (coefficient of variation) reflecting real NBA game-to-game variance.
    # NBA stats typically vary 35-50% around the mean each game; using the tight
    # ±15% / 1.645 estimate produced unrealistically high probabilities (90-100%).
    _stat_cv = {'PTS': 0.40, 'REB': 0.45, 'AST': 0.50, 'PRA': 0.35}
    cv = _stat_cv.get(request.stat, 0.40)
    estimated_std = prediction * cv
    confidence_info = {
        'confidence': 75,
        'low': prediction * (1 - cv),
        'high': prediction * (1 + cv),
        'std': estimated_std,
    }

    evaluation = service.evaluate_line(prediction, request.line, request.stat, confidence_info)

    return LineEvaluation(**evaluation)
