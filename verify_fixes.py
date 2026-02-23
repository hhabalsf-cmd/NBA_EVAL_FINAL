#!/usr/bin/env python3
"""
Verify fixes: Re-run today's 10 picks through the updated prediction pipeline
and compare before/after. Uses saved models (no API calls).

Note: Cross-stat feature pruning and AST_TOV_RATIO stabilization only take
full effect on model retrain. The other fixes (bias correction, dampening,
sample-size discount, PRA weight, edge cap) apply at prediction time.
"""

import pickle
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from nba_evaluator import MLPredictor, FeatureEngineer

MODEL_DIR = Path(os.path.dirname(__file__)) / 'models'

# Today's picks with the ORIGINAL predictions from the database
TODAYS_PICKS = [
    {"player": "Chet Holmgren", "stat": "PTS", "line": 18.5, "direction": "OVER", "actual": 17, "won": False, "opponent": "CLE", "old_pred": 23.1},
    {"player": "Jarrett Allen", "stat": "REB", "line": 8.5, "direction": "OVER", "actual": 13, "won": True, "opponent": "OKC", "old_pred": 13.4},
    {"player": "Jamal Shead", "stat": "REB", "line": 1.5, "direction": "OVER", "actual": 6, "won": True, "opponent": "MIL", "old_pred": 3.1},
    {"player": "Nolan Traore", "stat": "REB", "line": 2.5, "direction": "UNDER", "actual": 1, "won": True, "opponent": "ATL", "old_pred": 1.0},
    {"player": "Max Christie", "stat": "PTS", "line": 16.5, "direction": "UNDER", "actual": 16, "won": True, "opponent": "IND", "old_pred": 11.9},
    {"player": "Jaylen Brown", "stat": "REB", "line": 6.5, "direction": "UNDER", "actual": 8, "won": False, "opponent": "LAL", "old_pred": 4.1},
    {"player": "Luka Dončić", "stat": "REB", "line": 7.5, "direction": "OVER", "actual": 5, "won": False, "opponent": "BOS", "old_pred": 10.1},
    {"player": "Marcus Smart", "stat": "PRA", "line": 11.5, "direction": "OVER", "actual": 5, "won": False, "opponent": "BOS", "old_pred": 17.3},
    {"player": "VJ Edgecombe", "stat": "AST", "line": 3.5, "direction": "OVER", "actual": 1, "won": False, "opponent": "MIN", "old_pred": 6.0},
    {"player": "Kelly Oubre Jr.", "stat": "REB", "line": 4.5, "direction": "OVER", "actual": 5, "won": True, "opponent": "MIN", "old_pred": 6.5},
]


def load_predictor(player_name):
    """Load a player's MLPredictor from the saved model."""
    predictor = MLPredictor(model_type='gradient_boost')
    if predictor.load(player_name):
        return predictor
    return None


def get_new_prediction(predictor, stat, player_name):
    """Get the prediction from the updated code using saved model weights.

    Since we can't re-run the full pipeline without API calls, we simulate
    the prediction by feeding the model's stored recent averages through the
    updated bias correction and dampening code.

    The raw model output is the same (model weights haven't changed), but the
    post-processing corrections are different.
    """
    if stat not in predictor.models:
        return None

    # We need to build a feature vector. Since we don't have the actual game log,
    # we'll construct approximate features from the model's stored data.
    # The raw model prediction will be the same as before.
    # What changes: bias correction weights, dampening, PRA reconciliation.

    # Build a minimal feature vector using the model's feature names
    # We'll use zeros/defaults — the raw prediction won't match exactly,
    # but the post-processing differences will show the fix impact.

    # Instead, let's directly compute what the corrections would do to the old prediction.
    return None  # We'll use an analytical approach below


