"""
Backtest selection rules against the graded picks history.

Inputs come from the Supabase ``picks`` table (or any iterable of pick dicts)
and we compute, for each candidate rule, the volume that would have been
selected and the realized win rate. The output is a markdown report at
``docs/backtest_pick_rules_<date>.md``.

The 106-pick history is small and selection-biased (we only see picks the
old rule chose), so we evaluate each candidate rule **on the subset of past
picks the candidate rule would have kept**. This answers the question:

    "Of the picks the existing model already proposed, which subset has a
    win rate above breakeven, and what's the smallest, simplest rule that
    isolates that subset?"

It does **not** answer: "What picks would a different rule have generated
that we never made?" — that requires a true backfill (Phase B2.1, future).

Usage::

    python scripts/backtest_pick_rules.py
    python scripts/backtest_pick_rules.py --csv-out /tmp/picks.csv  # dump raw rows
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

# Allow running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402  — uses repo's shared connection pool


# ── Pure helpers (DB-free) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class RuleResult:
    """Backtest output for one candidate selection rule."""

    label: str
    n: int
    wins: int

    @property
    def win_pct(self) -> float:
        return (self.wins / self.n * 100.0) if self.n else 0.0

    @property
    def roi_at_minus110(self) -> float:
        """ROI at standard −110 sportsbook juice (bet 110 to win 100)."""
        if self.n == 0:
            return 0.0
        # Each win returns +100, each loss returns −110, on a normalized stake
        return (self.wins * 100 - (self.n - self.wins) * 110) / (self.n * 110) * 100


def prob_pick_wins(pick: dict) -> float | None:
    """Probability that *this specific pick* (over/under) wins, in [0, 100]."""
    p = pick.get("prob_over")
    if p is None:
        return None
    return p if pick.get("direction") == "OVER" else 100.0 - p


def evaluate_rule(
    picks: Sequence[dict],
    label: str,
    predicate: Callable[[dict], bool],
) -> RuleResult:
    """Return win-count + total for the picks where ``predicate`` is True."""
    keep = [p for p in picks if predicate(p)]
    wins = sum(1 for p in keep if p.get("won") == 1)
    return RuleResult(label=label, n=len(keep), wins=wins)


# ── Calibration buckets — does stored prob_over match realized hit rate? ──────


def calibration_buckets(picks: Sequence[dict]) -> list[tuple[str, RuleResult, float]]:
    """Bucket picks by ``prob_pick_wins`` and report observed win rate."""
    bins = [
        ("< 50%",  lambda p: p < 50),
        ("50–55%", lambda p: 50 <= p < 55),
        ("55–60%", lambda p: 55 <= p < 60),
        ("60–65%", lambda p: 60 <= p < 65),
        ("65–70%", lambda p: 65 <= p < 70),
        ("70–75%", lambda p: 70 <= p < 75),
        ("75–80%", lambda p: 75 <= p < 80),
        ("80%+",   lambda p: p >= 80),
    ]
    out: list[tuple[str, RuleResult, float]] = []
    for label, predicate in bins:
        bucket: list[dict] = []
        midpoints: list[float] = []
        for pk in picks:
            ppw = prob_pick_wins(pk)
            if ppw is None:
                continue
            if predicate(ppw):
                bucket.append(pk)
                midpoints.append(ppw)
        wins = sum(1 for p in bucket if p.get("won") == 1)
        avg_predicted = statistics.fmean(midpoints) if midpoints else 0.0
        out.append((label, RuleResult(label, len(bucket), wins), avg_predicted))
    return out


# ── Selection rule sweeps ─────────────────────────────────────────────────────


PROB_THRESHOLDS = (50, 52, 54, 55, 56, 58, 60, 62, 64, 65, 66, 68, 70, 72, 75)
EDGE_THRESHOLDS = (0, 5, 8, 10, 12, 15, 20, 25, 30)


def prob_threshold_sweep(picks: Sequence[dict]) -> list[RuleResult]:
    results: list[RuleResult] = []
    for thr in PROB_THRESHOLDS:
        def predicate(p: dict, t: float = thr) -> bool:
            ppw = prob_pick_wins(p)
            return ppw is not None and ppw >= t
        results.append(evaluate_rule(picks, f"prob_pick_wins ≥ {thr}", predicate))
    return results


def edge_threshold_sweep(picks: Sequence[dict]) -> list[RuleResult]:
    results: list[RuleResult] = []
    for thr in EDGE_THRESHOLDS:
        def predicate(p: dict, t: float = thr) -> bool:
            edge = p.get("edge")
            return edge is not None and abs(edge) >= t
        results.append(evaluate_rule(picks, f"|edge| ≥ {thr}", predicate))
    return results


def confidence_threshold_sweep(picks: Sequence[dict]) -> list[RuleResult]:
    """Existing 'displayed confidence' threshold — what the production rule does today."""
    results: list[RuleResult] = []
    for thr in (60, 65, 70, 72, 75, 78, 80, 82, 85):
        def predicate(p: dict, t: float = thr) -> bool:
            c = p.get("confidence")
            return c is not None and c >= t
        results.append(evaluate_rule(picks, f"confidence ≥ {thr}", predicate))
    return results


def combined_rule_sweep(picks: Sequence[dict]) -> list[RuleResult]:
    """Cross product of prob and edge — does adding edge to prob help?"""
    results: list[RuleResult] = []
    for prob_thr in (55, 60, 62, 65, 70):
        for edge_thr in (0, 5, 10):
            label = f"prob ≥ {prob_thr} AND |edge| ≥ {edge_thr}"
            def predicate(p: dict, pt: float = prob_thr, et: float = edge_thr) -> bool:
                ppw = prob_pick_wins(p)
                edge = p.get("edge")
                return (
                    ppw is not None
                    and edge is not None
                    and ppw >= pt
                    and abs(edge) >= et
                )
            results.append(evaluate_rule(picks, label, predicate))
    return results


def window_rule_sweep(picks: Sequence[dict]) -> list[RuleResult]:
    """Window rules: keep picks where prob_pick_wins lands inside a band.

    The hypothesis is that extreme probabilities (>~78) are catastrophically
    overconfident in this dataset, so a windowed rule should isolate the
    middle bucket where the calibration was tightest.
    """
    windows = [
        (60, 80), (60, 78), (60, 75), (62, 78), (62, 75),
        (65, 80), (65, 78), (65, 75), (68, 78), (68, 76),
        (70, 80), (70, 78), (70, 76), (70, 75),
    ]
    results: list[RuleResult] = []
    for low, high in windows:
        def predicate(p: dict, lo: float = low, hi: float = high) -> bool:
            ppw = prob_pick_wins(p)
            return ppw is not None and lo <= ppw < hi
        results.append(evaluate_rule(picks, f"{low} ≤ prob < {high}", predicate))
    return results


def cap_high_prob_rule(picks: Sequence[dict]) -> list[RuleResult]:
    """Rules of the form 'pick only if prob ≤ T'. Tests whether *capping*
    the maximum prob_pick_wins improves results — the calibration table
    shows the 80%+ bucket has 30% win rate, so excluding it should help.
    """
    results: list[RuleResult] = []
    for cap in (95, 90, 85, 80, 78, 75):
        def predicate(p: dict, c: float = cap) -> bool:
            ppw = prob_pick_wins(p)
            return ppw is not None and ppw <= c
        results.append(evaluate_rule(picks, f"prob ≤ {cap} (no extreme tails)", predicate))
    return results


# ── Data access ───────────────────────────────────────────────────────────────


_PICKS_QUERY = """
    SELECT player, stat, line, prediction, actual_result, won,
           confidence, prob_over, edge, direction
    FROM picks
    WHERE won IS NOT NULL
      AND (voided IS NULL OR voided = 0)
