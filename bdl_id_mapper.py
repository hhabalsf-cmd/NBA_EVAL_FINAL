"""BallDontLie <-> nba.com ID mapper.

BDLTeamMapper  : BDL team_id <-> NBA abbreviation (in-memory, no DB)
BDLPlayerMapper: BDL player_id <-> nba.com player_id (lazy, Supabase-backed cache)

Singletons: get_team_mapper() / get_player_mapper()
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BDLTeamMapper
# ---------------------------------------------------------------------------

class BDLTeamMapper:
    """Maps BDL team IDs <-> NBA abbreviations. Calls get_teams() once; read-only thereafter."""

    def __init__(self, bdl_client: Any) -> None:
        teams = bdl_client.get_teams()
        bdl_id_to_abbrev: dict[int, str] = {}
        abbrev_to_bdl_id: dict[str, int] = {}
        for team in teams:
            tid = team.get("id")
            abbrev = team.get("abbreviation") or team.get("abbr")
            if tid is None or not abbrev:
                logger.debug("BDLTeamMapper: skipping incomplete team record %s", team)
                continue
            bdl_id_to_abbrev[int(tid)] = str(abbrev).upper()
            abbrev_to_bdl_id[str(abbrev).upper()] = int(tid)

        self._bdl_id_to_abbrev: dict[int, str] = bdl_id_to_abbrev
        self._abbrev_to_bdl_id: dict[str, int] = abbrev_to_bdl_id
        logger.info("BDLTeamMapper: loaded %d teams", len(self._bdl_id_to_abbrev))

    def bdl_id_to_abbrev(self, bdl_team_id: int) -> str | None:
        """Return the NBA abbreviation for a BDL team ID, or None if unknown."""
        return self._bdl_id_to_abbrev.get(int(bdl_team_id))

    def abbrev_to_bdl_id(self, abbrev: str) -> int | None:
        """Return the BDL team ID for an NBA abbreviation, or None if unknown."""
        return self._abbrev_to_bdl_id.get(str(abbrev).upper())


# ---------------------------------------------------------------------------
# BDLPlayerMapper
# ---------------------------------------------------------------------------

class BDLPlayerMapper:
    """Maps BDL player IDs <-> nba.com player IDs via lazy Supabase-backed cache.

    Requires player_id_map table — run supabase/create_player_id_map.sql first.
    """

    def __init__(self, bdl_client: Any, db_conn_str: str) -> None:
        self._bdl_client = bdl_client
        self._db_conn_str = db_conn_str
        # In-memory caches — mutated only under _cache_lock
        self._bdl_to_nba: dict[int, int | None] = {}
        self._nba_to_bdl: dict[int, int | None] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bdl_to_nba(self, bdl_id: int, full_name: str | None = None) -> int | None:
        """Return nba.com player_id for a BDL player_id (cache → DB → name match)."""
        bdl_id = int(bdl_id)

        # 1. In-memory cache
        with self._cache_lock:
            if bdl_id in self._bdl_to_nba:
                return self._bdl_to_nba[bdl_id]

        # 2. Supabase lookup
        row = self._fetch_by_bdl_id(bdl_id)
        if row is not None:
            nba_id = row.get("nba_id")
            if nba_id is None:
                logger.warning(
                    "bdl_to_nba: DB row for bdl_id=%d has NULL nba_id — skipping cache, falling through to layer 3",
                    bdl_id
                )
                # Don't return here — fall through to layer 3 name match
            else:
                self._update_cache(bdl_id, int(nba_id))
                return int(nba_id)

        # 3. Name-based match against player_game_logs
        if full_name:
            try:
                nba_id = self._match_name_in_game_logs(full_name)
            except Exception as exc:
                logger.warning(
                    "bdl_to_nba: name match failed for bdl_id=%d name=%r: %s",
                    bdl_id, full_name, exc,
                )
                return None  # transient failure — do NOT cache the miss
            if nba_id is not None:
                self._upsert_mapping(bdl_id, nba_id, full_name, None)
                self._update_cache(bdl_id, nba_id)
                return nba_id
            # Confirmed no match found — safe to cache sentinel
            self._update_cache(bdl_id, None)
            logger.debug("bdl_to_nba: no mapping found for bdl_id=%d", bdl_id)
            return None

        logger.debug("bdl_to_nba: no mapping found for bdl_id=%d", bdl_id)
        return None

    def nba_to_bdl(self, nba_id: int, player_name: str | None = None) -> int | None:
        """Return BDL player_id for a nba.com player_id (cache → DB → BDL search)."""
        nba_id = int(nba_id)

        # 1. In-memory cache
        with self._cache_lock:
            if nba_id in self._nba_to_bdl:
                return self._nba_to_bdl[nba_id]

        # 2. Supabase lookup
        row = self._fetch_by_nba_id(nba_id)
        if row is not None:
            bdl_id = row.get("bdl_id")
            if bdl_id is None:
                logger.warning(
                    "nba_to_bdl: DB row for nba_id=%d has NULL bdl_id — skipping cache, falling through to layer 3",
                    nba_id
                )
                # Don't return here — fall through to layer 3 name search
            else:
                self._update_cache(int(bdl_id), nba_id)
                return int(bdl_id)

        # 3. BDL name search
        if player_name:
            try:
                bdl_id = self._search_bdl_by_name(player_name)
            except Exception as exc:
                logger.warning(
                    "nba_to_bdl: BDL search failed for nba_id=%d name=%r: %s",
                    nba_id, player_name, exc,
                )
                return None  # transient failure — do NOT cache
            if bdl_id is not None:
                self._upsert_mapping(bdl_id, nba_id, player_name, None)
                self._update_cache(bdl_id, nba_id)
                return bdl_id
            # Confirmed no match via name search — safe to cache miss sentinel
            self._update_cache(None, nba_id)

        logger.debug("nba_to_bdl: no mapping found for nba_id=%d", nba_id)
        return None

    def build_full_mapping(self) -> int:
        """One-time bulk mapping: fetches all BDL players, matches against game_logs by name.

        Returns count of mappings upserted. Run once after initial setup.
        """
        logger.info("build_full_mapping: fetching all BDL players …")
        bdl_players = self._bdl_client.get_players()
        logger.info("build_full_mapping: received %d BDL players", len(bdl_players))

        # Build normalized-name -> BDL record for fast lookup
        bdl_by_norm: dict[str, dict] = {}
        for p in bdl_players:
            first = p.get("first_name") or ""
            last = p.get("last_name") or ""
            full = f"{first} {last}".strip()
            norm = self._normalize_name(full)
            if norm:
                if norm in bdl_by_norm:
                    logger.warning(
                        "build_full_mapping: normalized name collision '%s' — "
                        "keeping first result (id=%s), skipping id=%s",
                        norm, bdl_by_norm[norm].get("id"), p.get("id"),
                    )
                else:
                    bdl_by_norm[norm] = p

        # Fetch all distinct (player_id, player_name) from player_game_logs
        nba_players = self._fetch_all_nba_players_from_logs()
        logger.info("build_full_mapping: found %d distinct players in game logs", len(nba_players))

        count = 0
        for nba_id, nba_name in nba_players:
            norm = self._normalize_name(nba_name)
            bdl_record = bdl_by_norm.get(norm)
            if bdl_record is None:
                logger.debug("build_full_mapping: no BDL match for '%s'", nba_name)
                continue

            bdl_id = bdl_record.get("id")
            if bdl_id is None:
                continue

            team_abbrev: str | None = None
            team = bdl_record.get("team")
            if isinstance(team, dict):
                team_abbrev = team.get("abbreviation")

            first = bdl_record.get("first_name") or ""
            last = bdl_record.get("last_name") or ""
            full_name = f"{first} {last}".strip() or nba_name

            self._upsert_mapping(int(bdl_id), int(nba_id), full_name, team_abbrev)
            self._update_cache(int(bdl_id), int(nba_id))
            count += 1

        logger.info("build_full_mapping: upserted %d mappings", count)
        return count

    # ------------------------------------------------------------------
    # Private: DB helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        """Open a direct (non-pooled) psycopg2 connection."""
        return psycopg2.connect(
            self._db_conn_str,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )

    def _fetch_by_bdl_id(self, bdl_id: int) -> dict | None:
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT bdl_id, nba_id, full_name, team_abbrev "
                        "FROM player_id_map WHERE bdl_id = %s LIMIT 1",
                        (bdl_id,),
                    )
                    return cur.fetchone()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("_fetch_by_bdl_id(%d) DB error: %s", bdl_id, exc)
            return None

    def _fetch_by_nba_id(self, nba_id: int) -> dict | None:
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT bdl_id, nba_id, full_name, team_abbrev "
                        "FROM player_id_map WHERE nba_id = %s LIMIT 1",
                        (nba_id,),
                    )
                    return cur.fetchone()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("_fetch_by_nba_id(%d) DB error: %s", nba_id, exc)
            return None

    def _match_name_in_game_logs(self, full_name: str) -> int | None:
        """Find a nba.com player_id by normalized name match in player_id_map.

        player_game_logs does not store player_name; fall back to searching
        player_id_map by full_name for previously-cached mappings.

        Raises on DB errors so callers can distinguish transient failures from
        a confirmed no-match (returns None).
        """
        norm = self._normalize_name(full_name)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nba_id FROM player_id_map "
                    "WHERE lower(regexp_replace(trim(full_name), '\\s+', ' ', 'g')) = %s "
                    "AND nba_id IS NOT NULL LIMIT 1",
                    (norm,),
                )
                row = cur.fetchone()
                if row:
                    return int(row["nba_id"])
        finally:
            conn.close()
        return None

    def _fetch_all_nba_players_from_logs(self) -> list[tuple[int, str]]:
        """Return list of (nba_id, full_name) from player_game_logs.

        Queries player_game_logs directly so build_full_mapping() works even when
        player_id_map is empty (the bootstrap case after initial migration).
        """
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT player_id AS nba_id, player_name AS full_name "
                        "FROM player_game_logs "
                        "WHERE player_id IS NOT NULL AND player_name IS NOT NULL"
                    )
                    rows = cur.fetchall()
                    return [(int(r["nba_id"]), str(r["full_name"])) for r in rows]
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("_fetch_all_nba_players_from_logs DB error: %s", exc)
            return []

    def _upsert_mapping(
        self,
        bdl_id: int,
        nba_id: int | None,
        full_name: str,
        team_abbrev: str | None = None,
    ) -> None:
        """Insert or update a row in player_id_map."""
        if nba_id is None:
            logger.debug(
                "_upsert_mapping: skipping write for bdl_id=%d (nba_id is None)", bdl_id
            )
            return
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO player_id_map (bdl_id, nba_id, full_name, team_abbrev, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (bdl_id) DO UPDATE
                            SET nba_id      = EXCLUDED.nba_id,
                                full_name   = EXCLUDED.full_name,
                                team_abbrev = EXCLUDED.team_abbrev,
                                updated_at  = NOW()
                        """,
                        (bdl_id, nba_id, full_name, team_abbrev),
                    )
                conn.commit()
                logger.debug(
                    "_upsert_mapping: bdl_id=%d nba_id=%s name='%s'",
                    bdl_id, nba_id, full_name,
                )
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("_upsert_mapping(%d, %s) DB error: %s", bdl_id, nba_id, exc)

    # ------------------------------------------------------------------
    # Private: BDL search
    # ------------------------------------------------------------------

    def _search_bdl_by_name(self, player_name: str) -> int | None:
        """Search BDL /v1/players?search=<name> and return the best-matching ID."""
        try:
            results = self._bdl_client.get_players(search=player_name)
        except Exception as exc:
            logger.warning("_search_bdl_by_name('%s') API error: %s", player_name, exc)
            return None

        if not results:
            return None

        norm_target = self._normalize_name(player_name)
        for p in results:
            first = p.get("first_name") or ""
            last = p.get("last_name") or ""
            full = f"{first} {last}".strip()
            if self._normalize_name(full) == norm_target:
                pid = p.get("id")
                return int(pid) if pid is not None else None

        # Fall back to first result only if there is at least one word overlap
        search_words = set(player_name.lower().split())
        first_name_words = set(
            self._normalize_name(
                f"{results[0].get('first_name', '')} {results[0].get('last_name', '')}"
            ).split()
        )
        if search_words & first_name_words:
            pid = results[0].get("id")
            logger.warning(
                "_search_bdl_by_name('%s'): no exact match, using first result '%s %s' id=%s"
                " — verify mapping",
                player_name,
                results[0].get("first_name"), results[0].get("last_name"), pid,
            )
            return int(pid) if pid is not None else None
        else:
            logger.warning("_search_bdl_by_name('%s'): no match found in BDL", player_name)
            return None

    # ------------------------------------------------------------------
    # Private: cache + normalization
    # ------------------------------------------------------------------

    def _update_cache(self, bdl_id: int | None, nba_id: int | None) -> None:
        """Update both in-memory cache dicts under the lock."""
        with self._cache_lock:
            if bdl_id is not None and nba_id is not None:
                self._bdl_to_nba[int(bdl_id)] = int(nba_id)
                self._nba_to_bdl[int(nba_id)] = int(bdl_id)
            elif bdl_id is not None and nba_id is None:
                # Store sentinel None so we don't re-query the same miss repeatedly
                self._bdl_to_nba[int(bdl_id)] = None
            elif nba_id is not None and bdl_id is None:
                # Store sentinel None so we don't re-query the same miss repeatedly
                self._nba_to_bdl[int(nba_id)] = None

    def _normalize_name(self, name: str) -> str:
        """Lowercase, strip, collapse whitespace for name comparison."""
        if not name:
            return ""
        return re.sub(r"\s+", " ", name.strip().lower())


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_team_mapper: BDLTeamMapper | None = None
_player_mapper: BDLPlayerMapper | None = None
_mapper_lock = threading.Lock()


