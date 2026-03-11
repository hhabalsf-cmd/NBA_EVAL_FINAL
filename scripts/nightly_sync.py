#!/usr/bin/env python3
"""
Nightly NBA Data Sync
=====================
Fetches current-season game logs for all active players and team stats,
then stores everything in Supabase so the deployed Railway backend
never needs to call the slow NBA API directly.

Run manually:
    python scripts/nightly_sync.py

Schedule as cron (11:45 PM ET every night):
    45 23 * * * cd /Users/hhabal/Downloads/Projects/NBA/EVAL && /usr/bin/python3 scripts/nightly_sync.py >> /tmp/nba_sync.log 2>&1
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

import db
from bdl_client import get_bdl_client
from bdl_id_mapper import get_team_mapper, get_player_mapper
from nba_evaluator import NBADataScraper

CURRENT_SEASON = '2025-26'


def get_active_player_ids():
    """Get all active NBA players using nba_api."""
    print("📋 Fetching active players from NBA API...")
    try:
        from nba_api.stats.static import players as nba_players
        active_list = nba_players.get_active_players()
        
        player_list = []
        for p in active_list:
            player_list.append({
                'id': p['id'],
                'name': p['full_name']
            })
            
        print(f"  ✅ Found {len(player_list)} active players")
        return player_list
    except Exception as e:
        print(f"  ❌ Failed to get active players: {e}")
        return []


def get_todays_players():
    """Get team abbreviations that played today via BallDontLie API."""
    print("📅 Checking today's games...")
    try:
        today_str = datetime.now().date().strftime('%Y-%m-%d')
        bdl = get_bdl_client()
        raw_games = bdl.get_games(dates=[today_str])
        if not raw_games:
            print("  ℹ️  No games today")
            return set()

        team_abbrevs = set()
        for g in raw_games:
            status = str(g.get('status') or '').lower()
            if status == 'final':
                home = g.get('home_team') or {}
                visitor = g.get('visitor_team') or {}
                h_abbrev = str(home.get('abbreviation') or '').upper()
                v_abbrev = str(visitor.get('abbreviation') or '').upper()
                if h_abbrev: team_abbrevs.add(h_abbrev)
                if v_abbrev: team_abbrevs.add(v_abbrev)

        print(f"  ✅ {len(team_abbrevs)} teams played today")
        return team_abbrevs
    except Exception as e:
        print(f"  ⚠️ Could not fetch today's games: {e}")
        return set()


def sync_player_game_logs(player_list, max_players=None):
    """Fetch and store current-season game logs via BallDontLie API."""
    import pandas as pd

    synced = 0
    errors = 0
    skipped = 0

    if max_players:
        player_list = player_list[:max_players]

    total = len(player_list)
    print(f"\n🔄 Syncing game logs for {total} players...")

    scraper = NBADataScraper()

    for i, player in enumerate(player_list):
        player_id = player['id']
        player_name = player['name']

        try:
            # Check if we already have recent data
            existing = db.get_game_logs_from_supabase(str(player_id), CURRENT_SEASON)
            if existing is not None and len(existing) > 0:
                latest_date = pd.to_datetime(existing['GAME_DATE']).max()
                days_old = (datetime.now() - latest_date).days
                if days_old <= 1:
                    skipped += 1
                    continue

            # Fetch via NBADataScraper (uses BDL internally)
            df = scraper.get_player_game_log(player_id, seasons=[CURRENT_SEASON])

            if df is None or df.empty:
                skipped += 1
                continue

            db.insert_game_logs_to_supabase(df, str(player_id), CURRENT_SEASON)
            synced += 1

            if (i + 1) % 25 == 0:
                print(f"  📊 Progress: {i + 1}/{total} ({synced} synced, {skipped} skipped, {errors} errors)")

        except Exception as e:
            errors += 1
            print(f"  ⚠️ Error syncing {player_name}: {e}")

    print(f"\n✅ Game log sync complete: {synced} synced, {skipped} up-to-date, {errors} errors")
    return synced


def sync_team_stats():
    """Fetch and store team defensive stats."""
    print("\n🛡️  Syncing team defensive stats...")
    try:
        from nba_evaluator import NBADataScraper
        scraper = NBADataScraper()
        team_data = scraper.get_team_defensive_stats(CURRENT_SEASON)
        if team_data:
            print(f"  ✅ Updated stats for {len(team_data)} teams")
            return True
    except Exception as e:
        print(f"  ❌ Failed to sync team stats: {e}")
    return False


def main():
    start = time.time()
    print(f"\n{'='*60}")
    print(f"🏀 NBA Nightly Data Sync — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    # 1. Get all active players
    all_players = get_active_player_ids()

    # 2. Sync game logs
    sync_player_game_logs(all_players)

    # 3. Sync team stats
    sync_team_stats()

    elapsed = time.time() - start
    print(f"\n⏱️  Total time: {elapsed / 60:.1f} minutes")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
