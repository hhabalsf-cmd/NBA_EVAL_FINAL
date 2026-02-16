#!/usr/bin/env python3
"""
NBA Evaluator Backtesting Script
=================================
Tests model accuracy on historical games using only pre-game data.

For each test game:
1. Takes only game log data from BEFORE the test date
2. Trains model on that data
3. Predicts PTS, REB, AST, PRA
4. Compares prediction to actual result
5. Simulates edge-based filtering using season avg as proxy line

Usage:
    python backtest.py
    python backtest.py --players "LeBron James,Nikola Jokic" --test-games 10
"""

import sys
import os
import time
import warnings
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nba_evaluator import (
    NBADataScraper, FeatureEngineer, MLPredictor,
    CacheManager, TEAM_ABBREV_TO_NAME, TEAM_NAME_TO_ABBREV
)


# High-volume players for backtesting
DEFAULT_PLAYERS = [
    "Nikola Jokic",
    "Luka Doncic",
    "Jayson Tatum",
    "Anthony Edwards",
    "Shai Gilgeous-Alexander",
    "LeBron James",
    "Giannis Antetokounmpo",
    "Kevin Durant",
    "Tyrese Haliburton",
    "De'Aaron Fox",
    "Donovan Mitchell",
    "Trae Young",
    "Karl-Anthony Towns",
    "Paolo Banchero",
    "Devin Booker",
]

STATS_TO_TEST = ['PTS', 'REB', 'AST', 'PRA']


def fetch_full_game_log(scraper, player_id):
    """Fetch full game log for a player (current + last season)."""
    seasons = ['2025-26', '2024-25']
    all_games = []
    for season in seasons:
        try:
            from nba_api.stats.endpoints import playergamelog
            log = playergamelog.PlayerGameLog(player_id=player_id, season=season)
            time.sleep(0.7)
            df = log.get_data_frames()[0]
            df['SEASON'] = season
            all_games.append(df)
        except Exception as e:
            print(f"    Warning: Could not fetch {season}: {e}")

    if all_games:
        combined = pd.concat(all_games, ignore_index=True)
        combined['GAME_DATE'] = pd.to_datetime(combined['GAME_DATE'])
        combined = combined.sort_values('GAME_DATE').reset_index(drop=True)
        return combined
    return pd.DataFrame()