def compute_fixed_prediction(old_pred, stat, recent_avg, games_trained):
    """
    Given the old prediction, apply the UPDATED corrections to see what the
    new prediction would be.

    The raw model output is the same. What changes:
    1. Bias correction weights increased
    2. Dampening increased + asymmetric (stronger when above avg)
    3. PRA reconciliation changed (85/15 vs 60/40)
    4. Sample-size penalty on confidence
    """
    # The old code did these steps on the raw model output:
    # 1. Minutes scaling (unchanged)
    # 2. Residual correction or bias correction
    # 3. Dampening
    # 4. Rolling feedback

    # We approximate: assume the old prediction was the result of old corrections
    # on some raw value. We can reverse-engineer the raw value and re-apply new corrections.

    # But actually, the simplest approach: we know the recent_avg and old_pred.
    # The corrections all pull toward recent_avg. The new corrections pull harder.
    # Let's compute the net effect of the changed correction weights.

    # Old bias correction weights
    OLD_BC = {'PTS': 0.10, 'REB': 0.10, 'AST': 0.15, 'PRA': 0.08}
    NEW_BC = {'PTS': 0.15, 'REB': 0.15, 'AST': 0.20, 'PRA': 0.12}

    OLD_DAMP = {'PTS': 0.05, 'REB': 0.06, 'AST': 0.06, 'PRA': 0.05}
    NEW_DAMP = {'PTS': 0.08, 'REB': 0.10, 'AST': 0.10, 'PRA': 0.08}

    base_stat = stat if stat != 'PRA' else 'PRA'

    old_bc = OLD_BC.get(base_stat, 0.10)
    new_bc = NEW_BC.get(base_stat, 0.15)
    old_damp = OLD_DAMP.get(base_stat, 0.05)
    new_damp = NEW_DAMP.get(base_stat, 0.08)

    # Reverse-engineer: old_pred = raw_after_residual - (raw_after_residual - recent_avg) * old_damp
    # old_pred = raw_ar * (1 - old_damp) + recent_avg * old_damp
    # raw_ar = (old_pred - recent_avg * old_damp) / (1 - old_damp)

    # And before that: raw_ar came from residual correction on raw_model:
    # raw_ar = (1 - old_bc) * raw_model + old_bc * recent_avg  (if using fallback BC)

    # So: raw_model → bias correction → dampening → old_pred
    # Let's reverse it:

    # Step 1: Reverse dampening
    # old_pred = raw_after_bc - (raw_after_bc - recent_avg) * old_damp
    # old_pred = raw_after_bc * (1 - old_damp) + recent_avg * old_damp
    raw_after_bc = (old_pred - recent_avg * old_damp) / (1 - old_damp)

    # Step 2: Reverse bias correction
    # raw_after_bc = (1 - old_bc) * raw_model + old_bc * recent_avg
    raw_model = (raw_after_bc - old_bc * recent_avg) / (1 - old_bc)

    # Now re-apply with NEW corrections:
    # Step 1: New bias correction
    new_after_bc = (1 - new_bc) * raw_model + new_bc * recent_avg

    # Step 2: New dampening (asymmetric — 1.5x stronger when above avg)
    diff = new_after_bc - recent_avg
    effective_damp = new_damp * 1.5 if diff > 0 else new_damp
    new_pred = new_after_bc - (diff * effective_damp)

    return round(new_pred, 1), round(raw_model, 1)


