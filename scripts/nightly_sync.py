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

from nba_api.stats.endpoints import (
    scoreboardv2,
    playergamelog,
    leaguedashteamstats,
    commonallplayers,
)
from nba_api.stats.static import players
from nba_api.library.http import NBAHTTP

import db

# Fix NBA API headers
_nba_session = NBAHTTP.get_session()
_nba_session.headers.update({
    'Referer': 'https://www.nba.com/',
    'Origin': 'https://www.nba.com',
})

CURRENT_SEASON = '2025-26'


def get_active_player_ids():
    """Get all players who played in the current season."""
    print("📋 Fetching active players for current season...")
    try:
        cap = commonallplayers.CommonAllPlayers(
            is_only_current_season=1,
            season=CURRENT_SEASON,
            timeout=30,
        )
        time.sleep(1)
        df = cap.get_data_frames()[0]
        player_list = [
            {'id': int(row['PERSON_ID']), 'name': str(row['DISPLAY_FIRST_LAST'])}
            for _, row in df.iterrows()
        ]
        print(f"  ✅ Found {len(player_list)} active players")
        return player_list
    except Exception as e:
        print(f"  ❌ Failed to get active players: {e}")
        # Fallback to static list
        return [{'id': p['id'], 'name': p['full_name']} for p in players.get_active_players()]


def get_todays_players():
    """Get players who played today (to prioritize syncing them)."""
    print("📅 Checking today's games...")
    try:
        scoreboard = scoreboardv2.ScoreboardV2()
        time.sleep(1)
        games = scoreboard.get_data_frames()[0]
        if games.empty:
            print("  ℹ️  No games today")
            return []

        # Get team IDs that played today
        team_ids = set()
        for _, game in games.iterrows():
            if game.get('GAME_STATUS_ID', 1) == 3:  # Final games only
                team_ids.add(game['HOME_TEAM_ID'])
                team_ids.add(game['VISITOR_TEAM_ID'])

        print(f"  ✅ {len(team_ids)} teams played today")
        return team_ids
    except Exception as e:
        print(f"  ⚠️ Could not fetch today's games: {e}")
        return []


def sync_player_game_logs(player_list, max_players=None):
    """Fetch and store current-season game logs for players."""
    import pandas as pd

    synced = 0
    errors = 0
    skipped = 0

    if max_players:
        player_list = player_list[:max_players]

    total = len(player_list)
    print(f"\n🔄 Syncing game logs for {total} players...")

    for i, player in enumerate(player_list):
        player_id = player['id']
        player_name = player['name']

        try:
            # Check if we already have recent data in Supabase
            existing = db.get_game_logs_from_supabase(str(player_id), CURRENT_SEASON)
            if existing is not None and len(existing) > 0:
                # Check if the data is from today
                latest_date = pd.to_datetime(existing['GAME_DATE']).max()
                days_old = (datetime.now() - latest_date).days
                if days_old <= 1:
                    skipped += 1
                    continue

            # Fetch from NBA API
            log = playergamelog.PlayerGameLog(
                player_id=player_id,
                season=CURRENT_SEASON,
                timeout=30,
            )
            time.sleep(0.8)  # Rate limiting
            df = log.get_data_frames()[0]

            if df.empty:
                skipped += 1
                continue

            df['SEASON'] = CURRENT_SEASON
            db.insert_game_logs_to_supabase(df, str(player_id), CURRENT_SEASON)
            synced += 1

            if (i + 1) % 25 == 0:
                print(f"  📊 Progress: {i + 1}/{total} ({synced} synced, {skipped} skipped, {errors} errors)")

        except Exception as e:
            errors += 1
            if 'timeout' in str(e).lower() or 'timed out' in str(e).lower():
                print(f"  ⏱️  Timeout for {player_name}, retrying in 5s...")
                time.sleep(5)
                try:
                    log = playergamelog.PlayerGameLog(
                        player_id=player_id,
                        season=CURRENT_SEASON,
                        timeout=45,
                    )
                    time.sleep(1)
                    df = log.get_data_frames()[0]
                    if not df.empty:
                        df['SEASON'] = CURRENT_SEASON
                        db.insert_game_logs_to_supabase(df, str(player_id), CURRENT_SEASON)
                        synced += 1
                        errors -= 1
                except Exception:
                    pass
            continue

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