def run_backtest_for_player(player_name, game_log, team_stats, num_test_games=15,
                            min_train_games=25, model_type='gradient_boost'):
    """
    Run walk-forward backtest for a single player.

    Uses the last `num_test_games` games in the current season as the test set.
    For each test game, trains on all games BEFORE it.
    """
    results = []

    # Filter to current season games for test set
    current_season = game_log[game_log['SEASON'] == '2025-26'].copy()

    if len(current_season) == 0:
        print(f"  Skipping {player_name}: no current season games")
        return results

    if len(current_season) < min_train_games + num_test_games:
        # Not enough current season games — use what we can
        # We can still train on last season data, so just need enough current season for testing
        available_test = len(current_season) - 5  # Leave at least 5 current season games for context
        num_test_games = max(1, min(num_test_games, available_test))

    # Check total data is enough
    total_before_first_test = len(game_log) - num_test_games
    if total_before_first_test < min_train_games:
        print(f"  Skipping {player_name}: not enough pre-test data ({total_before_first_test} games)")
        return results

    # Use the last N games of the current season as test set
    test_indices = list(range(len(current_season) - num_test_games, len(current_season)))

    for test_idx in test_indices:
        test_game = current_season.iloc[test_idx]
        test_date = test_game['GAME_DATE']

        # TEMPORAL BOUNDARY: only use data from BEFORE the test game
        train_data = game_log[game_log['GAME_DATE'] < test_date].copy()

        if len(train_data) < min_train_games:
            continue

        # Extract actual results
        actuals = {
            'PTS': float(test_game['PTS']),
            'REB': float(test_game['REB']),
            'AST': float(test_game['AST']),
        }
        actuals['PRA'] = actuals['PTS'] + actuals['REB'] + actuals['AST']

        # Extract game context from the test game
        matchup = str(test_game.get('MATCHUP', ''))
        is_home = 1 if 'vs.' in matchup else 0
        opponent = matchup.split(' ')[-1] if matchup else ''

        # Minutes check — skip DNPs
        min_val = test_game.get('MIN', 0)
        try:
            if ':' in str(min_val):
                minutes = float(str(min_val).split(':')[0])
            else:
                minutes = float(min_val) if pd.notna(min_val) else 0
        except (ValueError, TypeError):
            minutes = 0

        if minutes < 10:
            continue  # Skip DNP / very limited minutes

        try:
            # Feature engineering on training data only
            df_features = FeatureEngineer.create_features(train_data, team_stats=team_stats)

            if len(df_features) < min_train_games:
                continue

            # Calculate days rest from last training game to test game
            last_train_date = pd.to_datetime(train_data['GAME_DATE'].iloc[-1])
            days_rest = (test_date - last_train_date).days
            days_rest = min(days_rest, 7)

            # Get opponent stats
            opp_def_rating = team_stats.get(opponent, {}).get('def_rating', 110) if team_stats else 110
            opp_pace = team_stats.get(opponent, {}).get('pace', 100) if team_stats else 100
            opp_ast_allowed = team_stats.get(opponent, {}).get('opp_ast', 25) if team_stats else 25

            # Generate prediction features
            features_df = FeatureEngineer.get_prediction_features(
                df_features, is_home, opponent,
                injuries_team=0, injuries_opp=0,
                opp_def_rating=opp_def_rating, opp_pace=opp_pace,
                opp_ast_allowed=opp_ast_allowed, days_rest=days_rest,
                vs_stats=None
            )

            # Estimate expected minutes for this game
            estimated_minutes = FeatureEngineer.estimate_minutes(
                df_features, is_home, days_rest, injuries_team=0
            )

            # Train model on pre-game data
            predictor = MLPredictor(model_type=model_type)
            success = predictor.train(df_features, stats=['PTS', 'REB', 'AST'])

            if not success:
                continue

            # Make predictions with minutes-based scaling
            predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)

            if not predictions:
                continue

            # Calculate season averages up to this point (proxy for prop lines)
            season_data_before = current_season[current_season['GAME_DATE'] < test_date]
            season_avgs = {}
            for stat in ['PTS', 'REB', 'AST']:
                if stat in season_data_before.columns and len(season_data_before) > 0:
                    season_avgs[stat] = float(season_data_before[stat].mean())
                else:
                    season_avgs[stat] = 0
            season_avgs['PRA'] = season_avgs['PTS'] + season_avgs['REB'] + season_avgs['AST']

            # Record results for each stat
            for stat in STATS_TO_TEST:
                if stat not in predictions:
                    continue

                pred = predictions[stat]
                actual = actuals[stat]
                proxy_line = season_avgs[stat]

                # Calculate edge (using season avg as proxy line)
                if proxy_line > 0:
                    edge_pct = ((pred - proxy_line) / proxy_line) * 100
                else:
                    edge_pct = 0

                direction = "OVER" if pred > proxy_line else "UNDER"

                # Did the "pick" hit?
                if direction == "OVER":
                    hit = actual > proxy_line
                else:
                    hit = actual < proxy_line

                results.append({
                    'player': player_name,
                    'game_date': test_date.strftime('%Y-%m-%d'),
                    'stat': stat,
                    'prediction': round(pred, 1),
                    'actual': actual,
                    'proxy_line': round(proxy_line, 1),
                    'error': round(pred - actual, 1),
                    'abs_error': round(abs(pred - actual), 1),
                    'edge_pct': round(edge_pct, 1),
                    'abs_edge': round(abs(edge_pct), 1),
                    'direction': direction,
                    'hit': hit,
                    'opponent': opponent,
                    'is_home': is_home,
                    'minutes': minutes,
                    'games_trained_on': len(train_data),
                })

        except Exception as e:
            print(f"    Error on {test_date.strftime('%Y-%m-%d')} vs {opponent}: {e}")
            continue

    return results


