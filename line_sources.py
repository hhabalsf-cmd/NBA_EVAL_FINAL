"""Unified player-prop line sourcing with graceful fallback.

Source order:
    1. The Odds API — live consensus lines (needs a working ODDS_API_KEY /
       config.json key with remaining quota).
    2. Manual lines — rows entered via POST /api/bets/lines, stored in the
       Supabase ``manual_lines`` table.

BDL player props are gone for good (GOAT-tier endpoint, disabled on the
April 2026 tier downgrade), so they are intentionally not a source here.

Every source returns the same shape consumed by BestBetsService and the
daily-picks pipeline:
    {player, stat, consensus_line, home_team, away_team}
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config.json"


def _resolve_odds_api_key() -> str | None:
    """Key lookup: ODDS_API_KEY env var, then config.json."""
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f).get("odds_api_key") or None
    except (OSError, json.JSONDecodeError):
        return None


def _fetch_odds_api_props() -> list[dict]:
    """Fetch consensus props from The Odds API. Empty list on any failure."""
    key = _resolve_odds_api_key()
    if not key:
        logger.info("Odds API: no key configured — skipping source")
        return []

    try:
        # Local import: nba_evaluator is heavy (pulls the ML stack) and every
        # caller of this module already lazy-loads it for predictions.
        from nba_evaluator import OddsAPI

        props = OddsAPI(api_key=key).get_all_todays_props()
    except Exception as e:
        logger.error("Odds API props fetch failed: %s", e)
        return []

    normalized = [
        {
            "player": p["player"],
            "stat": p["stat"],
            "consensus_line": p["consensus_line"],
            "home_team": p.get("home_team", ""),
            "away_team": p.get("away_team", ""),
        }
        for p in props
        if p.get("consensus_line") is not None
    ]
    if normalized:
        logger.info("Odds API: %d props for today", len(normalized))
    return normalized


def _fetch_manual_props(date_str: str | None = None) -> list[dict]:
    """Fetch manually entered lines from Supabase. Empty list on failure."""
    try:
        import db

        rows = db.get_manual_lines(date_str)
    except Exception as e:
        logger.error("Manual lines fetch failed: %s", e)
        return []

    props = [
        {
            "player": r["player"],
            "stat": r["stat"],
            "consensus_line": float(r["line"]),
            "home_team": r.get("home_team") or "",
            "away_team": r.get("away_team") or "",
        }
        for r in rows
    ]
    if props:
        logger.info("Manual lines: %d props for %s", len(props), date_str or date.today())
    return props


def fetch_todays_props() -> list[dict]:
    """Return today's player props from the first source that has any.

    Order: Odds API → manual lines. Returns [] (with a loud log) when no
    source produces lines — best bets cannot run without a line source.
    """
    props = _fetch_odds_api_props()
    if props:
        return props

    props = _fetch_manual_props()
    if props:
        return props

    logger.error(
        "No line source produced props: Odds API unavailable/exhausted and no "
        "manual lines entered for today. Add lines via POST /api/bets/lines "
        "or configure a working ODDS_API_KEY."
    )
    return []
