"""Daily best picks endpoints — reads pre-computed picks from Supabase."""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import db
from ..limiter import limiter
from ..schemas.prediction import DailyPick, DailyPicksResponse
from ..routers.auth import verify_service_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bets", tags=["bets"])


@router.get("/today", response_model=DailyPicksResponse)
@limiter.limit("60/minute")
async def get_todays_daily_picks(
    request: Request,
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
@limiter.limit("2/minute")
async def trigger_generate_daily_picks(request: Request):
    """
    Trigger daily picks generation (fire-and-forget).
    Protected by X-Service-Key header (called by pg_cron or manual testing).
    Returns 202 immediately and runs the pipeline in the background so
    pg_cron/pg_net don't time out waiting for the full generation.
    """
    verify_service_key(request)

    async def _run_in_background():
        from scripts.daily_best_picks import run as run_generation
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, run_generation)
            if result.get('success'):
                logger.info(f"Background generation completed: {result.get('picks_count', 0)} picks")
            else:
                logger.error(f"Background generation failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Background generation exception: {e}", exc_info=True)

    asyncio.create_task(_run_in_background())

    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Daily picks generation started in background"},
    )


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
