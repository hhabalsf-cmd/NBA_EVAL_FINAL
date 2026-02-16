#!/usr/bin/env python3
"""
NBA Game Winner Backtesting Script V2
========================================
Tests game prediction model accuracy on historical 2025-26 season games
using only pre-game data (walk-forward methodology).

V2 improvements:
- Elo tracking updated game-by-game during backtest
- Rolling retraining every N games (includes current-season data)
- P/L analysis with Kelly criterion sizing
- ROI analysis by confidence tier

Usage:
    python backtest_games.py
    python backtest_games.py --start-date 2025-12-01 --retrain-every 50
"""

import sys
import os
import time
import warnings
import argparse
import numpy as np
import pandas as pd
from datetime import datetime

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_predictor import GamePredictor, EloTracker, TEAM_ABBREV_TO_NAME

from sklearn.base import clone as sklearn_clone
from sklearn.preprocessing import RobustScaler


MIN_GAMES_PER_TEAM = 10


def fetch_all_season_games(predictor, season='2025-26'):
    """Fetch all games for a season and pair home/away teams."""
    print(f"  Fetching {season} games...")
    games_df = predictor._get_historical_games(seasons=[season])
    if games_df.empty:
        return [], games_df

    games_df['GAME_DATE'] = pd.to_datetime(games_df['GAME_DATE'])
    games_df = games_df.sort_values('GAME_DATE')

    matchups = []
    for game_id, group in games_df.groupby('GAME_ID'):
        if len(group) != 2:
            continue

        home = group[group['MATCHUP'].str.contains('vs.')]
        away = group[group['MATCHUP'].str.contains('@')]

        if home.empty or away.empty:
            continue

        home = home.iloc[0]
        away = away.iloc[0]

        home_abbrev = home.get('TEAM_ABBREVIATION', '')
        away_abbrev = away.get('TEAM_ABBREVIATION', '')

        if not home_abbrev or not away_abbrev:
            continue

        margin = home.get('PLUS_MINUS', 0)
        if pd.isna(margin):
            margin = 0

        matchups.append({
            'game_date': home['GAME_DATE'],
            'game_id': game_id,
            'home_team': home_abbrev,
            'away_team': away_abbrev,
            'home_won': 1 if home['WL'] == 'W' else 0,
            'home_pts': home['PTS'],
            'away_pts': away['PTS'],
            'margin': margin,
        })

    matchups.sort(key=lambda x: x['game_date'])
    return matchups, games_df


