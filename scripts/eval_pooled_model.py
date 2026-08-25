"""Score the pooled cross-player model on the investigation's own holdout.

Same 44 players / 606 held-out games / 2,424 rows the Phase-0/1/2 reports and
``docs/diagnosis_resolution_failure_2026-08-23.md`` scored, so every number
here is directly comparable to those. The holdout actuals, the season-median
pseudo-lines, the production model's predictions and the eight trivial
baselines all come from ``cache/diagnostics_t60/rows.parquet``, written by
``scripts/diagnose_dump.py`` from ``scripts/backtest_unbiased.py``'s serve path.

Lookahead control. The pooled features for each held-out game are rebuilt here
from the player's cached stats.nba.com log, taking only the ``step`` games
before it -- and then asserted equal, to the last bit, to the ``b_*`` baseline
columns the harness computed independently inside its own walk-forward. If a
single feature disagreed, or used one game too many, the assertion fails. That
is also what rules out the Phase-0 PRA trap: PRA is recomputed from PTS/REB/AST
history rather than read from any PRA column.

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/eval_pooled_model.py \
        --model models/pooled/league_model.pkl
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

os.environ.setdefault("NBA_EVAL_DISABLE_TF", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

import pooled_features as pf  # noqa: E402
from pooled_model import PooledLeagueModel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ROWS = ROOT / "cache" / "diagnostics_t60" / "rows.parquet"
LOG_CACHE = ROOT / "cache" / "backtest_logs"

#: Trivial baselines, in the order the report tables print them.
BASELINES: Tuple[str, ...] = ("b_l3", "b_l5", "b_l10", "b_l20", "b_median",
                              "b_mean", "b_last", "b_ewma5")

#: Baselines the plan's exit criterion names explicitly.
EXIT_BASELINES: Tuple[str, ...] = ("b_ewma5", "b_l10", "b_median")

#: The harness baseline each pooled feature must reproduce exactly. Covers
#: every kind the builders can emit, not only the six production ones, so the
#: nine-feature reference variant is held to the same control.
_FEATURE_TO_BASELINE = {"L3": "b_l3", "L5": "b_l5", "L10": "b_l10",
                        "L20": "b_l20", "MEDIAN": "b_median", "MEAN": "b_mean",
                        "LAST": "b_last", "EWMA5": "b_ewma5", "STD": "hist_std"}

BOOTSTRAP_DRAWS = 2000
RNG_SEED = 20260825


# ── holdout reconstruction ───────────────────────────────────────────────────


def load_holdout(rows_path: Path) -> pd.DataFrame:
    if not rows_path.exists():
        raise FileNotFoundError(
            "{} not found. Rebuild it with scripts/diagnose_dump.py.".format(rows_path))
    rows = pd.read_parquet(rows_path)
    rows["game_date"] = pd.to_datetime(rows["game_date"])
    return rows


def _player_log(player_id: str, season: str) -> pd.DataFrame:
    path = LOG_CACHE / season / "{}.parquet".format(player_id)
    if not path.exists():
        raise FileNotFoundError(
            "no cached {} log for player {} at {}".format(season, player_id, path))
    return pf.normalize_game_log(pd.read_parquet(path))


def build_holdout_features(rows: pd.DataFrame, season: str) -> pd.DataFrame:
    """Pooled features for each held-out game, from that game's history alone."""
    keys = rows[["player", "player_id", "game_date", "step"]].drop_duplicates()
    records: List[Dict[str, object]] = []
    for player_id, group in keys.groupby("player_id"):
        log = _player_log(player_id, season)
        index = {pd.Timestamp(d): i for i, d in enumerate(log["GAME_DATE"])}
        for _, key in group.iterrows():
            position = index.get(pd.Timestamp(key["game_date"]))
            if position is None:
                raise ValueError("{} has no {} game on {}".format(
                    key["player"], season, key["game_date"].date()))
            if position != int(key["step"]):
                raise ValueError(
                    "{} on {}: cached log puts the game at index {} but the "
                    "harness split at step {}".format(
                        key["player"], key["game_date"].date(), position, key["step"]))
            history = log.iloc[:position]
            record = dict(player=key["player"], player_id=player_id,
                          game_date=key["game_date"], step=position)
            record.update(pf.serve_features(history, kinds=pf.ALL_KINDS))
            for stat in pf.POOLED_STATS:
                record["{}_DISPERSION".format(stat)] = pf.dispersion(history, stat)
            records.append(record)
    return pd.DataFrame.from_records(records)


