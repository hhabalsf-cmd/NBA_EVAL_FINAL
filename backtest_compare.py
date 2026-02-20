#!/usr/bin/env python3
"""
NBA Model Comparison Backtest
==============================
Side-by-side walk-forward backtest comparing:
  1. Random Forest  (MLPredictor from nba_evaluator.py)
  2. Gradient Boost (MLPredictor from nba_evaluator.py)
  3. Stacked        (EnhancedMLPredictor from enhanced_predictor.py)

Each model is evaluated on the same players, same games, same temporal split.

Usage:
    python backtest_compare.py
    python backtest_compare.py --players "Nikola Jokic,Luka Doncic" --test-games 10
"""

import sys
import os
import io
import warnings
import argparse
import numpy as np
import pandas as pd
from datetime import datetime
from contextlib import redirect_stdout

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Base predictor
from nba_evaluator import (
    NBADataScraper, FeatureEngineer, MLPredictor,
    CacheManager, TEAM_ABBREV_TO_NAME,
)

# Enhanced stacked predictor
from enhanced_predictor import EnhancedFeatureEngineer, EnhancedMLPredictor

# Shared backtest utilities
from backtest_utils import (
    DEFAULT_PLAYERS, STATS_TO_TEST, fetch_full_game_log,
    parse_minutes, build_result_row, compute_proxy_lines,
)

# ── Config ──────────────────────────────────────────────────────────────────

MODELS = ["random_forest", "gradient_boost", "stacked"]


# ── Per-game prediction helpers ───────────────────────────────────────────────

def predict_base(train_data, test_game, team_stats, model_type):
    """Run one walk-forward step using the base MLPredictor."""
    matchup = str(test_game.get("MATCHUP", ""))
    is_home = 1 if "vs." in matchup else 0
    opponent = matchup.split(" ")[-1] if matchup else ""
    minutes = parse_minutes(test_game.get("MIN", 0))

    last_train_date = pd.to_datetime(train_data["GAME_DATE"].iloc[-1])
    days_rest = min((test_game["GAME_DATE"] - last_train_date).days, 7)

    opp_def_rating = team_stats.get(opponent, {}).get("def_rating", 110) if team_stats else 110
    opp_pace = team_stats.get(opponent, {}).get("pace", 100) if team_stats else 100
    opp_ast_allowed = team_stats.get(opponent, {}).get("opp_ast", 25) if team_stats else 25

    df_features = FeatureEngineer.create_features(train_data, team_stats=team_stats)
    if len(df_features) < 20:
        return None

    features_df = FeatureEngineer.get_prediction_features(
        df_features, is_home, opponent,
        injuries_team=0, injuries_opp=0,
        opp_def_rating=opp_def_rating, opp_pace=opp_pace,
        opp_ast_allowed=opp_ast_allowed, days_rest=days_rest,
        vs_stats=None,
    )

    estimated_minutes = FeatureEngineer.estimate_minutes(
        df_features, is_home, days_rest, injuries_team=0
    )

    with redirect_stdout(io.StringIO()):
        predictor = MLPredictor(model_type=model_type)
        ok = predictor.train(df_features, stats=["PTS", "REB", "AST"])
        if not ok:
            return None
        predictions = predictor.predict(features_df, estimated_minutes=estimated_minutes)

    return predictions


def predict_stacked(train_data, test_game, team_stats):
    """Run one walk-forward step using the EnhancedMLPredictor (stacked)."""
    matchup = str(test_game.get("MATCHUP", ""))
    is_home = 1 if "vs." in matchup else 0
    opponent = matchup.split(" ")[-1] if matchup else ""

    last_train_date = pd.to_datetime(train_data["GAME_DATE"].iloc[-1])
    days_rest = min((test_game["GAME_DATE"] - last_train_date).days, 7)

    opp_def_rating = team_stats.get(opponent, {}).get("def_rating", 112) if team_stats else 112
    opp_pace = team_stats.get(opponent, {}).get("pace", 100) if team_stats else 100

    with redirect_stdout(io.StringIO()):
        df_features = EnhancedFeatureEngineer.create_advanced_features(
            train_data, team_stats=team_stats
        )
        if df_features is None or len(df_features) < 20:
            return None

        features_df = EnhancedFeatureEngineer.get_prediction_features(
            df_features, is_home, opponent,
            injuries_team=0, injuries_opp=0,
            opp_def_rating=opp_def_rating, opp_pace=opp_pace,
            days_rest=days_rest, vs_stats=None,
        )

        predictor = EnhancedMLPredictor(use_stacking=True)
        ok = predictor.train(df_features, stats=["PTS", "REB", "AST"])
        if not ok:
            return None
        predictions = predictor.predict(features_df)

    # Derive PRA
    if predictions and "PTS" in predictions and "REB" in predictions and "AST" in predictions:
        predictions["PRA"] = round(predictions["PTS"] + predictions["REB"] + predictions["AST"], 1)

    return predictions


