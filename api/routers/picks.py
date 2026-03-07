"""Pick tracking CRUD endpoints."""
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List

# Add parent directory to path to import db module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import db

from ..schemas.prediction import (
    PickCreate,
    PickResponse,
    PickGradeRequest,
    PerformanceStats,
    CumulativeProfitPoint,
)
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/picks", tags=["picks"])


def _pick_to_response(p: dict) -> PickResponse:
    """Convert a pick dict from the database to a PickResponse."""
    return PickResponse(
        id=p['id'],
        timestamp=p['timestamp'],
        player=p['player'],
        player_id=p.get('player_id'),
        team_abbrev=p.get('team_abbrev'),
        stat=p['stat'],
        line=p['line'],
        prediction=p['prediction'],
        direction=p['direction'],
        edge=p['edge'],
        confidence=p.get('confidence'),
        opponent=p.get('opponent'),
        is_home=bool(p.get('is_home')) if p.get('is_home') is not None else None,
        actual_result=p.get('actual_result'),
        won=bool(p['won']) if p['won'] is not None else None,
        model_type=p.get('model_type'),
        game_date=p.get('game_date'),
        voided=bool(p.get('voided')) if p.get('voided') is not None else None,
        void_reason=p.get('void_reason'),
        prob_over=p.get('prob_over'),
    )


@router.get("", response_model=List[PickResponse])
async def get_picks(
    days: int = Query(default=3650, ge=1, le=3650, description="Number of days to look back"),
    limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Return most recent N picks (overrides days)"),
    pending_only: bool = Query(default=False, description="Only return ungraded picks"),
    current_user: dict = Depends(get_current_user),
):
    """Get pick history."""
    user_id = current_user["id"]
    if pending_only:
        picks = db.get_pending_picks(user_id=user_id)
    else:
        picks = db.get_picks_history(days=days, user_id=user_id, limit=limit)

    return [_pick_to_response(p) for p in picks]


@router.post("", response_model=PickResponse)
async def create_pick(pick: PickCreate, current_user: dict = Depends(get_current_user)):
    """Save a new pick."""
    pick_data = {
        'player': pick.player,
        'player_id': pick.player_id,
        'team_abbrev': pick.team_abbrev,
        'stat': pick.stat,
        'line': pick.line,
        'prediction': pick.prediction,
        'direction': pick.direction,
        'edge': pick.edge,
        'confidence': pick.confidence,
        'opponent': pick.opponent,
        'is_home': 1 if pick.is_home else 0,
        'model_type': pick.model_type,
        'game_date': pick.game_date,
        'prob_over': pick.prob_over,
        'user_id': current_user["id"],
    }

    pick_id = db.save_pick(pick_data)

    # Fetch the created pick
    created_pick = db.get_pick_by_id(pick_id)

    if not created_pick:
        raise HTTPException(status_code=500, detail="Failed to retrieve created pick")

    return _pick_to_response(created_pick)


@router.get("/{pick_id}", response_model=PickResponse)
async def get_pick(pick_id: int, current_user: dict = Depends(get_current_user)):
    """Get a specific pick by ID."""
    pick = db.get_pick_by_id(pick_id)

    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")

    if pick['user_id'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Not your pick")

    return _pick_to_response(pick)


@router.put("/{pick_id}/grade", response_model=PickResponse)
async def grade_pick(pick_id: int, grade: PickGradeRequest, current_user: dict = Depends(get_current_user)):
    """Grade a pick with the actual result."""
    pick = db.get_pick_by_id(pick_id)

    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")

    if pick['user_id'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Not your pick")

    db.update_pick_result(pick_id, grade.actual_result, pick['line'], pick['direction'])

    # Fetch updated pick
    updated_pick = db.get_pick_by_id(pick_id)

    return _pick_to_response(updated_pick)


@router.delete("/{pick_id}")
async def delete_pick(pick_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a pick."""
    pick = db.get_pick_by_id(pick_id)

    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")

    if pick['user_id'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Not your pick")

    db.delete_pick(pick_id)
    return {"message": "Pick deleted", "id": pick_id}


@router.post("/auto-grade")
async def auto_grade_picks(current_user: dict = Depends(get_current_user)):
    """
    Automatically grade pending picks by fetching actual results,
    then derive and store results for any pending parlays whose picks are all resolved.
    """
    result = db.auto_grade_picks()
    parlay_result = db.grade_pending_parlays(user_id=current_user["id"])
    return {
        "graded_count": result['graded_count'],
        "parlays_graded": parlay_result['parlays_graded'],
        "errors": result['errors'],
        "results": result['results'],
    }


@router.get("/stats/performance", response_model=PerformanceStats)
async def get_performance_stats(current_user: dict = Depends(get_current_user)):
    """Get overall performance statistics."""
    stats = db.get_performance_stats(user_id=current_user["id"])
    return PerformanceStats(
        total_picks=stats['total_picks'],
        graded_picks=stats['graded_picks'],
        wins=stats['wins'],
        losses=stats['losses'],
        pushes=stats['pushes'],
        win_rate=stats['win_rate'],
        roi=stats['roi'],
        avg_edge_winners=stats['avg_edge_winners'],
        by_stat=stats['by_stat'],
        by_edge_range=stats['by_edge_range']
    )


@router.get("/stats/profit", response_model=List[CumulativeProfitPoint])
async def get_cumulative_profit(current_user: dict = Depends(get_current_user)):
    """Get cumulative profit over time for charting."""
    profit_data = db.get_cumulative_profit(user_id=current_user["id"])
    return [
        CumulativeProfitPoint(
            date=p['date'],
            profit=p['profit'],
            cumulative_profit=p['cumulative_profit']
        )
        for p in profit_data
    ]


@router.get("/stats/by-model")
async def get_performance_by_model(current_user: dict = Depends(get_current_user)):
    """Get performance statistics broken down by model type."""
    return db.get_performance_by_model(current_user["id"])


@router.get("/stats/by-model-stat")
async def get_performance_by_model_and_stat(current_user: dict = Depends(get_current_user)):
    """Get detailed performance breakdown by model type AND stat type."""
    return db.get_performance_by_model_and_stat(current_user["id"])