def print_results_summary(all_results):
    """Print comprehensive backtest results."""
    if not all_results:
        print("\nNo results to analyze.")
        return

    df = pd.DataFrame(all_results)

    print("\n" + "=" * 75)
    print("  BACKTEST RESULTS SUMMARY")
    print("=" * 75)

    # Overall accuracy metrics
    print(f"\n  Total predictions: {len(df)}")
    print(f"  Players tested: {df['player'].nunique()}")
    print(f"  Date range: {df['game_date'].min()} to {df['game_date'].max()}")

    # Per-stat accuracy
    print("\n" + "-" * 75)
    print("  PER-STAT ACCURACY (Prediction vs Actual)")
    print("-" * 75)
    print(f"  {'Stat':<6} {'MAE':>8} {'RMSE':>8} {'Avg Error':>10} {'Median AE':>10} {'Predictions':>12}")
    print(f"  {'-'*6:<6} {'-'*8:>8} {'-'*8:>8} {'-'*10:>10} {'-'*10:>10} {'-'*12:>12}")

    for stat in STATS_TO_TEST:
        stat_df = df[df['stat'] == stat]
        if len(stat_df) == 0:
            continue
        mae = stat_df['abs_error'].mean()
        rmse = np.sqrt((stat_df['error'] ** 2).mean())
        avg_err = stat_df['error'].mean()
        median_ae = stat_df['abs_error'].median()
        print(f"  {stat:<6} {mae:>8.2f} {rmse:>8.2f} {avg_err:>+10.2f} {median_ae:>10.2f} {len(stat_df):>12}")

    # Directional accuracy (using season avg as proxy line)
    print("\n" + "-" * 75)
    print("  DIRECTIONAL ACCURACY (vs Season Average as Proxy Line)")
    print("-" * 75)
    print(f"  {'Stat':<6} {'Hit Rate':>10} {'Wins':>6} {'Total':>7}")
    print(f"  {'-'*6:<6} {'-'*10:>10} {'-'*6:>6} {'-'*7:>7}")

    for stat in STATS_TO_TEST:
        stat_df = df[df['stat'] == stat]
        if len(stat_df) == 0:
            continue
        wins = stat_df['hit'].sum()
        total = len(stat_df)
        hit_rate = (wins / total) * 100
        print(f"  {stat:<6} {hit_rate:>9.1f}% {wins:>6} {total:>7}")

    # EDGE-BASED FILTERING (the key question)
    print("\n" + "-" * 75)
    print("  EDGE-BASED FILTERING (Key Question: Does higher edge = better picks?)")
    print("-" * 75)

    edge_thresholds = [0, 5, 10, 15, 20, 25, 30]
    print(f"  {'Min Edge':>10} {'Hit Rate':>10} {'Wins':>6} {'Total':>7} {'Avg AE':>8} {'Improvement':>12}")
    print(f"  {'-'*10:>10} {'-'*10:>10} {'-'*6:>6} {'-'*7:>7} {'-'*8:>8} {'-'*12:>12}")

    baseline_rate = (df['hit'].sum() / len(df)) * 100 if len(df) > 0 else 0

    for threshold in edge_thresholds:
        filtered = df[df['abs_edge'] >= threshold]
        if len(filtered) == 0:
            print(f"  {threshold:>9}% {'N/A':>10} {0:>6} {0:>7} {'N/A':>8} {'N/A':>12}")
            continue
        wins = filtered['hit'].sum()
        total = len(filtered)
        hit_rate = (wins / total) * 100
        avg_ae = filtered['abs_error'].mean()
        improvement = hit_rate - baseline_rate
        print(f"  {threshold:>9}% {hit_rate:>9.1f}% {wins:>6} {total:>7} {avg_ae:>8.2f} {improvement:>+11.1f}%")

    # Per-stat edge analysis at 20% threshold
    print("\n" + "-" * 75)
    print("  20%+ EDGE PICKS BY STAT")
    print("-" * 75)
    print(f"  {'Stat':<6} {'Hit Rate':>10} {'Wins':>6} {'Total':>7} {'Avg Edge':>10}")
    print(f"  {'-'*6:<6} {'-'*10:>10} {'-'*6:>6} {'-'*7:>7} {'-'*10:>10}")

    for stat in STATS_TO_TEST:
        filtered = df[(df['stat'] == stat) & (df['abs_edge'] >= 20)]
        if len(filtered) == 0:
            print(f"  {stat:<6} {'N/A':>10} {0:>6} {0:>7} {'N/A':>10}")
            continue
        wins = filtered['hit'].sum()
        total = len(filtered)
        hit_rate = (wins / total) * 100
        avg_edge = filtered['abs_edge'].mean()
        print(f"  {stat:<6} {hit_rate:>9.1f}% {wins:>6} {total:>7} {avg_edge:>9.1f}%")

    # Direction breakdown at 20%+ edge
    print("\n" + "-" * 75)
    print("  20%+ EDGE: OVER vs UNDER")
    print("-" * 75)
    for direction in ['OVER', 'UNDER']:
        filtered = df[(df['abs_edge'] >= 20) & (df['direction'] == direction)]
        if len(filtered) > 0:
            wins = filtered['hit'].sum()
            total = len(filtered)
            hit_rate = (wins / total) * 100
            print(f"  {direction:<8} {hit_rate:>8.1f}% ({wins}/{total})")

    # Per-player performance at 20%+ edge
    print("\n" + "-" * 75)
    print("  20%+ EDGE PICKS BY PLAYER")
    print("-" * 75)
    print(f"  {'Player':<28} {'Hit Rate':>10} {'W-L':>8} {'Avg Edge':>10} {'Avg AE':>8}")
    print(f"  {'-'*28:<28} {'-'*10:>10} {'-'*8:>8} {'-'*10:>10} {'-'*8:>8}")

    player_edge = df[df['abs_edge'] >= 20].groupby('player')
    for player, grp in sorted(player_edge, key=lambda x: -len(x[1])):
        wins = grp['hit'].sum()
        total = len(grp)
        hit_rate = (wins / total) * 100
        avg_edge = grp['abs_edge'].mean()
        avg_ae = grp['abs_error'].mean()
        print(f"  {player:<28} {hit_rate:>9.1f}% {f'{wins}-{total-wins}':>8} {avg_edge:>9.1f}% {avg_ae:>8.2f}")

    # Model bias analysis
    print("\n" + "-" * 75)
    print("  MODEL BIAS ANALYSIS")
    print("-" * 75)
    for stat in STATS_TO_TEST:
        stat_df = df[df['stat'] == stat]
        if len(stat_df) == 0:
            continue
        avg_error = stat_df['error'].mean()
        direction = "OVER-predicts" if avg_error > 0 else "UNDER-predicts"
        print(f"  {stat}: Model {direction} by {abs(avg_error):.2f} on average")

    # Save detailed results to CSV
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest_results.csv')
    df.to_csv(output_path, index=False)
    print(f"\n  Detailed results saved to: {output_path}")

    print("\n" + "=" * 75)


