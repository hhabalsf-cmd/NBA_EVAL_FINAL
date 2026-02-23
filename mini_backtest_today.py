#!/usr/bin/env python3
"""
Mini Backtest: Reconstruct today's 10 picks using saved model data only.
No API calls — uses stored recent_averages, feature_importance, and model internals.
"""

import pickle
import sys
import os
import numpy as np
from pathlib import Path

MODEL_DIR = Path(os.path.dirname(__file__)) / 'models'

# Today's 10 picks from the database
TODAYS_PICKS = [
    {"player": "Chet Holmgren", "stat": "PTS", "line": 18.5, "direction": "OVER", "actual": 17, "won": False, "opponent": "CLE"},
    {"player": "Jarrett Allen", "stat": "REB", "line": 8.5, "direction": "OVER", "actual": 13, "won": True, "opponent": "OKC"},
    {"player": "Jamal Shead", "stat": "REB", "line": 1.5, "direction": "OVER", "actual": 6, "won": True, "opponent": "MIL"},
    {"player": "Nolan Traore", "stat": "REB", "line": 2.5, "direction": "UNDER", "actual": 1, "won": True, "opponent": "ATL"},
    {"player": "Max Christie", "stat": "PTS", "line": 16.5, "direction": "UNDER", "actual": 16, "won": True, "opponent": "IND"},
    {"player": "Jaylen Brown", "stat": "REB", "line": 6.5, "direction": "UNDER", "actual": 8, "won": False, "opponent": "LAL"},
    {"player": "Luka Dončić", "stat": "REB", "line": 7.5, "direction": "OVER", "actual": 5, "won": False, "opponent": "BOS"},
    {"player": "Marcus Smart", "stat": "PRA", "line": 11.5, "direction": "OVER", "actual": 5, "won": False, "opponent": "BOS"},
    {"player": "VJ Edgecombe", "stat": "AST", "line": 3.5, "direction": "OVER", "actual": 1, "won": False, "opponent": "MIN"},
    {"player": "Kelly Oubre Jr.", "stat": "REB", "line": 4.5, "direction": "OVER", "actual": 5, "won": True, "opponent": "MIN"},
]


def load_model(player_name):
    """Load a player model pickle file."""
    filename = MODEL_DIR / f"{player_name.replace(' ', '_')}_model.pkl"
    if not filename.exists():
        # Try listing for special chars
        for f in MODEL_DIR.iterdir():
            if player_name.split(' ')[0] in f.name and player_name.split(' ')[-1].replace('ć', 'c') in f.name.replace('ć', 'c'):
                filename = f
                break
    if filename.exists():
        with open(filename, 'rb') as f:
            return pickle.load(f)
    return None


