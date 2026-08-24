"""Dump per-row diagnostic artifacts from the unbiased walk-forward replay.

Read-only diagnostic companion to ``scripts/backtest_unbiased.py``. It reuses
that harness's serve path verbatim (same ``build_serve``, same
``serve_features``, same ``predict`` / ``get_confidence`` / ``ProbabilityCalculator``
calls, same lookahead probe) but instead of aggregating into a report it writes
one row per (player, stat, held-out game) with everything needed to answer:

* does the point model beat trivial baselines (season median / mean, L5, L10,
  last game)?
* is the served probability directionally informative at the median line?
* do the low-decile median-line failures concentrate where recent form has
  diverged from the season median?
* how much of the served 81-feature vector actually carries importance?

Artifacts (all under ``cache/diagnostics/``, which is gitignored):

* ``rows.parquet``   -- one row per (player, stat, held-out game)
* ``served.parquet`` -- the exact served feature vector for each held-out game
* ``train/{player_id}.parquet`` -- the training feature frame for that player
* ``importance.json`` -- per (player, stat) feature importances

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/diagnose_dump.py --workers 5
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import warnings

warnings.filterwarnings("ignore")
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
os.environ.setdefault("NBA_EVAL_DISABLE_TF", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("tensorflow", None)  # type: ignore[arg-type]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import nba_evaluator as ev  # noqa: E402
import backtest_unbiased as bt  # noqa: E402
from season_utils import get_current_season  # noqa: E402
from team_stats_asof import TeamStatsProvider  # noqa: E402

OUT_ROOT = Path(__file__).resolve().parent.parent / "cache" / "diagnostics"


def _baselines(series: pd.Series) -> Dict[str, float]:
    """Trivial forecasts computable from the pre-game history alone."""
    vals = series.astype(float).values
    n = len(vals)
    out = {
        "hist_n": float(n),
        "b_median": float(np.median(vals)),
        "b_mean": float(np.mean(vals)),
        "b_l3": float(np.mean(vals[-3:])),
        "b_l5": float(np.mean(vals[-5:])),
        "b_l10": float(np.mean(vals[-10:])),
        "b_l20": float(np.mean(vals[-20:])),
        "b_last": float(vals[-1]),
        "hist_std": float(np.std(vals, ddof=1)) if n > 1 else float("nan"),
        "hist_std_l20": float(np.std(vals[-20:], ddof=1)) if n > 1 else float("nan"),
    }
    # Exponentially-weighted mean, half-life 5 games.
    w = 0.5 ** (np.arange(n - 1, -1, -1) / 5.0)
    out["b_ewma5"] = float(np.sum(w * vals) / np.sum(w))
    return out


def dump_player(
    name: str,
    player_id: str,
    log: pd.DataFrame,
    train_games: int,
    quick: bool,
    season: str,
    assert_no_lookahead: bool,
    prior_log: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Replay one player, returning per-row records + artifacts.

    ``prior_log`` prepends an earlier season, reproducing production's pooled
    ``get_game_logs_multi_season`` training volume while keeping the held-out
    games bit-identical to the single-season run: the split boundary is pinned
    to the date of the ``train_games``-th played game of ``season``, computed
    from the current-season log alone.
    """
    started = time.time()
    if log is None or len(log) < train_games + 5:
        return {"name": name, "skipped": "too few games"}
    log = log.reset_index(drop=True)
    boundary_date = None
    if prior_log is not None and len(prior_log):
        try:
            cur_probe = ev.FeatureEngineer.create_features(log)
        except Exception as exc:
            return {"name": name, "skipped": "probe failed: {}".format(exc)}
        if len(cur_probe) < train_games + 5:
            return {"name": name, "skipped": "only {} current-season rows".format(
                len(cur_probe))}
        boundary_date = pd.to_datetime(cur_probe["GAME_DATE"].iloc[train_games])
        log = pd.concat([prior_log, log], ignore_index=True)
        log["GAME_DATE"] = pd.to_datetime(log["GAME_DATE"], format="mixed")
        log = log.sort_values("GAME_DATE").reset_index(drop=True)
        log["GAME_DATE"] = log["GAME_DATE"].dt.strftime("%Y-%m-%d")

    try:
        team_provider = TeamStatsProvider(season, allow_fetch=False)
    except Exception as exc:
        return {"name": name, "skipped": "team context: {}".format(exc)}

    def build(as_of):
        return ev.FeatureEngineer.create_features(
            log, team_stats=team_provider.as_of(as_of)
        )

    def build_serve(history_log, target_row, as_of):
        team = str(target_row["MATCHUP"]).split(" ")[0]
        stats = team_provider.as_of(as_of)
        frame = ev.FeatureEngineer.create_features(
            history_log,
            game_info=bt.schedule_game_info(target_row, team),
            team_stats=stats,
        )
        return frame, stats

    try:
        probe = build(log["GAME_DATE"].iloc[-1])
    except Exception as exc:
        return {"name": name, "skipped": "create_features: {}".format(exc)}
    if probe.empty or len(probe) < train_games + 5:
        return {"name": name, "skipped": "only {} feature rows".format(len(probe))}

    row_dates = list(probe["GAME_DATE"])
    played = list(probe.index)
    if boundary_date is not None:
        n_before = int((pd.to_datetime(pd.Series(row_dates)) < boundary_date).sum())
        if n_before < 30 or len(probe) - n_before < 5:
            return {"name": name, "skipped": "bad split ({} train rows)".format(n_before)}
        train_games = n_before

    features_df = build(row_dates[train_games])
    if len(features_df) != len(probe):
        return {"name": name, "skipped": "frame length changed"}

    train_df = features_df.iloc[:train_games].copy()
    test_df = features_df.iloc[train_games:]

    predictor = ev.MLPredictor(model_type="gradient_boost", use_ensemble=not quick)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ok = predictor.train(train_df, stats=list(bt.COMPONENTS))
    except Exception as exc:
        return {"name": name, "skipped": "train failed: {}".format(exc)}
    if not ok:
        return {"name": name, "skipped": "train returned False"}

    cqr = {
        s: float(predictor.probability_calibrator.get(s, {}).get("cqr_correction", 0.0))
        for s in bt.EVAL_STATS
    }
    train_metrics = predictor.training_metrics

    records: List[Dict[str, object]] = []
    served_rows: List[Dict[str, object]] = []

    for i in range(len(test_df)):
        step = train_games + i
        target_label = played[step]
        target_raw = log.loc[target_label]
        history_log = log.loc[played[:step]]

        try:
            step_frame, step_team_stats = build_serve(
                history_log, target_raw, row_dates[step]
            )
        except Exception:
            continue
        if len(step_frame) != step + 1:
            continue

        history = step_frame.iloc[:-1]
        if not ev.has_upcoming_row(step_frame) or len(history) != step:
            continue

        try:
            ctx = bt.game_context(step_frame)
            pred_row = bt.serve_features(step_frame, ctx, step_team_stats, history)
        except Exception:
            continue

        if assert_no_lookahead and i == 0:
            problem = bt.lookahead_probe(
                log, played, step, row_dates[step], build_serve, pred_row,
            )
            if problem:
                return {"name": name, "skipped": "LOOKAHEAD: {}".format(problem)}

        row = probe.iloc[[step]]
        hist_ctx = history.assign(SEASON=get_current_season())

        try:
            with contextlib.redirect_stdout(io.StringIO()):
                predictor._update_recent_averages(history)
                preds = predictor.predict(pred_row)
        except Exception:
            continue

        served_rows.append(
            dict(
                player_id=player_id,
                game_date=str(row_dates[step]),
                step=step,
                **{
                    c: (float(pred_row[c].iloc[0]) if c in pred_row.columns else np.nan)
                    for c in ev.MLPredictor.FEATURE_COLS
                },
            )
        )

        for stat in bt.EVAL_STATS:
            if stat not in preds:
                continue
            actual = bt.actual_value(row, stat)
            if actual is None:
                continue
            pred = float(preds[stat])
            series = bt.history_series(history, stat)
            if series is None or len(series) == 0:
                continue
            base = _baselines(series)

            q10, q90 = bt.raw_quantiles(predictor, stat, pred_row)

            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    conf = predictor.get_confidence(hist_ctx, stat, pred, pred_row)
            except Exception:
                conf = {}
            std = conf.get("std")
            std = float(std) if std is not None and std > 0 else float("nan")

            calib = predictor.probability_calibrator.get(stat)
            median_line = base["b_median"]
            if not math.isnan(std):
                prob_median = float(
                    ev.ProbabilityCalculator.calculate(
                        pred, median_line, std, calib
                    )
                )
            else:
                prob_median = float("nan")

            tm = train_metrics.get(stat, {})
            records.append(
                dict(
                    player=name,
                    player_id=player_id,
                    game_date=str(row_dates[step]),
                    step=step,
                    stat=stat,
                    pred=pred,
                    actual=float(actual),
                    std=std,
                    q10=q10,
                    q90=q90,
                    cqr=cqr[stat],
                    median_line=median_line,
                    prob_median=prob_median,
                    outcome_median=(
                        np.nan if actual == median_line else int(actual > median_line)
                    ),
                    minutes=float(row["MIN"].values[0]) if "MIN" in row.columns else np.nan,
                    is_home=int(ctx["is_home"]),
                    days_rest=float(ctx["days_rest"]),
                    opponent=str(ctx["opponent"]),
                    train_mae=tm.get("mae"),
                    train_bias=tm.get("bias"),
                    **base,
                )
            )

    importance = {
        stat: {k: float(v) for k, v in d.items()}
        for stat, d in getattr(predictor, "feature_importance", {}).items()
    }

    return {
        "name": name,
        "player_id": player_id,
        "records": records,
        "served": served_rows,
        "train_df": train_df,
        "importance": importance,
        "seconds": time.time() - started,
    }


