#!/usr/bin/env python3
"""Record paper picks into the forward tracking sample.

Paper picks are stored in the ``picks`` table with ``is_paper = 1`` and
``user_id IS NULL``. That means:

  * the existing nightly grading sweep picks them up unchanged
    (``auto_grade_picks`` selects on ``won IS NULL``), and
  * they never appear in a user's history, the leaderboard, or the performance
    surface, all of which are scoped by ``user_id``.

The 114 existing real picks are untouched: ``is_paper`` defaults to 0.

This script is deliberately model-agnostic. It reads picks as JSON rather than
calling the predictor, for two reasons: the current per-player model is being
replaced (Track B), and model-driven pick generation is gated off behind
``NBA_EVAL_ENABLE_PICKS`` while the model is under remediation. Whatever model
produces candidates writes JSON; this records it.

Input: a JSON list of objects with at least
    player, stat (PTS/REB/AST/PRA), line, direction (OVER/UNDER), game_date
and optionally
    prediction, edge, confidence, prob_over, opponent, is_home, team_abbrev,
    player_id, model_type

Every row is validated before anything is written; one bad row rejects the batch.

Usage:
    python3 scripts/record_paper_picks.py --from-json picks.json          # dry run
    python3 scripts/record_paper_picks.py --from-json picks.json --commit
    cat picks.json | python3 scripts/record_paper_picks.py --from-json - --commit
"""
import argparse
import json
import logging
import sys

import _bootstrap  # noqa: F401

import paper_tracking

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MIGRATION_REQUIRED = 2
EXIT_INVALID_INPUT = 3


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-json", required=True, metavar="FILE",
                        help="JSON file with a list of picks, or '-' for stdin.")
    parser.add_argument("--commit", action="store_true",
                        help="Write to the database. Without it this only validates.")
    return parser.parse_args(argv)


def _load_rows(source: str) -> list:
    """Read and shape-check the input. Raises ValueError on bad input."""
    try:
        raw = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()
    except OSError as exc:
        raise ValueError(f"could not read {source}: {exc}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} is not valid JSON: {exc}")

    if not isinstance(parsed, list):
        raise ValueError(f"expected a JSON list of picks, got {type(parsed).__name__}")
    return parsed


def _validate_all(rows: list) -> list:
    """Validate every row up front. Raises ValueError naming the bad row."""
    validated = []
    for index, row in enumerate(rows):
        try:
            validated.append(paper_tracking._validate_paper_pick(row))
        except ValueError as exc:
            raise ValueError(f"row {index}: {exc}")
    return validated


def _write(rows: list) -> dict:
    """Insert validated rows, counting new inserts vs existing duplicates."""
    inserted, duplicates, failed = [], [], []
    for index, row in enumerate(rows):
        try:
            saved = paper_tracking.save_paper_pick(row)
        except Exception as exc:
            logging.error("row %d (%s %s) failed: %s",
                          index, row.get("player"), row.get("stat"), exc)
            failed.append(index)
            continue
        (inserted if saved["created"] else duplicates).append(saved["id"])
    return {"inserted": inserted, "duplicates": duplicates, "failed": failed}


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        rows = _load_rows(args.from_json)
        validated = _validate_all(rows)
    except ValueError as exc:
        print(f"\n  Invalid input: {exc}\n", file=sys.stderr)
        return EXIT_INVALID_INPUT

    if not validated:
        print("\n  No picks in input — nothing to record.\n")
        return EXIT_OK

    print(f"\n  {len(validated)} paper pick(s) validated:")
    for row in validated:
        print(f"    {row['game_date']}  {row['player']:<24} "
              f"{row['stat']:<4} {row['direction']:<5} {row['line']}")

    if not args.commit:
        print("\n  DRY RUN — nothing written. Re-run with --commit.\n")
        return EXIT_OK

    try:
        if not paper_tracking.has_paper_pick_support():
            raise paper_tracking.MigrationRequiredError(
                f"picks.is_paper column is missing. Apply "
                f"{paper_tracking.MIGRATION_FILE} first."
            )
        result = _write(validated)
    except paper_tracking.MigrationRequiredError as exc:
        print(f"\n  Schema not ready: {exc}\n", file=sys.stderr)
        return EXIT_MIGRATION_REQUIRED
    except Exception as exc:
        logging.error("Recording failed: %s", exc, exc_info=True)
        return EXIT_ERROR

    print(f"\n  recorded : {len(result['inserted'])}")
    print(f"  existing : {len(result['duplicates'])}")
    if result["failed"]:
        print(f"  FAILED   : {len(result['failed'])} (see errors above)")
        return EXIT_ERROR
    print()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