# ── Walk-forward backtest for a single player ─────────────────────────────────

def run_backtest_player(player_name, game_log, team_stats,
                        num_test_games=15, min_train_games=25):
    """
    Walk-forward backtest for a single player.
    Returns a dict: model_type -> list of result dicts.
    """
    results = {m: [] for m in MODELS}

    current = game_log[game_log["SEASON"] == "2025-26"].copy()
    if len(current) == 0:
        return results

    # Reduce num_test_games if not enough current season data
    available = len(current) - 5
    test_n = max(1, min(num_test_games, available))

    total_before = len(game_log) - test_n
    if total_before < min_train_games:
        return results

    test_indices = list(range(len(current) - test_n, len(current)))

    for test_idx in test_indices:
        test_game = current.iloc[test_idx]
        test_date = test_game["GAME_DATE"]

        train_data = game_log[game_log["GAME_DATE"] < test_date].copy()
        if len(train_data) < min_train_games:
            continue

        minutes = parse_minutes(test_game.get("MIN", 0))
        if minutes < 10:
            continue  # DNP / garbage time

        actuals = {
            "PTS": float(test_game["PTS"]),
            "REB": float(test_game["REB"]),
            "AST": float(test_game["AST"]),
        }
        actuals["PRA"] = actuals["PTS"] + actuals["REB"] + actuals["AST"]

        # Season averages as proxy line
        proxy_lines = compute_proxy_lines(current, test_date)

        matchup = str(test_game.get("MATCHUP", ""))
        opponent = matchup.split(" ")[-1] if matchup else ""
        is_home = 1 if "vs." in matchup else 0

        # ── Base models ──────────────────────────────────────────────────────
        for model_type in ["random_forest", "gradient_boost"]:
            try:
                preds = predict_base(train_data, test_game, team_stats, model_type)
            except Exception:
                preds = None

            if not preds:
                continue

            if "PTS" in preds and "REB" in preds and "AST" in preds:
                preds["PRA"] = round(preds["PTS"] + preds["REB"] + preds["AST"], 1)

            for stat in STATS_TO_TEST:
                if stat not in preds:
                    continue
                results[model_type].append(build_result_row(
                    player_name, test_date, stat,
                    pred=preds[stat], actual=actuals[stat],
                    proxy_line=proxy_lines[stat],
                    opponent=opponent, is_home=is_home, minutes=minutes,
                ))

        # ── Stacked model ────────────────────────────────────────────────────
        try:
            preds = predict_stacked(train_data, test_game, team_stats)
        except Exception:
            preds = None

        if preds:
            for stat in STATS_TO_TEST:
                if stat not in preds:
                    continue
                results["stacked"].append(build_result_row(
                    player_name, test_date, stat,
                    pred=preds[stat], actual=actuals[stat],
                    proxy_line=proxy_lines[stat],
                    opponent=opponent, is_home=is_home, minutes=minutes,
                ))

    return results


# ── Summary printing ──────────────────────────────────────────────────────────

MODEL_LABELS = {
    "random_forest": "Random Forest",
    "gradient_boost": "Gradient Boost",
    "stacked":        "Stacked (Enhanced)",
}


