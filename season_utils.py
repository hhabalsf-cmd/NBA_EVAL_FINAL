"""Date-derived NBA season strings.

Single source of truth for the current season so nothing breaks at the
October rollover. Replaces hardcoded '2025-26' literals that previously
lived in nba_evaluator, db, game_predictor, and the API services.

Season boundary: October 1. July–September belong to the just-completed
season (offseason); October onward belongs to the new season.
"""
from __future__ import annotations

from datetime import date

# First month of a new NBA season (regular season tips off in October).
SEASON_START_MONTH = 10


def get_current_season(today: date | None = None) -> str:
    """Return the NBA season string (e.g. '2026-27') for a given date.

    Args:
        today: Date to resolve; defaults to date.today().
    """
    d = today if today is not None else date.today()
    start_year = d.year if d.month >= SEASON_START_MONTH else d.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def get_recent_seasons(n: int, today: date | None = None) -> list[str]:
    """Return the current season plus the (n-1) seasons before it, newest first.

    Args:
        n: Number of seasons to return (must be >= 1).
        today: Date to resolve the current season from; defaults to today.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    d = today if today is not None else date.today()
    start_year = d.year if d.month >= SEASON_START_MONTH else d.year - 1
    return [
        f"{y}-{(y + 1) % 100:02d}"
        for y in range(start_year, start_year - n, -1)
    ]