def run_game_backtest(predictor, matchups, all_games_df, training_games_df,
                      start_date=None, retrain_every=50):
    """
    Walk-forward backtest with Elo tracking and rolling retraining.
    """
    results = []
    games_since_train = 0

    # Initialize Elo from training data
    print("  Computing Elo ratings from prior seasons...")
    elo_tracker = EloTracker()
    elo_tracker.initialize(list(TEAM_ABBREV_TO_NAME.keys()))
    elo_tracker.compute_from_games(training_games_df)
    print(f"  Elo initialized ({len(elo_tracker.ratings)} teams)")

    # Build initial training data with Elo
    print("  Building training features from prior seasons...")
    X_train, y_train = predictor._build_training_data(training_games_df, elo_tracker)
    if X_train.empty:
        print("  ERROR: Could not build training data from prior seasons")
        return results

    feature_names = list(X_train.columns)

    # Feature selection
    selected_idx, selected_names = predictor._select_features(X_train.values, y_train, feature_names)
    X_selected = X_train.values[:, selected_idx]

    # Scale
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X_selected)

    # Recency weights
    n_samples = len(X_train)
    recency_weights = np.exp(np.linspace(-2.0, 0, n_samples))
    recency_weights = recency_weights / recency_weights.sum() * n_samples

    # Train stacking ensemble
    print(f"  Training stacking ensemble on {len(X_train)} matchups...")
    model = predictor._fit_stacking_with_weights(X_scaled, y_train, recency_weights)

    # Train calibrator
    predictor._calibrate_probabilities(X_scaled, y_train, recency_weights)
    calibrator = predictor.calibrator

    print(f"  Model ready. Starting walk-forward backtest...")
    print()

    for i, game in enumerate(matchups):
        game_date = game['game_date']

        if start_date and game_date < pd.Timestamp(start_date):
            # Still update Elo
            elo_tracker.update(game['home_team'], game['away_team'],
                               game['home_won'] == 1, game['margin'])
            continue

        home_team = game['home_team']
        away_team = game['away_team']

        # Get pre-game data
        home_games = all_games_df[
            (all_games_df['TEAM_ABBREVIATION'] == home_team) &
            (all_games_df['GAME_DATE'] < game_date)
        ].sort_values('GAME_DATE')

        away_games = all_games_df[
            (all_games_df['TEAM_ABBREVIATION'] == away_team) &
            (all_games_df['GAME_DATE'] < game_date)
        ].sort_values('GAME_DATE')

        if len(home_games) < MIN_GAMES_PER_TEAM or len(away_games) < MIN_GAMES_PER_TEAM:
            elo_tracker.update(home_team, away_team, game['home_won'] == 1, game['margin'])
            continue

        try:
            # Build features with current Elo snapshot
            pre_game_df = all_games_df[all_games_df['GAME_DATE'] < game_date]
            features = predictor._build_historical_features(
                home_games, away_games, home_team, away_team,
                all_games_df=pre_game_df, elo_tracker=elo_tracker, game_date=game_date
            )

            # Align features
            feature_vector = [features.get(f, 0) for f in selected_names]
            X = np.array([feature_vector])
            X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)
            X_scaled_pred = scaler.transform(X)

            # Predict
            proba = model.predict_proba(X_scaled_pred)[0]
            home_win_prob = float(proba[1])
            away_win_prob = float(proba[0])

            # Apply calibration
            if calibrator is not None:
                home_win_prob = float(calibrator.predict([home_win_prob])[0])
                away_win_prob = 1.0 - home_win_prob

            predicted_winner = home_team if home_win_prob > 0.5 else away_team
            actual_winner = home_team if game['home_won'] == 1 else away_team
            confidence = max(home_win_prob, away_win_prob)
            correct = predicted_winner == actual_winner
            edge = abs(home_win_prob - 0.5) * 2

            results.append({
                'game_date': game_date.strftime('%Y-%m-%d'),
                'home_team': home_team,
                'away_team': away_team,
                'predicted_winner': predicted_winner,
                'actual_winner': actual_winner,
                'home_win_prob': round(home_win_prob * 100, 1),
                'away_win_prob': round(away_win_prob * 100, 1),
                'confidence': round(confidence * 100, 1),
                'edge': round(edge * 100, 1),
                'correct': correct,
                'home_pts': game['home_pts'],
                'away_pts': game['away_pts'],
            })

            games_since_train += 1

            # Rolling retrain
            if retrain_every and games_since_train >= retrain_every:
                print(f"  Retraining after {games_since_train} games (at {game_date.strftime('%Y-%m-%d')})...")
                current_before = all_games_df[all_games_df['GAME_DATE'] < game_date]
                combined = pd.concat([training_games_df, current_before], ignore_index=True)
                combined['GAME_DATE'] = pd.to_datetime(combined['GAME_DATE'])
                combined = combined.sort_values('GAME_DATE')

                X_retrain, y_retrain = predictor._build_training_data(combined, elo_tracker)
                if not X_retrain.empty:
                    # Re-select features
                    new_selected_idx, new_selected_names = predictor._select_features(
                        X_retrain.values, y_retrain, list(X_retrain.columns)
                    )
                    X_sel = X_retrain.values[:, new_selected_idx]

                    scaler = RobustScaler()
                    X_retrain_scaled = scaler.fit_transform(X_sel)

                    n = len(X_retrain)
                    w = np.exp(np.linspace(-2.0, 0, n))
                    w = w / w.sum() * n

                    model = predictor._fit_stacking_with_weights(X_retrain_scaled, y_retrain, w)

                    predictor._calibrate_probabilities(X_retrain_scaled, y_retrain, w)
                    calibrator = predictor.calibrator

                    selected_names = new_selected_names
                    selected_idx = new_selected_idx

                    print(f"    Retrained on {len(X_retrain)} matchups")
                games_since_train = 0

        except Exception as e:
            pass

        # Update Elo with actual result
        elo_tracker.update(home_team, away_team, game['home_won'] == 1, game['margin'])

    return results


