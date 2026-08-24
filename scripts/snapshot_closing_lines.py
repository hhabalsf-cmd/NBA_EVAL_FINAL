#!/usr/bin/env python3
"""Record closing lines for picks that do not have one yet.

Reads the append-only ``line_snapshots`` log and writes the latest observation
for each pick into ``picks.closing_line``, which is what CLV needs.

A snapshot only counts if it was captured strictly *after* the pick was created.
If nobody re-entered the line near tip-off, the closing line stays NULL. That is
the correct outcome: a closing line copied from the same observation the pick
was taken at would manufacture a CLV of exactly 0.0.

Safe to re-run. Only picks with ``closing_line IS NULL`` are considered, and the
UPDATE repeats that condition, so an already-recorded closing line is never
overwritten.

Usage:
    python3 scripts/snapshot_closing_lines.py                 # dry run
    python3 scripts/snapshot_closing_lines.py --commit        # actually write
    python3 scripts/snapshot_closing_lines.py --date 2026-08-24 --commit
    python3 scripts/snapshot_closing_lines.py --lookback-days 3
"""
import argparse
import logging
import sys

import _bootstrap  # noqa: F401

import paper_tracking

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

EXIT_OK = 0
EXIT_MIGRATION_REQUIRED = 2
EXIT_ERROR = 1


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=None,
                        help="Game date YYYY-MM-DD. Default: trailing window.")
    parser.add_argument("--lookback-days", type=int, default=1,
                        help="Days back to scan when --date is omitted (default 1).")
    parser.add_argument("--commit", action="store_true",
                        help="Write to the database. Without it this is a dry run.")
    return parser.parse_args(argv)


def _print_result(result: dict) -> None:
    mode = "DRY RUN — nothing written" if result["dry_run"] else "COMMITTED"
    print(f"\n  Closing-line capture [{mode}]")
    print(f"  {'-' * 46}")
    print(f"  picks awaiting a closing line : {result['candidates']}")
    print(f"  snapshots in window           : {result['snapshots']}")
    print(f"  eligible for a closing line   : {result['eligible']}")
    print(f"  written                       : {result['updated']}")

    if result["skipped"]:
        print("\n  Not recorded:")
        labels = {
            paper_tracking.SKIP_ALREADY_RECORDED: "already had a closing line",
            paper_tracking.SKIP_NO_SNAPSHOT: "no line snapshot for that player/stat/date",
            paper_tracking.SKIP_NO_LATER_SNAPSHOT: "no snapshot captured after the pick",
            paper_tracking.SKIP_NO_ENTRY_LINE: "pick has no usable entry line",
        }
        for reason, count in sorted(result["skipped"].items()):
            print(f"    {count:>4}  {labels.get(reason, reason)}")

    if result["dry_run"] and result["eligible"]:
        print("\n  Re-run with --commit to write these.")
    print()


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        result = paper_tracking.snapshot_closing_lines(
            date_str=args.date,
            lookback_days=args.lookback_days,
            dry_run=not args.commit,
        )
    except paper_tracking.MigrationRequiredError as exc:
        print(f"\n  Schema not ready: {exc}\n", file=sys.stderr)
        return EXIT_MIGRATION_REQUIRED
    except Exception as exc:
        logging.error("Closing-line capture failed: %s", exc, exc_info=True)
        return EXIT_ERROR

    _print_result(result)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