def assert_no_lookahead(rows: pd.DataFrame, features: pd.DataFrame) -> Dict[str, float]:
    """Every pooled feature must equal the harness's independently-built baseline.

    The harness computed ``b_l10`` and friends inside its own walk-forward, from
    ``step_frame.iloc[:-1]``. These features were rebuilt here from a different
    starting point. Agreement to 0.0 means both used exactly the ``step`` games
    before the target and neither reached past it.
    """
    worst: Dict[str, float] = {}
    for stat in pf.POOLED_STATS:
        actual = rows[rows["stat"] == stat][
            ["player", "game_date", "actual", "hist_std"] + list(BASELINES)]
        merged = actual.merge(features, on=["player", "game_date"], how="left",
                              validate="one_to_one")
        if merged[["{}_L10".format(stat)]].isna().any().any():
            raise AssertionError("{}: some held-out games got no features".format(stat))
        for kind, baseline in _FEATURE_TO_BASELINE.items():
            column = "{}_{}".format(stat, kind)
            gap = float(np.abs(merged[column] - merged[baseline]).max())
            worst[column] = gap
            if gap > 0.0:
                raise AssertionError(
                    "{} differs from the harness's {} by {:.6g} — the two are "
                    "not reading the same history".format(column, baseline, gap))
    return worst


# ── scoring ──────────────────────────────────────────────────────────────────


def score(rows: pd.DataFrame, features: pd.DataFrame,
          model: PooledLeagueModel) -> pd.DataFrame:
    """One row per (player, game, stat) with pooled prediction and probability."""
    feature_names = list(pf.all_feature_names(pf.ALL_KINDS))
    predictions = [model.predict(row) for row in
                   features[feature_names].to_dict(orient="records")]
    wide = features[["player", "game_date"]].copy()
    for stat in pf.POOLED_STATS:
        wide["pooled_{}".format(stat)] = [p[stat] for p in predictions]
        wide["sigma_{}".format(stat)] = [
            model.sigma(stat, d) for d in features["{}_DISPERSION".format(stat)]]

    frames = []
    for stat in pf.POOLED_STATS:
        part = rows[rows["stat"] == stat].merge(
            wide[["player", "game_date", "pooled_{}".format(stat),
                  "sigma_{}".format(stat)]],
            on=["player", "game_date"], how="left", validate="one_to_one")
        part = part.rename(columns={"pooled_{}".format(stat): "pooled",
                                    "sigma_{}".format(stat): "sigma"})
        part["pooled_prob"] = [
            model.prob_over(stat, p, line, s)
            for p, line, s in zip(part["pooled"], part["median_line"], part["sigma"])]
        frames.append(part)
    return pd.concat(frames, ignore_index=True)


def paired_bootstrap(scored: pd.DataFrame, stat: str, model_col: str,
                     baseline: str, draws: int = BOOTSTRAP_DRAWS
                     ) -> Tuple[float, float, float]:
    """mean|model| - mean|baseline| with a 95% CI, resampling PLAYERS.

    Clustered by player because the 606 games are 44 repeated measures, not 606
    independent ones — the same convention the investigation used.
    """
    part = scored[scored["stat"] == stat]
    groups = [g for _, g in part.groupby("player_id")]
    point = float((part[model_col] - part["actual"]).abs().mean()
                  - (part[baseline] - part["actual"]).abs().mean())
    rng = np.random.default_rng(RNG_SEED)
    diffs = np.empty(draws)
    n = len(groups)
    for i in range(draws):
        pick = pd.concat([groups[j] for j in rng.integers(0, n, n)])
        diffs[i] = ((pick[model_col] - pick["actual"]).abs().mean()
                    - (pick[baseline] - pick["actual"]).abs().mean())
    low, high = np.percentile(diffs, [2.5, 97.5])
    return point, float(low), float(high)


