#!/usr/bin/env python3
"""Delete the per-player model fleet from Supabase Storage.

The feature pipeline changed (de-leaked ratio features + new trade-awareness
features), which invalidates every pickled player model.  Retraining is
deferred, so this only removes the stale artifacts; the next prediction per
player cold-trains on the fixed pipeline.

Only objects under the ``players/`` prefix are touched.  The ``games/`` prefix
and the local ``models/games/game_predictor.pkl`` are left alone.

WARNING: ``model_storage.list_player_models()`` cannot be reused here -- it
calls ``storage.list()`` without options and storage3 defaults to
``{'limit': 100, 'offset': 0}``, so it silently truncates at 100 objects.
This script paginates explicitly.

Usage:
    python3 scripts/delete_player_model_fleet.py            # dry run
    python3 scripts/delete_player_model_fleet.py --confirm  # actually delete
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=True)

import model_storage  # noqa: E402  (must follow load_dotenv)

PAGE_SIZE = 1000
DELETE_BATCH = 100


def list_all_player_objects() -> List[str]:
    """Return every object name under ``players/``, paginating past the 100 default."""
    supa = model_storage._get_storage_client()
    bucket = supa.storage.from_(model_storage.BUCKET_NAME)
    names: List[str] = []
    offset = 0
    while True:
        page = bucket.list(
            model_storage._PLAYER_PREFIX,
            {"limit": PAGE_SIZE, "offset": offset,
             "sortBy": {"column": "name", "order": "asc"}},
        )
        if not page:
            break
        names = names + [f["name"] for f in page if f.get("name")]
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
    return names


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="actually delete (default is a dry run)")
    args = parser.parse_args(argv)

    try:
        names = list_all_player_objects()
    except Exception as exc:
        print(f"ERROR: could not list bucket '{model_storage.BUCKET_NAME}': {exc}")
        return 1

    pkls = [n for n in names if n.endswith(".pkl")]
    others = [n for n in names if not n.endswith(".pkl")]

    print(f"Bucket : {model_storage.BUCKET_NAME}")
    print(f"Prefix : {model_storage._PLAYER_PREFIX}")
    print(f"Objects: {len(names)} total ({len(pkls)} .pkl, {len(others)} other)")
    if others:
        print(f"  non-pkl (left alone): {others}")
    if not pkls:
        print("Nothing to delete.")
        return 0

    if not args.confirm:
        print("\nDRY RUN - nothing deleted. Re-run with --confirm to delete.")
        print("First 5:", pkls[:5])
        return 0

    paths = [f"{model_storage._PLAYER_PREFIX}{n}" for n in pkls]
    deleted = 0
    for i in range(0, len(paths), DELETE_BATCH):
        batch = paths[i:i + DELETE_BATCH]
        try:
            supa = model_storage._get_storage_client()
            supa.storage.from_(model_storage.BUCKET_NAME).remove(batch)
            deleted += len(batch)
            print(f"  deleted {deleted}/{len(paths)}")
        except Exception as exc:
            print(f"ERROR deleting batch starting at {i}: {exc}")
            return 1

    remaining = [n for n in list_all_player_objects() if n.endswith(".pkl")]
    print(f"\nDeleted {deleted}. Remaining .pkl under players/: {len(remaining)}")
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
