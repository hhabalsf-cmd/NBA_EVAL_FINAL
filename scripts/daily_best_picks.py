#!/usr/bin/env python3
"""
Daily Best Picks Generator
===========================
Runs each morning (8 AM ET via pg_cron → POST /api/bets/generate),
evaluates every player on today's slate, and stores the top 15 picks
in the `daily_picks` Supabase table for instant frontend reads.

Line strategy: Uses each player's L10 average as a proxy "line" until
a new OddsAPI key is added.  The `odds_line` column stays NULL for now.

Run manually:
    python scripts/daily_best_picks.py

Schedule (handled by pg_cron hitting the /api/bets/generate endpoint):
    8:00 AM ET = 1:00 PM UTC
"""

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Project root setup ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

import numpy as np
import pandas as pd
from bdl_client import get_bdl_client
from bdl_id_mapper import get_team_mapper, get_player_mapper
from sleeper_client import get_headshot_url as get_sleeper_headshot

import db
from nba_evaluator import (
    NBADataScraper,
    FeatureEngineer,
    MLPredictor,
    MODEL_DIR,
    CURRENT_SEASON,
)

# ── NBA CDN headshot fallback ──────────────────────────────────
_nba_name_to_id: dict[str, int] = {}


def _get_nba_headshot_url(player_name: str) -> Optional[str]:
    """Fallback: look up NBA person ID via nba_api static list, return CDN URL."""
    global _nba_name_to_id
    if not _nba_name_to_id:
        try:
            from nba_api.stats.static import players as nba_players
            for p in nba_players.get_active_players():
                _nba_name_to_id[p['full_name'].lower()] = p['id']
        except Exception as exc:
            logging.getLogger(__name__).warning("nba_api player lookup failed: %s", exc)
            return None

    name_lower = player_name.lower().strip()
    nba_id = _nba_name_to_id.get(name_lower)
    if nba_id:
        return f"https://cdn.nba.com/headshots/nba/latest/260x190/{nba_id}.png"
    # Partial match fallback
    for name, nba_id in _nba_name_to_id.items():
        if name_lower in name or name in name_lower:
            return f"https://cdn.nba.com/headshots/nba/latest/260x190/{nba_id}.png"
    return None


def _get_best_headshot_url(player_name: str) -> Optional[str]:
    """Try Sleeper CDN first, fall back to NBA CDN."""
    url = get_sleeper_headshot(player_name)
    if url:
        return url
    return _get_nba_headshot_url(player_name)

# ── Configuration ───────────────────────────────────────────────
MIN_EDGE_PCT = 20.0          # Minimum absolute edge to include
MAX_EDGE_PCT = 46.0          # Maximum absolute edge to include
MIN_CONFIDENCE = 60.0        # Minimum model confidence
MAX_PICKS = 10               # Cap on total picks returned
MIN_MINUTES_AVG = 20.0       # Minimum average minutes to evaluate
MIN_GAMES_TO_TRAIN = 15      # Minimum historical games to train a model
STATS_TO_EVALUATE = ['PTS', 'REB', 'AST', 'PRA']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


# ── Helper functions ────────────────────────────────────────────

def _get_teams_playing_today() -> list[dict]:
    """
    Fetch today's schedule via BallDontLie API and return game dicts:
    [{'home_abbrev': str, 'away_abbrev': str, 'game_date': str, 'bdl_game_id': int}, ...]
    If no games are found for today, falls back to checking tomorrow.
    """
    logger.info("📅 Fetching today's NBA schedule...")
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    target_date = datetime.now(ZoneInfo("America/New_York")).date()
    today_str = target_date.strftime('%Y-%m-%d')
    bdl = get_bdl_client()
    raw_games = bdl.get_games(dates=[today_str])

    # Fallback to tomorrow if no games today
    if not raw_games:
        tomorrow_date = target_date + timedelta(days=1)
        tomorrow_str = tomorrow_date.strftime('%Y-%m-%d')
        logger.info(f"No games found for today ({today_str}). Falling back to tomorrow ({tomorrow_str}).")
        target_date = tomorrow_date
        today_str = tomorrow_str
        raw_games = bdl.get_games(dates=[today_str])

    if not raw_games:
        logger.warning(f"No games on schedule for {today_str} either.")
        return []

    games = []
    for g in raw_games:
        home = g.get('home_team') or {}
        visitor = g.get('visitor_team') or {}
        home_abbrev = str(home.get('abbreviation') or '').upper()
        visitor_abbrev = str(visitor.get('abbreviation') or '').upper()
        if not home_abbrev or not visitor_abbrev:
            continue
        bdl_game_id = g.get('id')
        games.append({
            'home_abbrev': home_abbrev,
            'away_abbrev': visitor_abbrev,
            'game_date': today_str,
            'bdl_game_id': int(bdl_game_id) if bdl_game_id is not None else None,
        })

    logger.info(f"  Found {len(games)} games today.")
    return games