def median_line_auc(scored: pd.DataFrame, stat: str, score_col: str,
                    draws: int = 600) -> Tuple[float, float, float]:
    part = scored[(scored["stat"] == stat) & scored["outcome_median"].notna()].copy()
    y = part["outcome_median"].astype(int).to_numpy()
    s = part[score_col].to_numpy(dtype=float)
    point = float(roc_auc_score(y, s))
    groups = [g for _, g in part.groupby("player_id")]
    rng = np.random.default_rng(RNG_SEED)
    values = []
    n = len(groups)
    for _ in range(draws):
        pick = pd.concat([groups[j] for j in rng.integers(0, n, n)])
        outcomes = pick["outcome_median"].astype(int)
        if outcomes.nunique() < 2:
            continue
        values.append(roc_auc_score(outcomes, pick[score_col].to_numpy(dtype=float)))
    low, high = np.percentile(values, [2.5, 97.5]) if values else (np.nan, np.nan)
    return point, float(low), float(high)


def reliability(scored: pd.DataFrame, prob_col: str) -> pd.DataFrame:
    """Decile reliability on the UNCLIPPED probability, plus the 60-80% band."""
    part = scored[scored["outcome_median"].notna()].copy()
    edges = np.arange(0, 101, 10)
    part["bucket"] = pd.cut(part[prob_col], edges, right=False)
    out = []
    for bucket, group in part.groupby("bucket", observed=True):
        out.append(dict(bucket=str(bucket), n=len(group),
                        predicted=float(group[prob_col].mean()),
                        realized=100 * float(group["outcome_median"].mean())))
    table = pd.DataFrame(out)
    table["gap"] = table["predicted"] - table["realized"]
    return table


def band_gap(scored: pd.DataFrame, prob_col: str,
             low: float = 60.0, high: float = 80.0) -> Tuple[int, float, float, float]:
    part = scored[scored["outcome_median"].notna()]
    band = part[(part[prob_col] >= low) & (part[prob_col] < high)]
    if band.empty:
        return 0, float("nan"), float("nan"), float("nan")
    predicted = float(band[prob_col].mean())
    realized = 100 * float(band["outcome_median"].mean())
    return len(band), predicted, realized, predicted - realized


# ── report ───────────────────────────────────────────────────────────────────


def _fmt(value: float, digits: int = 3) -> str:
    return "—" if value is None or not np.isfinite(value) else "{:.{}f}".format(value, digits)


def render_variants(rows: pd.DataFrame, features: pd.DataFrame,
                    variants: Dict[str, PooledLeagueModel]) -> List[str]:
    """MAE for alternative pooled fits, scored on the identical holdout.

    Used to reproduce the nine-feature 2023-24-only ridge the diagnosis
    measured, so this scorecard can be checked against the number the plan of
    record is built on.
    """
    lines = ["\n## Reference variants on the identical holdout\n",
             "| Variant | features/stat | train rows | " +
             " | ".join(pf.POOLED_STATS) + " |",
             "|---|---:|---:|" + "---:|" * len(pf.POOLED_STATS)]
    for name, variant in variants.items():
        part = score(rows, features, variant)
        maes = [float((part[part["stat"] == stat]["pooled"]
                       - part[part["stat"] == stat]["actual"]).abs().mean())
                for stat in pf.POOLED_STATS]
        lines.append("| {} | {} | {} | {} |".format(
            name, len(variant.stats["PTS"].feature_names),
            variant.stats["PTS"].n_train, " | ".join(_fmt(m) for m in maes)))
    return lines


