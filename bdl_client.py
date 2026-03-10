"""
BallDontLie REST API low-level HTTP client (GOAT tier, 600 req/min).

Rate limits are enforced server-side via 429 responses; this client handles
retries with exponential backoff — callers never need time.sleep().

Usage::

    from bdl_client import get_bdl_client
    client = get_bdl_client()
    games  = client.get_games(dates=["2026-03-08"])
    teams  = client.get_teams()
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [1, 2, 4, 8, 16]   # seconds — one entry per retry attempt
_BASE_URL = "https://api.balldontlie.io"
_DEFAULT_PER_PAGE = 100
_MAX_PAGES = 500   # safety cap for unbounded pagination

_client_instance: "BDLClient | None" = None   # module-level singleton
_client_lock = threading.Lock()


class BDLClient:
    """Low-level HTTP client for the BallDontLie REST API.

    Handles authentication, cursor-based auto-pagination, and
    exponential-backoff retry on 429 / 5xx responses.

    Args:
        api_key: BallDontLie API key — sent as the ``Authorization`` header.
    """

    def __init__(self, api_key: str) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Authorization": api_key, "Accept": "application/json"})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """Expand list values to bracket notation; drop None/empty lists."""
        if not params:
            return {}
        out: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, list):
                if value:                     # omit empty arrays
                    out[f"{key}[]"] = value
            elif value is not None:
                out[key] = value
        return out

    def _request_with_retry(self, method: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """HTTP request with up to 5 retries (429 / 5xx); raises on other 4xx.

        Issue 1 fix: only one sleep fires per attempt.  The loop is restructured
        so that the top-of-loop backoff delay and a 429 Retry-After delay are
        mutually exclusive — a 429 response computes its own wait and sleeps
        immediately, then ``continue``s into the *next* iteration which has
        ``skip_delay=True`` to suppress the redundant top-of-loop sleep.
        """
        last_exc: Exception | None = None
        skip_delay = False   # set to True after a 429 sleep to avoid double-wait

        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if skip_delay:
                # The previous iteration already slept due to a 429 Retry-After.
                # Suppress the normal backoff sleep for this attempt only.
                skip_delay = False
            elif delay:
                logger.warning("BDL retry %d/%d — sleeping %ds", attempt, len(_RETRY_DELAYS), delay)
                time.sleep(delay)

            try:
                resp = self._session.request(method, url, params=params, timeout=30)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("BDL request error (attempt %d): %s", attempt, exc)
                continue

            if resp.status_code < 300:
                # Issue 3 fix: guard resp.json() with try/except.
                try:
                    return resp.json()
                except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"BDL returned non-JSON on {resp.status_code} for {url}: {resp.text[:200]}"
                    ) from exc

            if resp.status_code == 429:
                # Issue 1 fix: sleep exactly once here using Retry-After; set
                # skip_delay so the next iteration's top-of-loop sleep is suppressed.
                wait = int(resp.headers.get("Retry-After", delay or 1))
                logger.warning("BDL 429 — Retry-After: %ds (attempt %d)", wait, attempt)
                time.sleep(wait)
                skip_delay = True
                continue

            if resp.status_code >= 500:
                logger.warning("BDL %d (attempt %d) — %s", resp.status_code, attempt, resp.text[:200])
                last_exc = requests.HTTPError(response=resp)
                continue

            resp.raise_for_status()   # 4xx != 429 → raise immediately

        raise RuntimeError(f"BDL request failed after {len(_RETRY_DELAYS)} retries. Last: {last_exc}")

    # ------------------------------------------------------------------
    # Public primitives
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Single GET request — returns full JSON body (includes ``data`` + ``meta``)."""
        url = f"{_BASE_URL}{path}"
        built = self._build_params(params)
        logger.debug("BDL GET %s params=%s", path, built)
        return self._request_with_retry("GET", url, built)

    def get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Auto-paginate via ``meta.next_cursor`` and return all ``data`` items."""
        base = dict(params or {})
        base.setdefault("per_page", _DEFAULT_PER_PAGE)

        results: list[dict[str, Any]] = []
        cursor: int | None = None
        page = 0

        while True:
            # Issue 4 fix: guard against unbounded pagination loops.
            if page >= _MAX_PAGES:
                logger.error(
                    "BDL pagination exceeded _MAX_PAGES=%d for %s — aborting loop. "
                    "Returning %d items collected so far.",
                    _MAX_PAGES, path, len(results),
                )
                break

            page_params = dict(base)
            if cursor is not None:
                page_params["cursor"] = cursor

            body = self.get(path, page_params)
            data = body.get("data", [])
            results.extend(data)
            page += 1
            logger.debug("BDL paginate %s — page %d, +%d items (%d total)", path, page, len(data), len(results))

            cursor = body.get("meta", {}).get("next_cursor")
            if cursor is None:
                break

        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def season_int(season_str: str) -> int:
        """Convert ``"2025-26"`` → ``2025`` (starting year).

        Args:
            season_str: Season string in ``"YYYY-YY"`` format, e.g. ``"2025-26"``.

        Raises:
            ValueError: If ``season_str`` is not a non-empty string or cannot be parsed.
        """
        # Issue 2 fix: validate input before processing.
        if not isinstance(season_str, str) or not season_str:
            raise ValueError(f"season_str must be a non-empty string, got: {season_str!r}")
        try:
            return int(season_str.split("-")[0])
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Cannot parse season string: {season_str!r}") from exc

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get_games(
        self,
        dates: list[str] | None = None,
        seasons: list[int] | None = None,
        team_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /v1/games`` (FREE tier). Filter by dates, seasons, teams, or date range."""
        return self.get_all("/v1/games", {
            "dates": dates, "seasons": seasons, "team_ids": team_ids,
            "start_date": start_date, "end_date": end_date,
        })

    def get_teams(self) -> list[dict[str, Any]]:
        """``GET /v1/teams`` (FREE tier). Returns all 30 NBA teams."""
        return self.get_all("/v1/teams")

    def get_players(
        self,
        search: str | None = None,
        player_ids: list[int] | None = None,
        per_page: int = _DEFAULT_PER_PAGE,
    ) -> list[dict[str, Any]]:
        """``GET /v1/players`` (FREE tier). Name search or ID lookup."""
        return self.get_all("/v1/players", {"search": search, "player_ids": player_ids, "per_page": per_page})

    def get_player_stats(
        self,
        player_ids: list[int] | None = None,
        seasons: list[int] | None = None,
        game_ids: list[int] | None = None,
        dates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /v1/stats`` (ALL-STAR tier). Per-game player stats."""
        return self.get_all("/v1/stats", {
            "player_ids": player_ids, "seasons": seasons, "game_ids": game_ids, "dates": dates,
        })

    def get_injuries(
        self,
        team_ids: list[int] | None = None,
        player_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /v1/player_injuries`` (ALL-STAR tier). Current injury report."""
        return self.get_all("/v1/player_injuries", {"team_ids": team_ids, "player_ids": player_ids})

    def get_team_season_averages(
        self,
        category: str,
        type_: str,
        season: int,
        season_type: str = "regular",
    ) -> list[dict[str, Any]]:
        """``GET /v1/team_season_averages/{category}`` (GOAT tier).

        Args:
            category: Stat category slug, e.g. ``"general"``.
            type_: Breakdown type, e.g. ``"base"``.
            season: Starting year, e.g. ``2024``.
            season_type: ``"regular"`` or ``"playoffs"``.
        """
        return self.get_all(
            f"/v1/team_season_averages/{category}",
            {"type": type_, "season": season, "season_type": season_type},
        )

    def get_season_averages(
        self,
        category: str,
        type_: str,
        season: int,
        season_type: str = "regular",
    ) -> list[dict[str, Any]]:
        """``GET /v1/season_averages/{category}`` (GOAT tier).

        Args:
            category: Stat category slug, e.g. ``"general"``.
            type_: Breakdown type, e.g. ``"base"``.
            season: Starting year, e.g. ``2024``.
            season_type: ``"regular"`` or ``"playoffs"``.
        """
        return self.get_all(
            f"/v1/season_averages/{category}",
            {"type": type_, "season": season, "season_type": season_type},
        )

    def get_player_props(
        self,
        game_id: int,
        player_id: int | None = None,
        prop_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /v2/odds/player_props`` (GOAT tier). Requires ``game_id``."""
        return self.get_all("/v2/odds/player_props", {
            "game_id": game_id, "player_id": player_id, "prop_type": prop_type,
        })

    def get_odds(
        self,
        game_ids: list[int] | None = None,
        dates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /v2/odds`` (GOAT tier). Requires ``game_ids`` or ``dates``.

        Raises:
            ValueError: If neither ``game_ids`` nor ``dates`` is provided.
        """
        if not game_ids and not dates:
            raise ValueError("get_odds requires either game_ids or dates")
        return self.get_all("/v2/odds", {"game_ids": game_ids, "dates": dates})

    def get_standings(self, season: int) -> list[dict[str, Any]]:
        """``GET /v1/standings`` (GOAT tier). One entry per team for the given season."""
        return self.get_all("/v1/standings", {"season": season})

    def get_box_scores(self, date: str) -> list[dict[str, Any]]:
        """``GET /v1/box_scores`` (GOAT tier). One object per game; not cursor-paginated.

        Args:
            date: Game date in ``"YYYY-MM-DD"`` format.
        """
        body = self.get("/v1/box_scores", {"date": date})
        return body.get("data", [])


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

def get_bdl_client() -> BDLClient:
    """Return the module-level ``BDLClient`` singleton (lazy init).

    Reads ``BALLDONTLIE_API_KEY`` from the environment.
    Thread-safe via double-checked locking.

    Raises:
        EnvironmentError: If ``BALLDONTLIE_API_KEY`` is not set.
    """
    global _client_instance  # noqa: PLW0603

    # Issue 5 fix: double-checked locking for thread-safe singleton initialisation.
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                api_key = os.getenv("BALLDONTLIE_API_KEY")
                if not api_key:
                    raise EnvironmentError(
                        "BALLDONTLIE_API_KEY environment variable is not set. "
                        "Add it to your .env file and load it before importing bdl_client."
                    )
                logger.info("Initialising BDLClient singleton")
                _client_instance = BDLClient(api_key)

    return _client_instance