def print_results_summary(results):
    """Print comprehensive backtest results with P/L analysis."""
    if not results:
        print("\nNo results to analyze.")
        return

    df = pd.DataFrame(results)

    print("\n" + "=" * 75)
    print("  GAME WINNER BACKTEST RESULTS (V2)")
    print("=" * 75)

    total = len(df)
    correct = df['correct'].sum()
    accuracy = (correct / total) * 100

    print(f"\n  Total games predicted: {total}")
    print(f"  Date range: {df['game_date'].min()} to {df['game_date'].max()}")
    print(f"\n  Record: {correct}W - {total - correct}L")
    print(f"  Accuracy: {accuracy:.1f}%")

    # By confidence tier
    print("\n" + "-" * 75)
    print("  ACCURACY BY CONFIDENCE TIER")
    print("-" * 75)
    print(f"  {'Confidence':>14} {'Record':>10} {'Accuracy':>10} {'Games':>7}")
    print(f"  {'-'*14:>14} {'-'*10:>10} {'-'*10:>10} {'-'*7:>7}")

    tiers = [(50, 55), (55, 60), (60, 65), (65, 70), (70, 75), (75, 100)]
    for low, high in tiers:
        tier_df = df[(df['confidence'] >= low) & (df['confidence'] < high)]
        if len(tier_df) == 0:
            continue
        tier_correct = tier_df['correct'].sum()
        tier_total = len(tier_df)
        tier_acc = (tier_correct / tier_total) * 100
        label = f"{low}-{high}%"
        record = f"{tier_correct}W-{tier_total - tier_correct}L"
        print(f"  {label:>14} {record:>10} {tier_acc:>9.1f}% {tier_total:>7}")

    # By month
    print("\n" + "-" * 75)
    print("  ACCURACY BY MONTH")
    print("-" * 75)
    df['month'] = pd.to_datetime(df['game_date']).dt.to_period('M')
    print(f"  {'Month':>10} {'Record':>10} {'Accuracy':>10} {'Games':>7}")
    print(f"  {'-'*10:>10} {'-'*10:>10} {'-'*10:>10} {'-'*7:>7}")

    for month, grp in df.groupby('month'):
        m_correct = grp['correct'].sum()
        m_total = len(grp)
        m_acc = (m_correct / m_total) * 100
        record = f"{m_correct}W-{m_total - m_correct}L"
        print(f"  {str(month):>10} {record:>10} {m_acc:>9.1f}% {m_total:>7}")

    # Home vs away predictions
    print("\n" + "-" * 75)
    print("  HOME vs AWAY PREDICTIONS")
    print("-" * 75)
    home_picks = df[df['predicted_winner'] == df['home_team']]
    away_picks = df[df['predicted_winner'] == df['away_team']]

    if len(home_picks) > 0:
        hp_correct = home_picks['correct'].sum()
        hp_total = len(home_picks)
        print(f"  Predicted HOME: {hp_correct}W-{hp_total - hp_correct}L  ({(hp_correct/hp_total)*100:.1f}%)  [{hp_total} games]")

    if len(away_picks) > 0:
        ap_correct = away_picks['correct'].sum()
        ap_total = len(away_picks)
        print(f"  Predicted AWAY: {ap_correct}W-{ap_total - ap_correct}L  ({(ap_correct/ap_total)*100:.1f}%)  [{ap_total} games]")

    # Calibration
    print("\n" + "-" * 75)
    print("  CALIBRATION (Does X% confidence hit X% of the time?)")
    print("-" * 75)
    print(f"  {'Predicted':>12} {'Actual':>10} {'Gap':>8} {'Games':>7}")
    print(f"  {'-'*12:>12} {'-'*10:>10} {'-'*8:>8} {'-'*7:>7}")

    cal_bins = [(50, 55), (55, 60), (60, 65), (65, 70), (70, 100)]
    for low, high in cal_bins:
        tier_df = df[(df['confidence'] >= low) & (df['confidence'] < high)]
        if len(tier_df) == 0:
            continue
        predicted_rate = (low + high) / 2
        actual_rate = (tier_df['correct'].sum() / len(tier_df)) * 100
        gap = actual_rate - predicted_rate
        print(f"  {predicted_rate:>11.0f}% {actual_rate:>9.1f}% {gap:>+7.1f}% {len(tier_df):>7}")

    # High confidence picks (65%+)
    high_conf = df[df['confidence'] >= 65]
    if len(high_conf) > 0:
        hc_correct = high_conf['correct'].sum()
        hc_total = len(high_conf)
        print(f"\n  HIGH CONFIDENCE (65%+): {hc_correct}W-{hc_total - hc_correct}L  ({(hc_correct/hc_total)*100:.1f}%)  [{hc_total} games]")

    # === P/L ANALYSIS ===
    print("\n" + "-" * 75)
    print("  ROI BY CONFIDENCE TIER (at -110 odds)")
    print("-" * 75)
    print(f"  {'Confidence':>14} {'ROI':>8} {'Units P/L':>10} {'Games':>7}")
    print(f"  {'-'*14:>14} {'-'*8:>8} {'-'*10:>10} {'-'*7:>7}")

    for low, high in tiers:
        tier_df = df[(df['confidence'] >= low) & (df['confidence'] < high)]
        if len(tier_df) == 0:
            continue
        wins = tier_df['correct'].sum()
        losses = len(tier_df) - wins
        profit = wins * (100 / 110) - losses * 1.0
        roi = (profit / len(tier_df)) * 100
        label = f"{low}-{high}%"
        print(f"  {label:>14} {roi:>+7.1f}% {profit:>+9.1f}u {len(tier_df):>7}")

    total_profit = df['correct'].sum() * (100 / 110) - (len(df) - df['correct'].sum()) * 1.0
    total_roi = (total_profit / len(df)) * 100
    print(f"\n  OVERALL: ROI = {total_roi:>+.1f}%  ({total_profit:>+.1f} units on {len(df)} bets)")

    # === KELLY CRITERION ANALYSIS ===
    print("\n" + "-" * 75)
    print("  KELLY CRITERION P/L (simulated $1000 bankroll)")
    print("-" * 75)

    bankroll = 1000.0
    peak = bankroll
    max_drawdown = 0
    total_wagered = 0
    bet_count = 0

    for _, row in df.iterrows():
        p = row['confidence'] / 100  # Estimated win probability
        payout = 100 / 110  # -110 odds payout ratio
        kelly = (p * (1 + payout) - 1) / payout
        kelly = max(0, min(kelly, 0.05))  # Cap at 5% of bankroll

        bet_size = bankroll * kelly
        if bet_size < 1:
            continue

        bet_count += 1
        total_wagered += bet_size

        if row['correct']:
            bankroll += bet_size * payout
        else:
            bankroll -= bet_size

        peak = max(peak, bankroll)
        drawdown = (peak - bankroll) / peak
        max_drawdown = max(max_drawdown, drawdown)

    print(f"  Starting bankroll:  $1,000.00")
    print(f"  Final bankroll:     ${bankroll:,.2f}")
    print(f"  Net profit:         ${bankroll - 1000:+,.2f}")
    print(f"  ROI:                {((bankroll - 1000) / total_wagered) * 100:+.1f}%" if total_wagered > 0 else "  ROI: N/A")
    print(f"  Max drawdown:       {max_drawdown * 100:.1f}%")
    print(f"  Bets placed:        {bet_count}/{len(df)} ({bet_count/len(df)*100:.0f}%)")

    print("\n" + "=" * 75)


