"""Daily best picks endpoints — reads pre-computed picks from Supabase."""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

import db
from ..schemas.prediction import DailyPick, DailyPicksResponse
from ..routers.auth import verify_service_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bets", tags=["bets"])


@router.get("/today", response_model=DailyPicksResponse)
async def get_todays_daily_picks(
    date: str = Query(default=None, description="Date in YYYY-MM-DD format (defaults to today)"),
):
    """
    Get pre-computed daily picks for today (or a specific date).
    No auth required — picks are visible to everyone.
    """
    date_str = date or datetime.now().strftime('%Y-%m-%d')
    picks = db.get_daily_picks(date_str)

    return DailyPicksResponse(
        picks=[DailyPick(**_row_to_daily_pick(row)) for row in picks],
        generated_at=picks[0]['created_at'].isoformat() if picks else datetime.now().isoformat(),
        date=date_str,
    )


@router.post("/generate")
async def trigger_generate_daily_picks(request: Request):
    """
    Trigger daily picks generation.
    Protected by X-Service-Key header (called by pg_cron or manual testing).
    """
    verify_service_key(request)

    from scripts.daily_best_picks import run as run_generation

    result = run_generation()

    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Generation failed'))

    return result


def _row_to_daily_pick(row: dict) -> dict:
    """Convert a database row dict to DailyPick-compatible dict."""
    result = dict(row)
    # Ensure generated_date is a string
    if hasattr(result.get('generated_date'), 'isoformat'):
        result['generated_date'] = result['generated_date'].isoformat()
    elif result.get('generated_date') is None:
        result['generated_date'] = datetime.now().strftime('%Y-%m-%d')
    else:
        result['generated_date'] = str(result['generated_date'])
    return result
