"""Analyse the per-row artifacts from ``scripts/diagnose_dump.py``.

Answers H1 (does the point model beat trivial baselines), H2 (is it
directionally informative at the median line), H3 (is the median pseudo-line an
adversarial benchmark), H4 (how thin is the feature signal) and H5 (where is the
noise ceiling) on the *same held-out games* the reference backtest scored.

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/diagnose_analyze.py --dir cache/diagnostics_t60
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
STATS = ("PTS", "REB", "AST", "PRA")
BASELINES = ["b_median", "b_mean", "b_l3", "b_l5", "b_l10", "b_l20", "b_last", "b_ewma5"]
RNG = np.random.default_rng(20260823)


def sec(t: str) -> None:
    print("\n" + "=" * 82 + "\n" + t + "\n" + "=" * 82)


def paired_boot(a: np.ndarray, b: np.ndarray, n: int = 4000) -> tuple:
    """Bootstrap CI for mean(a) - mean(b) over paired absolute errors."""
    d = a - b
    idx = RNG.integers(0, len(d), size=(n, len(d)))
    boots = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def h1(d: pd.DataFrame) -> None:
    sec("H1 -- does the point model beat trivial baselines on the SAME held-out games?")
    print("MAE (pooled over every held-out game), model vs causal baselines.\n")
    hdr = "{:5}{:>7}{:>9}".format("stat", "N", "model")
    for b in BASELINES:
        hdr += "{:>9}".format(b.replace("b_", ""))
    print(hdr)
    for s in STATS:
        x = d[d.stat == s]
        line = "{:5}{:7d}{:9.3f}".format(s, len(x), (x.pred - x.actual).abs().mean())
        for b in BASELINES:
            line += "{:9.3f}".format((x[b] - x.actual).abs().mean())
        print(line)

    print("\nRMSE:")
    hdr = "{:5}{:>9}".format("stat", "model")
    for b in BASELINES:
        hdr += "{:>9}".format(b.replace("b_", ""))
    print(hdr)
    for s in STATS:
        x = d[d.stat == s]
        rm = lambda v: float(np.sqrt(((v - x.actual) ** 2).mean()))  # noqa: E731
        print("{:5}{:9.3f}".format(s, rm(x.pred))
              + "".join("{:9.3f}".format(rm(x[b])) for b in BASELINES))

    print("\nPaired: mean(|model err|) - mean(|baseline err|), 95% bootstrap CI.")
    print("Negative => model better. CI straddling 0 => no distinguishable edge.")
    for s in STATS:
        x = d[d.stat == s]
        me = (x.pred - x.actual).abs().values
        print("  {}:".format(s))
        for b in ("b_median", "b_mean", "b_l5", "b_l10", "b_l20", "b_ewma5"):
            be = (x[b] - x.actual).abs().values
            m, lo, hi = paired_boot(me, be)
            flag = "MODEL BETTER" if hi < 0 else ("MODEL WORSE" if lo > 0 else "tie")
            print("    vs {:9} {:+7.3f}  [{:+.3f}, {:+.3f}]  {}".format(
                b.replace("b_", ""), m, lo, hi, flag))

    print("\nPer-player: on how many of the players does the model beat the baseline?")
    print("{:5}{:>10}".format("stat", "players")
          + "".join("{:>10}".format(b.replace("b_", "")) for b in
                    ("b_median", "b_mean", "b_l5", "b_l10", "b_l20")))
    for s in STATS:
        x = d[d.stat == s]
        pm = x.groupby("player").apply(
            lambda g: pd.Series({
                "model": (g.pred - g.actual).abs().mean(),
                **{b: (g[b] - g.actual).abs().mean() for b in BASELINES},
            }), include_groups=False)
        line = "{:5}{:10d}".format(s, len(pm))
        for b in ("b_median", "b_mean", "b_l5", "b_l10", "b_l20"):
            line += "{:>10}".format("{}/{}".format(int((pm["model"] < pm[b]).sum()), len(pm)))
        print(line)



def h1b(d: pd.DataFrame) -> None:
    sec("H1b -- is the deficit LEVEL BIAS or RESOLUTION?")
    print("Pooled bias (pred - actual) and per-player |bias|, model vs baselines.\n")
    print("{:5}{:>10}{:>10}{:>10}{:>10}{:>12}{:>12}".format(
        "stat", "bias_mdl", "bias_med", "bias_l10", "bias_l20", "|bias|_mdl", "|bias|_l10"))
    for s in STATS:
        x = d[d.stat == s]
        pb = lambda c: float((x[c] - x.actual).mean())  # noqa: E731
        pp = lambda c: float(x.groupby("player").apply(
            lambda g: (g[c] - g.actual).mean(), include_groups=False).abs().mean())  # noqa: E731
        print("{:5}{:10.3f}{:10.3f}{:10.3f}{:10.3f}{:12.3f}{:12.3f}".format(
            s, float((x.pred - x.actual).mean()), pb("b_median"), pb("b_l10"),
            pb("b_l20"),
            float(x.groupby("player").apply(
                lambda g: (g.pred - g.actual).mean(), include_groups=False).abs().mean()),
            pp("b_l10")))

    print("\nORACLE DE-BIAS: subtract each player's own held-out mean error, then re-score.")
    print("This is not achievable in production -- it is a diagnostic. If the")
    print("de-biased model beats L10 while the raw model does not, the deficit is a")
    print("per-player level offset, which is fixable. If it still does not, the")
    print("model has no resolution to recover.\n")
    print("{:5}{:>11}{:>13}{:>11}{:>11}{:>13}".format(
        "stat", "MAE model", "MAE debiased", "MAE l10", "MAE l20", "MAE l10_deb"))
    for s in STATS:
        x = d[d.stat == s].copy()
        x["dp"] = x.pred - x.groupby("player").apply(
            lambda g: (g.pred - g.actual).mean(), include_groups=False).reindex(x.player).values
        x["d10"] = x.b_l10 - x.groupby("player").apply(
            lambda g: (g.b_l10 - g.actual).mean(), include_groups=False).reindex(x.player).values
        print("{:5}{:11.3f}{:13.3f}{:11.3f}{:11.3f}{:13.3f}".format(
            s, (x.pred - x.actual).abs().mean(), (x.dp - x.actual).abs().mean(),
            (x.b_l10 - x.actual).abs().mean(), (x.b_l20 - x.actual).abs().mean(),
            (x.d10 - x.actual).abs().mean()))

    print("\nCorrelation of model prediction with the actual, held out")
    print("(within-player, after removing each player's holdout means):")
    print("{:5}{:>10}{:>10}{:>10}{:>10}".format("stat", "model", "l5", "l10", "median"))
    for s in STATS:
        x = d[d.stat == s]
        def wc(col):
            g = x.groupby("player")
            a = x[col] - g[col].transform("mean")
            b = x.actual - g.actual.transform("mean")
            if a.std() == 0:
                return float("nan")
            return float(np.corrcoef(a, b)[0, 1])
        print("{:5}{:10.4f}{:10.4f}{:10.4f}{:10.4f}".format(
            s, wc("pred"), wc("b_l5"), wc("b_l10"), wc("b_median")))


def h2(d: pd.DataFrame) -> None:
    sec("H2 -- is the model directionally informative at the median line?")
    m = d[d.outcome_median.notna() & d.prob_median.notna()].copy()
    m["edge_model"] = m.pred - m.median_line
    print("N median-line samples (pushes excluded): {}".format(len(m)))
    print("\nAUC for the event `actual > season-to-date median`.")
    print("0.50 = coin flip.  <0.50 = the signal points the WRONG way.\n")
    print("{:5}{:>7}{:>11}{:>11}{:>11}{:>11}{:>11}{:>11}".format(
        "stat", "N", "prob", "pred-med", "L5-med", "L10-med", "L20-med", "mean-med"))
    for s in STATS + ("ALL",):
        x = m if s == "ALL" else m[m.stat == s]
        y = x.outcome_median.astype(int).values
        if len(set(y)) < 2:
            continue
        row = "{:5}{:7d}".format(s, len(x))
        for v in (x.prob_median.values, x.edge_model.values,
                  (x.b_l5 - x.median_line).values, (x.b_l10 - x.median_line).values,
                  (x.b_l20 - x.median_line).values, (x.b_mean - x.median_line).values):
            row += "{:11.4f}".format(roc_auc_score(y, v))
        print(row)

    print("\nSign test: does sign(pred - median) match sign(actual - median)?")
    print("Base rate = share of rows where actual > median (the always-OVER rate).\n")
    print("{:5}{:>8}{:>11}{:>11}{:>11}{:>11}".format(
        "stat", "N", "base(over)", "model_acc", "L5_acc", "L10_acc"))
    for s in STATS + ("ALL",):
        x = m if s == "ALL" else m[m.stat == s]
        y = x.outcome_median.astype(int).values
        acc = lambda sig: float((((sig > 0).astype(int)) == y).mean())  # noqa: E731
        print("{:5}{:8d}{:11.4f}{:11.4f}{:11.4f}{:11.4f}".format(
            s, len(x), y.mean(), acc(x.edge_model.values),
            acc((x.b_l5 - x.median_line).values), acc((x.b_l10 - x.median_line).values)))

    print("\nMedian-line reliability by predicted-probability decile (model):")
    print("{:>12}{:>7}{:>10}{:>10}{:>9}{:>12}".format(
        "bucket", "N", "pred", "realized", "gap", "L5 would"))
    m["bucket"] = (m.prob_median // 10).astype(int).clip(1, 8)
    for b, g in m.groupby("bucket"):
        l5_dir = (g.b_l5 > g.median_line).astype(int)
        print("{:>12}{:7d}{:10.1%}{:10.1%}{:+9.1f}{:>12}".format(
            "{}-{}%".format(b * 10, b * 10 + 10), len(g), g.prob_median.mean() / 100,
            g.outcome_median.mean(),
            (g.prob_median.mean() - 100 * g.outcome_median.mean()),
            "{:.0%} over".format(l5_dir.mean())))


def h3(d: pd.DataFrame) -> None:
    sec("H3 -- is the median pseudo-line adversarial, or is the model on the wrong side?")
    m = d[d.outcome_median.notna() & d.prob_median.notna()].copy()
    m["form_gap"] = (m.b_l5 - m.median_line) / m.hist_std.replace(0, np.nan)
    m["model_gap"] = (m.pred - m.median_line) / m.hist_std.replace(0, np.nan)
    m = m.dropna(subset=["form_gap", "model_gap"])
    print("Realized over-rate by recent-form gap, on the SAME held-out rows.")
    print("A rising over-rate means the median line rewards form-tracking;")
    print("i.e. the benchmark is NOT adversarial to a recent-form predictor.\n")
    edges = [-9, -0.5, -0.2, 0.2, 0.5, 9]
    m["fbin"] = pd.cut(m.form_gap, edges)
    print("{:>16}{:>8}{:>12}{:>14}".format("form_gap", "N", "over_rate", "mean model P"))
    for b, g in m.groupby("fbin", observed=True):
        print("{:>16}{:8d}{:12.1%}{:14.1f}".format(
            str(b), len(g), g.outcome_median.mean(), g.prob_median.mean()))

    print("\nWhere do the model's low-probability (<30%) median picks sit on form?")
    lo = m[m.prob_median < 30]
    print("  N={}  realized over-rate={:.1%}".format(len(lo), lo.outcome_median.mean()))
    print("  mean form_gap (L5 vs median) = {:+.3f} sigma".format(lo.form_gap.mean()))
    print("  mean model_gap (pred vs median) = {:+.3f} sigma".format(lo.model_gap.mean()))
    print("  share where L5 and the model DISAGREE on direction: {:.1%}".format(
        float(((lo.form_gap > 0) != (lo.model_gap > 0)).mean())))
    dis = lo[(lo.form_gap > 0) != (lo.model_gap > 0)]
    if len(dis):
        print("  ...on those disagreements the over-rate is {:.1%} (L5 was right {:.1%})".format(
            dis.outcome_median.mean(),
            float(((dis.form_gap > 0).astype(int) == dis.outcome_median).mean())))

    print("\nCorrelation of the model's own gap with the form gap:")
    for s in STATS:
        x = m[m.stat == s]
        print("  {:4} corr(model_gap, form_gap) = {:+.3f}   mean model_gap={:+.3f}".format(
            s, float(np.corrcoef(x.model_gap, x.form_gap)[0, 1]), x.model_gap.mean()))


def h4(dirpath: Path, d: pd.DataFrame) -> None:
    sec("H4 -- how much of the 81-feature vector actually carries importance?")
    imp = json.loads((dirpath / "importance.json").read_text())
    conc = []
    for player, per_stat in imp.items():
        for stat, feats in per_stat.items():
            if not feats:
                continue
            v = np.array(sorted(feats.values(), reverse=True), dtype=float)
            tot = v.sum()
            if tot <= 0:
                continue
            v = v / tot
            cs = np.cumsum(v)
            conc.append(dict(
                player=player, stat=stat, n_feat=len(v),
                top1=v[0], top5=cs[min(4, len(cs) - 1)], top10=cs[min(9, len(cs) - 1)],
                n_for_80=int(np.searchsorted(cs, 0.80) + 1),
                n_above_1pct=int((v >= 0.01).sum()),
            ))
    c = pd.DataFrame(conc)
    print("Per (player, stat) importance concentration, averaged:")
    print(c.groupby("stat")[["n_feat", "top1", "top5", "top10", "n_for_80", "n_above_1pct"]]
          .mean().round(3).to_string())
    print("\nAll (player, stat) pairs: {}".format(len(c)))
    print(c[["n_feat", "top1", "top5", "top10", "n_for_80", "n_above_1pct"]]
          .describe().round(3).to_string())

    agg = {}
    for per_stat in imp.values():
        for stat, feats in per_stat.items():
            tot = sum(feats.values()) or 1.0
            for k, v in feats.items():
                agg.setdefault(stat, {}).setdefault(k, []).append(v / tot)
    for stat in ("PTS", "REB", "AST"):
        if stat not in agg:
            continue
        top = sorted(((np.mean(v), k) for k, v in agg[stat].items()), reverse=True)[:12]
        print("\n  {} -- top mean-normalised importances across players:".format(stat))
        for score, k in top:
            print("    {:38} {:.4f}".format(k, score))


def h5(d: pd.DataFrame) -> None:
    sec("H5 -- noise ceiling: model error against the player's own game-to-game sigma")
    print("{:5}{:>10}{:>10}{:>10}{:>10}{:>10}".format(
        "stat", "sigma", "rmse", "rmse/sig", "mae", "mae/sig"))
    for s in STATS:
        x = d[d.stat == s]
        rmse = float(np.sqrt(((x.pred - x.actual) ** 2).mean()))
        mae = float((x.pred - x.actual).abs().mean())
        sig = float(x.hist_std.mean())
        print("{:5}{:10.3f}{:10.3f}{:10.3f}{:10.3f}{:10.3f}".format(
            s, sig, rmse, rmse / sig, mae, mae / sig))
    print("\nVariance explained by the model on held-out games")
    print("(R^2 vs predicting the player's own season-to-date mean):")
    for s in STATS:
        x = d[d.stat == s]
        ss_res = float(((x.actual - x.pred) ** 2).sum())
        ss_base = float(((x.actual - x.b_mean) ** 2).sum())
        ss_tot = float(((x.actual - x.actual.mean()) ** 2).sum())
        print("  {:4} R2_vs_grand_mean={:+.4f}   R2_vs_player_STD_mean={:+.4f}".format(
            s, 1 - ss_res / ss_tot, 1 - ss_res / ss_base))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=ROOT / "cache" / "diagnostics_t60")
    args = p.parse_args(argv)
    d = pd.read_parquet(args.dir / "rows.parquet")
    print("{} rows | {} players | {} held-out games".format(
        len(d), d.player.nunique(), d.groupby(["player", "game_date"]).ngroups))
    h1(d)
    h1b(d)
    h2(d)
    h3(d)
    h4(args.dir, d)
    h5(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
