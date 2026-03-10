"""Parlay persistence endpoints."""
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db

from ..schemas.prediction import ParlayCreate, ParlayResponse, ParlayLegDetail
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/parlays", tags=["parlays"])


def _parlay_to_response(p: dict) -> ParlayResponse:
    legs = [
        ParlayLegDetail(
            id=leg['id'],
            pick_id=leg['pick_id'],
            player=leg['player'],
            player_id=leg.get('player_id'),
            team_abbrev=leg.get('team_abbrev'),
            stat=leg['stat'],
            line=float(leg['line']),
            prediction=float(leg['prediction']),
            direction=leg['direction'],
            edge=float(leg['edge']),
            prob_over=leg.get('prob_over'),
            actual_result=leg.get('actual_result'),
            won=bool(leg['won']) if leg.get('won') is not None else None,
            voided=bool(leg.get('voided')) if leg.get('voided') is not None else None,
            void_reason=leg.get('void_reason'),
            game_date=leg.get('game_date'),
            opponent=leg.get('opponent'),
        )
        for leg in p.get('legs', [])
    ]
    return ParlayResponse(
        id=p['id'],
        legs_count=p['legs_count'],
        status=p['status'],
        graded_at=p.get('graded_at'),
        created_at=p['created_at'],
        legs=legs,
    )


@router.post("", response_model=ParlayResponse, status_code=201)
async def create_parlay(
    body: ParlayCreate,
    current_user: dict = Depends(get_current_user),
):
    """Save a parlay from a list of pick IDs."""
    user_id = current_user["id"]

    # Validate all pick_ids belong to this user and are not voided
    for pick_id in body.pick_ids:
        pick = db.get_pick_by_id(pick_id)
        if not pick:
            raise HTTPException(status_code=404, detail=f"Pick {pick_id} not found")
        if pick['user_id'] != user_id:
            raise HTTPException(status_code=403, detail=f"Pick {pick_id} is not yours")
        if pick.get('voided'):
            raise HTTPException(status_code=400, detail=f"Pick {pick_id} is voided")

    parlay = db.create_parlay(
        user_id=user_id,
        pick_ids=body.pick_ids,
    )
    # Fetch with legs
    parlays = db.get_parlays(user_id=user_id)
    full = next((p for p in parlays if p['id'] == parlay['id']), None)
    if not full:
        raise HTTPException(status_code=500, detail="Failed to retrieve created parlay")
    return _parlay_to_response(full)


@router.get("", response_model=List[ParlayResponse])
async def list_parlays(current_user: dict = Depends(get_current_user)):
    """List the authenticated user's saved parlays."""
    parlays = db.get_parlays(user_id=current_user["id"])
    return [_parlay_to_response(p) for p in parlays]


@router.delete("/{parlay_id}")
async def delete_parlay(parlay_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a saved parlay and its legs. Picks are not affected."""
    parlays = db.get_parlays(user_id=current_user["id"])
    match = next((p for p in parlays if p['id'] == parlay_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Parlay not found")
    db.delete_parlay(parlay_id=parlay_id, user_id=current_user["id"])
    return {"message": "Parlay deleted", "id": parlay_id}
