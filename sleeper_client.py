"""
Sleeper API client for NBA player headshots and projections.

Free public API — no auth required.
Players cache: 24 h. Projections cache: 30 min.
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_SLEEPER_BASE = "https://api.sleeper.app/v1"
_CDN_BASE = "https://sleepercdn.com/content/nba/players"

# ---------------------------------------------------------------------------
# Player cache — name -> sleeper player_id
# ---------------------------------------------------------------------------
_players_cache: dict = {}
_players_cache_time: float = 0
_PLAYERS_TTL = 60 * 60 * 24  # 24 hours
_name_to_id: dict[str, str] = {}


def _load_players() -> None:
    """Fetch all NBA players from Sleeper and populate name -> id map."""
    global _players_cache, _players_cache_time, _name_to_id
    now = time.time()
    if _players_cache and now - _players_cache_time < _PLAYERS_TTL:
        return
    try:
        resp = requests.get(f"{_SLEEPER_BASE}/players/nba", timeout=20)
        resp.raise_for_status()
        data: dict = resp.json()
        _players_cache = data
        _players_cache_time = now

        mapping: dict[str, str] = {}
        for pid, p in data.items():
            fn = (p.get("first_name") or "").strip().lower()
            ln = (p.get("last_name") or "").strip().lower()
            full = f"{fn} {ln}".strip()
            if full:
                mapping[full] = pid
        _name_to_id = mapping
        logger.info("Sleeper: loaded %d NBA players", len(mapping))
    except Exception as exc:
        logger.warning("Sleeper player fetch failed: %s", exc)


def get_headshot_url(player_name: str) -> Optional[str]:
    """Return Sleeper CDN headshot URL for a player by full name, or None."""
    _load_players()
    norm = player_name.strip().lower()
    pid = _name_to_id.get(norm)
    if pid:
        return f"{_CDN_BASE}/{pid}.jpg"
    # Partial fallback
    for name, pid in _name_to_id.items():
        if norm in name or name in norm:
            return f"{_CDN_BASE}/{pid}.jpg"
    return None


# ---------------------------------------------------------------------------
# Projections cache — player_id -> {stat -> projected_value}
# ---------------------------------------------------------------------------
_proj_cache: dict = {}
_proj_cache_time: float = 0
_PROJ_TTL = 30 * 60  # 30 minutes


def _get_current_nba_week() -> int:
    """Rough estimate of the current NBA week number (1-based, starting Oct 22)."""
    import datetime
    season_start = datetime.date(2024, 10, 22)
    today = datetime.date.today()
    delta = (today - season_start).days
    return max(1, delta // 7 + 1)


def get_projections(season: int = 2024) -> dict[str, dict]:
    """Fetch Sleeper NBA projections for the current week.

    Returns {player_id: {stat_abbrev: projected_value}} e.g.:
        {"2544": {"PTS": 26.3, "REB": 7.1, "AST": 8.2}}
    """
    global _proj_cache, _proj_cache_time
    now = time.time()
    if _proj_cache and now - _proj_cache_time < _PROJ_TTL:
        return _proj_cache

    week = _get_current_nba_week()
    url = f"{_SLEEPER_BASE}/projections/nba/{season}/{week}"
    try:
        resp = requests.get(url, params={"season_type": "regular"}, timeout=15)
        resp.raise_for_status()
        raw: dict = resp.json()
    except Exception as exc:
        logger.warning("Sleeper projections fetch failed: %s", exc)
        return _proj_cache  # return stale if available

    # Sleeper stat keys -> our abbreviations
    _STAT_MAP = {
        "pts": "PTS",
        "reb": "REB",
        "ast": "AST",
        "stl": "STL",
        "blk": "BLK",
        "to": "TOV",
        "fg3m": "FG3M",
        "min": "MIN",
    }

    result: dict[str, dict] = {}
    for player_id, stats in raw.items():
        if not isinstance(stats, dict):
            continue
        mapped: dict[str, float] = {}
        for sleeper_key, our_key in _STAT_MAP.items():
            val = stats.get(sleeper_key)
            if val is not None:
                try:
                    mapped[our_key] = round(float(val), 1)
                except (ValueError, TypeError):
                    pass
        if mapped:
            result[player_id] = mapped

    _proj_cache = result
    _proj_cache_time = now
    logger.info("Sleeper: loaded projections for %d players (week %d)", len(result), week)
    return result


def get_player_projections(player_name: str, season: int = 2024) -> Optional[dict]:
    """Return Sleeper projected stats for a player by name, or None."""
    _load_players()
    norm = player_name.strip().lower()
    pid = _name_to_id.get(norm)
    if not pid:
        for name, p in _name_to_id.items():
            if norm in name or name in norm:
                pid = p
                break
    if not pid:
        return None

    projs = get_projections(season=season)
    return projs.get(pid)
