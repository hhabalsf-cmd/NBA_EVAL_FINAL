#!/usr/bin/env python3
"""Print the current standing of the forward paper-pick sample.

This is the measurement apparatus that decides whether the prop model is ever
trusted again. It runs whether or not the model UI is enabled.

It reports n, wins, losses, win rate, a 95% Wilson interval, the distance to
both the 52.4% breakeven and the n>=500 target, and a CLV summary. It refuses to
offer a verdict below n=500 (--min-n to override for experimentation only).

Exit codes let a cron or CI job act on the standing:
    0  reported successfully (any verdict, including "no conclusion")
    1  failed to produce a report
    2  schema not ready — the migration has not been applied

Usage:
    python3 scripts/paper_pick_report.py
    python3 scripts/paper_pick_report.py --json
    python3 scripts/paper_pick_report.py --min-n 100     # experimentation only
"""
import argparse
import json
import logging
import sys

import _bootstrap  # noqa: F401

import clv
import paper_report
import paper_tracking

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MIGRATION_REQUIRED = 2


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true",
                        help="Emit the raw report as JSON instead of text.")
    parser.add_argument("--min-n", type=int, default=clv.MIN_CONCLUSIVE_N,
                        help=f"Minimum n before any verdict (default {clv.MIN_CONCLUSIVE_N}). "
                             "Lowering this does not make a small sample informative.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.min_n < 1:
        print("--min-n must be at least 1", file=sys.stderr)
        return EXIT_ERROR

    try:
        report = paper_tracking.build_report(min_n=args.min_n)
    except Exception as exc:
        logging.error("Could not build the paper-pick report: %s", exc, exc_info=True)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(paper_report.render(report))

    if not report.get("ready", False):
        return EXIT_MIGRATION_REQUIRED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