def _fetch_player_props_lookup(games: list[dict]) -> dict:
    """
    Fetch player props for all of today's games from BDL v2 API.
    Returns: {'by_id': {bdl_player_id: {stat: median_line}}}

    Only uses over_under market type props. Computes median line across
    vendors for each player+stat combo to resist outlier lines.

    BDL v2 response format per prop:
      {'player_id': int, 'prop_type': str, 'line_value': str,
       'market': {'type': 'over_under', ...}, 'vendor': str, ...}
    """
    _PROP_TYPE_MAP: dict[str, str] = {
        'points': 'PTS',
        'rebounds': 'REB',
        'assists': 'AST',
        'points_rebounds_assists': 'PRA',
    }

    bdl = get_bdl_client()
    # Collect all lines per player+stat for median calculation
    # {bdl_player_id: {stat: [line_values_from_different_vendors]}}
    raw_lines: dict[int, dict[str, list[float]]] = {}

    for g in games:
        bdl_game_id = g.get('bdl_game_id')
        if bdl_game_id is None:
            logger.debug("_fetch_player_props_lookup: skipping game with no bdl_game_id: %s", g)
            continue

        try:
            raw_props = bdl.get_player_props(game_id=bdl_game_id)
        except Exception as exc:
            logger.warning(
                "_fetch_player_props_lookup: failed to fetch props for game_id=%s: %s",
                bdl_game_id, exc,
            )
            continue

        for prop in raw_props:
            # BDL v2: player_id at top level, filter for over_under market
            market = prop.get('market') or {}
            if market.get('type') != 'over_under':
                continue

            bdl_player_id = prop.get('player_id')
            if bdl_player_id is None:
                continue

            prop_type = str(prop.get('prop_type') or '').lower()
            stat = _PROP_TYPE_MAP.get(prop_type)
            if stat is None:
                # Check for combo props containing all three components
                if 'points' in prop_type and 'rebounds' in prop_type and 'assists' in prop_type:
                    stat = 'PRA'
                else:
                    continue

            raw_line = prop.get('line_value')
            if raw_line is None:
                continue

            bdl_player_id = int(bdl_player_id)
            line_val = float(raw_line)

            # Accumulate lines from all vendors for median calculation
            player_lines = raw_lines.get(bdl_player_id, {})
            stat_lines = player_lines.get(stat, [])
            raw_lines[bdl_player_id] = {**player_lines, stat: [*stat_lines, line_val]}

    # Compute median line per player+stat (consensus across vendors)
    props_lookup: dict[int, dict[str, float]] = {}
    total_props = 0
    for pid, stat_dict in raw_lines.items():
        player_entry: dict[str, float] = {}
        for stat, lines in stat_dict.items():
            player_entry[stat] = round(float(np.median(lines)), 1)
            total_props += 1
        props_lookup[pid] = player_entry

    logger.info(
        "_fetch_player_props_lookup: fetched %d consensus lines across %d players.",
        total_props, len(props_lookup),
    )
    return {'by_id': props_lookup, 'by_name': {}}


