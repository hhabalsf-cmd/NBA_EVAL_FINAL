"""Pooled forecast engine: prebuilt artifacts, empirical uncertainty, priced offers."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from api.limiter import limiter
from api.routers.auth import get_current_user
from api.routers.players import get_prediction_service
from forecasting.offers import Offer
from forecasting.service import forecast_player, load_model
from season_utils import get_recent_seasons

router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=100)
    player_id: str = Field(min_length=1, max_length=100)
    stat: Literal["PTS", "REB", "AST", "PRA"]
    side: Literal["OVER", "UNDER"]
    line: float = Field(ge=0)
    decimal_odds: float = Field(gt=1)
    book: str = Field(min_length=1, max_length=100)
    captured_at: AwareDatetime
    starts_at: AwareDatetime


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_name: str = Field(min_length=2, max_length=100)
    event_id: str = Field(min_length=1, max_length=100)
    starts_at: AwareDatetime
    team: str = Field(pattern=r"^[A-Z]{2,3}$")
    home: bool
    availability: Literal["available", "questionable", "out", "unknown"] = "unknown"
    offers: list[QuoteRequest] = Field(default_factory=list, max_length=50)


@router.post("/player")
@limiter.limit("15/minute")
def player_forecast(request: Request, body: ForecastRequest, current_user: dict = Depends(get_current_user)):
    """Research output; never enable wagering merely because a point model improved."""
    if body.availability == "out":
        raise HTTPException(422, "Player is out; no active-player forecast is available.")
    try:
        model = load_model()
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Forecast artifact unavailable; run the offline rebuild.") from exc
    service = get_prediction_service()
    info = service.get_player_info(body.player_name)
    if not info:
        raise HTTPException(404, "Player not found")
    player_id = str(info["player_id"])
    logs = service.scraper.get_player_game_log(info["player_id"], seasons=get_recent_seasons(3))
    if logs is None or logs.empty:
        raise HTTPException(503, "Completed game logs unavailable")
    try:
        result = forecast_player(logs, model=model, player_id=player_id,
                                 event_id=body.event_id, starts_at=body.starts_at,
                                 team=body.team, home=body.home,
                                 as_of=datetime.now(timezone.utc), availability=body.availability,
                                 offers=[Offer(**offer.model_dump()) for offer in body.offers])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result["player_name"] = info.get("player_name", body.player_name)
    return result
