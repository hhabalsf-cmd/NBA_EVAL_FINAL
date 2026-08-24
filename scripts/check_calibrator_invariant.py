#!/usr/bin/env python3
"""Gate check: is the probability calibrator fit against what serve consumes?

The invariant, assertable from a persisted model alone:

    (training_metrics[s]['interval_width'] + 2 * cqr_correction) / divisor
    -------------------------------------------------------------------  ~= 1
                    probability_calibrator[s]['std_estimate']

The numerator is the mean CQR-corrected quantile std -- the exact quantity
``ProbabilityCalculator.calculate`` receives at serve. The denominator is the
std the Platt calibrator was fit against. A ratio away from 1.0 means the
calibrator learned a map on a different scale than it is asked to apply.

Trains ad hoc from the on-disk backtest game-log cache (no network, no
``models/`` pickles required) so the ratio can be measured before and after a
change without a fleet retrain.

Usage:
    NBA_EVAL_DISABLE_TF=1 python3 scripts/check_calibrator_invariant.py \
        --players 203999,1628983 --train-games 60 --json out.json
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import nba_evaluator as ev  # noqa: E402
import backtest_unbiased as bt  # noqa: E402
from team_stats_asof import TeamStatsProvider  # noqa: E402

STATS = ("PTS", "REB", "AST", "PRA")


def train_one(player_id: str, season: str, train_games: int, quick: bool):
    """Train a single player's MLPredictor exactly as the backtest harness does."""
    log = bt.fetch_player_log(player_id, season)
    if log is None or len(log) < train_games + 5:
        raise RuntimeError(f"{player_id}: only {0 if log is None else len(log)} games")
    log = bt.normalize_player_log(log).reset_index(drop=True)
    provider = TeamStatsProvider(season, allow_fetch=False)
    probe = ev.FeatureEngineer.create_features(
        log, team_stats=provider.as_of(log["GAME_DATE"].iloc[-1])
    )
    row_dates = list(probe["GAME_DATE"])
    features_df = ev.FeatureEngineer.create_features(
        log, team_stats=provider.as_of(row_dates[train_games])
    )
    train_df = features_df.iloc[:train_games].copy()
    predictor = ev.MLPredictor(model_type="gradient_boost", use_ensemble=not quick)
    with contextlib.redirect_stdout(io.StringIO()):
        ok = predictor.train(train_df, stats=["PTS", "REB", "AST"])
    if not ok:
        raise RuntimeError(f"{player_id}: train returned False")
    return predictor


def invariant_rows(predictor, player_id: str):
    """One row per stat with every term of the invariant spelled out."""
    rows = []
    for stat in STATS:
        calib = (getattr(predictor, "probability_calibrator", {}) or {}).get(stat)
        metrics = (getattr(predictor, "training_metrics", {}) or {}).get(stat)
        if not calib or not metrics:
            rows.append({"player": player_id, "stat": stat, "error": "no calibrator/metrics"})
            continue
        width = metrics.get("interval_width")
        cqr = float(calib.get("cqr_correction", 0.0))
        divisor = predictor._interval_divisor(stat)
        std_estimate = float(calib.get("std_estimate", float("nan")))
        served_std = None
        ratio = None
        if width is not None and std_estimate:
            served_std = (float(width) + 2 * cqr) / divisor
            ratio = served_std / std_estimate
        platt = calib.get("calibrator")
        row = {
            "player": player_id,
            "stat": stat,
            "interval_width": None if width is None else round(float(width), 4),
            "cqr_correction": round(cqr, 4),
            "divisor": round(float(divisor), 4),
            "std_estimate": round(std_estimate, 4),
            "served_std": None if served_std is None else round(served_std, 4),
            "ratio": None if ratio is None else round(ratio, 4),
            "coverage_80_raw": metrics.get("coverage_80"),
            "cqr_coverage": calib.get("cqr_coverage"),
            "cqr_coverage_insample": calib.get("cqr_coverage_insample"),
            "residual_std": calib.get("residual_std"),
            "calibrator_std_source": calib.get("calibrator_std_source"),
            "oof_mae": metrics.get("mae"),
            "n": metrics.get("n"),
            "interval_width_insample": metrics.get("interval_width_insample"),
        }
        if platt is not None and hasattr(platt, "coef_"):
            row["platt_slope"] = round(float(np.ravel(platt.coef_)[0]), 4)
            row["platt_intercept"] = round(float(np.ravel(platt.intercept_)[0]), 4)
        rows.append(row)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", default="203999,1628983,201939,1629029")
    ap.add_argument("--season", default="2024-25")
    ap.add_argument("--train-games", type=int, default=60)
    ap.add_argument("--quick", action="store_true", help="skip the ensemble (faster)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    all_rows = []
    for pid in [p.strip() for p in args.players.split(",") if p.strip()]:
        try:
            predictor = train_one(pid, args.season, args.train_games, args.quick)
        except Exception as exc:  # noqa: BLE001 - report, never abort the sweep
            print(f"{pid}: SKIPPED ({exc})")
            continue
        rows = invariant_rows(predictor, pid)
        all_rows.extend(rows)
        for r in rows:
            if "error" in r:
                print(f"  {pid} {r['stat']}: {r['error']}")
                continue
            print(
                "  {p} {s:<3} width={w} +2*cqr={c} /{d} = served_std={ss}  "
                "std_estimate={se}  RATIO={ratio}  cov80raw={cv} cqr_cov={cq}".format(
                    p=r["player"], s=r["stat"], w=r["interval_width"],
                    c=round(2 * r["cqr_correction"], 3), d=r["divisor"],
                    ss=r["served_std"], se=r["std_estimate"], ratio=r["ratio"],
                    cv=r["coverage_80_raw"], cq=r["cqr_coverage"],
                )
            )

    ok_rows = [r for r in all_rows if r.get("ratio") is not None]
    print("\n=== per-stat mean ratio (target 1.00) ===")
    for stat in STATS:
        vals = [r["ratio"] for r in ok_rows if r["stat"] == stat]
        if vals:
            print(f"  {stat:<4} n={len(vals)}  mean={np.mean(vals):.4f}  "
                  f"min={min(vals):.4f}  max={max(vals):.4f}")
    if ok_rows:
        print(f"  ALL  n={len(ok_rows)}  mean={np.mean([r['ratio'] for r in ok_rows]):.4f}")

    if args.json:
        Path(args.json).write_text(json.dumps(all_rows, indent=2, default=float))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
