"""Daily best picks endpoints — reads pre-computed picks from Supabase."""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import db
from season_utils import today_et_str
from ..limiter import limiter
from ..schemas.prediction import (
    DailyPick,
    DailyPicksResponse,
    ManualLine,
    ManualLinesResponse,
    ManualLinesUpsert,
)
from ..routers.auth import get_current_user, verify_service_key

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
    date_str = date or today_et_str()
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


# ── Manual line entry (fallback line source) ─────────────────────────


def _row_to_manual_line(row: dict) -> ManualLine:
    r = dict(row)
    if hasattr(r.get('game_date'), 'isoformat'):
        r['game_date'] = r['game_date'].isoformat()
    r['line'] = float(r['line'])
    return ManualLine(**r)


@router.get("/lines", response_model=ManualLinesResponse)
@limiter.limit("60/minute")
async def get_manual_lines(
    request: Request,
    date: str = Query(default=None, description="YYYY-MM-DD (defaults to today)"),
    current_user: dict = Depends(get_current_user),
):
    """List manually entered lines for a date."""
    date_str = date or today_et_str()
    rows = db.get_manual_lines(date_str)
    return ManualLinesResponse(
        lines=[_row_to_manual_line(r) for r in rows],
        date=date_str,
    )


@router.post("/lines", response_model=ManualLinesResponse)
@limiter.limit("30/minute")
async def upsert_manual_lines(
    request: Request,
    payload: ManualLinesUpsert,
    current_user: dict = Depends(get_current_user),
):
    """Insert or update manual lines (unique per game_date+player+stat)."""
    date_str = payload.game_date or today_et_str()
    try:
        db.upsert_manual_lines([l.model_dump() for l in payload.lines], date_str)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    rows = db.get_manual_lines(date_str)
    logger.info("Manual lines upserted by %s: %d lines for %s",
                current_user.get('id'), len(payload.lines), date_str)
    return ManualLinesResponse(
        lines=[_row_to_manual_line(r) for r in rows],
        date=date_str,
    )


@router.delete("/lines/{line_id}")
@limiter.limit("30/minute")
async def delete_manual_line(
    request: Request,
    line_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a manual line by id."""
    if not db.delete_manual_line(line_id):
        raise HTTPException(status_code=404, detail="Line not found")
    return {"deleted": line_id}


def _row_to_daily_pick(row: dict) -> dict:
    """Convert a database row dict to DailyPick-compatible dict."""
    result = dict(row)
    # Ensure generated_date is a string
    if hasattr(result.get('generated_date'), 'isoformat'):
        result['generated_date'] = result['generated_date'].isoformat()
    elif result.get('generated_date') is None:
        result['generated_date'] = today_et_str()
    else:
        result['generated_date'] = str(result['generated_date'])
    return result