def _worker(payload):
    name, pid, log, train_games, quick, season, check, prior = payload
    try:
        return dump_player(name, pid, log, train_games, quick, season, check, prior)
    except Exception as exc:  # noqa: BLE001 - a crashed player must not kill the run
        return {"name": name, "skipped": "worker error: {!r}".format(exc)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--season", default="2024-25")
    p.add_argument("--train-games", type=int, default=60)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--players", default=None)
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--skip-lookahead-check", action="store_true")
    p.add_argument("--prior-season", default=None,
                   help="prepend this season's cached log to the training data "
                        "(e.g. 2023-24), reproducing production's pooled "
                        "multi-season training volume. Held-out games are "
                        "unchanged.")
    p.add_argument("--out", type=Path, default=OUT_ROOT)
    args = p.parse_args(argv)

    selected = bt.select_players(args.players, args.limit)
    if not selected:
        print("No players selected.")
        return 1

    out = args.out
    (out / "train").mkdir(parents=True, exist_ok=True)

    started = time.time()
    provider = TeamStatsProvider(args.season)
    print("team context: {} team-games".format(provider.n_team_games))

    payloads = []
    for name, pid in selected:
        try:
            log = bt.fetch_player_log(pid, args.season, refresh_cache=False)
        except Exception as exc:
            print("  {}: FETCH FAILED — {}".format(name, exc))
            continue
        prior = None
        if args.prior_season:
            ppath = bt.log_cache_path(pid, args.prior_season)
            if ppath.exists():
                prior = pd.read_parquet(ppath)
            else:
                print("  {}: no {} log cached — single-season training".format(
                    name, args.prior_season))
        payloads.append(
            (name, pid, log, args.train_games, args.quick, args.season,
             not args.skip_lookahead_check, prior)
        )

    print("replaying {} players...".format(len(payloads)))
    results = []
    workers = max(1, min(args.workers, len(payloads)))
    if workers == 1:
        for pl in payloads:
            results.append(_worker(pl))
            print("  {}".format(results[-1].get("name")))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_worker, pl): pl[0] for pl in payloads}
            for k, fut in enumerate(as_completed(futs), start=1):
                res = fut.result()
                results.append(res)
                if res.get("skipped"):
                    print("  [{}/{}] {}: SKIP — {}".format(
                        k, len(payloads), res["name"], res["skipped"]))
                else:
                    print("  [{}/{}] {}: {} rows [{:.0f}s]".format(
                        k, len(payloads), res["name"], len(res["records"]),
                        res.get("seconds", 0)))

    rows, served, importance = [], [], {}
    for res in results:
        if res.get("skipped"):
            continue
        rows.extend(res["records"])
        served.extend(res["served"])
        importance[res["name"]] = res["importance"]
        res["train_df"].to_parquet(out / "train" / "{}.parquet".format(res["player_id"]))

    pd.DataFrame(rows).to_parquet(out / "rows.parquet")
    pd.DataFrame(served).to_parquet(out / "served.parquet")
    (out / "importance.json").write_text(json.dumps(importance), encoding="utf-8")
    print("\n{} rows / {} served vectors / {} players -> {} ({:.1f} min)".format(
        len(rows), len(served), len(importance), out, (time.time() - started) / 60))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