def main():
    parser = argparse.ArgumentParser(description='NBA Game Winner Backtesting V2')
    parser.add_argument('--start-date', type=str, default=None,
                        help='Earliest test date (YYYY-MM-DD). Default: auto')
    parser.add_argument('--retrain-every', type=int, default=50,
                        help='Retrain model after N predictions (default: 50)')
    args = parser.parse_args()

    print("=" * 75)
    print("  NBA GAME WINNER BACKTEST V2")
    print("  Walk-Forward + Elo + Stacking + Calibration")
    print("=" * 75)

    predictor = GamePredictor()

    # Fetch 2025-26 season games
    matchups, season_df = fetch_all_season_games(predictor, '2025-26')
    if not matchups:
        print("  No 2025-26 games found!")
        return

    print(f"  Found {len(matchups)} games in 2025-26 season")
    print(f"  Date range: {matchups[0]['game_date'].strftime('%Y-%m-%d')} to {matchups[-1]['game_date'].strftime('%Y-%m-%d')}")

    # Fetch prior seasons for training
    print("\n  Fetching prior season data for training...")
    training_df = predictor._get_historical_games(seasons=['2024-25', '2023-24'])
    if training_df.empty:
        print("  ERROR: Could not fetch prior season data")
        return

    training_df['GAME_DATE'] = pd.to_datetime(training_df['GAME_DATE'])
    training_df = training_df.sort_values('GAME_DATE')
    print(f"  Training data: {len(training_df)} game entries from prior seasons")

    # Run backtest
    print(f"\n  Running walk-forward backtest...")
    print(f"  Retraining every {args.retrain_every} predictions")

    results = run_game_backtest(
        predictor, matchups, season_df, training_df,
        start_date=args.start_date,
        retrain_every=args.retrain_every,
    )

    if not results:
        print("  No predictions generated!")
        return

    # Save results
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest_game_results.csv')
    pd.DataFrame(results).to_csv(output_path, index=False)
    print(f"\n  Results saved to: {output_path}")

    # Print summary
    print_results_summary(results)


if __name__ == '__main__':
    main()
