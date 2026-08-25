"""Fit the pooled cross-player prop model and write the league artifact.

One ridge per stat over six causal recency features, fitted on every league
game strictly before ``--through``. Nothing here is per-player: the whole point
is that n goes from ~60 rows per player to ~25,000 pooled rows, which is what
fixes the p/n = 1.35 that the 2026-08 investigation identified as the root
cause of the per-player model's failure.

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py
    NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py --through 2025-02-28
    NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py --refresh

``--refresh`` repulls ``player_game_logs`` from Supabase. Everything reading
through ``db.py`` needs ``load_dotenv(override=True)`` first or the connection
fails with a misleading "password authentication failed for user postgres".
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

os.environ.setdefault("NBA_EVAL_DISABLE_TF", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import pooled_features as pf  # noqa: E402
from pooled_model import PooledLeagueModel, resolve_model_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEAGUE_LOGS = ROOT / "cache" / "league_logs.parquet"

LEAGUE_LOG_QUERY = """
    SELECT player_id, player_name, season, game_date, matchup, min, pts, reb, ast
    FROM player_game_logs
    WHERE min IS NOT NULL
    ORDER BY player_id, season, game_date
"""


def refresh_league_logs(destination: Path) -> pd.DataFrame:
    """Repull every player game log from Supabase into the parquet cache."""
    from dotenv import load_dotenv

    load_dotenv(override=True)  # without this db.py reports a bogus auth failure
    import db  # noqa: E402  — imported late so the env is loaded first

    with db.borrow_conn() as conn:
        frame = pd.read_sql(LEAGUE_LOG_QUERY, conn)
    if frame.empty:
        raise RuntimeError("player_game_logs returned no rows")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(destination)
    return frame


def load_league_logs(path: Path, refresh: bool) -> pd.DataFrame:
    if refresh:
        return refresh_league_logs(path)
    if not path.exists():
        raise FileNotFoundError(
            "{} not found. Run with --refresh to pull player_game_logs from "
            "Supabase.".format(path))
    return pd.read_parquet(path)


def train(logs: pd.DataFrame, through: Optional[str], min_prior: int,
          out_path: Optional[Path], kinds: Sequence[str] = pf.RECENCY_KINDS,
          seasons: Optional[Sequence[str]] = None) -> PooledLeagueModel:
    """Build the panel, cut it at ``through``, fit, and persist."""
    if seasons:
        logs = logs[logs["season"].isin(list(seasons))]
        if logs.empty:
            raise ValueError("no logs for season(s) {}".format(", ".join(seasons)))
    panel = pf.build_panel(logs, min_prior=min_prior, kinds=kinds)
    panel["game_date"] = pd.to_datetime(panel["game_date"])
    if through:
        cutoff = pd.Timestamp(through)
        before = len(panel)
        panel = panel[panel["game_date"] < cutoff]
        print("cut at {}: {} -> {} training rows".format(
            cutoff.date(), before, len(panel)))
        if panel.empty:
            raise ValueError("no training rows before {}".format(cutoff.date()))
    trained_through = str(panel["game_date"].max().date())
    model = PooledLeagueModel.fit(panel, trained_through=trained_through, kinds=kinds)

    print("pooled league model | {} features/stat | {} rows | {} players | "
          "through {}".format(len(kinds), model.stats["PTS"].n_train,
                              model.n_players, model.trained_through))
    for stat in pf.POOLED_STATS:
        fit = model.stats[stat]
        print("  {:4} train MAE {:6.3f} | sigma = {:.3f} + {:.3f}*dispersion "
              "| shrink slope {:.3f}".format(
                  stat, fit.train_mae, fit.sigma_intercept, fit.sigma_slope,
                  fit.shrinker.slope))
    written = model.save(out_path)
    print("wrote {}".format(written))
    return model


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, default=LEAGUE_LOGS,
                        help="league game-log parquet (default cache/league_logs.parquet)")
    parser.add_argument("--refresh", action="store_true",
                        help="repull player_game_logs from Supabase first")
    parser.add_argument("--through", default=None,
                        help="train only on games strictly before this date "
                             "(YYYY-MM-DD). Omit to use every game available.")
    parser.add_argument("--min-prior", type=int, default=pf.MIN_PRIOR_GAMES,
                        help="in-season games of history a training row needs")
    parser.add_argument("--out", type=Path, default=None,
                        help="artifact path (default {})".format(resolve_model_path()))
    parser.add_argument("--feature-kinds", default=",".join(pf.RECENCY_KINDS),
                        help="comma-separated recency kinds. Default is the "
                             "six production features; the nine-feature "
                             "reference the 2026-08 diagnosis measured is "
                             "L3,L5,L10,L20,MEDIAN,MEAN,LAST,EWMA5,STD.")
    parser.add_argument("--seasons", default=None,
                        help="comma-separated seasons to train on (default all)")
    args = parser.parse_args(argv)
    kinds = tuple(k.strip().upper() for k in args.feature_kinds.split(",") if k.strip())
    seasons = tuple(s.strip() for s in args.seasons.split(",")) if args.seasons else None

    logs = load_league_logs(args.logs, args.refresh)
    print("{} game logs | {} players".format(len(logs), logs["player_id"].nunique()))
    train(logs, args.through, args.min_prior, args.out, kinds, seasons)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