def print_comparison(all_results):
    """Print side-by-side model comparison."""
    dfs = {}
    for model, rows in all_results.items():
        if rows:
            dfs[model] = pd.DataFrame(rows)

    if not dfs:
        print("\nNo results to compare.")
        return

    W = 75
    print("\n" + "=" * W)
    print("  MODEL COMPARISON — WALK-FORWARD BACKTEST")
    print("=" * W)

    # ── Overall MAE & Hit Rate ─────────────────────────────────────────────
    print("\n  OVERALL SUMMARY")
    print("-" * W)
    header = f"  {'Model':<22} {'Predictions':>12} {'MAE (all)':>10} {'Hit Rate':>10}"
    print(header)
    print(f"  {'-'*22:<22} {'-'*12:>12} {'-'*10:>10} {'-'*10:>10}")

    summary_rows = []
    for model in MODELS:
        if model not in dfs:
            print(f"  {MODEL_LABELS[model]:<22} {'N/A':>12}")
            continue
        df = dfs[model]
        total = len(df)
        mae = df["abs_error"].mean()
        hit = df["hit"].mean() * 100
        summary_rows.append((model, total, mae, hit))
        print(f"  {MODEL_LABELS[model]:<22} {total:>12,} {mae:>9.2f} {hit:>9.1f}%")

    # ── Per-stat MAE ───────────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("  MAE BY STAT")
    print("-" * W)

    stat_col_w = 6
    model_col_w = 22
    header2 = f"  {'Stat':<{stat_col_w}}"
    for model in MODELS:
        if model in dfs:
            header2 += f"  {MODEL_LABELS[model]:>{model_col_w}}"
    print(header2)

    for stat in STATS_TO_TEST:
        row = f"  {stat:<{stat_col_w}}"
        best_mae = None
        stat_maes = {}
        for model in MODELS:
            if model not in dfs:
                continue
            stat_df = dfs[model][dfs[model]["stat"] == stat]
            if len(stat_df) == 0:
                stat_maes[model] = None
            else:
                stat_maes[model] = stat_df["abs_error"].mean()
                if best_mae is None or stat_maes[model] < best_mae:
                    best_mae = stat_maes[model]

        for model in MODELS:
            if model not in dfs:
                continue
            mae = stat_maes.get(model)
            if mae is None:
                row += f"  {'N/A':>{model_col_w}}"
            else:
                marker = " ★" if abs(mae - best_mae) < 0.001 else "  "
                row += f"  {mae:>{model_col_w - 2}.2f}{marker}"
        print(row)

    # ── Per-stat Hit Rate ──────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("  HIT RATE BY STAT  (directional accuracy vs season avg proxy)")
    print("-" * W)

    header3 = f"  {'Stat':<{stat_col_w}}"
    for model in MODELS:
        if model in dfs:
            header3 += f"  {MODEL_LABELS[model]:>{model_col_w}}"
    print(header3)

    for stat in STATS_TO_TEST:
        row = f"  {stat:<{stat_col_w}}"
        best_hr = None
        stat_hrs = {}
        for model in MODELS:
            if model not in dfs:
                continue
            stat_df = dfs[model][dfs[model]["stat"] == stat]
            if len(stat_df) == 0:
                stat_hrs[model] = None
            else:
                stat_hrs[model] = stat_df["hit"].mean() * 100
                if best_hr is None or stat_hrs[model] > best_hr:
                    best_hr = stat_hrs[model]

        for model in MODELS:
            if model not in dfs:
                continue
            hr = stat_hrs.get(model)
            if hr is None:
                row += f"  {'N/A':>{model_col_w}}"
            else:
                marker = " ★" if hr is not None and abs(hr - best_hr) < 0.01 else "  "
                row += f"  {hr:>{model_col_w - 2}.1f}%{marker}"
        print(row)

    # ── 20%+ Edge picks ────────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("  HIGH-EDGE PICKS (abs_edge >= 20%)  — quality filter")
    print("-" * W)
    print(f"  {'Model':<22} {'Picks':>8} {'Hit Rate':>10} {'Avg MAE':>10}")
    print(f"  {'-'*22:<22} {'-'*8:>8} {'-'*10:>10} {'-'*10:>10}")
    for model in MODELS:
        if model not in dfs:
            continue
        df = dfs[model]
        edge_df = df[df["abs_edge"] >= 20]
        if len(edge_df) == 0:
            print(f"  {MODEL_LABELS[model]:<22} {'0':>8} {'N/A':>10} {'N/A':>10}")
        else:
            hr = edge_df["hit"].mean() * 100
            mae = edge_df["abs_error"].mean()
            print(f"  {MODEL_LABELS[model]:<22} {len(edge_df):>8,} {hr:>9.1f}% {mae:>10.2f}")

    # ── Bias ──────────────────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("  BIAS (avg signed error: positive = over-predicts)")
    print("-" * W)
    header4 = f"  {'Stat':<{stat_col_w}}"
    for model in MODELS:
        if model in dfs:
            header4 += f"  {MODEL_LABELS[model]:>{model_col_w}}"
    print(header4)
    for stat in STATS_TO_TEST:
        row = f"  {stat:<{stat_col_w}}"
        for model in MODELS:
            if model not in dfs:
                continue
            stat_df = dfs[model][dfs[model]["stat"] == stat]
            if len(stat_df) == 0:
                row += f"  {'N/A':>{model_col_w}}"
            else:
                bias = stat_df["error"].mean()
                row += f"  {bias:>{model_col_w - 0}.2f}"
        print(row)

    # ── Winner ────────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("  VERDICT")
    print("=" * W)
    if summary_rows:
        best_mae_model = min(summary_rows, key=lambda x: x[2])
        best_hit_model = max(summary_rows, key=lambda x: x[3])
        print(f"\n  Lowest MAE:   {MODEL_LABELS[best_mae_model[0]]}  ({best_mae_model[2]:.2f})")
        print(f"  Best Hit Rate: {MODEL_LABELS[best_hit_model[0]]}  ({best_hit_model[3]:.1f}%)")
        if best_mae_model[0] == best_hit_model[0]:
            print(f"\n  ★  Clear winner: {MODEL_LABELS[best_mae_model[0]]}")
        else:
            print(f"\n  MAE and Hit Rate favour different models — see per-stat table above.")
    print("\n" + "=" * W)

    # Save CSVs
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for model, df in dfs.items():
        path = os.path.join(base_dir, f"backtest_{model}.csv")
        df.to_csv(path, index=False)
    print(f"\n  Detailed CSVs saved: backtest_random_forest.csv, backtest_gradient_boost.csv, backtest_stacked.csv")
    print("=" * W + "\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NBA Model Comparison Backtest")
    parser.add_argument("--players", type=str, default=None,
                        help="Comma-separated player names (default: top 15 stars)")
    parser.add_argument("--test-games", type=int, default=15,
                        help="Test games per player (default: 15)")
    parser.add_argument("--min-train", type=int, default=25,
                        help="Minimum training games required (default: 25)")
    args = parser.parse_args()

    players = [p.strip() for p in args.players.split(",")] if args.players else DEFAULT_PLAYERS

    print("=" * 75)
    print("  NBA MODEL COMPARISON BACKTEST")
    print("  Random Forest  vs  Gradient Boost  vs  Stacked (Enhanced)")
    print("=" * 75)
    print(f"\n  Players:        {len(players)}")
    print(f"  Test games:     {args.test_games} per player")
    print(f"  Min train:      {args.min_train} games")
    print(f"  Stats:          {', '.join(STATS_TO_TEST)}")

    scraper = NBADataScraper()
    print("\n  Fetching team defensive stats...")
    team_stats = scraper.get_team_defensive_stats()

    all_results = {m: [] for m in MODELS}
    processed = 0
    skipped = 0

    for i, player_name in enumerate(players, 1):
        print(f"\n{'='*60}")
        print(f"  [{i}/{len(players)}] {player_name}")
        print("=" * 60)

        player_info = scraper.get_player_info(player_name)
        if not player_info:
            print(f"  Could not find player: {player_name}")
            skipped += 1
            continue

        print(f"  Fetching game log...")
        game_log = None
        with redirect_stdout(io.StringIO()):
            game_log = fetch_full_game_log(scraper, player_info["player_id"])

        if game_log is None or len(game_log) < args.min_train + 5:
            print(f"  Insufficient data ({len(game_log) if game_log is not None else 0} games)")
            skipped += 1
            continue

        cur = game_log[game_log["SEASON"] == "2025-26"]
        print(f"  Total games: {len(game_log)} | Current season: {len(cur)}")

        print(f"  Running walk-forward backtest ({args.test_games} test games × 3 models)...")
        player_results = run_backtest_player(
            player_name, game_log, team_stats,
            num_test_games=args.test_games,
            min_train_games=args.min_train,
        )

        for model in MODELS:
            all_results[model].extend(player_results[model])

        # Quick summary per player
        for model in MODELS:
            rows = player_results[model]
            if not rows:
                continue
            df_p = pd.DataFrame(rows)
            pts = df_p[df_p["stat"] == "PTS"]
            if len(pts):
                mae = pts["abs_error"].mean()
                hr = pts["hit"].mean() * 100
                label = MODEL_LABELS[model]
                print(f"    {label:<22}  PTS MAE={mae:.1f}  PTS Hit={hr:.0f}%")

        processed += 1

    print(f"\n  Players processed: {processed} | Skipped: {skipped}")
    print_comparison(all_results)


if __name__ == "__main__":
    main()
