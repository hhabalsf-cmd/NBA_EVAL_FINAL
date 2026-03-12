"""Live parlay status endpoint — real-time game stats for active parlays."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db

from ..limiter import limiter
from ..routers.auth import get_current_user
from ..services.live_stats_service import get_live_stats_service, LivePlayerStat, LiveGameInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/live", tags=["live"])

_ET = ZoneInfo("America/New_York")


def _compute_leg_status(
    pick: dict,
    player_stat: LivePlayerStat | None,
    game_info: LiveGameInfo | None,
) -> tuple[str, int | None]:
    """Determine leg status and current stat value.

    Returns:
        (leg_status, current_value) where leg_status is one of:
        pending, in_progress, hit, miss, final_hit, final_miss, voided
    """
    if pick.get("voided"):
        return "voided", None

    # Already graded by the batch pipeline
    if pick.get("won") is not None:
        won = bool(pick["won"])
        return ("final_hit" if won else "final_miss"), pick.get("actual_result")

    # No live data for this player
    if player_stat is None:
        return "pending", None

    stat_key = (pick.get("stat") or "").upper()
    stat_map = {"PTS": "pts", "REB": "reb", "AST": "ast", "PRA": "pra"}
    attr = stat_map.get(stat_key)
    if attr is None:
        return "pending", None

    current = getattr(player_stat, attr, 0)
    line = float(pick.get("line") or 0)
    direction = (pick.get("direction") or "").upper()

    # Check if game is final (handles "Final", "Final/OT", "Final/2OT", etc.)
    is_final = game_info is not None and "final" in game_info.status.lower()

    if is_final:
        if direction == "OVER":
            return ("final_hit" if current > line else "final_miss"), current
        if direction == "UNDER":
            return ("final_hit" if current < line else "final_miss"), current
        logger.warning("Invalid direction '%s' for pick %s", direction, pick.get("pick_id"))
        return "pending", current

    # In-progress: determine trending hit/miss
    # OVER "hits" definitively once current > line (stats only go up)
    # UNDER can only "miss" definitively once current > line; stays "in_progress" while below
    if direction == "OVER":
        status = "hit" if current > line else "in_progress"
    elif direction == "UNDER":
        status = "miss" if current > line else "in_progress"
    else:
        logger.warning("Invalid direction '%s' for pick %s", direction, pick.get("pick_id"))
        return "pending", current

    return status, current


def _build_game_dict(game: LiveGameInfo | None) -> dict[str, Any] | None:
    """Build serialisable game info dict."""
    if game is None:
        return None
    return {
        "home_team": game.home_team,
        "visitor_team": game.visitor_team,
        "home_score": game.home_score,
        "visitor_score": game.visitor_score,
        "status": game.status,
        "period": game.period,
        "time_remaining": game.time_remaining,
    }


def _find_game_for_pick(
    pick: dict,
    games: dict[int, LiveGameInfo],
) -> LiveGameInfo | None:
    """Match a pick to its game via team abbreviation."""
    team = (pick.get("team_abbrev") or "").upper()
    opponent = (pick.get("opponent") or "").upper()
    if not team:
        return None

    for game in games.values():
        home = game.home_team.upper()
        away = game.visitor_team.upper()
        if team in (home, away) or opponent in (home, away):
            return game

    return None


@router.get("/parlay-status")
@limiter.limit("120/minute")
async def get_live_parlay_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Return live status for all pending parlays belonging to the current user.

    Fetches BDL data from a shared 60-second TTL cache — costs 0 API calls
    if another request already refreshed the cache this minute.
    """
    user_id = current_user["id"]

    # Fetch all parlays (reuses existing DB function)
    all_parlays = db.get_parlays(user_id=user_id)
    pending = [p for p in all_parlays if p.get("status") == "pending"]

    if not pending:
        return {
            "parlays": [],
            "fetched_at": datetime.now(_ET).isoformat(),
            "has_live_games": False,
            "next_refresh_seconds": 300,
        }

    # Get cached live snapshot
    service = get_live_stats_service()
    snapshot = service.get_snapshot()

    result_parlays: list[dict[str, Any]] = []

    for parlay in pending:
        legs_result: list[dict[str, Any]] = []
        hit_count = 0
        miss_count = 0
        pending_count = 0
        live_count = 0

        for leg in parlay.get("legs", []):
            player_id = leg.get("player_id")
            player_stat = snapshot.player_stats.get(player_id) if player_id else None
            game_info = _find_game_for_pick(leg, snapshot.games)

            leg_status, current_value = _compute_leg_status(leg, player_stat, game_info)

            if leg_status in ("hit", "final_hit"):
                hit_count += 1
            elif leg_status in ("miss", "final_miss"):
                miss_count += 1
            elif leg_status == "in_progress":
                live_count += 1
            elif leg_status == "pending":
                pending_count += 1

            legs_result.append({
                "pick_id": leg.get("pick_id"),
                "player_name": leg.get("player", ""),
                "player_id": player_id,
                "stat": leg.get("stat", ""),
                "line": float(leg.get("line") or 0),
                "direction": leg.get("direction", ""),
                "prediction": float(leg.get("prediction") or 0),
                "edge": float(leg.get("edge") or 0),
                "current_value": current_value,
                "leg_status": leg_status,
                "game": _build_game_dict(game_info),
            })

        result_parlays.append({
            "parlay_id": parlay["id"],
            "status": parlay["status"],
            "created_at": str(parlay.get("created_at", "")),
            "legs_count": parlay.get("legs_count", len(legs_result)),
            "legs": legs_result,
            "legs_hit": hit_count,
            "legs_miss": miss_count,
            "legs_pending": pending_count,
            "legs_in_progress": live_count,
        })

    return {
        "parlays": result_parlays,
        "fetched_at": datetime.now(_ET).isoformat(),
        "has_live_games": snapshot.has_live_games,
        "next_refresh_seconds": 60 if snapshot.has_live_games else 300,
    }
