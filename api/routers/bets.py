"""Best bets endpoint."""
from fastapi import APIRouter, Query
from typing import Optional

from ..schemas.prediction import BestBetsResponse, BestBet
from ..services.prediction_service import BestBetsService

router = APIRouter(prefix="/api/bets", tags=["bets"])

# Singleton service instance
_bets_service: Optional[BestBetsService] = None


def get_bets_service() -> BestBetsService:
    global _bets_service
    if _bets_service is None:
        _bets_service = BestBetsService()
    return _bets_service


@router.get("/today", response_model=BestBetsResponse)
async def get_todays_best_bets(
    min_edge: float = Query(default=5.0, description="Minimum edge percentage to include"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of bets to return")
):
    """Best bets disabled — returns empty until re-enabled."""
    from datetime import datetime
    return BestBetsResponse(bets=[], generated_at=datetime.now().isoformat(), games_count=0)


@router.get("/quick", response_model=BestBetsResponse)
async def get_quick_bets():
    """
    Get a quick list of sample best bets.

    This is a faster endpoint that returns pre-computed or cached results.
    Useful for homepage display without waiting for full analysis.
    """
    from datetime import datetime

    # Return empty for now - in production, this would return cached results
    return BestBetsResponse(
        bets=[],
        generated_at=datetime.now().isoformat(),
        games_count=0
    )