def main():
    print("\n" + "=" * 90)
    print("  VERIFICATION: BEFORE vs AFTER FIXES — TODAY'S 10 PICKS")
    print("=" * 90)

    print(f"\n  {'Player':<20} {'Stat':<5} {'Line':>5} {'Old':>6} {'New':>6} {'Chg':>6} {'Actual':>7} {'Old Dir':>8} {'New Dir':>8} {'Result':<6}")
    print("  " + "─" * 88)

    old_wins = 0
    new_wins = 0

    for pick in TODAYS_PICKS:
        player = pick['player']
        stat = pick['stat']
        line = pick['line']
        actual = pick['actual']
        old_pred = pick['old_pred']

        # Load model to get recent averages
        predictor = load_predictor(player)
        if predictor is None:
            print(f"  {player:<20} Model not found")
            continue

        recent_avg = float(predictor.recent_averages.get(stat, old_pred))
        games = predictor.games_trained_on

        # For PRA, compute based on component averages
        if stat == 'PRA':
            # PRA reconciliation changed from 60/40 to 85/15
            # Get component recent averages
            pts_avg = float(predictor.recent_averages.get('PTS', 0))
            reb_avg = float(predictor.recent_averages.get('REB', 0))
            ast_avg = float(predictor.recent_averages.get('AST', 0))
            component_sum = pts_avg + reb_avg + ast_avg

            # Old: PRA = 0.6 * component_sum + 0.4 * pra_model
            # New: PRA = 0.85 * component_sum + 0.15 * pra_model
            # From old: old_pred = 0.6 * comp + 0.4 * pra_model → pra_model = (old_pred - 0.6*comp) / 0.4
            # But we also need to account for bias correction changes on PRA itself...
            # Let's use the simpler approach and compute the correction effect
            new_pred, raw = compute_fixed_prediction(old_pred, stat, recent_avg, games)

            # Additional PRA reconciliation effect
            # The compute above handles bias/dampening. PRA reconciliation further
            # pulls toward component_sum.
            # Estimate: old used 60/40, new uses 85/15
            # If we assume the component-based pred is closer to component_sum * bias_corrected,
            # the shift would pull PRA prediction toward component_sum
            pra_shift = 0.25 * (component_sum - new_pred)  # 85-60=25% more weight on components
            new_pred = round(new_pred + pra_shift, 1)
        else:
            new_pred, raw = compute_fixed_prediction(old_pred, stat, recent_avg, games)

        change = round(new_pred - old_pred, 1)

        # Determine old and new directions
        old_dir = "OVER" if old_pred > line else "UNDER"
        new_dir = "OVER" if new_pred > line else "UNDER"

        # Check edge cap (55% max)
        new_edge = abs((new_pred - line) / line * 100)
        edge_note = ""
        if new_edge > 55:
            edge_note = " [FILTERED]"

        # Would the pick have won with new prediction?
        if new_dir == "OVER":
            new_would_win = actual > line
        else:
            new_would_win = actual < line

        if old_dir == "OVER":
            old_would_win = actual > line
        else:
            old_would_win = actual < line

        old_wins += 1 if old_would_win else 0
        new_wins += 1 if new_would_win and not edge_note else 0

        old_result = "WIN" if old_would_win else "LOSS"
        new_result = "WIN" if new_would_win and not edge_note else ("SKIP" if edge_note else "LOSS")

        # Sample size penalty
        penalty = ""
        if games < 100:
            pen = predictor._sample_size_penalty()
            penalty = f" [SS:{pen:.0%}]"

        print(f"  {player:<20} {stat:<5} {line:>5} {old_pred:>6.1f} {new_pred:>6.1f} {change:>+6.1f} {actual:>7} {old_dir:>8} {new_dir:>8} {old_result}→{new_result}{edge_note}{penalty}")

    print("  " + "─" * 88)
    print(f"\n  Old record: {old_wins}/{len(TODAYS_PICKS)}")

    # Count non-filtered picks for new record
    print(f"  New record: {new_wins}/{len(TODAYS_PICKS)} (skipped picks count as avoided losses)")

    print("\n  FIXES APPLIED:")
    print("  1. Bias correction weights increased (PTS: 10%→15%, REB: 10%→15%, AST: 15%→20%)")
    print("  2. Dampening increased + asymmetric (1.5x stronger when above avg)")
    print("  3. PRA reconciliation shifted to 85/15 component/model (from 60/40)")
    print("  4. Sample-size confidence penalty for <100 game models")
    print("  5. Max edge cap set to 55% (filters 60%+ bucket which hits 45.8%)")
    print("  6. Cross-stat feature pruning (takes effect on retrain)")
    print("  7. AST_TOV_RATIO stabilized with floor(TOV, 2) and cap at 6.0 (takes effect on retrain)")
    print()


if __name__ == '__main__':
    main()