def get_team_mapper() -> BDLTeamMapper:
    """Return the module-level BDLTeamMapper singleton (thread-safe, lazy).

    Raises EnvironmentError if BALLDONTLIE_API_KEY is not set.
    """
    global _team_mapper  # noqa: PLW0603
    if _team_mapper is None:
        with _mapper_lock:
            if _team_mapper is None:
                api_key = os.getenv("BALLDONTLIE_API_KEY")
                if not api_key:
                    raise EnvironmentError("BALLDONTLIE_API_KEY environment variable is not set.")
                from bdl_client import get_bdl_client  # local import to avoid circular
                logger.info("Initialising BDLTeamMapper singleton")
                _team_mapper = BDLTeamMapper(get_bdl_client())
    return _team_mapper


def get_player_mapper() -> BDLPlayerMapper:
    """Return the module-level BDLPlayerMapper singleton (thread-safe, lazy).

    Raises EnvironmentError if DATABASE_URL is not set.
    """
    global _player_mapper  # noqa: PLW0603
    if _player_mapper is None:
        with _mapper_lock:
            if _player_mapper is None:
                from bdl_client import get_bdl_client  # local import to avoid circular
                db_url = os.getenv("DATABASE_URL")
                if not db_url:
                    raise EnvironmentError(
                        "DATABASE_URL environment variable is not set. "
                        "Add it to your .env file and load it before using BDLPlayerMapper."
                    )
                logger.info("Initialising BDLPlayerMapper singleton")
                _player_mapper = BDLPlayerMapper(get_bdl_client(), db_url)
    return _player_mapper
