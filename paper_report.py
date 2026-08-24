"""Render the forward paper-sample standing as plain text.

Pure formatting — no database, no network. Kept separate from paper_tracking so
the wording of the honesty guarantees can be tested directly.

Design rule: this report must never make the sample look more informative than
it is. A 0-0 record renders as "n/a", not "0.0%"; no verdict is offered below
``clv.MIN_CONCLUSIVE_N``; and the interval shown is Wilson, not a normal
approximation that would be badly wrong at the small n this sample starts at.
"""
from __future__ import annotations

import clv

WIDTH = 62
_RULE = "-" * WIDTH

_VERDICT_TEXT = {
    clv.VERDICT_INSUFFICIENT: (
        "NO CONCLUSION — sample too small",
        "Not enough picks to distinguish skill from noise. This is not a\n"
        "  negative result; it is the absence of a result.",
    ),
    clv.VERDICT_CLEARS: (
        "CLEARS BREAKEVEN",
        "The 95% Wilson interval sits entirely above the 52.4% breakeven.",
    ),
    clv.VERDICT_BELOW: (
        "BELOW BREAKEVEN",
        "The 95% Wilson interval sits entirely below the 52.4% breakeven.",
    ),
    clv.VERDICT_INCONCLUSIVE: (
        "INCONCLUSIVE at n >= {min_n}",
        "The interval straddles breakeven. The sample is large enough to\n"
        "  report but does not separate the model from a coin flip.",
    ),
}


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _signed_pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:+.1f} pts"


def _render_not_ready(report: dict) -> str:
    lines = [
        "",
        "  FORWARD PAPER SAMPLE",
        f"  {_RULE}",
        "",
        "  Schema is not ready — tracking has not started.",
        "",
        "  Missing:",
    ]
    lines.extend(f"    - {item}" for item in report.get("missing_schema", []))
    lines += [
        "",
        f"  Apply: {report.get('migration_file', 'the pending migration')}",
        "  (deliberately not auto-applied — it needs review first)",
        "",
    ]
    return "\n".join(lines)


def _render_record(record: dict) -> list:
    n = record["n"]
    low, high = record["wilson_low"], record["wilson_high"]
    interval = "n/a" if low is None else f"{_pct(low)} .. {_pct(high)}"

    return [
        "  Record",
        f"  {_RULE}",
        f"    graded picks (n)        : {n}",
        f"    wins / losses           : {record['wins']} / {record['losses']}",
        f"    win rate                : {_pct(record['win_rate'])}",
        f"    95% Wilson interval     : {interval}",
        "",
        f"    breakeven (-110)        : {_pct(record['breakeven'])}",
        f"    distance to breakeven   : {_signed_pct(record['distance_to_breakeven'])}",
        f"    picks until n >= {record['min_n']}    : {record['picks_to_min_n']}",
    ]


def _render_clv(clv_summary: dict) -> list:
    lines = ["  Closing line value", f"  {_RULE}"]
    n = clv_summary.get("n", 0)
    missing = clv_summary.get("picks_without_closing_line", 0)

    if n == 0:
        lines += [
            "    no closing lines recorded yet",
            "",
            "    CLV is the fastest read on whether the model beats a book,",
            "    but it needs a line re-observed near tip-off. Enter lines a",
            "    second time before the game to make it exist.",
        ]
    else:
        lines += [
            f"    picks with a closing line : {n}",
            f"    average CLV               : {clv_summary['avg_clv']:+.2f}",
            f"    positive CLV rate         : {_pct(clv_summary['positive_clv_rate'])}",
        ]
    if missing:
        lines.append(f"    picks without a close     : {missing}")
    return lines


def _render_verdict(record: dict) -> list:
    headline, detail = _VERDICT_TEXT[record["verdict"]]
    return [
        "  Verdict",
        f"  {_RULE}",
        f"    {headline.format(min_n=record['min_n'])}",
        "",
        f"  {detail}",
    ]


def render(report: dict) -> str:
    """Render a report dict from ``paper_tracking.build_report`` as text.

    Pure: the input is never mutated.
    """
    if not report.get("ready", False):
        return _render_not_ready(report)

    record = report["record"]
    lines = ["", "  FORWARD PAPER SAMPLE", f"  {_RULE}", ""]
    lines += _render_record(record)
    lines += ["", f"    ungraded / pending      : {report.get('pending', 0)}",
              f"    total paper picks       : {report.get('total_recorded', 0)}", ""]
    lines += _render_clv(report.get("clv", {}))
    lines += [""]
    lines += _render_verdict(record)
    lines += [""]
    return "\n".join(lines)
