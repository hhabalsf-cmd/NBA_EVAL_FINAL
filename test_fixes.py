#!/usr/bin/env python3
"""
Test the updated prediction pipeline on today's 10 picks.
Runs the real pipeline (loads models, fetches game logs, builds features)
and compares new predictions to the originals stored in the DB.
"""

import sys
import os
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from nba_evaluator import MLPredictor, FeatureEngineer, NBADataScraper

TODAYS_PICKS = [
    {"player": "Chet Holmgren", "stat": "PTS", "line": 18.5, "direction": "OVER", "actual": 17, "won": False, "opponent": "CLE", "old_pred": 23.1, "old_edge": 24.9},
    {"player": "Jarrett Allen", "stat": "REB", "line": 8.5, "direction": "OVER", "actual": 13, "won": True, "opponent": "OKC", "old_pred": 13.4, "old_edge": 57.6},
    {"player": "Jamal Shead", "stat": "REB", "line": 1.5, "direction": "OVER", "actual": 6, "won": True, "opponent": "MIL", "old_pred": 3.1, "old_edge": 106.7},
    {"player": "Nolan Traore", "stat": "REB", "line": 2.5, "direction": "UNDER", "actual": 1, "won": True, "opponent": "ATL", "old_pred": 1.0, "old_edge": -60.0},
    {"player": "Max Christie", "stat": "PTS", "line": 16.5, "direction": "UNDER", "actual": 16, "won": True, "opponent": "IND", "old_pred": 11.9, "old_edge": -27.9},
    {"player": "Jaylen Brown", "stat": "REB", "line": 6.5, "direction": "UNDER", "actual": 8, "won": False, "opponent": "LAL", "old_pred": 4.1, "old_edge": -36.9},
    {"player": "Luka Dončić", "stat": "REB", "line": 7.5, "direction": "OVER", "actual": 5, "won": False, "opponent": "BOS", "old_pred": 10.1, "old_edge": 34.7},
    {"player": "Marcus Smart", "stat": "PRA", "line": 11.5, "direction": "OVER", "actual": 5, "won": False, "opponent": "BOS", "old_pred": 17.3, "old_edge": 50.4},
    {"player": "VJ Edgecombe", "stat": "AST", "line": 3.5, "direction": "OVER", "actual": 1, "won": False, "opponent": "MIN", "old_pred": 6.0, "old_edge": 71.4},
    {"player": "Kelly Oubre Jr.", "stat": "REB", "line": 4.5, "direction": "OVER", "actual": 5, "won": True, "opponent": "MIN", "old_pred": 6.5, "old_edge": 44.4},
]


def run_prediction(scraper, player_name, stat, opponent):
    """Run the full updated prediction pipeline for a single player/stat."""

    # Get player info
    info = scraper.get_player_info(player_name)
    if not info:
        return None, None, None

    player_id = info['player_id']
    team_abbrev = info.get('team_abbrev', '')

    # Get game log
    df = scraper.get_player_game_log(player_id)
    if df.empty:
        return None, None, None

    # Add features
    df = FeatureEngineer.create_features(df)

    # Get opponent context (use defaults - same as original run would have)
    vs_stats = scraper.get_vs_team_stats(player_id, opponent)

    features_df = FeatureEngineer.get_prediction_features(
        df, is_home=1, opponent=opponent,
        injuries_team=0, injuries_opp=0,
        opp_def_rating=110, opp_pace=100, opp_ast_allowed=25,
        days_rest=2, vs_stats=vs_stats
    )

    estimated_minutes = FeatureEngineer.estimate_minutes(df, is_home=1, days_rest=2)

    # Load model and predict
    predictor = MLPredictor(model_type='gradient_boost')
    if not predictor.load(player_name):
        return None, None, None

    predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)
    predictions = predictor.apply_injury_boost(predictions, 0, 0)

    pred = predictions.get(stat)
    if pred is None:
        return None, None, None

    # Get confidence
    confidence_info = predictor.get_confidence(df, stat, pred, features_df=features_df)

    return round(pred, 1), confidence_info, predictor


