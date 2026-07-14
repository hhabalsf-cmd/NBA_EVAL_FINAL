"""
Phase B1 calibration audit.

Reads graded picks and game_predictions from Supabase, computes per-stat
calibration / bias / hit-rate metrics, and writes a markdown report to
``docs/calibration_audit_<YYYY-MM-DD>.md``.

This is a **read-only** audit — it does not retrain or mutate any models.
The numbers it surfaces are inputs for Phase B2 (recalibrating
``CONFIDENCE_CAPS``, the PRA blend, and applying any per-stat bias correction).

Usage::

    python scripts/audit_calibration.py [--out PATH] [--min-n 10]

The default output path includes today's date so multiple runs can be diffed.
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

# Allow running as a script: ``python scripts/audit_calibration.py``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402  — local module, must come after sys.path patch


# ── Pure helpers ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StatSummary:
    """Aggregate calibration numbers for a single stat or bucket."""

    label: str
    n: int
    win_pct: float
    mae: float | None
    signed_bias: float | None
    avg_confidence: float | None
    avg_edge: float | None


def _safe_mean(values: Sequence[float]) -> float | None:
    cleaned = [v for v in values if v is not None]
    return statistics.fmean(cleaned) if cleaned else None


def _safe_pct(numerator: int, denominator: int) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def summarize_picks(rows: Iterable[dict], label: str) -> StatSummary:
    """Aggregate a flat iterable of pick rows into a single summary line."""
    rows_list = list(rows)
    n = len(rows_list)
    if n == 0:
        return StatSummary(label, 0, 0.0, None, None, None, None)

    wins = sum(1 for r in rows_list if r.get("won") == 1)
    abs_errors = [
        abs(r["prediction"] - r["actual_result"])
        for r in rows_list
        if r.get("prediction") is not None and r.get("actual_result") is not None
    ]
    signed_errors = [
        r["prediction"] - r["actual_result"]
        for r in rows_list
        if r.get("prediction") is not None and r.get("actual_result") is not None
    ]
    confidences = [r["confidence"] for r in rows_list if r.get("confidence") is not None]
    edges = [r["edge"] for r in rows_list if r.get("edge") is not None]

    return StatSummary(
        label=label,
        n=n,
        win_pct=_safe_pct(wins, n),
        mae=_safe_mean(abs_errors),
        signed_bias=_safe_mean(signed_errors),
        avg_confidence=_safe_mean(confidences),
        avg_edge=_safe_mean(edges),
    )


def confidence_buckets(rows: Sequence[dict]) -> list[StatSummary]:
    """Bucket picks by stored confidence and report hit rate per bucket."""
    bins = [
        ("conf <60", lambda c: c < 60),
        ("conf 60–65", lambda c: 60 <= c < 65),
        ("conf 65–70", lambda c: 65 <= c < 70),
        ("conf 70–75", lambda c: 70 <= c < 75),
        ("conf 75–80", lambda c: 75 <= c < 80),
        ("conf 80+", lambda c: c >= 80),
    ]
    summaries: list[StatSummary] = []
    for label, predicate in bins:
        bucket = [r for r in rows if r.get("confidence") is not None and predicate(r["confidence"])]
        summaries.append(summarize_picks(bucket, label))
    return summaries


def edge_buckets(rows: Sequence[dict]) -> list[StatSummary]:
    """Bucket picks by absolute edge magnitude.

    ``edge`` is stored signed in the picks table (positive for OVER picks where
    prediction > line, negative for UNDER picks where prediction < line). The
    bucket boundaries are about edge *magnitude*, so we take ``abs(edge)``.
    """
    bins = [
        ("|edge| <5", lambda e: e < 5),
        ("|edge| 5–10", lambda e: 5 <= e < 10),
        ("|edge| 10–20", lambda e: 10 <= e < 20),
        ("|edge| >=20", lambda e: e >= 20),
    ]
    summaries: list[StatSummary] = []
    for label, predicate in bins:
        bucket = [
            r for r in rows
            if r.get("edge") is not None and predicate(abs(r["edge"]))
        ]
        summaries.append(summarize_picks(bucket, label))
    return summaries


def per_stat_direction(rows: Sequence[dict]) -> list[StatSummary]:
    """Stat × direction breakdown — surfaces over/under asymmetry."""
    summaries: list[StatSummary] = []
    for stat in ("PTS", "REB", "AST", "PRA"):
        for direction in ("OVER", "UNDER"):
            subset = [r for r in rows if r.get("stat") == stat and r.get("direction") == direction]
            summaries.append(summarize_picks(subset, f"{stat} {direction}"))
    return summaries


def per_stat(rows: Sequence[dict]) -> list[StatSummary]:
    """One row per stat."""
    return [
        summarize_picks([r for r in rows if r.get("stat") == stat], stat)
        for stat in ("PTS", "REB", "AST", "PRA")
    ]


# ── Calibration metrics for game predictions ──────────────────────────────────


def game_prediction_summary(rows: Sequence[dict]) -> dict[str, float | int]:
    """Aggregate game-level prediction accuracy and home-side calibration."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    correct = sum(1 for r in rows if r.get("correct"))
    home_wins = sum(1 for r in rows if r.get("actual_winner") == r.get("home_team"))

    # ``home_win_prob`` is stored as 0–100 in this schema; coerce defensively.
    home_probs = [
        float(r["home_win_prob"]) for r in rows if r.get("home_win_prob") is not None
    ]
    if home_probs and max(home_probs) <= 1.0:
        # If anyone ever switches to 0–1 storage, normalize automatically.
        home_probs = [p * 100.0 for p in home_probs]

    return {
        "n": n,
        "accuracy_pct": _safe_pct(correct, n),
        "home_win_pct_actual": _safe_pct(home_wins, n),
        "home_win_pct_predicted": _safe_mean(home_probs) or 0.0,
    }


