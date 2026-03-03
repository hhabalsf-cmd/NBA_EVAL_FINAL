"""
One-time backfill: fetch historical game logs for all trained players and store in Supabase.

Usage:
    DATABASE_URL="postgresql://..." python scripts/backfill_game_logs.py [--dry-run]

Options:
    --dry-run   Print what would be fetched without writing to Supabase
    --season    Season to backfill (default: both historical seasons)

Safe to re-run: uses ON CONFLICT DO NOTHING, skips players already stored.
"""
import sys
import os
import time
import argparse
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from nba_evaluator import NBADataScraper, CURRENT_SEASON, HISTORICAL_SEASONS

MODEL_DIR = Path(__file__).parent.parent / "models"


def get_trained_player_names() -> list:
    """Read player names from existing model .pkl filenames."""
    return [
        p.stem.replace("_model", "").replace("_", " ")
        for p in MODEL_DIR.glob("*_model.pkl")
        if p.parent == MODEL_DIR  # skip models/games/
    ]


def name_to_player_id(scraper: NBADataScraper, name: str):
    try:
        info = scraper.get_player_info(name)
        return str(info["player_id"]) if info else None
    except Exception:
        return None


def already_stored(player_id: str, season: str) -> bool:
    """Return True if Supabase already has rows for this player+season."""
    df = db.get_game_logs_from_supabase(player_id, season)
    return df is not None and not df.empty


def backfill(dry_run: bool = False, seasons=None):
    if seasons is None:
        seasons = HISTORICAL_SEASONS

    scraper = NBADataScraper()
    player_names = get_trained_player_names()
    total = len(player_names) * len(seasons)

    print(f"Backfilling {len(player_names)} players × {len(seasons)} seasons = {total} checks")
    print(f"Seasons: {seasons}")
    if dry_run:
        print("DRY RUN — no writes\n")

    stored = skipped = failed = 0

    for name in sorted(player_names):
        player_id = name_to_player_id(scraper, name)
        if not player_id:
            print(f"  ⚠️  {name}: player not found")
            failed += 1
            continue

        for season in seasons:
            if already_stored(player_id, season):
                print(f"  ✓  {name} {season}: already in Supabase (skip)")
                skipped += 1
                continue

            print(f"  → {name} {season}: fetching...", end=" ", flush=True)
            if dry_run:
                print("(dry run)")
                continue

            try:
                from nba_api.stats.endpoints import playergamelog
                import pandas as pd
                log = playergamelog.PlayerGameLog(player_id=player_id, season=season)
                time.sleep(0.6)
                df = log.get_data_frames()[0]
                df['SEASON'] = season
                db.insert_game_logs_to_supabase(df, player_id, season)
                print(f"{len(df)} rows stored")
                stored += 1
            except Exception as e:
                print(f"ERROR: {e}")
                failed += 1

    print(f"\nDone. Stored: {stored} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--season", help="Single season to backfill (e.g. 2024-25)")
    args = parser.parse_args()

    seasons = [args.season] if args.season else None
    backfill(dry_run=args.dry_run, seasons=seasons)
