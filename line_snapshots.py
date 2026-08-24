"""Append-only line observation log and closing-line capture.

``manual_lines`` holds exactly one mutable row per (game_date, player, stat), so
re-entering a line closer to tip-off overwrites the earlier observation and the
line's path is lost. Closing line value needs that path, so every observation is
also appended here: no unique constraint, no upsert, one row per observation.
"""
from __future__ import annotations

import clv
import tracking_schema as ts
from season_utils import today_et_str
from tracking_schema import MigrationRequiredError  # noqa: F401  (re-export)

logger = ts.logger

SOURCE_MANUAL = "manual"
SOURCE_ODDS_API = "odds_api"
VALID_SOURCES = (SOURCE_MANUAL, SOURCE_ODDS_API)

SKIP_ALREADY_RECORDED = "already_recorded"
SKIP_NO_SNAPSHOT = "no_snapshot"
SKIP_NO_LATER_SNAPSHOT = "no_snapshot_after_pick"
SKIP_NO_ENTRY_LINE = "no_entry_line"

def record_line_snapshots(rows: list, date_str: str | None = None,
                          source: str = SOURCE_MANUAL) -> int:
    """Append observed lines to the snapshot log. Returns rows written.

    Append-only by design: the point is to keep the whole path of a line, so
    there is no unique constraint and no upsert.
    """
    ts.require(ts.has_line_snapshot_support(), "line_snapshots table")

    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

    game_date = ts.norm_date(date_str) or today_et_str()
    validated = []
    for row in rows:
        player = " ".join(str(row.get("player") or "").split())
        stat = str(row.get("stat") or "").strip().upper()
        raw_line = row.get("line", row.get("consensus_line"))
        if not player:
            raise ValueError("player is required for a line snapshot")
        if stat not in ts.VALID_STATS:
            raise ValueError(f"stat must be one of {ts.VALID_STATS}, got {stat!r}")
        try:
            line = float(raw_line)
        except (TypeError, ValueError):
            raise ValueError(f"line must be numeric, got {raw_line!r}")
        if line <= 0:
            raise ValueError(f"line must be positive, got {line}")
        validated.append((ts.norm_date(row.get("game_date")) or game_date,
                          player, stat, line, source))

    if not validated:
        return 0

    with ts.borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO line_snapshots
                       (game_date, player, stat, line, source)
                   VALUES (%s, %s, %s, %s, %s)""",
                validated,
            )
            conn.commit()
    logger.info("Recorded %d line snapshots (source=%s)", len(validated), source)
    return len(validated)


def get_line_snapshots(date_str: str | None = None,
                       lookback_days: int = 1) -> list:
    """Fetch snapshots for a date, or for a trailing window ending today."""
    ts.require(ts.has_line_snapshot_support(), "line_snapshots table")
    with ts.borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            if date_str:
                cur.execute(
                    """SELECT game_date, player, stat, line, source, captured_at
                       FROM line_snapshots WHERE game_date = %s""",
                    (ts.norm_date(date_str),),
                )
            else:
                cur.execute(
                    """SELECT game_date, player, stat, line, source, captured_at
                       FROM line_snapshots
                       WHERE game_date >= (CURRENT_DATE - %s * INTERVAL '1 day')""",
                    (lookback_days,),
                )
            return [dict(r) for r in cur.fetchall()]

# ── Closing-line capture ─────────────────────────────────────────────────────

def _fetch_picks_awaiting_closing_line(date_str: str | None,
                                       lookback_days: int) -> list:
    """Picks with no closing line yet, for the target date or trailing window.

    Deliberately does *not* filter on ``won IS NULL``. Snapshots are durable, so
    a closing line can still be recovered after grading. The original
    implementation gated on ungraded picks and lost the value permanently
    whenever grading won the race.
    """
    with ts.borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            base = """SELECT id, player, stat, game_date, direction, line,
                             opening_line, closing_line, timestamp
                      FROM picks
                      WHERE closing_line IS NULL
                        AND game_date IS NOT NULL
                        AND (voided IS NULL OR voided = 0)"""
            if date_str:
                cur.execute(base + " AND game_date = %s", (ts.norm_date(date_str),))
            else:
                # picks.game_date is TEXT 'YYYY-MM-DD', so the bound must be
                # cast ::date::text, not ::text. A bare ::text on a timestamp
                # yields '2026-08-23 00:00:00', and '2026-08-23' compares as
                # LESS than that, so the boundary day -- the exact day this job
                # targets -- would be silently excluded.
                cur.execute(
                    base + " AND game_date >= (CURRENT_DATE - %s * INTERVAL '1 day')::date::text",
                    (lookback_days,),
                )
            return [dict(r) for r in cur.fetchall()]


def snapshot_closing_lines(date_str: str | None = None, lookback_days: int = 1,
                           dry_run: bool = True) -> dict:
    """Record closing lines for picks that do not have one yet.

    Idempotent: only picks with ``closing_line IS NULL`` are considered and the
    write is guarded by the same condition, so re-running never overwrites an
    already-recorded closing line.

    Returns a summary dict; with ``dry_run=True`` (the default) nothing is
    written and ``updated`` is 0.
    """
    missing = ts.missing_schema()
    if "line_snapshots table" in missing:
        ts.require(False, "line_snapshots table")

    pending = _fetch_picks_awaiting_closing_line(date_str, lookback_days)
    snapshots = get_line_snapshots(date_str, lookback_days)
    updates, skipped = _plan_closing_line_updates(pending, snapshots)

    reasons: dict = {}
    for item in skipped:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1

    result = {
        "candidates": len(pending),
        "snapshots": len(snapshots),
        "eligible": len(updates),
        "updated": 0,
        "skipped": reasons,
        "dry_run": dry_run,
        "updates": updates,
    }
    if dry_run or not updates:
        return result

    written = 0
    with ts.borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            for update in updates:
                # The IS NULL guard makes a concurrent second run a no-op.
                cur.execute(
                    """UPDATE picks SET closing_line = %s
                       WHERE id = %s AND closing_line IS NULL""",
                    (update["closing_line"], update["pick_id"]),
                )
                written += cur.rowcount
            conn.commit()

    logger.info("Recorded closing lines for %d picks", written)
    return {**result, "updated": written}

# ── Pure planning logic ──────────────────────────────────────────────────────

def _plan_closing_line_updates(pending: list, snapshots: list) -> tuple:
    """Decide which pending picks get a closing line, and why the rest do not.

    Pure: takes rows, returns ``(updates, skipped)`` as new lists. Never mutates
    its inputs and never touches the database.

    A snapshot only counts as a *closing* observation if it was captured
    strictly after the pick was created. A snapshot taken at or before the pick
    is the same number we bet into; recording it would manufacture a CLV of 0.0
    and quietly corrupt the only honest measurement we have.
    """
    by_key: dict = {}
    for snap in snapshots:
        by_key.setdefault(ts.snapshot_key(snap), []).append(snap)

    updates, skipped = [], []
    for pick in pending:
        pick_id = pick.get("id")

        if pick.get("closing_line") is not None:
            skipped.append({"pick_id": pick_id, "reason": SKIP_ALREADY_RECORDED})
            continue

        candidates = by_key.get(ts.snapshot_key(pick), [])
        if not candidates:
            skipped.append({"pick_id": pick_id, "reason": SKIP_NO_SNAPSHOT})
            continue

        try:
            pick_time = ts.to_utc_naive(pick.get("timestamp"))
        except ValueError as exc:
            logger.warning("Pick %s has an unparseable timestamp: %s", pick_id, exc)
            skipped.append({"pick_id": pick_id, "reason": SKIP_NO_LATER_SNAPSHOT})
            continue

        later = [c for c in candidates
                 if ts.to_utc_naive(c.get("captured_at")) > pick_time]
        if not later:
            skipped.append({"pick_id": pick_id, "reason": SKIP_NO_LATER_SNAPSHOT})
            continue

        entry = pick.get("opening_line")
        if entry is None:
            entry = pick.get("line")
        if entry is None:
            skipped.append({"pick_id": pick_id, "reason": SKIP_NO_ENTRY_LINE})
            continue

        closing = max(later, key=lambda c: ts.to_utc_naive(c.get("captured_at")))
        try:
            value = clv.compute_clv(pick.get("direction"), entry, closing.get("line"))
        except ValueError as exc:
            logger.warning("Pick %s CLV could not be computed: %s", pick_id, exc)
            skipped.append({"pick_id": pick_id, "reason": SKIP_NO_ENTRY_LINE})
            continue

        updates.append({
            "pick_id": pick_id,
            "closing_line": float(closing["line"]),
            "captured_at": closing.get("captured_at"),
            "entry_line": float(entry),
            "clv": value,
        })

    return updates, skipped
