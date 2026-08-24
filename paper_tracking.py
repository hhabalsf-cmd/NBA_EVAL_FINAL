"""Paper-pick tracking — the forward sample that decides if the model is trusted.

The 2026-08 investigation could not tell whether the prop model beats a
sportsbook: every accuracy number was measured against a synthetic pseudo-line,
and ``picks.closing_line`` was NULL on all 106 graded picks.

Paper picks are rows in ``picks`` carrying ``is_paper = 1``. They ride the
existing nightly grading path unchanged (``auto_grade_picks`` selects on
``won IS NULL``) but carry ``user_id IS NULL``, so they never reach a user's
history, the leaderboard, or the performance surface.

Nothing here relabels the 114 existing picks: ``is_paper`` defaults to 0.
"""
from __future__ import annotations

from datetime import datetime

import clv
import tracking_schema as ts
from line_snapshots import (  # noqa: F401  (re-exported for callers/scripts)
    SKIP_ALREADY_RECORDED,
    SKIP_NO_ENTRY_LINE,
    SKIP_NO_LATER_SNAPSHOT,
    SKIP_NO_SNAPSHOT,
    SOURCE_MANUAL,
    SOURCE_ODDS_API,
    get_line_snapshots,
    record_line_snapshots,
    snapshot_closing_lines,
)
from tracking_schema import (  # noqa: F401  (re-exported)
    MIGRATION_FILE,
    PAPER_FLAG,
    VALID_STATS,
    MigrationRequiredError,
    has_line_snapshot_support,
    has_paper_pick_support,
    missing_schema,
)

logger = ts.logger

def _validate_paper_pick(pick_data: dict) -> dict:
    """Validate and normalize a paper pick, returning a new dict.

    Boundary validation: nothing reaches the database unchecked.
    """
    if not isinstance(pick_data, dict):
        raise ValueError(f"pick_data must be a dict, got {type(pick_data).__name__}")

    player = " ".join(str(pick_data.get("player") or "").split())
    if not player:
        raise ValueError("player is required")

    stat = str(pick_data.get("stat") or "").strip().upper()
    if stat not in VALID_STATS:
        raise ValueError(f"stat must be one of {VALID_STATS}, got {pick_data.get('stat')!r}")

    direction = str(pick_data.get("direction") or "").strip().upper()
    if direction not in clv.VALID_DIRECTIONS:
        raise ValueError(
            f"direction must be one of {clv.VALID_DIRECTIONS}, "
            f"got {pick_data.get('direction')!r}"
        )

    try:
        line = float(pick_data.get("line"))
    except (TypeError, ValueError):
        raise ValueError(f"line must be numeric, got {pick_data.get('line')!r}")
    if line <= 0:
        raise ValueError(f"line must be positive, got {line}")

    game_date = ts.norm_date(pick_data.get("game_date"))
    if not game_date:
        raise ValueError("game_date is required")
    try:
        datetime.strptime(game_date, ts.DATE_FMT)
    except ValueError:
        raise ValueError(f"game_date must be YYYY-MM-DD, got {pick_data.get('game_date')!r}")

    opening = pick_data.get("opening_line")
    opening = line if opening is None else float(opening)

    return {
        **pick_data,
        "player": player,
        "stat": stat,
        "direction": direction,
        "line": line,
        "game_date": game_date,
        "opening_line": opening,
        "is_paper": ts.PAPER_FLAG,
        "user_id": None,
    }

def save_paper_pick(pick_data: dict) -> dict:
    """Insert a paper pick, or return the existing one for the same key.

    Paper picks carry ``is_paper = 1`` and ``user_id IS NULL``, which keeps them
    out of every user-facing query while still being visible to the nightly
    ``auto_grade_picks`` sweep.

    Returns ``{"id": int, "created": bool}``. ``created`` distinguishes a new
    row from a pre-existing duplicate, which the caller cannot otherwise tell
    from the id alone.
    """
    ts.require(ts.has_paper_pick_support(), "picks.is_paper column")
    validated = _validate_paper_pick(pick_data)

    with ts.borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM picks
                   WHERE is_paper = 1 AND player = %s AND stat = %s
                     AND game_date = %s AND (voided IS NULL OR voided = 0)
                   LIMIT 1""",
                (validated["player"], validated["stat"], validated["game_date"]),
            )
            existing = cur.fetchone()
            if existing:
                return {"id": existing["id"], "created": False}

            cur.execute(
                """INSERT INTO picks (timestamp, player, stat, line, prediction,
                       direction, edge, confidence, opponent, is_home, model_type,
                       game_date, player_id, team_abbrev, prob_over, user_id,
                       opening_line, is_paper)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s)
                   RETURNING id""",
                (
                    datetime.now().isoformat(),
                    validated["player"],
                    validated["stat"],
                    validated["line"],
                    validated.get("prediction"),
                    validated["direction"],
                    validated.get("edge"),
                    validated.get("confidence"),
                    validated.get("opponent"),
                    validated.get("is_home", 0),
                    validated.get("model_type", "paper"),
                    validated["game_date"],
                    validated.get("player_id"),
                    validated.get("team_abbrev"),
                    validated.get("prob_over"),
                    None,
                    validated["opening_line"],
                    ts.PAPER_FLAG,
                ),
            )
            pick_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": pick_id, "created": True}


def get_paper_picks() -> list:
    """All non-voided paper picks, newest first."""
    ts.require(ts.has_paper_pick_support(), "picks.is_paper column")
    with ts.borrow_conn_lazy() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, player, stat, line, opening_line, closing_line,
                          direction, prediction, edge, confidence, game_date,
                          won, actual_result, graded_at, timestamp
                   FROM picks
                   WHERE is_paper = 1 AND (voided IS NULL OR voided = 0)
                   ORDER BY game_date DESC, id DESC"""
            )
            return [dict(r) for r in cur.fetchall()]


def build_report(min_n: int = clv.MIN_CONCLUSIVE_N) -> dict:
    """Assemble the forward paper-sample standing.

    Returns a new dict. Refuses to reach a verdict below ``min_n`` -- see
    ``clv.summarize_record``.
    """
    missing = ts.missing_schema()
    if missing:
        return {"ready": False, "missing_schema": missing,
                "migration_file": ts.MIGRATION_FILE}

    picks = get_paper_picks()
    wins = sum(1 for p in picks if p.get("won") == 1)
    losses = sum(1 for p in picks if p.get("won") == 0)
    pending = sum(1 for p in picks if p.get("won") is None)

    clv_values, missing_close = [], 0
    for pick in picks:
        entry = pick.get("opening_line")
        if entry is None:
            entry = pick.get("line")
        if pick.get("closing_line") is None or entry is None:
            missing_close += 1
            continue
        try:
            clv_values.append(
                clv.compute_clv(pick.get("direction"), entry, pick["closing_line"])
            )
        except ValueError as exc:
            logger.warning("Pick %s CLV skipped: %s", pick.get("id"), exc)
            missing_close += 1

    return {
        "ready": True,
        "record": clv.summarize_record(wins, losses, min_n=min_n),
        "pending": pending,
        "total_recorded": len(picks),
        "clv": {**clv.summarize_clv(clv_values),
                "picks_without_closing_line": missing_close},
    }
