"""Exact-price expected value. No recommendation from a point-estimate gap."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from forecasting.model import CountDistribution


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Offer timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def decimal_odds(american: float) -> float:
    if not math.isfinite(american) or abs(american) < 100:
        raise ValueError("American odds must be <= -100 or >= +100")
    return 1 + (american / 100 if american > 0 else 100 / abs(american))


@dataclass(frozen=True)
class Offer:
    event_id: str
    player_id: str
    stat: str
    side: str
    line: float
    decimal_odds: float
    book: str
    captured_at: datetime
    starts_at: datetime


def evaluate_offer(distribution: CountDistribution, offer: Offer, *, event_id: str,
                   player_id: str, stat: str, as_of: datetime, eligible: bool,
                   betting_validated: bool = False, max_age_seconds: int = 900,
                   minimum_ev: float = 0.03) -> dict:
    if not all((offer.event_id, offer.player_id, offer.book)):
        raise ValueError("An offer needs event/player/book identity")
    if (offer.event_id, str(offer.player_id), offer.stat) != (event_id, str(player_id), stat):
        raise ValueError("Offer does not match the forecast event/player/stat")
    if offer.side not in ("OVER", "UNDER"):
        raise ValueError("Offer side must be OVER or UNDER")
    if not math.isfinite(offer.decimal_odds) or offer.decimal_odds <= 1:
        raise ValueError("Decimal odds must be finite and greater than one")
    now, captured, start = utc(as_of), utc(offer.captured_at), utc(offer.starts_at)
    if captured > now or now >= start or captured >= start:
        raise ValueError("Require an observed pregame quote for a future event")
    if (now - captured).total_seconds() > max_age_seconds:
        raise ValueError("Offer is stale")
    p = distribution.probabilities(offer.line)
    win = p[offer.side.lower()]
    loss = p["under" if offer.side == "OVER" else "over"]
    ev = win * (offer.decimal_odds - 1) - loss
    reasons = []
    if not eligible:
        reasons.append("Player availability/role is not confirmed")
    if not betting_validated:
        reasons.append("Model has not passed priced betting validation")
    if ev < minimum_ev:
        reasons.append("Estimated return does not clear the prespecified threshold")
    return {"event_id": offer.event_id, "player_id": str(offer.player_id), "stat": stat,
            "side": offer.side, "line": offer.line, "book": offer.book,
            "decimal_odds": offer.decimal_odds, "prob_win": win,
            "prob_loss": loss, "prob_push": p["push"],
            "expected_profit_per_unit_risked": ev, "recommend": not reasons,
            "reasons": reasons, "quote_at": captured.isoformat(), "as_of": now.isoformat()}