def main():
    scraper = NBADataScraper()

    print("\n" + "=" * 95)
    print("  TESTING UPDATED PREDICTIONS vs ORIGINALS — TODAY'S 10 PICKS")
    print("=" * 95)

    results = []

    for i, pick in enumerate(TODAYS_PICKS):
        player = pick['player']
        stat = pick['stat']
        line = pick['line']
        actual = pick['actual']
        old_pred = pick['old_pred']
        old_edge = pick['old_edge']
        won = pick['won']

        print(f"\n  [{i+1}/10] {player} {stat}...", end="", flush=True)

        new_pred, conf_info, predictor = run_prediction(scraper, player, stat, pick['opponent'])

        if new_pred is None:
            print(f" FAILED")
            results.append({**pick, 'new_pred': None, 'error': True})
            continue

        new_edge = round(((new_pred - line) / line) * 100, 1)
        new_dir = "OVER" if new_pred > line else "UNDER"
        change = round(new_pred - old_pred, 1)
        games = getattr(predictor, 'games_trained_on', '?')
        confidence = conf_info.get('confidence', '?') if conf_info else '?'

        # Would new pick win?
        if new_dir == "OVER":
            new_wins = actual > line
        else:
            new_wins = actual < line

        # Edge cap filter
        filtered = abs(new_edge) > 55

        results.append({
            **pick,
            'new_pred': new_pred,
            'new_edge': new_edge,
            'new_dir': new_dir,
            'change': change,
            'new_wins': new_wins,
            'filtered': filtered,
            'confidence': confidence,
            'games': games,
            'error': False,
        })

        status = "WIN" if new_wins and not filtered else ("SKIP" if filtered else "LOSS")
        print(f" Old: {old_pred} → New: {new_pred} ({change:+.1f}) | {status}")

        time.sleep(0.3)

    # Print summary table
    print("\n\n" + "=" * 95)
    print(f"  {'Player':<20} {'Stat':<5} {'Line':>5} {'Old':>6} {'New':>6} {'Chg':>6} {'Actual':>7} {'OldEdge':>8} {'NewEdge':>8} {'Conf':>5} {'Result'}")
    print("  " + "─" * 93)

    old_wins = 0
    new_wins_count = 0
    new_played = 0  # picks that wouldn't be filtered

    for r in results:
        if r.get('error'):
            print(f"  {r['player']:<20} ERROR")
            continue

        old_result = "WIN" if r['won'] else "LOSS"
        if r['filtered']:
            new_result = "SKIP"
        elif r['new_wins']:
            new_result = "WIN"
        else:
            new_result = "LOSS"

        old_wins += 1 if r['won'] else 0
        if not r['filtered']:
            new_played += 1
            new_wins_count += 1 if r['new_wins'] else 0

        flag = " [FILTERED]" if r['filtered'] else ""
        ss = f" [SS:{r['games']}g]" if isinstance(r['games'], int) and r['games'] < 100 else ""

        print(f"  {r['player']:<20} {r['stat']:<5} {r['line']:>5} {r['old_pred']:>6.1f} {r['new_pred']:>6.1f} {r['change']:>+6.1f} {r['actual']:>7} {r['old_edge']:>+8.1f}% {r['new_edge']:>+7.1f}% {r['confidence']:>5} {old_result}→{new_result}{flag}{ss}")

    print("  " + "─" * 93)
    print(f"\n  Old: {old_wins}/10")
    print(f"  New: {new_wins_count}/{new_played} played ({10 - new_played} filtered out)")

    # Analyze impact on losses
    old_losses = [r for r in results if not r['won'] and not r.get('error')]
    filtered_losses = [r for r in old_losses if r.get('filtered')]
    remaining_losses = [r for r in old_losses if not r.get('filtered') and not r.get('new_wins')]
    flipped_wins = [r for r in old_losses if not r.get('filtered') and r.get('new_wins')]

    print(f"\n  Impact on original 5 losses:")
    print(f"    Filtered out (avoided): {len(filtered_losses)}")
    print(f"    Flipped to wins:        {len(flipped_wins)}")
    print(f"    Still losses:           {len(remaining_losses)}")

    # Check if any old wins were broken
    old_wins_list = [r for r in results if r['won'] and not r.get('error')]
    broken_wins = [r for r in old_wins_list if not r.get('filtered') and not r.get('new_wins')]
    filtered_wins = [r for r in old_wins_list if r.get('filtered')]
    print(f"\n  Impact on original 5 wins:")
    print(f"    Still wins:             {len([r for r in old_wins_list if not r.get('filtered') and r.get('new_wins')])}")
    print(f"    Filtered out (missed):  {len(filtered_wins)}")
    print(f"    Broken (flipped loss):  {len(broken_wins)}")
    print()


if __name__ == '__main__':
    main()
