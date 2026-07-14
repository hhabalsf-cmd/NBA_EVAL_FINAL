"""
Walk-forward holdout evaluation for the per-player MLPredictor.

Pulls game logs from ``nba_api`` (stats.nba.com) for a curated list of
players, trains on the first ``--train-games`` games of the requested season,
and evaluates the held-out remainder. Aggregates per-stat MAE / bias / RMSE
across players and writes a markdown report.

This is the empirical companion to the per-pickle ``training_metrics`` added
in Phase B1 — same OOF metric definitions, but measured on a *true holdout*
slice instead of a CV fold.

Usage::

    python scripts/eval_holdout.py
    python scripts/eval_holdout.py --season 2024-25 --train-games 60
    python scripts/eval_holdout.py --quick   # smaller pipeline, faster
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

warnings.filterwarnings("ignore")  # nba_api emits urllib3 warnings on macOS LibreSSL

# Allow ``python scripts/eval_holdout.py`` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub tensorflow so ``import nba_evaluator`` doesn't drag in TF — the eval only
# uses gradient_boost models, never neural, and TF init can hang on macOS LibreSSL.
sys.modules.setdefault("tensorflow", None)  # type: ignore[arg-type]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import nba_evaluator as ev  # noqa: E402


# 20 players selected for high availability across recent seasons.
# Format: (display_name, nba.com player_id).
DEFAULT_PLAYERS: tuple[tuple[str, str], ...] = (
    ("LeBron James", "2544"),
    ("Stephen Curry", "201939"),
    ("Kevin Durant", "201142"),
    ("Giannis Antetokounmpo", "203507"),
    ("Luka Doncic", "1629029"),
    ("Jayson Tatum", "1628369"),
    ("Nikola Jokic", "203999"),
    ("Joel Embiid", "203954"),
    ("Damian Lillard", "203081"),
    ("Anthony Davis", "203076"),
    ("Jimmy Butler", "202710"),
    ("Trae Young", "1629027"),
    ("Donovan Mitchell", "1628378"),
    ("Devin Booker", "1626164"),
    ("De'Aaron Fox", "1628368"),
    ("Jaylen Brown", "1627759"),
    ("Karl-Anthony Towns", "1626157"),
    ("Pascal Siakam", "1627783"),
    ("Jalen Brunson", "1628973"),
    ("Tyrese Haliburton", "1630169"),
)

EVAL_STATS: tuple[str, ...] = ("PTS", "REB", "AST")


# ── Data fetch ────────────────────────────────────────────────────────────────


def fetch_player_log(player_id: str, season: str, sleep_s: float = 0.6) -> pd.DataFrame:
    """Fetch one player's regular-season game log from stats.nba.com.

    Output is sorted ascending by GAME_DATE so rolling features at row ``i``
    summarize rows ``0..i-1`` (matching FeatureEngineer's shift(1) convention).
    """
    from nba_api.stats.endpoints import playergamelog

    df = playergamelog.PlayerGameLog(
        player_id=str(player_id), season=season
    ).get_data_frames()[0]
    time.sleep(sleep_s)  # be polite to stats.nba.com

    if df.empty:
        return df

    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], format="mixed")
    df = df.sort_values("GAME_DATE", ascending=True).reset_index(drop=True)
    df["GAME_DATE"] = df["GAME_DATE"].dt.strftime("%Y-%m-%d")
    return df


# ── Per-player evaluation ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class StatHoldoutResult:
    """Held-out metrics for a single (player, stat) pair."""

    stat: str
    n_test: int
    mae: float
    bias: float
    rmse: float
    train_mae: float | None = None
    train_bias: float | None = None
    train_coverage_80: float | None = None
    holdout_cov_raw: float | None = None       # holdout coverage from raw q10/q90
    holdout_cov_cqr: float | None = None       # holdout coverage with CQR correction applied
    cqr_correction: float | None = None        # the CQR additive expansion learned at training


@dataclass(frozen=True)
class PlayerResult:
    name: str
    player_id: str
    n_total: int
    n_train: int
    n_test: int
    stats: tuple[StatHoldoutResult, ...]
    skipped: bool = False
    reason: str | None = None


@dataclass
class AggregateMetrics:
    """Mean MAE / bias / RMSE for a stat across all evaluated players."""

    stat: str
    players: int = 0
    n_test_total: int = 0
    mae_values: list[float] = field(default_factory=list)
    bias_values: list[float] = field(default_factory=list)
    rmse_values: list[float] = field(default_factory=list)
    train_mae_values: list[float] = field(default_factory=list)
    train_bias_values: list[float] = field(default_factory=list)
    train_cov_values: list[float] = field(default_factory=list)
    cov_raw_values: list[float] = field(default_factory=list)
    cov_cqr_values: list[float] = field(default_factory=list)
    cqr_correction_values: list[float] = field(default_factory=list)


def evaluate_player(
    name: str,
    player_id: str,
    season: str,
    train_games: int,
    quick: bool,
    log_dir: Path | None = None,
) -> PlayerResult:
    """Train on first ``train_games`` games and predict the remainder."""
    try:
        log = fetch_player_log(player_id, season)
    except Exception as exc:  # network / API error
        return PlayerResult(
            name, player_id, 0, 0, 0, (), skipped=True, reason=f"fetch failed: {exc}"
        )

    if len(log) < train_games + 5:
        return PlayerResult(
            name, player_id, len(log), 0, 0, (),
            skipped=True,
            reason=f"only {len(log)} games available (need ≥ {train_games + 5})",
        )

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log.to_csv(log_dir / f"{player_id}_{season}.csv", index=False)

    # Single feature build over all games — shift(1) means row i sees rows 0..i-1
    features_df = ev.FeatureEngineer.create_features(log)
    if features_df.empty or len(features_df) < train_games + 5:
        return PlayerResult(
            name, player_id, len(log), 0, 0, (),
            skipped=True, reason="create_features yielded too few rows after DNP filter",
        )

    train_df = features_df.iloc[:train_games].copy()
    test_df = features_df.iloc[train_games:].copy()

    predictor = ev.MLPredictor(model_type="gradient_boost", use_ensemble=not quick)
    try:
        ok = predictor.train(train_df, stats=list(EVAL_STATS))
    except Exception as exc:
        return PlayerResult(
            name, player_id, len(log), train_games, len(test_df), (),
            skipped=True, reason=f"train failed: {exc}",
        )

    if not ok:
        return PlayerResult(
            name, player_id, len(log), train_games, len(test_df), (),
            skipped=True, reason="train returned False",
        )

    # Walk forward through the test set, one row at a time
    preds: dict[str, list[float]] = {s: [] for s in EVAL_STATS}
    actuals: dict[str, list[float]] = {s: [] for s in EVAL_STATS}
    q10s: dict[str, list[float]] = {s: [] for s in EVAL_STATS}
    q90s: dict[str, list[float]] = {s: [] for s in EVAL_STATS}
    cqr_corrections: dict[str, float] = {s: 0.0 for s in EVAL_STATS}
    for s in EVAL_STATS:
        cal = predictor.probability_calibrator.get(s, {}) if hasattr(predictor, 'probability_calibrator') else {}
        cqr_corrections[s] = float(cal.get('cqr_correction', 0.0))

    for i in range(len(test_df)):
        row = test_df.iloc[[i]]
        try:
            out = predictor.predict(row)
        except Exception:
            continue
        for s in EVAL_STATS:
            if s in out and s in row.columns:
                actual = row[s].values[0]
                if pd.notna(actual):
                    preds[s].append(float(out[s]))
                    actuals[s].append(float(actual))

                    # Capture raw quantile predictions for the same row so we can
                    # measure both raw and CQR-adjusted coverage on the holdout.
                    q10_key, q90_key = f"{s}_q10", f"{s}_q90"
                    qmod_lo = predictor.quantile_models.get(q10_key)
                    qmod_hi = predictor.quantile_models.get(q90_key)
                    if qmod_lo is not None and qmod_hi is not None:
                        try:
                            x_vec = np.array(
                                [
                                    row[f].values[0] if f in row.columns else 0
                                    for f in predictor.feature_names
                                ]
                            ).reshape(1, -1)
                            x_scaled = predictor.scalers["features"].transform(x_vec)
                            if predictor.selected_features and s in predictor.selected_features:
                                expected = getattr(qmod_lo, "n_features_in_", x_scaled.shape[1])
                                sel = predictor.selected_features[s]
                                if len(sel) == expected:
                                    x_scaled = x_scaled[:, sel]
                            q10s[s].append(float(qmod_lo.predict(x_scaled)[0]))
                            q90s[s].append(float(qmod_hi.predict(x_scaled)[0]))
                        except Exception:
                            q10s[s].append(np.nan)
                            q90s[s].append(np.nan)
                    else:
                        q10s[s].append(np.nan)
                        q90s[s].append(np.nan)

    stat_results: list[StatHoldoutResult] = []
    for s in EVAL_STATS:
        if not preds[s]:
            continue
        p = np.asarray(preds[s])
        a = np.asarray(actuals[s])
        diff = p - a
        train_m = predictor.training_metrics.get(s, {})

        # Holdout coverage: raw quantile band vs CQR-corrected band
        cov_raw: float | None = None
        cov_cqr: float | None = None
        q10_arr = np.asarray(q10s[s])
        q90_arr = np.asarray(q90s[s])
        valid_q = ~np.isnan(q10_arr) & ~np.isnan(q90_arr)
        if valid_q.any():
            qa = a[: len(q10_arr)][valid_q]
            ql = q10_arr[valid_q]
            qh = q90_arr[valid_q]
            cov_raw = float(np.mean((qa >= ql) & (qa <= qh)))
            cqr = cqr_corrections[s]
            cov_cqr = float(np.mean((qa >= ql - cqr) & (qa <= qh + cqr)))

        stat_results.append(
            StatHoldoutResult(
                stat=s,
                n_test=int(len(p)),
                mae=float(np.mean(np.abs(diff))),
                bias=float(np.mean(diff)),
                rmse=float(np.sqrt(np.mean(diff ** 2))),
                train_mae=train_m.get("mae"),
                train_bias=train_m.get("bias"),
                train_coverage_80=train_m.get("coverage_80"),
                holdout_cov_raw=cov_raw,
                holdout_cov_cqr=cov_cqr,
                cqr_correction=cqr_corrections[s],
            )
        )

    return PlayerResult(
        name=name,
        player_id=player_id,
        n_total=len(log),
        n_train=train_games,
        n_test=len(test_df),
        stats=tuple(stat_results),
    )


# ── Aggregation ───────────────────────────────────────────────────────────────


def aggregate(results: Sequence[PlayerResult]) -> dict[str, AggregateMetrics]:
    agg: dict[str, AggregateMetrics] = {s: AggregateMetrics(s) for s in EVAL_STATS}
    for r in results:
        if r.skipped:
            continue
        for sr in r.stats:
            bucket = agg[sr.stat]
            bucket.players += 1
            bucket.n_test_total += sr.n_test
            bucket.mae_values.append(sr.mae)
            bucket.bias_values.append(sr.bias)
            bucket.rmse_values.append(sr.rmse)
            if sr.train_mae is not None:
                bucket.train_mae_values.append(sr.train_mae)
            if sr.train_bias is not None:
                bucket.train_bias_values.append(sr.train_bias)
            if sr.train_coverage_80 is not None:
                bucket.train_cov_values.append(sr.train_coverage_80)
            if sr.holdout_cov_raw is not None:
                bucket.cov_raw_values.append(sr.holdout_cov_raw)
            if sr.holdout_cov_cqr is not None:
                bucket.cov_cqr_values.append(sr.holdout_cov_cqr)
            if sr.cqr_correction is not None:
                bucket.cqr_correction_values.append(sr.cqr_correction)
    return agg


def _mean(xs: Sequence[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


# ── Report rendering ──────────────────────────────────────────────────────────


def _fmt(value: float | None, digits: int = 2, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return (f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}")


def render_report(
    results: Sequence[PlayerResult],
    agg: dict[str, AggregateMetrics],
    season: str,
    train_games: int,
    quick: bool,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    evaluated = [r for r in results if not r.skipped]
    skipped = [r for r in results if r.skipped]

    lines: list[str] = []
    lines.append(f"# Holdout Evaluation — {today}")
    lines.append("")
    lines.append(f"- **Season:** {season}")
    lines.append(f"- **Train games:** first {train_games} per player")
    lines.append(f"- **Test games:** remainder (per-player; varies)")
    lines.append(f"- **Pipeline:** `{'quick (no ensemble)' if quick else 'full (ensemble + meta-learner)'}`")
    lines.append(f"- **Players attempted:** {len(results)}")
    lines.append(f"- **Players evaluated:** {len(evaluated)}")
    lines.append(f"- **Players skipped:** {len(skipped)}")
    lines.append("")

    # Aggregate table
    lines.append("## Aggregate (mean across evaluated players)")
    lines.append("")
    lines.append(
        "| Stat | Players | N test | Holdout MAE | Holdout Bias | Holdout RMSE | "
        "Train OOF MAE | Train OOF Bias | Train OOF 80% Cov |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for stat in EVAL_STATS:
        a = agg[stat]
        lines.append(
            f"| {stat} | {a.players} | {a.n_test_total} | "
            f"{_fmt(_mean(a.mae_values))} | "
            f"{_fmt(_mean(a.bias_values), signed=True)} | "
            f"{_fmt(_mean(a.rmse_values))} | "
            f"{_fmt(_mean(a.train_mae_values))} | "
            f"{_fmt(_mean(a.train_bias_values), signed=True)} | "
            f"{_fmt(_mean(a.train_cov_values))} |"
        )
    lines.append("")

    # Coverage table — separate to spotlight the most actionable miscalibration
    lines.append("## Quantile interval coverage (holdout test sets)")
    lines.append("")
    lines.append(
        "Target for the 80% interval (q10, q90) is 0.80; the CQR correction is "
        "tuned to push it to ~0.92 at training time."
    )
    lines.append("")
    lines.append(
        "| Stat | Mean CQR correction | Holdout Cov RAW (target 0.80) | Holdout Cov CQR (target 0.92) |"
    )
    lines.append("|---|---:|---:|---:|")
    for stat in EVAL_STATS:
        a = agg[stat]
        lines.append(
            f"| {stat} | {_fmt(_mean(a.cqr_correction_values))} | "
            f"{_fmt(_mean(a.cov_raw_values))} | "
            f"{_fmt(_mean(a.cov_cqr_values))} |"
        )
    lines.append("")

    # Per-player breakdown
    lines.append("## Per-player breakdown")
    lines.append("")
    lines.append(
        "| Player | N total | N test | Stat | Holdout MAE | Holdout Bias | Train MAE | Train Bias |"
    )
    lines.append("|---|---:|---:|---|---:|---:|---:|---:|")
    for r in evaluated:
        for sr in r.stats:
            lines.append(
                f"| {r.name} | {r.n_total} | {sr.n_test} | {sr.stat} | "
                f"{_fmt(sr.mae)} | {_fmt(sr.bias, signed=True)} | "
                f"{_fmt(sr.train_mae)} | {_fmt(sr.train_bias, signed=True)} |"
            )
    if not evaluated:
        lines.append("| _no players evaluated_ | | | | | | | |")
    lines.append("")

    # Skips
    if skipped:
        lines.append("## Skipped players")
        lines.append("")
        for r in skipped:
            lines.append(f"- **{r.name}** ({r.player_id}): {r.reason}")
        lines.append("")

    # Reading guide
    lines.append("## Reading guide")
    lines.append("")
    lines.append(
        "- **Holdout MAE vs Train OOF MAE.** Large gap ⇒ overfitting. Roughly equal ⇒ training "
        "metrics are honest."
    )
    lines.append(
        "- **Holdout bias.** Persistent positive bias = model over-predicts the stat on held-out games; "
        "negative = under-predicts. This is the *unbiased* version of the bias seen on graded picks."
    )
    lines.append(
        "- **Holdout RMSE.** Heavier penalty on large misses than MAE; comparing the two surfaces "
        "fat-tail behaviour."
    )
    lines.append(
        "- **Train OOF 80% Coverage.** Should be ~0.80 if quantile models are well-calibrated. "
        "Lower ⇒ intervals too narrow; higher ⇒ too wide."
    )
    lines.append("")

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--season",
        default="2024-25",
        help=(
            'NBA season string, e.g. "2024-25". Defaults to the last completed season '
            'because 2025-26 is in progress and most players do not yet have ≥65 games.'
        ),
    )
    parser.add_argument("--train-games", type=int, default=60)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip ensemble for faster runs (~3-5x speedup, single GBM only).",
    )
    parser.add_argument(
        "--players",
        type=int,
        default=20,
        help="Number of players from the curated list to evaluate (default 20).",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--cache-logs",
        type=Path,
        default=None,
        help="Optional directory to dump fetched game logs as CSV for debugging.",
    )
    args = parser.parse_args(argv)

    selected = DEFAULT_PLAYERS[: args.players]
    print(f"Evaluating {len(selected)} players on season={args.season}, "
          f"train={args.train_games}, quick={args.quick}")

    results: list[PlayerResult] = []
    for idx, (name, pid) in enumerate(selected, start=1):
        print(f"\n[{idx}/{len(selected)}] {name} ({pid})...")
        result = evaluate_player(
            name, pid, args.season, args.train_games, args.quick, args.cache_logs
        )
        if result.skipped:
            print(f"  SKIP — {result.reason}")
        else:
            for sr in result.stats:
                print(
                    f"  {sr.stat}: holdout MAE={sr.mae:.2f}, bias={sr.bias:+.2f} "
                    f"(train OOF MAE={_fmt(sr.train_mae)}, bias={_fmt(sr.train_bias, signed=True)})"
                )
        results.append(result)

    agg = aggregate(results)
    report = render_report(results, agg, args.season, args.train_games, args.quick)

    out_path = args.out or (
        Path(__file__).resolve().parent.parent
        / "docs"
        / f"holdout_eval_{args.season}_{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
