"""Reproducible public-data rebuild: prepare -> select -> evaluate.

No test rows enter candidate selection, fitting, or distribution calibration.
Run from the project root; see docs/PREDICTOR_REBUILD_PROTOCOL.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import requests

from forecasting.features import STATS, build_panel, normalize_logs
from forecasting.model import BASELINES, CANDIDATES, DEFAULT_PATH, ForecastModel, PointModel, scale

CACHE = ROOT / "cache" / "research"
REVISION = "3e809e9a04c4015de49dbdb86ac00e5a2fd2d7c9"
ALIASES = {"BRK": "BKN", "NOR": "NOP", "PHO": "PHX", "SAN": "SAS"}


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = {"repository": "https://github.com/llimllib/nba_data", "revision": REVISION, "files": []}
    files = ["data/espn/player_box.parquet"] + [f"data/gamelog_{y}.parquet" for y in range(2022, 2027)]
    for source in files:
        url = f"https://raw.githubusercontent.com/llimllib/nba_data/{REVISION}/{source}"
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        dest = CACHE / Path(source).name
        dest.write_bytes(response.content)
        manifest["files"].append({"path": source, "url": url, "bytes": len(response.content),
                                  "sha256": hashlib.sha256(response.content).hexdigest()})
    write_json(CACHE / "source_manifest.json", manifest)


def prepare():
    manifest = json.loads((CACHE / "source_manifest.json").read_text())
    for source in manifest["files"]:
        path = CACHE / Path(source["path"]).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path.name}")
    boxes = pd.read_parquet(CACHE / "player_box.parquet")
    boxes["team"] = boxes.team.replace(ALIASES)
    boxes = boxes[boxes.game_id.str.startswith("002") & boxes.season.between(2022, 2026)].copy()
    games = pd.concat([pd.read_parquet(CACHE / f"gamelog_{y}.parquet") for y in range(2022, 2027)], ignore_index=True)
    games = games[games.game_id.str.startswith("002")].copy()
    if games.duplicated(["game_id", "team_abbreviation"]).any():
        raise ValueError("Duplicate regular-season schedule identity")
    schedule = games[["game_id", "team_abbreviation", "game_date", "pts"]].rename(
        columns={"team_abbreviation": "team", "pts": "team_pts"})
    merged = boxes.merge(schedule, on=["game_id", "team"], how="left", validate="many_to_one")
    unmatched = int(merged.game_date.isna().sum())
    merged = merged.dropna(subset=["game_date"])
    totals = merged.groupby(["game_id", "team"]).agg(box_pts=("pts", "sum"), team_pts=("team_pts", "first"))
    bad = set(totals.index.get_level_values(0)[totals.box_pts != totals.team_pts])
    teams_per_game = totals.reset_index().groupby("game_id").size()
    bad.update(teams_per_game.index[teams_per_game != 2])
    merged = merged[~merged.game_id.isin(bad)]
    raw = merged.rename(columns={"minutes_played": "MIN", "rebounder": "REB", "assister": "AST"})
    logs = normalize_logs(raw[["player_id", "game_id", "game_date", "team", "home", "MIN", "pts", "REB", "AST"]])
    logs.to_parquet(CACHE / "forecast_logs.parquet", index=False)
    panel = build_panel(logs)
    panel.to_parquet(CACHE / "forecast_panel.parquet", index=False)
    report = {"revision": manifest["revision"], "unmatched_rows": unmatched,
              "excluded_incomplete_games": sorted(bad), "appearances": len(logs),
              "eligible_rows": len(panel), "players": int(logs.PLAYER_ID.nunique()),
              "first_date": str(logs.GAME_DATE.min().date()), "last_date": str(logs.GAME_DATE.max().date()),
              "seasons": {str(k): {"rows": len(v), "games": int(v.GAME_ID.nunique())}
                          for k, v in logs.groupby("SEASON_START")}}
    write_json(CACHE / "data_quality.json", report)
    print(json.dumps(report, indent=2), flush=True)


def select(panel):
    train = panel[panel.game_date < "2023-07-01"]
    validation = panel[(panel.game_date >= "2023-10-01") & (panel.game_date < "2024-07-01")]
    if train.empty or validation.empty:
        raise ValueError("Selection split missing")
    table, winners, baseline_winners = {}, {}, {}
    for stat in STATS:
        table[stat] = {}
        y = validation[f"{stat}_actual"].to_numpy()
        for kind in CANDIDATES:
            start = time.perf_counter()
            fit = PointModel.fit(train, stat, kind)
            pred = fit.predict(validation)
            table[stat][kind] = {"mae": float(np.mean(np.abs(pred - y))),
                                 "seconds": time.perf_counter() - start}
            print(stat, kind, table[stat][kind], flush=True)
        winners[stat] = min(CANDIDATES, key=lambda kind: table[stat][kind]["mae"])
        baseline_winners[stat] = min(BASELINES, key=lambda kind: table[stat][kind]["mae"])
    minutes_table = {}
    for kind in ("l5", "l10", "l20", "mean", "ewma5", "ridge", "boost"):
        pred = PointModel.fit(train, "MIN", kind).predict(validation)
        minutes_table[kind] = float(np.mean(np.abs(pred - validation.MIN_actual.to_numpy())))
    result = {"protocol": "docs/PREDICTOR_REBUILD_PROTOCOL.md", "selected": winners,
              "baseline_selected": baseline_winners, "validation": table, "minutes_mae": minutes_table,
              "training_rows": len(train), "validation_rows": len(validation),
              "train_through": str(train.game_date.max().date()),
              "validation_through": str(validation.game_date.max().date())}
    write_json(CACHE / "forecast_selection.json", result)
    print("Selected", winners, flush=True)
    return result


def metrics(y, pred, std, residuals):
    # 501 fixed empirical quantiles approximate CRPS; all samples use the same grid.
    grid = np.quantile(residuals, (np.arange(501) + 0.5) / 501, method="inverted_cdf")
    q = np.quantile(residuals, [0.1, 0.9], method="inverted_cdf")
    low = np.maximum(0, np.floor(pred + std * q[0] + 0.5))
    high = np.maximum(0, np.floor(pred + std * q[1] + 0.5))
    crps = []
    weights = 2 * np.arange(1, len(grid) + 1) - len(grid) - 1
    for offset in range(0, len(y), 256):
        sl = slice(offset, offset + 256)
        samples = np.maximum(0, np.floor(pred[sl, None] + std[sl, None] * grid + 0.5))
        crps.extend(np.mean(np.abs(samples - y[sl, None]), axis=1) - (samples * weights).sum(axis=1) / len(grid) ** 2)
    return {"n": len(y), "mae": float(np.mean(np.abs(pred - y))),
            "rmse": float(np.sqrt(np.mean((pred - y) ** 2))), "bias": float(np.mean(pred - y)),
            "coverage_80": float(np.mean((y >= low) & (y <= high))),
            "width_80": float(np.mean(high - low)), "crps_501": float(np.mean(crps))}


def clustered_difference(dates, errors, baseline_errors):
    frame = pd.DataFrame({"date": dates.to_numpy(), "delta": errors - baseline_errors})
    clusters = frame.groupby("date").delta.agg(["sum", "count"])
    rng = np.random.default_rng(240924)
    draws = rng.integers(0, len(clusters), size=(2000, len(clusters)))
    means = clusters["sum"].to_numpy()[draws].sum(axis=1) / clusters["count"].to_numpy()[draws].sum(axis=1)
    return {"difference": float(frame.delta.mean()), "ci95": np.quantile(means, [0.025, 0.975]).tolist(),
            "date_clusters": len(clusters)}


def evaluate(panel, selection):
    training = panel[panel.game_date < "2024-07-01"]
    calibration = panel[(panel.game_date >= "2024-10-01") & (panel.game_date < "2025-01-01")]
    test = panel[panel.game_date >= "2025-01-01"]
    if selection["validation_through"] >= "2024-07-01":
        raise ValueError("Selection overlaps later data")
    selection_hash = hashlib.sha256((CACHE / "forecast_selection.json").read_bytes()).hexdigest()
    provenance = {"source_manifest": json.loads((CACHE / "source_manifest.json").read_text()),
                  "selection_sha256": selection_hash,
                  "protocol_sha256": hashlib.sha256((ROOT / selection["protocol"]).read_bytes()).hexdigest()}
    start = time.perf_counter()
    model = ForecastModel.fit(training, calibration, selection["selected"], provenance)
    baseline = ForecastModel.fit(training, calibration, selection["baseline_selected"], provenance)
    digest = model.save(DEFAULT_PATH.with_name("evaluation.pkl"))
    report = {"artifact": {**model.metadata, "sha256": digest}, "selection": selection,
              "evaluation_rows": len(test), "data_quality": json.loads((CACHE / "data_quality.json").read_text()),
              "metrics": {}, "betting_profitability": "Not measured: no historical priced offers supplied."}
    scored = test[["game_date", "game_id", "player_id", "season", "MIN_l10", "season_games"]].copy()
    for stat in STATS:
        pred = model.models[stat].predict(test)
        base = baseline.models[stat].predict(test)
        actual = test[f"{stat}_actual"].to_numpy()
        std = scale(test, stat)
        masks = {"all": np.ones(len(test), dtype=bool),
                 "pregame_minutes_at_least_28": test.MIN_l10.to_numpy() >= 28,
                 "first_10_season_appearances": test.season_games.to_numpy() < 10}
        masks.update({f"season_{int(s)}": test.season.to_numpy() == s for s in sorted(test.season.unique())})
        report["metrics"][stat] = {}
        for group, mask in masks.items():
            if not mask.any():
                continue
            report["metrics"][stat][group] = {
                "selected": metrics(actual[mask], pred[mask], std[mask], model.residuals[stat]),
                "baseline": metrics(actual[mask], base[mask], std[mask], baseline.residuals[stat]),
                "paired_mae": clustered_difference(test.game_date[mask], abs(actual[mask] - pred[mask]), abs(actual[mask] - base[mask]))}
        scored[f"{stat}_actual"] = actual
        scored[f"{stat}_forecast"] = pred
        scored[f"{stat}_baseline"] = base
        print(stat, json.dumps(report["metrics"][stat]["all"]), flush=True)
    report["fit_and_evaluate_seconds"] = time.perf_counter() - start
    scored.to_parquet(CACHE / "forecast_holdout_predictions.parquet", index=False)
    write_json(ROOT / "docs" / "forecast_rebuild_results.json", report)
    print("Saved artifact and docs/forecast_rebuild_results.json", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "select", "evaluate", "fit-current"])
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--calibration-start", help="Required for fit-current; YYYY-MM-DD")
    parser.add_argument("--through", help="Exclusive data cutoff for fit-current; YYYY-MM-DD")
    args = parser.parse_args()
    if args.download:
        download()
    if args.stage == "prepare":
        prepare()
    else:
        panel = pd.read_parquet(CACHE / "forecast_panel.parquet")
        if args.stage == "select":
            select(panel)
        elif args.stage == "evaluate":
            evaluate(panel, json.loads((CACHE / "forecast_selection.json").read_text()))
        else:
            if not args.calibration_start or not args.through:
                parser.error("fit-current requires --calibration-start and --through")
            selection = json.loads((CACHE / "forecast_selection.json").read_text())
            if pd.Timestamp(args.calibration_start) <= pd.Timestamp(selection["validation_through"]):
                parser.error("Current calibration must be after model selection")
            training = panel[panel.game_date < pd.Timestamp(args.calibration_start)]
            calibration = panel[(panel.game_date >= pd.Timestamp(args.calibration_start)) &
                                (panel.game_date < pd.Timestamp(args.through))]
            provenance = {"source_manifest": json.loads((CACHE / "source_manifest.json").read_text()),
                          "selection_sha256": hashlib.sha256((CACHE / "forecast_selection.json").read_bytes()).hexdigest(),
                          "purpose": "Current research artifact; not the frozen evaluation artifact"}
            fitted = ForecastModel.fit(training, calibration, selection["selected"], provenance)
            digest = fitted.save()
            print(json.dumps({**fitted.metadata, "sha256": digest}, indent=2), flush=True)


if __name__ == "__main__":
    main()