def analyze_pick(pick):
    """Analyze a single pick using model internals."""
    player = pick["player"]
    stat = pick["stat"]
    line = pick["line"]
    actual = pick["actual"]
    direction = pick["direction"]
    won = pick["won"]

    data = load_model(player)
    if data is None:
        return {**pick, "error": "Model not found"}

    result = {
        "player": player,
        "stat": stat,
        "line": line,
        "actual": actual,
        "direction": direction,
        "won": won,
        "opponent": pick["opponent"],
        "games_trained": data.get("games_trained_on", "?"),
        "trained_at": data.get("trained_at", "?"),
    }

    # Recent averages
    recent_avgs = data.get("recent_averages", {})
    result["recent_avg"] = round(float(recent_avgs.get(stat, 0)), 1) if stat in recent_avgs else None

    # For PRA, also get component averages
    if stat == "PRA":
        for s in ["PTS", "REB", "AST"]:
            result[f"recent_avg_{s}"] = round(float(recent_avgs.get(s, 0)), 1) if s in recent_avgs else None

    # Feature importance for this stat
    fi = data.get("feature_importance", {}).get(stat, {})
    if fi:
        top_features = sorted(fi.items(), key=lambda x: -x[1])[:7]
        result["top_features"] = [(name, round(imp * 100, 1)) for name, imp in top_features]

        # Cross-stat contamination analysis
        pts_features = [n for n, v in top_features if any(x in n for x in ['PTS', 'FG', 'TS_PCT', 'EFG', 'PTS_PER'])]
        reb_features = [n for n, v in top_features if 'REB' in n]
        ast_features = [n for n, v in top_features if any(x in n for x in ['AST', 'TOV'])]

        if stat == "PTS":
            cross_stat = [(n, v) for n, v in top_features if any(x in n for x in ['REB', 'AST']) and 'BLOWOUT' not in n]
            cross_pct = sum(v for _, v in cross_stat)
            result["cross_stat_contamination"] = round(cross_pct, 1) if cross_pct > 3 else 0
        elif stat == "REB":
            cross_stat = [(n, v) for n, v in top_features if any(x in n for x in ['PTS', 'FG', 'TS', 'EFG', 'AST', 'TOV']) and 'BLOWOUT' not in n]
            cross_pct = sum(v for _, v in cross_stat)
            result["cross_stat_contamination"] = round(cross_pct, 1) if cross_pct > 3 else 0
        elif stat == "AST":
            # AST_TOV_RATIO dominance check
            atov_imp = fi.get('AST_TOV_RATIO', 0) * 100
            result["ast_tov_dominance"] = round(atov_imp, 1)

    # Selected features count
    selected = data.get("selected_features", {})
    if selected and stat in selected:
        result["n_selected_features"] = len(selected[stat])

    # Performance history (rolling bias)
    perf_history = data.get("performance_history", [])
    stat_history = [h for h in perf_history if h.get("stat") == stat]
    if stat_history:
        recent = stat_history[-20:]
        bias = np.mean([h["predicted"] - h["actual"] for h in recent])
        mae = np.mean([abs(h["predicted"] - h["actual"]) for h in recent])
        result["rolling_bias"] = round(bias, 2)
        result["rolling_mae"] = round(mae, 2)
        result["perf_history_count"] = len(stat_history)

    # Prediction vs actual analysis
    if result.get("recent_avg") is not None:
        # The DB recorded prediction
        db_prediction = {
            "Chet Holmgren": 23.1, "Jarrett Allen": 13.4, "Jamal Shead": 3.1,
            "Nolan Traore": 1.0, "Max Christie": 11.9, "Jaylen Brown": 4.1,
            "Luka Dončić": 10.1, "Marcus Smart": 17.3, "VJ Edgecombe": 6.0,
            "Kelly Oubre Jr.": 6.5,
        }.get(player, None)

        if db_prediction is not None:
            result["db_prediction"] = db_prediction
            result["pred_vs_avg_diff"] = round(db_prediction - result["recent_avg"], 1)
            result["pred_vs_avg_pct"] = round(((db_prediction - result["recent_avg"]) / result["recent_avg"]) * 100, 1) if result["recent_avg"] != 0 else 0
            result["miss"] = round(db_prediction - actual, 1)
            result["edge_pct"] = round(((db_prediction - line) / line) * 100, 1)

    return result