def main():
    parser = argparse.ArgumentParser(description='NBA Evaluator Backtesting')
    parser.add_argument('--players', type=str, default=None,
                        help='Comma-separated player names (default: top 15 stars)')
    parser.add_argument('--test-games', type=int, default=15,
                        help='Number of recent games to test per player (default: 15)')
    parser.add_argument('--model', type=str, default='gradient_boost',
                        choices=['random_forest', 'gradient_boost'],
                        help='Model type (default: gradient_boost)')
    parser.add_argument('--min-train', type=int, default=25,
                        help='Minimum training games required (default: 25)')
    args = parser.parse_args()

    players = args.players.split(',') if args.players else DEFAULT_PLAYERS
    players = [p.strip() for p in players]

    print("=" * 75)
    print("  NBA EVALUATOR BACKTEST")
    print("  Walk-Forward Testing with Temporal Boundaries")
    print("=" * 75)
    print(f"\n  Model: {args.model}")
    print(f"  Players: {len(players)}")
    print(f"  Test games per player: {args.test_games}")
    print(f"  Min training games: {args.min_train}")
    print(f"  Stats: {', '.join(STATS_TO_TEST)}")

    # Initialize scraper and fetch team stats
    scraper = NBADataScraper()
    print("\n  Fetching team defensive stats...")
    team_stats = scraper.get_team_defensive_stats()

    all_results = []
    players_processed = 0
    players_skipped = 0

    for i, player_name in enumerate(players, 1):
        print(f"\n{'='*60}")
        print(f"  [{i}/{len(players)}] {player_name}")
        print(f"{'='*60}")

        # Get player info
        player_info = scraper.get_player_info(player_name)
        if not player_info:
            print(f"  Could not find player: {player_name}")
            players_skipped += 1
            continue

        player_id = player_info['player_id']

        # Fetch full game log
        print(f"  Fetching game log for {player_name}...")
        game_log = fetch_full_game_log(scraper, player_id)

        if game_log is None or len(game_log) < args.min_train + 5:
            print(f"  Insufficient data: {len(game_log) if game_log is not None else 0} games")
            players_skipped += 1
            continue

        print(f"  Total games: {len(game_log)} | Current season: {len(game_log[game_log['SEASON'] == '2025-26'])}")

        # Suppress training output for cleaner backtest logs
        import io
        from contextlib import redirect_stdout

        # Run backtest with suppressed training output
        print(f"  Running walk-forward backtest ({args.test_games} test games)...")
        player_results = []

        # Redirect stdout to suppress per-game training noise
        with redirect_stdout(io.StringIO()):
            player_results = run_backtest_for_player(
                player_name, game_log, team_stats,
                num_test_games=args.test_games,
                min_train_games=args.min_train,
                model_type=args.model
            )

        if player_results:
            player_df = pd.DataFrame(player_results)
            pts_results = player_df[player_df['stat'] == 'PTS']
            if len(pts_results) > 0:
                mae = pts_results['abs_error'].mean()
                hit_rate = pts_results['hit'].mean() * 100
                print(f"  Results: {len(player_results)} predictions | PTS MAE: {mae:.1f} | PTS Hit Rate: {hit_rate:.0f}%")

                # Show 20%+ edge performance
                edge_picks = player_df[player_df['abs_edge'] >= 20]
                if len(edge_picks) > 0:
                    edge_hits = edge_picks['hit'].mean() * 100
                    print(f"  20%+ Edge: {len(edge_picks)} picks | Hit Rate: {edge_hits:.0f}%")

            all_results.extend(player_results)
            players_processed += 1
        else:
            print(f"  No valid predictions generated")
            players_skipped += 1

    # Print summary
    print(f"\n\n  Players processed: {players_processed} | Skipped: {players_skipped}")
    print_results_summary(all_results)


if __name__ == '__main__':
    main()
