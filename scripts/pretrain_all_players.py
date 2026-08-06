#!/usr/bin/env python3
"""
Pre-train ML Models for All Active Players
==========================================
Scrapes the 2023-24, 2024-25, and current season game logs for every single
active NBA player via the BDL and nba_api endpoints. It then generates the ML
features and trains the Gradient Boost models, permanently caching them to disk
so the application has zero loading times for any user searches.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env', override=True)

from season_utils import today_et

DEFAULT_MAX_AGE_DAYS = 7


def should_skip(trained_at, max_age_days: int, force: bool,
                today: date | None = None) -> bool:
    """Return True when an existing model is fresh enough to keep.

    Args:
        trained_at: 'YYYY-MM-DD' string from the model pickle (or None).
        max_age_days: Models older than this get retrained.
        force: Retrain regardless of age.
        today: Reference date, defaults to today in ET (injectable for tests).
    """
    if force:
        return False
    if not trained_at:
        return False  # Unknown age — retrain to be safe
    try:
        trained_date = datetime.strptime(str(trained_at)[:10], '%Y-%m-%d').date()
    except ValueError:
        return False
    ref = today if today is not None else today_et()
    return (ref - trained_date).days <= max_age_days


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Pre-train models for all active players")
    parser.add_argument('--force', action='store_true',
                        help="Retrain every player even if a fresh model exists")
    parser.add_argument('--max-age-days', type=int, default=DEFAULT_MAX_AGE_DAYS,
                        help=f"Retrain models older than this many days (default {DEFAULT_MAX_AGE_DAYS})")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Heavy imports stay inside main() so tests can import should_skip/parse_args
    # without loading the ML stack.
    from nba_api.stats.static import players as nba_players
    from nba_evaluator import NBADataScraper, FeatureEngineer, MLPredictor
    from api.services.prediction_service import PredictionService

    print("Initializing mass pre-training for all active NBA players...")
    if args.force:
        print("--force: retraining every player from scratch.")
    else:
        print(f"Retraining models older than {args.max_age_days} days.")
    scraper = NBADataScraper()
    pred_svc = PredictionService()
    active_list = nba_players.get_active_players()
    total_players = len(active_list)
    print(f"Found {total_players} active players to process.")
    
    trained_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Optional team stats / injuries (to maximize feature resolution during training)
    print("Fetching league-wide team stats and injuries context...")
    team_stats = pred_svc.get_team_stats()
    injuries = pred_svc.get_injuries()
    
    for idx, p in enumerate(active_list, 1):
        player_name = p['full_name']
        print(f"\n[{idx}/{total_players}] Processing {player_name}...")
        
        # 1. Look up player info
        player_info = scraper.get_player_info(player_name)
        if not player_info:
            print(f"Could not find {player_name} in BDL. Skipping.")
            failed_count += 1
            continue
            
        # 2. Skip only when an existing model is fresh enough
        predictor = MLPredictor(model_type='gradient_boost')
        if not args.force and predictor.load(player_info['player_name']):
            if should_skip(getattr(predictor, 'trained_at', None), args.max_age_days, args.force):
                print(f"Fresh model exists for {player_name} (trained {predictor.trained_at}). Skipping.")
                skipped_count += 1
                continue
            print(f"Model for {player_name} is stale (trained {predictor.trained_at}) — retraining.")
            predictor = MLPredictor(model_type='gradient_boost')  # clean slate for retrain


        # 3. Fetch Game Log (automatically pulls 3 seasons if not in DB)
        try:
            game_log = scraper.get_player_game_log(player_info['player_id'])
            if game_log is None or game_log.empty:
                print(f"No game log found for {player_name}. Skipping.")
                failed_count += 1
                continue
                
            game_info = scraper.get_player_next_game(player_info)
            
            # 4. Feature Engineering
            df_features = FeatureEngineer.create_features(
                game_log,
                player_info=player_info,
                game_info=game_info,
                injuries=injuries,
                team_stats=team_stats
            )
            
            # 5. Train and Save
            if predictor.train(df_features):
                predictor.save(player_info['player_name'])
                print(f"Successfully trained and saved model for {player_name}.")
                trained_count += 1
            else:
                print(f"Insufficient data to train model for {player_name}.")
                failed_count += 1
                
        except Exception as e:
            print(f"Error processing {player_name}: {e}")
            failed_count += 1
            
        # Be gentle to the API 
        time.sleep(0.5)

    print("\n" + "="*50)
    print(f"PRE-TRAINING COMPLETE")
    print(f"   Trained (New): {trained_count}")
    print(f"   Skipped (Existing): {skipped_count}")
    print(f"   Failed (No Data/Errors): {failed_count}")
    print("="*50)

if __name__ == "__main__":
    main()
