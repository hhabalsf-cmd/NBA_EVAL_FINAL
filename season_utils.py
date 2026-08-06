"""Date-derived NBA season strings and Eastern Time date helpers.

Single source of truth for the current season so nothing breaks at the
October rollover. Replaces hardcoded '2025-26' literals that previously
lived in nba_evaluator, db, game_predictor, and the API services.

Season boundary: October 1. July–September belong to the just-completed
season (offseason); October onward belongs to the new season.

All "what day is it" logic must use the ET helpers here: NBA game dates
are Eastern Time dates, and servers (Railway, Supabase) run on UTC where
`date.today()` rolls over at 7-8 PM ET — mid-slate — splitting reads and
writes across two different dates.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

# First month of a new NBA season (regular season tips off in October).
SEASON_START_MONTH = 10

# NBA schedule dates are Eastern Time dates regardless of venue.
ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    """Return the current datetime in US Eastern Time (DST-aware)."""
    return datetime.now(ET)


def today_et() -> date:
    """Return today's date in US Eastern Time.

    Use instead of date.today()/datetime.now().date() anywhere a "game
    date" is read or written — on UTC servers those roll over at 7-8 PM ET.
    """
    return now_et().date()


def today_et_str() -> str:
    """Return today's ET date as 'YYYY-MM-DD'."""
    return today_et().isoformat()


def get_current_season(today: date | None = None) -> str:
    """Return the NBA season string (e.g. '2026-27') for a given date.

    Args:
        today: Date to resolve; defaults to today in Eastern Time.
    """
    d = today if today is not None else today_et()
    start_year = d.year if d.month >= SEASON_START_MONTH else d.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def get_recent_seasons(n: int, today: date | None = None) -> list[str]:
    """Return the current season plus the (n-1) seasons before it, newest first.

    Args:
        n: Number of seasons to return (must be >= 1).
        today: Date to resolve the current season from; defaults to today in ET.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    d = today if today is not None else today_et()
    start_year = d.year if d.month >= SEASON_START_MONTH else d.year - 1
    return [
        f"{y}-{(y + 1) % 100:02d}"
        for y in range(start_year, start_year - n, -1)
    ]