def print_report(results):
    """Print formatted analysis report."""
    losses = [r for r in results if not r["won"] and "error" not in r]
    wins = [r for r in results if r["won"] and "error" not in r]

    print("\n" + "=" * 85)
    print("  MINI BACKTEST: TODAY'S 10 PICKS — MODEL INTERNALS ANALYSIS")
    print("=" * 85)

    print("\n  LOSSES (5)")
    print("  " + "─" * 80)

    for r in losses:
        print(f"\n  {r['player']} — {r['stat']} {r['direction']} {r['line']}")
        print(f"  vs {r['opponent']} | Actual: {r['actual']} | LOSS")
        print(f"  Games: {r.get('games_trained', '?')} | L10 avg: {r.get('recent_avg', '?')} | Prediction: {r.get('db_prediction', '?')}")

        if r.get('pred_vs_avg_pct') is not None:
            overshoot = "ABOVE" if r['pred_vs_avg_pct'] > 0 else "BELOW"
            print(f"  Prediction was {abs(r['pred_vs_avg_pct'])}% {overshoot} recent average (diff: {r.get('pred_vs_avg_diff', '?'):+.1f})")

        if r.get('miss') is not None:
            print(f"  Miss: {r['miss']:+.1f} | Edge: {r.get('edge_pct', '?'):+.1f}%")

        if r.get('rolling_bias') is not None:
            direction = "over-predicting" if r['rolling_bias'] > 0 else "under-predicting"
            print(f"  Rolling bias: {r['rolling_bias']:+.2f} ({direction}) | MAE: {r.get('rolling_mae', '?')} | History: {r.get('perf_history_count', '?')} games")

        if r.get('cross_stat_contamination') and r['cross_stat_contamination'] > 0:
            print(f"  ** CROSS-STAT CONTAMINATION: {r['cross_stat_contamination']}% of top feature importance from wrong stat category")

        if r.get('ast_tov_dominance') and r['ast_tov_dominance'] > 20:
            print(f"  ** AST_TOV_RATIO DOMINANCE: {r['ast_tov_dominance']}% of model importance on single noisy feature")

        if r.get('top_features'):
            feats = ', '.join(f"{n} ({v}%)" for n, v in r['top_features'][:5])
            print(f"  Top features: {feats}")

        # Classification
        games = r.get('games_trained', 0)
        recent_avg = r.get('recent_avg')
        pred = r.get('db_prediction')
        actual = r['actual']

        issues = []
        if isinstance(games, int) and games < 75:
            issues.append(f"Small sample ({games} games)")
        if r.get('cross_stat_contamination', 0) > 10:
            issues.append(f"Cross-stat features ({r['cross_stat_contamination']}%)")
        if r.get('ast_tov_dominance', 0) > 30:
            issues.append(f"AST_TOV_RATIO overfit ({r['ast_tov_dominance']}%)")
        if pred and recent_avg and abs(pred - recent_avg) / max(recent_avg, 1) > 0.15:
            issues.append(f"Prediction {abs(r.get('pred_vs_avg_pct', 0))}% from avg")
        if r.get('rolling_bias') and abs(r['rolling_bias']) > 1.0:
            issues.append(f"Systemic bias ({r['rolling_bias']:+.2f})")

        if issues:
            print(f"  ** Issues: {' | '.join(issues)}")
        print()

    print("  WINS (5)")
    print("  " + "─" * 80)

    for r in wins:
        print(f"  {r['player']} — {r['stat']} {r['direction']} {r['line']} | Actual: {r['actual']} | WIN")
        print(f"    Games: {r.get('games_trained', '?')} | L10 avg: {r.get('recent_avg', '?')} | Pred: {r.get('db_prediction', '?')} | Miss: {r.get('miss', '?'):+.1f}" if isinstance(r.get('miss'), (int, float)) else f"    {r.get('games_trained', '?')} games")

    # Summary stats
    print("\n" + "=" * 85)
    print("  SUMMARY")
    print("=" * 85)

    loss_misses = [abs(r['miss']) for r in losses if r.get('miss') is not None]
    win_misses = [abs(r['miss']) for r in wins if r.get('miss') is not None]

    if loss_misses:
        print(f"  Avg absolute miss (losses): {np.mean(loss_misses):.1f}")
    if win_misses:
        print(f"  Avg absolute miss (wins):   {np.mean(win_misses):.1f}")

    over_picks = [r for r in results if r['direction'] == 'OVER' and 'error' not in r]
    under_picks = [r for r in results if r['direction'] == 'UNDER' and 'error' not in r]
    over_wins = sum(1 for r in over_picks if r['won'])
    under_wins = sum(1 for r in under_picks if r['won'])
    print(f"  OVER picks: {over_wins}/{len(over_picks)} ({100*over_wins/max(len(over_picks),1):.0f}%)")
    print(f"  UNDER picks: {under_wins}/{len(under_picks)} ({100*under_wins/max(len(under_picks),1):.0f}%)")

    # Contamination summary
    contaminated = [r for r in losses if r.get('cross_stat_contamination', 0) > 5 or r.get('ast_tov_dominance', 0) > 30]
    if contaminated:
        print(f"  Losses with feature issues: {len(contaminated)}/5")

    small_sample = [r for r in losses if isinstance(r.get('games_trained'), int) and r['games_trained'] < 100]
    if small_sample:
        print(f"  Losses with small sample (<100 games): {len(small_sample)}/5")

    print()


if __name__ == '__main__':
    results = []
    for pick in TODAYS_PICKS:
        r = analyze_pick(pick)
        results.append(r)

    print_report(results)