def render(scored: pd.DataFrame, model: PooledLeagueModel,
           lookahead: Dict[str, float],
           variant_lines: Optional[List[str]] = None) -> str:
    lines: List[str] = []
    add = lines.append
    players = scored["player_id"].nunique()
    games = scored.groupby(["player_id", "step"]).ngroups
    add("# Pooled cross-player model — holdout scorecard\n")
    add("{} players / {} held-out games / {} rows. Training: {} pooled rows "
        "from {} players, every game strictly before the holdout "
        "(through {}).\n".format(players, games, len(scored),
                                 model.stats["PTS"].n_train, model.n_players,
                                 model.trained_through))
    add("Lookahead control: {} pooled features rebuilt independently and "
        "matched to the harness's own baselines with a maximum absolute "
        "difference of {:.1f}.\n".format(len(lookahead), max(lookahead.values())))

    add("\n## MAE — pooled model vs production vs every trivial baseline\n")
    header = "| Stat | pooled | production (81f) | " + " | ".join(
        b.replace("b_", "") for b in BASELINES) + " | best baseline |"
    add(header)
    add("|" + "---|" * (len(BASELINES) + 4))
    for stat in pf.POOLED_STATS:
        part = scored[scored["stat"] == stat]
        maes = {b: float((part[b] - part["actual"]).abs().mean()) for b in BASELINES}
        best = min(maes, key=maes.get)
        add("| {} | **{}** | {} | {} | {} ({}) |".format(
            stat, _fmt(float((part["pooled"] - part["actual"]).abs().mean())),
            _fmt(float((part["pred"] - part["actual"]).abs().mean())),
            " | ".join(_fmt(maes[b]) for b in BASELINES),
            _fmt(maes[best]), best.replace("b_", "")))

    add("\n## Paired bootstrap — mean|pooled| − mean|baseline|, 95% CI\n")
    add("Negative = the pooled model wins. Resampled over the 44 players, "
        "{} draws.\n".format(BOOTSTRAP_DRAWS))
    add("| Stat | baseline | Δ MAE | 95% CI | verdict |")
    add("|---|---|---:|---|---|")
    for stat in pf.POOLED_STATS:
        for baseline in BASELINES:
            point, low, high = paired_bootstrap(scored, stat, "pooled", baseline)
            if high < 0:
                verdict = "**pooled wins**"
            elif low > 0:
                verdict = "**pooled loses**"
            else:
                verdict = "tie"
            add("| {} | {} | {:+.3f} | [{:+.3f}, {:+.3f}] | {} |".format(
                stat, baseline.replace("b_", ""), point, low, high, verdict))

    add("\n## Exit criterion 1 — beat EWMA5 / L10 / season median on all four stats\n")
    add("The plan names those three. The stricter bar — the best of ALL eight "
        "trivial baselines — is reported beside it, because a model that only "
        "clears the three it was asked about has not cleared the field.\n")
    add("| Stat | pooled | EWMA5 | L10 | season median | worst of the 3 | "
        "criterion 1 | best of all 8 | margin vs best | bootstrap |")
    add("|---|---:|---:|---:|---:|---:|---|---|---:|---|")
    for stat in pf.POOLED_STATS:
        part = scored[scored["stat"] == stat]
        pooled_mae = float((part["pooled"] - part["actual"]).abs().mean())
        named = {b: float((part[b] - part["actual"]).abs().mean())
                 for b in EXIT_BASELINES}
        every = {b: float((part[b] - part["actual"]).abs().mean()) for b in BASELINES}
        best = min(every, key=every.get)
        worst_named = max(pooled_mae - v for v in named.values())
        point, low, high = paired_bootstrap(scored, stat, "pooled", best)
        verdict = ("**pooled wins**" if high < 0
                   else "**pooled loses**" if low > 0 else "tie")
        add("| {} | {} | {} | {} | {} | {:+.3f} | {} | {} ({}) | {:+.3f} | {} "
            "[{:+.3f}, {:+.3f}] |".format(
                stat, _fmt(pooled_mae), _fmt(named["b_ewma5"]), _fmt(named["b_l10"]),
                _fmt(named["b_median"]), worst_named,
                "PASS" if worst_named < 0 else "**FAIL**",
                _fmt(every[best]), best.replace("b_", ""), point, verdict, low, high))

    add("\n## Exit criterion 2 — median-line AUC >= 0.58\n")
    add("| Stat | pooled AUC | 95% CI | production AUC | L10 signal | PASS? |")
    add("|---|---:|---|---:|---:|---|")
    for stat in pf.POOLED_STATS:
        scored_stat = scored[scored["stat"] == stat].copy()
        scored_stat["pooled_gap"] = scored_stat["pooled"] - scored_stat["median_line"]
        scored_stat["prod_gap"] = scored_stat["pred"] - scored_stat["median_line"]
        scored_stat["l10_gap"] = scored_stat["b_l10"] - scored_stat["median_line"]
        auc, low, high = median_line_auc(scored_stat, stat, "pooled_gap")
        prod, _, _ = median_line_auc(scored_stat, stat, "prod_gap", draws=1)
        l10, _, _ = median_line_auc(scored_stat, stat, "l10_gap", draws=1)
        add("| {} | **{}** | [{}, {}] | {} | {} | {} |".format(
            stat, _fmt(auc, 4), _fmt(low, 4), _fmt(high, 4), _fmt(prod, 4),
            _fmt(l10, 4), "PASS" if auc >= 0.58 else "**FAIL**"))

    add("\n## Exit criterion 3 — unclipped 60-80% reliability gap within ±5 points\n")
    add("Positive = the probability claims more than it delivers "
        "(overconfident); negative = it delivers more than it claims.\n")
    add("| Probability source | band | N | predicted | realized | gap | PASS? |")
    add("|---|---|---:|---:|---:|---:|---|")
    for label, source, band in (("pooled (shrunk)", "pooled_prob", (60.0, 80.0)),
                                ("pooled (shrunk)", "pooled_prob", (40.0, 60.0)),
                                ("production (81f, reference)", "prob_median", (60.0, 80.0))):
        n, predicted, realized, gap = band_gap(scored, source, *band)
        verdict = "—" if source != "pooled_prob" or band != (60.0, 80.0) else (
            "PASS" if abs(gap) < 5 else "**FAIL**")
        add("| {} | {:.0f}-{:.0f}% | {} | {} | {} | {:+.1f} | {} |".format(
            label, band[0], band[1], n, _fmt(predicted, 1), _fmt(realized, 1),
            gap, verdict))

    add("\n### Full reliability table, pooled, unclipped\n")
    table = reliability(scored, "pooled_prob")
    add("| Bucket | N | predicted | realized | gap |")
    add("|---|---:|---:|---:|---:|")
    for _, row in table.iterrows():
        add("| {} | {} | {} | {} | {:+.1f} |".format(
            row["bucket"], int(row["n"]), _fmt(row["predicted"], 1),
            _fmt(row["realized"], 1), row["gap"]))
    lines.extend(variant_lines or [])
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--rows", type=Path, default=ROWS)
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the markdown scorecard here as well as stdout")
    parser.add_argument("--compare", action="append", default=[],
                        metavar="NAME=PATH",
                        help="also score this artifact on the same holdout "
                             "(repeatable)")
    args = parser.parse_args(argv)

    rows = load_holdout(args.rows)
    features = build_holdout_features(rows, args.season)
    lookahead = assert_no_lookahead(rows, features)
    print("lookahead control passed: {} features, max |difference| = {:.1f}".format(
        len(lookahead), max(lookahead.values())))

    model = PooledLeagueModel.load(args.model)
    scored = score(rows, features, model)

    variants: Dict[str, PooledLeagueModel] = {}
    for spec in args.compare:
        if "=" not in spec:
            raise ValueError("--compare expects NAME=PATH, got {!r}".format(spec))
        name, path = spec.split("=", 1)
        variants[name] = PooledLeagueModel.load(Path(path))
    variant_lines = render_variants(rows, features, variants) if variants else None

    report = render(scored, model, lookahead, variant_lines)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print("wrote {}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
