"""Closing Line Value and forward-sample statistics.

Pure functions only — no database, no network, no I/O. This module holds the
arithmetic that decides whether the prop model is ever trusted again, so it is
deliberately kept small, dependency-free and exhaustively tested.

Two ideas live here:

*CLV* — did the market move toward our number after we took it? A pick taken at
OVER 25.5 that closes at 26.5 has +1.0 CLV. CLV is the fastest, lowest-variance
signal that a model is beating a book, because it does not wait on the outcome.

*Forward-sample verdicts* — the 2026-08 investigation concluded that the model
had "signal" from measurements that could not support the claim. Every helper
here therefore refuses to produce a verdict below ``MIN_CONCLUSIVE_N``, and uses
a Wilson score interval rather than a normal approximation, which is badly
wrong at small n and near the 0/1 boundaries.
"""
from __future__ import annotations

import math

# -110 on both sides: risk 110 to win 100. 110/210 = 52.38%.
BREAKEVEN_RATE = 110 / 210

# Plan of record (docs/NEXT_STEPS_2026-08-23.md): n >= 500 for a +/-4% band.
MIN_CONCLUSIVE_N = 500

# 95% two-sided normal quantile, used for the Wilson score interval.
DEFAULT_Z = 1.959963984540054

DIRECTION_OVER = "OVER"
DIRECTION_UNDER = "UNDER"
VALID_DIRECTIONS = (DIRECTION_OVER, DIRECTION_UNDER)

VERDICT_INSUFFICIENT = "INSUFFICIENT_SAMPLE"
VERDICT_CLEARS = "CLEARS_BREAKEVEN"
VERDICT_BELOW = "BELOW_BREAKEVEN"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"


def _as_finite_float(value, label: str) -> float:
    """Coerce to float, rejecting None, non-numerics, NaN and infinities."""
    if value is None:
        raise ValueError(f"{label} is required, got None")
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, got a bool")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric, got {value!r}")
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return result


def _as_count(value, label: str) -> int:
    """Coerce to a non-negative int."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an int, got {value!r}")
    if value < 0:
        raise ValueError(f"{label} must be non-negative, got {value}")
    return value


def compute_clv(direction: str, entry_line, closing_line) -> float:
    """Signed closing line value, in units of the stat.

    Positive means the market moved in our favour after we took the number.

    OVER  wins when the line rises  (we hold the cheaper number).
    UNDER wins when the line falls  (we hold the richer number).

    Raises:
        ValueError: unknown direction, or a missing/non-finite line.
    """
    if not isinstance(direction, str):
        raise ValueError(f"direction must be a string, got {direction!r}")
    normalized = direction.strip().upper()
    if normalized not in VALID_DIRECTIONS:
        raise ValueError(
            f"direction must be one of {VALID_DIRECTIONS}, got {direction!r}"
        )

    entry = _as_finite_float(entry_line, "entry_line")
    closing = _as_finite_float(closing_line, "closing_line")

    if normalized == DIRECTION_OVER:
        return closing - entry
    return entry - closing


def wilson_interval(wins, n, z: float = DEFAULT_Z):
    """Wilson score interval for a binomial rate.

    Returns ``(low, high)`` as floats in [0, 1], or ``None`` when n == 0.

    Preferred over the normal approximation because the forward sample starts at
    n=0 and spends a long time small, where the normal interval produces bounds
    outside [0, 1] and badly understates uncertainty.
    """
    wins = _as_count(wins, "wins")
    n = _as_count(n, "n")
    if wins > n:
        raise ValueError(f"wins ({wins}) cannot exceed n ({n})")
    if n == 0:
        return None

    p_hat = wins / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denominator
    margin = (z / denominator) * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))

    # At the boundaries the Wilson bounds are exactly 0 and 1; floating-point
    # rounding lands a hair inside, so snap them rather than report 0.99999...
    low = 0.0 if wins == 0 else max(0.0, center - margin)
    high = 1.0 if wins == n else min(1.0, center + margin)
    return (low, high)


def _verdict(wins: int, n: int, min_n: int, z: float) -> str:
    """Classify a record against breakeven, refusing to conclude below min_n."""
    if n < min_n:
        return VERDICT_INSUFFICIENT
    interval = wilson_interval(wins, n, z=z)
    low, high = interval
    if low > BREAKEVEN_RATE:
        return VERDICT_CLEARS
    if high < BREAKEVEN_RATE:
        return VERDICT_BELOW
    return VERDICT_INCONCLUSIVE


def summarize_record(wins, losses, min_n: int = MIN_CONCLUSIVE_N,
                     z: float = DEFAULT_Z) -> dict:
    """Summarize a win/loss record with an honest verdict.

    Returns a new dict; nothing is mutated. ``win_rate`` and the interval bounds
    are ``None`` at n=0 rather than a misleading 0.0.
    """
    wins = _as_count(wins, "wins")
    losses = _as_count(losses, "losses")
    min_n = _as_count(min_n, "min_n")
    n = wins + losses

    interval = wilson_interval(wins, n, z=z)
    win_rate = (wins / n) if n else None

    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "wilson_low": interval[0] if interval else None,
        "wilson_high": interval[1] if interval else None,
        "breakeven": BREAKEVEN_RATE,
        "distance_to_breakeven": (win_rate - BREAKEVEN_RATE) if n else None,
        "min_n": min_n,
        "picks_to_min_n": max(0, min_n - n),
        "verdict": _verdict(wins, n, min_n, z),
    }


def summarize_clv(values) -> dict:
    """Summarize a sequence of signed CLV numbers.

    A CLV of exactly 0.0 counts as *not* positive — an unmoved line is no
    evidence of an edge.
    """
    cleaned = [_as_finite_float(v, "clv value") for v in values]
    n = len(cleaned)
    if n == 0:
        return {"n": 0, "avg_clv": None, "positive_clv_rate": None}

    positive = sum(1 for v in cleaned if v > 0)
    return {
        "n": n,
        "avg_clv": sum(cleaned) / n,
        "positive_clv_rate": positive / n,
    }
