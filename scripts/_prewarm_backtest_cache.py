"""Pre-warm the backtest game-log cache.

Thin wrapper around ``backtest_unbiased.fetch_player_log`` so the cache
contract lives in exactly one place. Resumable: already-cached players are
skipped, and each fetch is written immediately (atomically), so a killed run
never loses what it already has.

Cache contract (owned by scripts/backtest_unbiased.py):
    cache/backtest_logs/{season}/{player_id}.parquet
    GAME_DATE is a 'YYYY-MM-DD' string, rows sorted ascending by date.

Usage::

    NBA_EVAL_DISABLE_TF=1 python3 scripts/_prewarm_backtest_cache.py [season] [sleep_s]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest_unbiased import (  # noqa: E402  (scripts/ on path)
    DEFAULT_PLAYERS,
    fetch_player_log,
    log_cache_path,
)


def main(season: str = "2024-25", sleep_s: float = 0.6) -> int:
    total = len(DEFAULT_PLAYERS)
    fetched = skipped = failed = 0

    for i, (name, pid) in enumerate(DEFAULT_PLAYERS, 1):
        if log_cache_path(pid, season).exists():
            skipped += 1
            print("[{}/{}] skip (cached) {}".format(i, total, name), flush=True)
            continue
        try:
            df = fetch_player_log(pid, season, sleep_s=float(sleep_s))
            fetched += 1
            print("[{}/{}] ok {}: {} rows".format(i, total, name, len(df)), flush=True)
        except Exception as exc:
            failed += 1
            print("[{}/{}] FAIL {} ({}): {}: {}".format(
                i, total, name, pid, type(exc).__name__, exc), flush=True)

    print("\ndone: fetched={} skipped={} failed={} -> {}".format(
        fetched, skipped, failed, log_cache_path("*", season).parent), flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
