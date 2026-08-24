"""Shared schema helpers for the forward-measurement tables.

Capability probes, normalizers and the migration guard used by both
``line_snapshots`` and ``paper_tracking``.

Schema dependency: ``supabase/001_paper_picks_and_line_snapshots.sql``. Until it
is applied, the probes here report the gap loudly rather than letting an opaque
``UndefinedColumn`` surface from deep inside psycopg2.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

MIGRATION_FILE = "supabase/001_paper_picks_and_line_snapshots.sql"

VALID_STATS = ("PTS", "REB", "AST", "PRA")
PAPER_FLAG = 1
REAL_FLAG = 0

DATE_FMT = "%Y-%m-%d"


class MigrationRequiredError(RuntimeError):
    """Raised when a required schema object has not been created yet."""

# ── Normalizers ──────────────────────────────────────────────────────────────

def norm_date(value) -> str | None:
    """Normalize a game date (date, datetime or string) to 'YYYY-MM-DD'."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def norm_player(value) -> str:
    """Case- and whitespace-insensitive key for matching a player name.

    Known limitation: manual lines are typed by an admin, so a genuinely
    different spelling ("Steph Curry" vs "Stephen Curry") will not match and the
    closing line is simply left NULL. Leaving it NULL is correct — a wrong
    closing line is worse than a missing one.
    """
    return " ".join(str(value or "").split()).casefold()


def to_utc_naive(value) -> datetime:
    """Normalize a timestamp to a naive UTC datetime for safe comparison.

    ``picks.timestamp`` is TEXT written by ``datetime.now().isoformat()`` on a
    UTC server, while ``line_snapshots.captured_at`` is timestamptz. Both are
    reduced to naive UTC here so they can be ordered against each other.
    """
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp is required, got empty value")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(f"could not parse timestamp {value!r}")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def snapshot_key(row) -> tuple:
    return (norm_date(row.get("game_date")),
            norm_player(row.get("player")),
            str(row.get("stat") or "").strip().upper())

# ── Schema capability checks ─────────────────────────────────────────────────

_capability_cache: dict = {}


def borrow_conn_lazy():
    """Lazy import of the db pool.

    Deferred so this module stays importable (and unit-testable) without a
    DATABASE_URL, which db.py demands at import time.
    """
    from db import borrow_conn
    return borrow_conn()


def _probe(key: str, sql: str, params: tuple, refresh: bool) -> bool:
    """Run a one-row existence probe, caching the answer for the process."""
    if not refresh and key in _capability_cache:
        return _capability_cache[key]
    with borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            present = cur.fetchone() is not None
    _capability_cache[key] = present
    return present


def has_paper_pick_support(refresh: bool = False) -> bool:
    """True when picks.is_paper exists."""
    return _probe(
        "picks.is_paper",
        """SELECT 1 FROM information_schema.columns
           WHERE table_name = %s AND column_name = %s""",
        ("picks", "is_paper"),
        refresh,
    )


def has_line_snapshot_support(refresh: bool = False) -> bool:
    """True when the line_snapshots table exists."""
    return _probe(
        "line_snapshots",
        """SELECT 1 FROM information_schema.tables
           WHERE table_name = %s""",
        ("line_snapshots",),
        refresh,
    )


def require(present: bool, what: str) -> None:
    if not present:
        raise MigrationRequiredError(
            f"{what} is missing. Apply {MIGRATION_FILE} to the database first. "
            "It has deliberately not been auto-applied."
        )


def missing_schema() -> list:
    """Return a list of human-readable missing schema objects (empty when ready)."""
    missing = []
    if not has_paper_pick_support():
        missing.append("picks.is_paper column")
    if not has_line_snapshot_support():
        missing.append("line_snapshots table")
    return missing
