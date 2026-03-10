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

# ── Project root setup ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

import numpy as np
import pandas as pd
from bdl_client import get_bdl_client
from bdl_id_mapper import get_team_mapper, get_player_mapper

import db
from nba_evaluator import (
    NBADataScraper,
    FeatureEngineer,
    MLPredictor,
    MODEL_DIR,
    CURRENT_SEASON,
)

# ── Configuration ───────────────────────────────────────────────
MIN_EDGE_PCT = 20.0          # Minimum absolute edge to include
MAX_EDGE_PCT = 45.0          # Maximum absolute edge to include
MIN_CONFIDENCE = 80.0        # Minimum model confidence
MAX_PICKS = 15               # Cap on total picks returned
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
    """
    logger.info("📅 Fetching today's NBA schedule...")
    today_str = datetime.now().strftime('%Y-%m-%d')
    bdl = get_bdl_client()
    raw_games = bdl.get_games(dates=[today_str])

    if not raw_games:
        logger.warning("No games on today's schedule.")
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
    Fetch player props for all of today's games from BDL.
    Returns: {bdl_player_id: {stat: line_value}}

    Prop type mapping (BDL prop_type -> our stat):
      'points'       -> 'PTS'
      'rebounds'     -> 'REB'
      'assists'      -> 'AST'
      'pts_reb_ast'  -> 'PRA'  (or any combo containing all three)

    If get_player_props() raises, log warning and return {} for that game.
    """
    _PROP_TYPE_MAP: dict[str, str] = {
        'points': 'PTS',
        'rebounds': 'REB',
        'assists': 'AST',
        'pts_reb_ast': 'PRA',
    }

    bdl = get_bdl_client()
    # {bdl_player_id (int): {stat (str): line_value (float)}}
    props_lookup: dict[int, dict[str, float]] = {}
    total_props = 0

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
            player_obj = prop.get('player') or {}
            bdl_player_id = player_obj.get('id')
            if bdl_player_id is None:
                continue

            prop_type = str(prop.get('prop_type') or '').lower()
            stat = _PROP_TYPE_MAP.get(prop_type)
            if stat is None:
                # Check for combo props containing all three components
                if 'pts' in prop_type and 'reb' in prop_type and 'ast' in prop_type:
                    stat = 'PRA'
                else:
                    continue

            raw_line = prop.get('line')
            if raw_line is None:
                continue

            bdl_player_id = int(bdl_player_id)
            # Only store the first line found per player+stat (immutable: build new dict entry)
            existing = props_lookup.get(bdl_player_id, {})
            if stat not in existing:
                props_lookup[bdl_player_id] = {**existing, stat: float(raw_line)}
                total_props += 1

    logger.info(
        "_fetch_player_props_lookup: fetched %d prop lines across %d players.",
        total_props, len(props_lookup),
    )
    return props_lookup


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


def _compute_l10_avg(game_log_df: pd.DataFrame, stat: str) -> float | None:
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


# ── Core pipeline ───────────────────────────────────────────────

def generate_daily_picks() -> list[dict]:
    """
    Main entry point: evaluate all eligible players and return
    the top picks sorted by abs(edge) descending.
    """
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 1. Get today's games
    games = _get_teams_playing_today()
    if not games:
        logger.info("No games today — nothing to generate.")
        return []

    # Fetch real prop lines (may return {} if API unavailable)
    props_lookup = _fetch_player_props_lookup(games)
    logger.info(f"📊 Fetched props for {len(props_lookup)} players.")

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

    # 2. Get team defensive stats (shared context)
    scraper = NBADataScraper()
    team_stats = scraper.get_team_defensive_stats()
    logger.info(f"📊 Loaded defensive stats for {len(team_stats)} teams.")

    # 3. Get eligible players
    eligible_players = _get_players_for_teams(team_abbrevs_today)
    if not eligible_players:
        logger.info("No eligible players found.")
        return []

    # 4. Evaluate each player
    all_candidates: list[dict] = []
    players_evaluated = 0
    models_trained = 0
    players_skipped = 0

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

        # Get opponent defensive stats
        opp_stats = team_stats.get(opponent, {})
        opp_def_rating = opp_stats.get('def_rating', 110.0)
        opp_pace = opp_stats.get('pace', 100.0)
        opp_ast_allowed = opp_stats.get('opp_ast', 25.0)

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

        # Get prediction features for today's game
        try:
            features_df = FeatureEngineer.get_prediction_features(
                df,
                is_home=1 if is_home else 0,
                opponent=opponent,
                opp_def_rating=opp_def_rating,
                opp_pace=opp_pace,
                opp_ast_allowed=opp_ast_allowed,
                days_rest=2,  # Default; could be computed from game log
                player_info=player_info,
            )
        except Exception as e:
            logger.warning(f"  ⚠️ Prediction features failed for {player_name}: {e}")
            continue

        # Estimate minutes
        estimated_minutes = FeatureEngineer.estimate_minutes(
            df,
            is_home=1 if is_home else 0,
            days_rest=2,
        )

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
            odds_line: float | None = None
            if player_mapper is not None and props_lookup:
                try:
                    bdl_player_id = player_mapper.nba_to_bdl(int(player_id), player_name=player_name)
                    if bdl_player_id is not None:
                        player_props = props_lookup.get(int(bdl_player_id), {})
                        raw_line = player_props.get(stat)
                        if raw_line is not None:
                            odds_line = round(float(raw_line), 1)
                except Exception as exc:
                    logger.debug(
                        "Props lookup failed for %s stat=%s: %s", player_name, stat, exc
                    )

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
                'team_abbrev': team_abbrev,
                'stat': stat,
                'prediction': pred_value,
                'confidence': round(confidence, 1),
                'range_low': round(float(range_low), 1),
                'range_high': round(float(range_high), 1),
                'recent_avg': l10_avg,
                'odds_line': odds_line,  # real prop line, or None if using L10 avg
                'edge': edge_pct,
                'direction': direction,
                'opponent': opponent,
                'is_home': is_home,
                'matchup': matchup,
                'game_date': today_str,
                'model_type': 'gradient_boost',
                'prob_over': round(float(prob_over), 1) if prob_over is not None else None,
            })

    logger.info(
        f"📈 Evaluated {players_evaluated} players, "
        f"trained {models_trained} new models, "
        f"skipped {players_skipped}, "
        f"found {len(all_candidates)} candidates meeting filters."
    )

    # 5. Rank and cap
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

    # Save to Supabase
    saved_count = db.save_daily_picks(picks, today_str)
    logger.info(f"💾 Saved {saved_count} picks to daily_picks table.")

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
