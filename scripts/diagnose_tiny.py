"""H4 -- does a deliberately tiny model match the 81-feature model?

Trains alternative predictors on the EXACT same 60 training rows each player's
production model was fitted on, and scores them on the EXACT same served
81-feature vectors the walk-forward replay handed to ``predict``. The only thing
that changes is which columns the estimator is allowed to look at.

Requires ``scripts/diagnose_dump.py`` to have run first.

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/diagnose_tiny.py --dir cache/diagnostics_t60
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
COMP = ("PTS", "REB", "AST")


def feature_sets(stat: str):
    return {
        "T1_roll10": ["ROLL_10_{}".format(stat)],
        "T3_roll+min": ["ROLL_5_{}".format(stat), "ROLL_10_{}".format(stat),
                        "ROLL_10_MIN_NUMERIC"],
        "T5_+opp+home": ["ROLL_5_{}".format(stat), "ROLL_10_{}".format(stat),
                         "ROLL_10_MIN_NUMERIC", "OPP_DEF_RATING_NORM", "IS_HOME"],
        "T8_+std+rest": ["ROLL_5_{}".format(stat), "ROLL_10_{}".format(stat),
                         "ROLL_5_MIN_NUMERIC", "ROLL_10_MIN_NUMERIC",
                         "OPP_DEF_RATING_NORM", "IS_HOME",
                         "STD_10_{}".format(stat), "DAYS_REST"],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=ROOT / "cache" / "diagnostics_t60")
    args = p.parse_args(argv)

    rows = pd.read_parquet(args.dir / "rows.parquet")
    served = pd.read_parquet(args.dir / "served.parquet")
    served["key"] = served.player_id.astype(str) + "|" + served.step.astype(str)
    rows["key"] = rows.player_id.astype(str) + "|" + rows.step.astype(str)

    import nba_evaluator as ev  # noqa: E402
    all_feats = list(ev.MLPredictor.FEATURE_COLS)

    est = {
        "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=3.0)),
        "gbm": lambda: GradientBoostingRegressor(
            n_estimators=150, learning_rate=0.05, max_depth=3, random_state=0),
    }

    preds = {}   # (setname, estname) -> {key: {stat: value}}
    for pid, grp in served.groupby("player_id"):
        tf = args.dir / "train" / "{}.parquet".format(pid)
        if not tf.exists():
            continue
        tr = pd.read_parquet(tf)
        for stat in COMP:
            if stat not in tr.columns:
                continue
            ytr = tr[stat].astype(float).values
            for sname, cols in list(feature_sets(stat).items()) + [("FULL_81", all_feats)]:
                cols_ok = [c for c in cols if c in tr.columns and c in grp.columns]
                if not cols_ok:
                    continue
                Xtr = tr[cols_ok].astype(float).fillna(0).values
                Xte = grp[cols_ok].astype(float).fillna(0).values
                for ename, mk in est.items():
                    if sname == "FULL_81" and ename == "ridge":
                        pass  # keep both, ridge on 81 with n=60 is informative
                    try:
                        m = mk().fit(Xtr, ytr)
                        yp = m.predict(Xte)
                    except Exception:
                        continue
                    d = preds.setdefault((sname, ename), {})
                    for k, v in zip(grp["key"].values, yp):
                        d.setdefault(k, {})[stat] = float(v)

    # Score every variant against the same actuals the replay measured.
    base = rows.set_index(["key", "stat"])
    out = []
    for (sname, ename), d in preds.items():
        for stat in ("PTS", "REB", "AST", "PRA"):
            errs, aucs_y, aucs_s = [], [], []
            for k, per in d.items():
                if stat == "PRA":
                    if not all(c in per for c in COMP):
                        continue
                    yp = sum(per[c] for c in COMP)
                else:
                    if stat not in per:
                        continue
                    yp = per[stat]
                try:
                    r = base.loc[(k, stat)]
                except KeyError:
                    continue
                errs.append(abs(yp - float(r.actual)))
                if pd.notna(r.outcome_median):
                    aucs_y.append(int(r.outcome_median))
                    aucs_s.append(yp - float(r.median_line))
            if not errs:
                continue
            auc = (roc_auc_score(aucs_y, aucs_s)
                   if len(set(aucs_y)) > 1 else float("nan"))
            out.append(dict(featureset=sname, est=ename, stat=stat,
                            n=len(errs), mae=float(np.mean(errs)), auc_median=auc))

    res = pd.DataFrame(out)

    print("Production model, for reference (same rows):")
    ref = []
    for stat in ("PTS", "REB", "AST", "PRA"):
        x = rows[rows.stat == stat]
        m = x[x.outcome_median.notna()]
        ref.append(dict(featureset="PRODUCTION", est="ensemble", stat=stat, n=len(x),
                        mae=float((x.pred - x.actual).abs().mean()),
                        auc_median=roc_auc_score(
                            m.outcome_median.astype(int), m.pred - m.median_line)))
        b = []
    ref = pd.DataFrame(ref)

    print("\nMAE by feature set (lower is better):")
    piv = pd.concat([ref, res]).pivot_table(
        index=["featureset", "est"], columns="stat", values="mae")
    print(piv.round(3).to_string())

    print("\nAUC at the season-median line (0.50 = coin flip):")
    piv2 = pd.concat([ref, res]).pivot_table(
        index=["featureset", "est"], columns="stat", values="auc_median")
    print(piv2.round(4).to_string())

    print("\nTrivial baselines on the same rows, for scale:")
    for stat in ("PTS", "REB", "AST", "PRA"):
        x = rows[rows.stat == stat]
        m = x[x.outcome_median.notna()]
        print("  {:4} MAE l10={:.3f} l20={:.3f} median={:.3f} | AUC l10={:.4f}".format(
            stat, (x.b_l10 - x.actual).abs().mean(),
            (x.b_l20 - x.actual).abs().mean(),
            (x.b_median - x.actual).abs().mean(),
            roc_auc_score(m.outcome_median.astype(int), m.b_l10 - m.median_line)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