# ── Data access ───────────────────────────────────────────────────────────────


_PICKS_QUERY = """
    SELECT player, stat, line, prediction, actual_result, won,
           confidence, prob_over, edge, direction, opponent, is_home,
           game_date, model_type
    FROM picks
    WHERE won IS NOT NULL
      AND (voided IS NULL OR voided = 0)
    ORDER BY game_date DESC
"""

_GAMES_QUERY = """
    SELECT home_team, away_team, predicted_winner, home_win_prob,
           confidence, actual_winner, correct, game_date
    FROM game_predictions
    WHERE actual_winner IS NOT NULL
    ORDER BY game_date DESC
"""


def fetch_picks() -> list[dict]:
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=db.psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_PICKS_QUERY)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def fetch_game_predictions() -> list[dict]:
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=db.psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_GAMES_QUERY)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Report rendering ──────────────────────────────────────────────────────────


def _fmt(value: float | None, digits: int = 2, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def _summary_table(summaries: Sequence[StatSummary], min_n: int = 0) -> str:
    header = "| Bucket | N | Win % | MAE | Bias (pred − actual) | Avg Conf | Avg Edge |\n"
    sep = "|---|---:|---:|---:|---:|---:|---:|\n"
    body_rows: list[str] = []
    for s in summaries:
        if s.n < min_n:
            continue
        body_rows.append(
            f"| {s.label} | {s.n} | "
            f"{_fmt(s.win_pct, 1)} | "
            f"{_fmt(s.mae)} | "
            f"{_fmt(s.signed_bias, signed=True)} | "
            f"{_fmt(s.avg_confidence, 1)} | "
            f"{_fmt(s.avg_edge, 1)} |"
        )
    return header + sep + ("\n".join(body_rows) if body_rows else "| _no rows_ | | | | | | |")


def render_report(picks: Sequence[dict], games: Sequence[dict], min_n: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    overall = summarize_picks(picks, "Overall")
    by_stat = per_stat(picks)
    by_dir = per_stat_direction(picks)
    by_conf = confidence_buckets(picks)
    by_edge = edge_buckets(picks)
    games_summary = game_prediction_summary(games)

    high_conf = [r for r in picks if (r.get("confidence") or 0) >= 75]
    high_conf_summary = summarize_picks(high_conf, "confidence ≥ 75")
    low_conf = [r for r in picks if (r.get("confidence") or 0) < 65]
    low_conf_summary = summarize_picks(low_conf, "confidence < 65")

    confidence_gap = (
        overall.avg_confidence - overall.win_pct
        if overall.avg_confidence is not None
        else None
    )

    return f"""# Calibration Audit — {today}

Generated by `scripts/audit_calibration.py`. Read-only; no models retrained.

## Overall

- **Graded picks:** {overall.n}
- **Win rate:** {_fmt(overall.win_pct, 1)}%
- **Average confidence:** {_fmt(overall.avg_confidence, 1)}%
- **Confidence − Win rate gap:** {_fmt(confidence_gap, 1, signed=True)} pp _(positive = overconfident)_
- **Average MAE:** {_fmt(overall.mae)}
- **Average signed bias (pred − actual):** {_fmt(overall.signed_bias, signed=True)}

## Per-stat

{_summary_table(by_stat, min_n=min_n)}

## Per-stat × direction

{_summary_table(by_dir, min_n=min_n)}

## Confidence buckets (calibration sanity check)

A well-calibrated model has the bucket midpoint ≈ the bucket win rate.

- High confidence (≥ 75): N={high_conf_summary.n}, win rate {_fmt(high_conf_summary.win_pct, 1)}%, avg conf {_fmt(high_conf_summary.avg_confidence, 1)}%
- Low confidence  (< 65): N={low_conf_summary.n}, win rate {_fmt(low_conf_summary.win_pct, 1)}%, avg conf {_fmt(low_conf_summary.avg_confidence, 1)}%

{_summary_table(by_conf, min_n=min_n)}

## Edge buckets (edge calibration sanity check)

If edges reflect true mispricings, larger edges should hit at higher rates.

{_summary_table(by_edge, min_n=min_n)}

## Game-level model

- **Graded games:** {games_summary.get("n", 0)}
- **Accuracy:** {_fmt(games_summary.get("accuracy_pct"), 1)}%
- **Actual home win rate:** {_fmt(games_summary.get("home_win_pct_actual"), 1)}%
- **Predicted home win rate (avg):** {_fmt(games_summary.get("home_win_pct_predicted"), 1)}%

## Reading guide

- **Overconfidence:** if `confidence − win rate` > ~5 pp consistently, `CONFIDENCE_CAPS` are too high.
- **Bias:** a non-zero per-stat signed bias is the residual model's job. Persistent bias on graded picks (selection-biased!) is a hint, not proof — confirm against an unbiased backfill before tuning constants.
- **Direction asymmetry:** very different OVER vs UNDER hit rates within a stat usually mean the model under- or over-predicts that stat.
- **Edge calibration:** if huge edges hit at the same or worse rate than small edges, the edge metric is noise, not signal.

## Next steps (Phase B2)

1. Run a true backfill (predict on past games using only data pre-game) to remove selection bias.
2. Re-tune `CONFIDENCE_CAPS` so each bucket's predicted confidence ≈ observed win rate.
3. Decide on the PRA 85/15 blend with held-out PRA picks (current N too small).
4. Drop dead Vegas features and force a clean retrain across all 207 player models.
"""


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path for the markdown report (default: docs/calibration_audit_<date>.md)",
    )
    parser.add_argument(
        "--min-n",
        type=int,
        default=0,
        help="Hide rows with fewer than this many graded picks (default 0).",
    )
    args = parser.parse_args(argv)

    picks = fetch_picks()
    games = fetch_game_predictions()

    if not picks:
        print("No graded picks found — nothing to audit.")
        return 1

    report = render_report(picks, games, min_n=args.min_n)

    out_path = args.out or (
        Path(__file__).resolve().parent.parent
        / "docs"
        / f"calibration_audit_{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path} ({len(picks)} picks, {len(games)} games)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