def _get_players_for_teams(team_abbrevs: set[str]) -> list[dict]:
    """
    Return active players on the given teams by scanning Supabase game logs.
    Filters to players who average >= MIN_MINUTES_AVG in the current season.
    """
    logger.info(f"🏀 Finding active players on {len(team_abbrevs)} teams...")
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    player_id,
                    MAX(player_name) AS player_name,
                    MAX(matchup) AS last_matchup,
                    AVG(min) AS avg_min,
                    COUNT(*) AS games_played
                FROM player_game_logs
                WHERE season = %s
                GROUP BY player_id
                HAVING AVG(min) >= %s AND COUNT(*) >= %s
            """, (CURRENT_SEASON, MIN_MINUTES_AVG, MIN_GAMES_TO_TRAIN))
            rows = cur.fetchall()
    finally:
        db.put_connection(conn)

    if not rows:
        logger.warning("No players found meeting the criteria.")
        return []

    result = []
    for row in rows:
        pid = row['player_id']
        player_name = str(row.get('player_name') or '').strip()
        if not player_name:
            # player_name column may not exist in the DB schema; fall back to player_id string
            player_name = str(pid)

        # Derive team from last matchup: first 3 chars are always the player's team
        last_matchup = row.get('last_matchup', '') or ''
        team_abbrev = last_matchup[:3].strip() if len(last_matchup) >= 3 else None

        # Check if this player's team is playing today
        if team_abbrev and team_abbrev in team_abbrevs:
            result.append({
                'player_id': pid,
                'player_name': player_name,
                'team_abbrev': team_abbrev,
                'avg_min': float(row['avg_min']),
                'games_played': int(row['games_played']),
            })

    logger.info(f"  Found {len(result)} eligible players (avg min >= {MIN_MINUTES_AVG}, games >= {MIN_GAMES_TO_TRAIN}).")
    return result


def _compute_l10_avg(game_log_df: pd.DataFrame, stat: str) -> Optional[float]:
    """Compute the last-10-game average for a stat, or None if insufficient data."""
    if game_log_df is None or game_log_df.empty:
        return None
    col = stat
    if stat == 'PRA':
        vals = game_log_df['PTS'].tail(10) + game_log_df['REB'].tail(10) + game_log_df['AST'].tail(10)
    elif col in game_log_df.columns:
        vals = game_log_df[col].tail(10)
    else:
        return None
    avg = vals.mean()
    return round(float(avg), 1) if not np.isnan(avg) else None


def _build_matchup_string(player_team: str, opponent: str, is_home: bool) -> str:
    """Build a matchup display string like 'LAL vs. BOS'."""
    if is_home:
        return f"{player_team} vs. {opponent}"
    return f"{player_team} @ {opponent}"


def _sync_game_logs_for_prop_players(props_lookup: dict) -> int:
    """
    Ensure game logs exist in Supabase for all players who have prop lines.
    Fetches full current-season logs from BDL for any player missing data.
    Returns the number of players synced.
    """
    by_id = props_lookup.get('by_id', {})
    if not by_id:
        return 0

    bdl_player_ids = list(by_id.keys())
    logger.info(f"🔄 Checking game logs for {len(bdl_player_ids)} players with prop lines...")

    scraper = NBADataScraper()
    season_int = int(CURRENT_SEASON.split('-')[0])
    synced = 0
    already_have = 0

    for bdl_pid in bdl_player_ids:
        # Check if we already have sufficient game logs
        existing = db.get_game_logs_from_supabase(str(bdl_pid), CURRENT_SEASON)
        if existing is not None and len(existing) >= MIN_GAMES_TO_TRAIN:
            already_have += 1
            continue

        # Fetch full season game log from BDL
        try:
            df = scraper._fetch_bdl_game_log(bdl_pid, bdl_pid, season_int, CURRENT_SEASON)
            if df is not None and not df.empty:
                db.insert_game_logs_to_supabase(df, str(bdl_pid), CURRENT_SEASON)
                synced += 1
                logger.debug(f"  ✅ Synced {len(df)} games for player {bdl_pid}")
        except Exception as exc:
            logger.debug(f"  ⚠️ Could not sync player {bdl_pid}: {exc}")

    logger.info(
        f"🔄 Game log sync: {synced} new, {already_have} already populated, "
        f"{len(bdl_player_ids) - synced - already_have} failed/empty."
    )
    return synced


# ── Core pipeline ───────────────────────────────────────────────

def generate_daily_picks() -> list[dict]:
    """
    Main entry point: evaluate all eligible players and return
    the top picks sorted by abs(edge) descending.
    """
    # 1. Get today's games (or tomorrow's if none today)
    games = _get_teams_playing_today()
    if not games:
        logger.info("No games today — nothing to generate.")
        return []
        
    # Use the actual date of the games we fetched (could be today or tomorrow)
    active_date_str = games[0]['game_date']

    # Fetch real prop lines (may return {} if API unavailable)
    props_lookup = _fetch_player_props_lookup(games)
    logger.info(f"📊 Fetched props for {len(props_lookup.get('by_id', {}))} players.")

    # Initialize player mapper for nba.com ID → BDL ID lookup
    try:
        player_mapper = get_player_mapper()
    except Exception as exc:
        logger.warning("Could not initialize player mapper: %s — props will not be used.", exc)
        player_mapper = None

    # Build lookup structures
    team_abbrevs_today = set()
    team_game_map: dict[str, dict] = {}  # team_abbrev → game dict
    for g in games:
        team_abbrevs_today.add(g['home_abbrev'])
        team_abbrevs_today.add(g['away_abbrev'])
        team_game_map[g['home_abbrev']] = g
        team_game_map[g['away_abbrev']] = g

    # 2. Ensure game logs exist for all players with prop lines
    _sync_game_logs_for_prop_players(props_lookup)

    # 3. Get team defensive stats
    scraper = NBADataScraper()
    team_stats = scraper.get_team_defensive_stats()
    logger.info(f"📊 Loaded defensive stats for {len(team_stats)} teams.")

    # 4. Get eligible players
    eligible_players = _get_players_for_teams(team_abbrevs_today)
    if not eligible_players:
        logger.info("No eligible players found.")
        return []

    # 5. Evaluate each player
    all_candidates: list[dict] = []
    players_evaluated = 0
    models_trained = 0
    players_skipped = 0
    skipped_missing_lines = 0

    for player in eligible_players:
        player_name = player['player_name']
        player_id = player['player_id']
        team_abbrev = player['team_abbrev']

        # Determine game context
        game = team_game_map.get(team_abbrev)
        if not game:
            continue

        is_home = game['home_abbrev'] == team_abbrev
        opponent = game['away_abbrev'] if is_home else game['home_abbrev']

        # Load game log from Supabase (no NBA API call)
        game_log = db.get_game_logs_from_supabase(str(player_id), CURRENT_SEASON)
        if game_log is None or len(game_log) < MIN_GAMES_TO_TRAIN:
            logger.debug(f"  ⏭️ Skipping {player_name}: only {len(game_log) if game_log is not None else 0} games (need {MIN_GAMES_TO_TRAIN})")
            players_skipped += 1
            continue

        # Parse MIN column to numeric if needed
        if 'MIN' in game_log.columns and game_log['MIN'].dtype == object:
            def _parse_min(val):
                try:
                    parts = str(val).split(':')
                    return float(parts[0]) + float(parts[1]) / 60 if len(parts) == 2 else float(parts[0])
                except Exception:
                    return 0.0
            game_log['MIN'] = game_log['MIN'].apply(_parse_min)

        # Add MIN_NUMERIC alias (used by FeatureEngineer)
        game_log['MIN_NUMERIC'] = pd.to_numeric(game_log['MIN'], errors='coerce').fillna(0)

        # Sort ascending by date (FeatureEngineer expects this)
        game_log['GAME_DATE'] = pd.to_datetime(game_log['GAME_DATE'], format='mixed')
        game_log = game_log.sort_values('GAME_DATE').reset_index(drop=True)

        # Build player_info dict for FeatureEngineer
        player_info = {
            'player_id': player_id,
            'player_name': player_name,
            'team_abbrev': team_abbrev,
            'position': '',
        }

        # Create features
        try:
            df = FeatureEngineer.create_features(
                game_log,
                player_info=player_info,
                team_stats=team_stats,
            )
        except Exception as e:
            logger.warning(f"  ⚠️ Feature engineering failed for {player_name}: {e}")
            continue

        if df is None or df.empty or len(df) < MIN_GAMES_TO_TRAIN:
            players_skipped += 1
            continue

        # Load or train model
        predictor = MLPredictor(model_type='gradient_boost')
        model_loaded = predictor.load(player_name)

        if not model_loaded:
            # Train a new model on the spot
            logger.info(f"  🔧 Training new model for {player_name} ({len(df)} games)...")
            try:
                train_success = predictor.train(df, stats=STATS_TO_EVALUATE[:3])  # PTS, REB, AST
                if not train_success:
                    logger.warning(f"  ⚠️ Training failed for {player_name}")
                    players_skipped += 1
                    continue
                predictor.save(player_name)
                models_trained += 1
            except Exception as e:
                logger.warning(f"  ⚠️ Training error for {player_name}: {e}")
                players_skipped += 1
                continue
        else:
            # Warm-start update with latest game data
            try:
                predictor.update(df)
                predictor.save(player_name)
            except Exception as e:
                logger.warning(f"  ⚠️ Update error for {player_name}: {e}")

        # Calculate actual days rest from game log
        days_rest = 2
        if 'GAME_DATE' in df.columns and len(df) > 1:
            try:
                last_game = pd.to_datetime(df['GAME_DATE'].iloc[-1])
                days_rest = min((datetime.now() - last_game).days, 7)
            except Exception:
                pass

        # Get full opponent context (enhanced stats)
        opp_ctx = FeatureEngineer.extract_opp_stats(team_stats, opponent)

        # Get prediction features for today's game
        try:
            features_df = FeatureEngineer.get_prediction_features(
                df,
                is_home=1 if is_home else 0,
                opponent=opponent,
                days_rest=days_rest,
                player_info=player_info,
                **opp_ctx,
            )
        except Exception as e:
            logger.warning(f"  ⚠️ Prediction features failed for {player_name}: {e}")
            continue

        # Estimate minutes
        injuries_team = 0  # Could be enhanced with injury data later
        estimated_minutes = FeatureEngineer.estimate_minutes(
            df,
            is_home=1 if is_home else 0,
            days_rest=days_rest,
            injuries_team=injuries_team,
        )

        # Ensure recent averages are fresh (not stale from pickle) before predicting
        predictor._update_recent_averages(df)

        # Predict
        try:
            predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)
        except Exception as e:
            logger.warning(f"  ⚠️ Prediction failed for {player_name}: {e}")
            continue

        players_evaluated += 1

        # Evaluate each stat
        for stat in STATS_TO_EVALUATE:
            pred_value = predictions.get(stat)
            if pred_value is None or np.isnan(pred_value):
                continue

            pred_value = round(float(pred_value), 1)

            # L10 average (always computed as secondary reference)
            l10_avg = _compute_l10_avg(game_log, stat)
            if l10_avg is None or l10_avg == 0:
                continue

            # Try to get real prop line from BDL
            prediction = predictions.get(stat)
            if prediction is None:
                continue

            # Need odds line to evaluate edge
            # 1. Try BDL ID first
            bdl_id = None
            if player_mapper is not None:
                try:
                    bdl_id = player_mapper.nba_to_bdl(int(player_id), player_name=player_name)
                except Exception as exc:
                    logger.debug(f"BDL ID lookup failed for {player_name} (NBA ID: {player_id}): {exc}")
            
            # 2. Extract props
            player_props = None
            if bdl_id is not None:
                player_props = props_lookup.get('by_id', {}).get(bdl_id, {})
                
            # 3. Fallback to name search if ID failed or no props
            if not player_props:
                player_name_lower = str(player_name or '').strip().lower()
                player_props = props_lookup.get('by_name', {}).get(player_name_lower, {})
                if player_props:
                    logger.debug(f"Used name fallback for props lookup on {player_name}")

            if not player_props:
                skipped_missing_lines += 1
                continue

            odds_line = player_props.get(stat)
            if odds_line is None:
                skipped_missing_lines += 1
                continue
            odds_line = round(float(odds_line), 1) # Ensure odds_line is rounded float

            # Use real line if available, else fall back to L10 average
            line_used = odds_line if odds_line is not None else l10_avg
            if line_used is None or line_used == 0:
                continue

            # Recompute edge against whichever line is used
            edge_pct = round(((pred_value - line_used) / line_used) * 100, 1)
            abs_edge = abs(edge_pct)

            # Direction
            direction = 'OVER' if pred_value > line_used else 'UNDER'

            # Get confidence + range
            conf_data: dict = {}
            try:
                conf_data = predictor.get_confidence(df, stat, pred_value, features_df=features_df)
                confidence = conf_data.get('confidence', 0)
                range_low = conf_data.get('low', pred_value)
                range_high = conf_data.get('high', pred_value)
            except Exception:
                confidence = 0
                range_low = pred_value
                range_high = pred_value

            # Probability over (use isotonic calibration if available)
            try:
                prob_over = conf_data.get('prob_over')
                if prob_over is None:
                    # Fallback: estimate from confidence + direction
                    prob_over = confidence if direction == 'OVER' else (100 - confidence)
            except Exception:
                prob_over = 50.0

            # Apply filters
            if confidence < MIN_CONFIDENCE:
                continue
            if abs_edge < MIN_EDGE_PCT or abs_edge > MAX_EDGE_PCT:
                continue

            matchup = _build_matchup_string(team_abbrev, opponent, is_home)

            all_candidates.append({
                'player': player_name,
                'player_id': player_id,
                'headshot_url': _get_best_headshot_url(player_name),
                'team_abbrev': team_abbrev,
                'stat': stat,
                'prediction': pred_value,
                'confidence': round(float(confidence), 1),
                'range_low': round(float(range_low), 1),
                'range_high': round(float(range_high), 1),
                'recent_avg': l10_avg,
                'odds_line': odds_line,  # real prop line, or None if using L10 avg
                'edge': edge_pct,
                'direction': direction,
                'opponent': opponent,
                'is_home': is_home,
                'matchup': matchup,
                'game_date': active_date_str,
                'model_type': 'gradient_boost',
                'prob_over': round(float(prob_over), 1) if prob_over is not None else None,
            })

    logger.info(
        f"📈 Evaluated {players_evaluated} players, "
        f"trained {models_trained} new models, "
        f"skipped {players_skipped}, "
        f"found {len(all_candidates)} candidates meeting filters."
    )

    # 6. Rank and cap
    ranked = sorted(all_candidates, key=lambda c: abs(c['edge']), reverse=True)
    top_picks = ranked[:MAX_PICKS]

    # Assign ranks
    for i, pick in enumerate(top_picks, start=1):
        pick['rank'] = i

    return top_picks


def run() -> dict:
    """
    Generate picks and persist to Supabase.
    Returns a summary dict for logging / API response.
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"🚀 Starting Daily Best Picks generation for {today_str}")

    start_time = time.time()

    try:
        picks = generate_daily_picks()
    except Exception as e:
        logger.error(f"❌ Generation failed: {e}", exc_info=True)
        return {'success': False, 'error': str(e), 'picks_count': 0}

    # Use the date from the first pick if available, otherwise today
    target_date_str = picks[0]['game_date'] if picks else today_str

    # Save to Supabase
    saved_count = db.save_daily_picks(picks, target_date_str)
    logger.info(f"💾 Saved {saved_count} picks to daily_picks table for {target_date_str}.")

    # Housekeeping: remove picks older than 7 days
    deleted = db.clear_old_daily_picks(days_to_keep=7)
    if deleted > 0:
        logger.info(f"🧹 Cleaned up {deleted} old daily pick rows.")

    elapsed = round(time.time() - start_time, 1)
    logger.info(f"✅ Done in {elapsed}s — {saved_count} picks generated.")

    return {
        'success': True,
        'picks_count': saved_count,
        'elapsed_seconds': elapsed,
        'date': today_str,
    }


if __name__ == '__main__':
    result = run()
    if result['success']:
        logger.info(f"Summary: {result}")
    else:
        logger.error(f"Failed: {result}")
        sys.exit(1)
