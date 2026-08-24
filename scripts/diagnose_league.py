"""Model-free league-wide diagnostics for the prop model's resolution failure.

Uses ``player_game_logs`` (2023-24 + 2024-25, 79,811 rows, ~700 player-seasons)
pulled to ``cache/league_logs.parquet``. Nothing here touches the model — the
point is to establish, from the data alone:

* H3 -- is a season-to-date median pseudo-line adversarial to any predictor that
  tracks recent form?  i.e. does P(actual > season median) fall as recent form
  runs above the season median (mean reversion), so that a recent-form tracker
  is structurally forced onto the losing side?
* H5 -- what is the noise ceiling?  How do trivial level-only forecasts compare
  with each other, with an oracle that knows the player's true forward level,
  and with an oracle that knows the player's actual minutes?

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/diagnose_league.py --min-prior 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "cache" / "league_logs.parquet"
STATS = ("pts", "reb", "ast", "pra")


def build_panel(df: pd.DataFrame, min_prior: int) -> pd.DataFrame:
    """One row per (player-season, game, stat) with every causal baseline."""
    df = df.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["pra"] = df["pts"] + df["reb"] + df["ast"]
    df = df.sort_values(["player_id", "season", "game_date"]).reset_index(drop=True)
    # Production's DNP filter: create_features drops games with no minutes.
    df = df[df["min"].fillna(0) > 0].reset_index(drop=True)

    out = []
    for (pid, season), g in df.groupby(["player_id", "season"], sort=False):
        n = len(g)
        if n < min_prior + 5:
            continue
        mins = g["min"].values.astype(float)
        for stat in STATS:
            y = g[stat].values.astype(float)
            season_mean = float(np.mean(y))
            for t in range(min_prior, n):
                hist = y[:t]
                fwd = y[t:]
                rate_hist = y[:t] / np.maximum(mins[:t], 1e-6)
                out.append(
                    dict(
                        player_id=pid,
                        player_name=g["player_name"].iloc[0],
                        season=season,
                        game_date=g["game_date"].iloc[t],
                        t=t,
                        n_games=n,
                        stat=stat.upper(),
                        actual=y[t],
                        minutes=mins[t],
                        b_median=float(np.median(hist)),
                        b_mean=float(np.mean(hist)),
                        b_l3=float(np.mean(hist[-3:])),
                        b_l5=float(np.mean(hist[-5:])),
                        b_l10=float(np.mean(hist[-10:])),
                        b_l20=float(np.mean(hist[-20:])),
                        b_last=float(hist[-1]),
                        hist_std=float(np.std(hist, ddof=1)),
                        # Oracle A: the player's mean over the games from t on.
                        # Knows the future; upper bound on any level-only forecast.
                        o_fwd_mean=float(np.mean(fwd)),
                        o_season_mean=season_mean,
                        # Oracle B: L10 per-minute rate x THIS game's actual minutes.
                        # Isolates how much of the error is minutes uncertainty.
                        o_minutes=float(np.mean(rate_hist[-10:]) * mins[t]),
                    )
                )
    return pd.DataFrame(out)


BASELINES = ["b_median", "b_mean", "b_l3", "b_l5", "b_l10", "b_l20", "b_last",
             "o_fwd_mean", "o_season_mean", "o_minutes"]


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--min-prior", type=int, default=20,
                   help="games of history required before a row is scored")
    p.add_argument("--out", type=Path, default=ROOT / "cache" / "league_panel.parquet")
    args = p.parse_args(argv)

    raw = pd.read_parquet(LOGS)
    panel = build_panel(raw, args.min_prior)
    panel.to_parquet(args.out)
    print("panel: {} rows | {} player-seasons | min_prior={}".format(
        len(panel), panel.groupby(["player_id", "season"]).ngroups, args.min_prior))

    # ── H5: trivial-baseline league table ────────────────────────────────────
    section("H5 -- baseline accuracy, league-wide (MAE / RMSE)")
    hdr = "{:6} {:>7}".format("stat", "N")
    for b in BASELINES:
        hdr += " {:>11}".format(b)
    print(hdr)
    for stat in ("PTS", "REB", "AST", "PRA"):
        s = panel[panel.stat == stat]
        line = "{:6} {:7d}".format(stat, len(s))
        for b in BASELINES:
            line += " {:11.3f}".format((s[b] - s.actual).abs().mean())
        print(line)
    print()
    print("RMSE, and the player's own game-to-game sigma for scale:")
    print("{:6} {:>9} {:>9} {:>9} {:>9} {:>9}".format(
        "stat", "sigma", "rmse_l10", "rmse_med", "rmse_oracle", "rmse_omin"))
    for stat in ("PTS", "REB", "AST", "PRA"):
        s = panel[panel.stat == stat]
        r = lambda c: float(np.sqrt(((s[c] - s.actual) ** 2).mean()))  # noqa: E731
        print("{:6} {:9.3f} {:9.3f} {:9.3f} {:9.3f} {:9.3f}".format(
            stat, s.hist_std.mean(), r("b_l10"), r("b_median"),
            r("o_fwd_mean"), r("o_minutes")))

    # ── H3: is a season-to-date median line adversarial? ─────────────────────
    section("H3 -- P(actual > season-to-date median), league-wide")
    print("Unconditional base rate (pushes excluded):")
    for stat in ("PTS", "REB", "AST", "PRA"):
        s = panel[panel.stat == stat]
        live = s[s.actual != s.b_median]
        print("  {:4} N={:6d}  push_rate={:5.1%}  over_rate={:6.2%}".format(
            stat, len(live), 1 - len(live) / len(s),
            float((live.actual > live.b_median).mean())))

    print("\nOver-rate conditioned on recent form vs season median")
    print("(form_gap = (L5 mean - season-to-date median) / hist_std)")
    print("If the median line were adversarial to a form-tracker, over_rate would")
    print("FALL as form_gap rises. If it RISES, recent form is genuinely predictive.")
    for stat in ("PTS", "REB", "AST", "PRA"):
        s = panel[panel.stat == stat].copy()
        s = s[s.actual != s.b_median]
        s["form_gap"] = (s.b_l5 - s.b_median) / s.hist_std.replace(0, np.nan)
        s = s.dropna(subset=["form_gap"])
        edges = [-9, -1.0, -0.5, -0.2, 0.2, 0.5, 1.0, 9]
        s["bin"] = pd.cut(s.form_gap, edges)
        print("\n  {}:".format(stat))
        for b, gg in s.groupby("bin", observed=True):
            print("    form_gap {:>14}  N={:6d}  over_rate={:6.2%}".format(
                str(b), len(gg), float((gg.actual > gg.b_median).mean())))

    # ── H2-adjacent: does any trivial signal discriminate the median line? ───
    section("H2/H5 -- rank discrimination of trivial signals at the median line")
    print("AUC of (signal - season median) as a score for the event actual > median.")
    print("0.50 = no discrimination. Ceiling for ANY point model that uses only")
    print("these inputs.")
    from sklearn.metrics import roc_auc_score
    sigs = ["b_l3", "b_l5", "b_l10", "b_l20", "b_mean", "b_last", "o_fwd_mean"]
    print("{:6} {:>8}".format("stat", "N") + "".join(
        " {:>10}".format(x) for x in sigs))
    for stat in ("PTS", "REB", "AST", "PRA"):
        s = panel[panel.stat == stat]
        s = s[s.actual != s.b_median]
        y = (s.actual > s.b_median).astype(int).values
        line = "{:6} {:8d}".format(stat, len(s))
        for x in sigs:
            line += " {:10.4f}".format(roc_auc_score(y, (s[x] - s.b_median).values))
        print(line)

    # ── H5: autocorrelation of the deviation from the player's season level ──
    section("H5 -- is there any serial signal left after removing the level?")
    print("Correlation of dev_t = actual_t - season_mean with the mean of the")
    print("previous k deviations. Zero => per-game residuals are white noise and")
    print("nothing beyond a level estimate is extractable from the box score alone.")
    print("{:6} {:>10} {:>10} {:>10} {:>10}".format(
        "stat", "lag1", "prev3", "prev5", "prev10"))
    for stat in ("PTS", "REB", "AST", "PRA"):
        s = panel[panel.stat == stat]
        dev = s.actual - s.o_season_mean
        row = "{:6}".format(stat)
        for col, k in (("b_last", 1), ("b_l3", 3), ("b_l5", 5), ("b_l10", 10)):
            prior_dev = s[col] - s.o_season_mean
            row += " {:10.4f}".format(float(np.corrcoef(dev, prior_dev)[0, 1]))
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
