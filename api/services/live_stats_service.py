"""
Live game stats service — fetches BDL box scores with a 60-second TTL cache.

Provides a single cached snapshot of all live player stats and game info,
shared across all user requests to minimise BDL API usage (2 req/min max).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from bdl_client import get_bdl_client

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_CACHE_TTL_SECONDS = 60


# ---------------------------------------------------------------------------
# Immutable data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LiveGameInfo:
    """Snapshot of a single game's state."""
    game_id: int
    home_team: str          # abbreviation e.g. "LAL"
    visitor_team: str       # abbreviation e.g. "BOS"
    home_score: int
    visitor_score: int
    status: str             # "Final", "3rd Qtr", ISO timestamp (scheduled), etc.
    period: int
    time_remaining: str     # game clock e.g. "5:32" or ""
    home_q1: int | None = None
    home_q2: int | None = None
    home_q3: int | None = None
    home_q4: int | None = None
    visitor_q1: int | None = None
    visitor_q2: int | None = None
    visitor_q3: int | None = None
    visitor_q4: int | None = None


@dataclass(frozen=True)
class LivePlayerStat:
    """Snapshot of one player's current box score."""
    player_id: int
    player_name: str
    pts: int
    reb: int
    ast: int
    pra: int            # pts + reb + ast
    minutes: str        # e.g. "25" or "00"
    game_id: int


@dataclass(frozen=True)
class LiveStatusSnapshot:
    """Immutable snapshot of all live data at a point in time."""
    games: dict[int, LiveGameInfo] = field(default_factory=dict)
    player_stats: dict[int, LivePlayerStat] = field(default_factory=dict)
    fetched_at: float = 0.0
    has_live_games: bool = False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LiveStatsService:
    """Thread-safe, TTL-cached live stats provider.

    Calls BDL at most once per ``_CACHE_TTL_SECONDS`` regardless of how many
    users request data concurrently.
    """

    def __init__(self) -> None:
        self._cache: LiveStatusSnapshot | None = None
        self._lock = threading.Lock()

    def get_snapshot(self, date_str: str | None = None) -> LiveStatusSnapshot:
        """Return a cached snapshot, refreshing from BDL if stale.

        Args:
            date_str: Date in YYYY-MM-DD format. Defaults to today (ET).
        """
        if date_str is None:
            date_str = datetime.now(_ET).strftime("%Y-%m-%d")

        now = time.time()
        cached = self._cache
        if cached is not None and (now - cached.fetched_at) < _CACHE_TTL_SECONDS:
            return cached

        with self._lock:
            # Double-check after acquiring lock
            cached = self._cache
            if cached is not None and (now - cached.fetched_at) < _CACHE_TTL_SECONDS:
                return cached

            snapshot = self._fetch_from_bdl(date_str)
            self._cache = snapshot
            return snapshot

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_from_bdl(self, date_str: str) -> LiveStatusSnapshot:
        """Fetch games + box scores from BDL API (2 requests)."""
        bdl = get_bdl_client()

        # 1. Fetch all games for the date
        try:
            raw_games = bdl.get_games(dates=[date_str])
        except Exception:
            logger.exception("Failed to fetch games from BDL for %s", date_str)
            return LiveStatusSnapshot(fetched_at=time.time())

        games: dict[int, LiveGameInfo] = {}
        has_active = False

        for g in raw_games:
            game_id = g.get("id")
            if game_id is None:
                continue

            status_raw = str(g.get("status", ""))
            home_team = g.get("home_team", {})
            visitor_team = g.get("visitor_team", {})

            game_info = LiveGameInfo(
                game_id=game_id,
                home_team=home_team.get("abbreviation", ""),
                visitor_team=visitor_team.get("abbreviation", ""),
                home_score=int(g.get("home_team_score") or 0),
                visitor_score=int(g.get("visitor_team_score") or 0),
                status=status_raw,
                period=int(g.get("period") or 0),
                time_remaining=str(g.get("time") or ""),
            )
            games[game_id] = game_info

            if _is_in_progress(status_raw):
                has_active = True

        # 2. Fetch box scores (only if games exist)
        player_stats: dict[int, LivePlayerStat] = {}
        if games:
            try:
                box_scores = bdl.get_box_scores(date_str)
                player_stats = _parse_box_scores(box_scores)
            except Exception:
                logger.exception("Failed to fetch box scores from BDL for %s", date_str)

        return LiveStatusSnapshot(
            games=games,
            player_stats=player_stats,
            fetched_at=time.time(),
            has_live_games=has_active,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_in_progress(status: str) -> bool:
    """Determine if a game status string indicates the game is currently live."""
    if not status:
        return False
    s = status.lower()
    # BDL uses descriptive strings like "3rd Qtr", "Halftime", "in progress"
    # Scheduled games have ISO timestamps, final games have "Final"
    if s == "final" or s.startswith("20"):  # ISO timestamp = scheduled
        return False
    # Anything else (e.g. "1st Qtr", "Halftime", "OT1") is in-progress
    return True


def _parse_box_scores(box_scores: list[dict[str, Any]]) -> dict[int, LivePlayerStat]:
    """Extract player stats from BDL box score response."""
    result: dict[int, LivePlayerStat] = {}

    for bs in box_scores:
        game_id = bs.get("id")
        if game_id is None:
            logger.debug("Box score entry missing game id, skipping")
            continue

        for side_key in ("home_team", "visitor_team"):
            side = bs.get(side_key, {})
            if not isinstance(side, dict):
                logger.debug("Box score game %s: %s is not a dict", game_id, side_key)
                continue

            players = side.get("players", [])
            for p_data in players:
                player_info = p_data.get("player", {})
                pid = player_info.get("id")
                if pid is None:
                    logger.debug("Box score game %s: player entry missing id", game_id)
                    continue

                pts = int(p_data.get("pts") or 0)
                reb = int(p_data.get("reb") or 0)
                ast = int(p_data.get("ast") or 0)

                result[pid] = LivePlayerStat(
                    player_id=pid,
                    player_name=(
                        f"{player_info.get('first_name', '')} "
                        f"{player_info.get('last_name', '')}"
                    ).strip(),
                    pts=pts,
                    reb=reb,
                    ast=ast,
                    pra=pts + reb + ast,
                    minutes=str(p_data.get("min") or "0"),
                    game_id=game_id,
                )

    return result


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: LiveStatsService | None = None
_instance_lock = threading.Lock()


def get_live_stats_service() -> LiveStatsService:
    """Return the module-level LiveStatsService singleton (lazy init)."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LiveStatsService()
    return _instance