"""


def fetch_picks() -> list[dict]:
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=db.psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_PICKS_QUERY)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Report rendering ──────────────────────────────────────────────────────────


def _fmt(v: float, digits: int = 1, signed: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"


def _rule_table(results: Sequence[RuleResult], min_n: int = 0) -> str:
    header = "| Rule | N | Wins | Win % | ROI @ −110 |\n|---|---:|---:|---:|---:|\n"
    rows: list[str] = []
    for r in results:
        if r.n < min_n:
            continue
        rows.append(
            f"| {r.label} | {r.n} | {r.wins} | "
            f"{_fmt(r.win_pct)} | {_fmt(r.roi_at_minus110, signed=True)} |"
        )
    return header + ("\n".join(rows) if rows else "| _no rows_ | | | | |")


def render_report(picks: Sequence[dict]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    overall = evaluate_rule(picks, "all picks", lambda p: True)

    cal_rows = calibration_buckets(picks)
    cal_table_rows: list[str] = [
        "| prob_pick_wins bucket | N | Wins | Win % | Avg Predicted % | Calibration gap |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, res, avg_pred in cal_rows:
        gap = res.win_pct - avg_pred if res.n else 0.0
        cal_table_rows.append(
            f"| {label} | {res.n} | {res.wins} | "
            f"{_fmt(res.win_pct) if res.n else '—'} | "
            f"{_fmt(avg_pred) if res.n else '—'} | "
            f"{_fmt(gap, signed=True) if res.n else '—'} |"
        )

    sections = [
        f"# Pick-Selection Rule Backtest — {today}",
        "",
        f"- **Total graded picks:** {overall.n}",
        f"- **Wins:** {overall.wins}",
        f"- **Overall win rate:** {_fmt(overall.win_pct)}%",
        f"- **Overall ROI @ −110 juice:** {_fmt(overall.roi_at_minus110, signed=True)}%",
        f"- **Breakeven win rate at −110:** 52.4%",
        "",
        "## 1. Calibration of stored `prob_over`",
        "",
        "Bucket each pick by *prob_pick_wins* (= prob_over if direction=OVER else 100 − prob_over).",
        "Calibration gap > 0 ⇒ model is *underconfident* in that bucket; < 0 ⇒ *overconfident*.",
        "",
        "\n".join(cal_table_rows),
        "",
        "## 2. Sweep — `prob_pick_wins ≥ T`",
        "",
        "Replaces the current ``diff_pct > 8`` rule with one based on the calibrated probability.",
        "",
        _rule_table(prob_threshold_sweep(picks), min_n=5),
        "",
        "## 3. Sweep — current `|edge|` rule",
        "",
        "Edge magnitude in pp. This is roughly what production uses today.",
        "",
        _rule_table(edge_threshold_sweep(picks), min_n=5),
        "",
        "## 4. Sweep — displayed `confidence`",
        "",
        "Sanity check: does the heuristic confidence cap correlate with hit rate?",
        "",
        _rule_table(confidence_threshold_sweep(picks), min_n=5),
        "",
        "## 5. Combined `prob ∧ |edge|` rule",
        "",
        "Does adding an edge requirement on top of a probability threshold help or hurt?",
        "",
        _rule_table(combined_rule_sweep(picks), min_n=5),
        "",
        "## 6. Window rules — keep only the middle of the prob distribution",
        "",
        "Calibration table shows the 80%+ bucket only hits 30%; tail picks lose money. "
        "A windowed rule isolates the calibrated middle (~60–78%). ",
        "",
        _rule_table(window_rule_sweep(picks), min_n=10),
        "",
        "## 7. Cap-high-prob rule — exclude extreme tails",
        "",
        "Simpler than a window: just refuse picks where prob_pick_wins is suspiciously high.",
        "",
        _rule_table(cap_high_prob_rule(picks), min_n=10),
        "",
        "## Reading guide",
        "",
        "- **Volume cliff matters.** A rule that hits 80% on 4 picks is statistically meaningless.",
        "  Look for the rule with the highest win rate at ≥30 picks.",
        "- **Calibration gap signals model behaviour.** Persistently negative gap means lower the",
        "  caps in `CONFIDENCE_CAPS`. Persistently positive means the model is too humble — but",
        "  with N=106 we cannot distinguish that from noise.",
        "- **ROI > 0 at −110 needs win rate > 52.4%.** Anything below is a losing strategy at",
        "  standard juice, regardless of how confident the model sounds.",
        "",
        "## Selection-bias caveat",
        "",
        "All picks here came from the existing rule (high `|edge|`, high heuristic confidence).",
        "Sweeping a *stricter* rule across this dataset is fair because every candidate rule's",
        "kept-set is a subset of what we already saw graded. Sweeping a *looser* rule is **not**",
        "fair — those picks were never made, so we don't know how they would have graded.",
        "",
    ]
    return "\n".join(sections)


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Optional path to dump the raw pick rows as CSV for offline analysis.",
    )
    args = parser.parse_args(argv)

    picks = fetch_picks()
    if not picks:
        print("No graded picks found.")
        return 1

    if args.csv_out:
        import csv
        cols = list(picks[0].keys())
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            writer.writerows(picks)
        print(f"Wrote raw picks CSV → {args.csv_out}")

    report = render_report(picks)
    out_path = args.out or (
        Path(__file__).resolve().parent.parent
        / "docs"
        / f"backtest_pick_rules_{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path} ({len(picks)} picks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
