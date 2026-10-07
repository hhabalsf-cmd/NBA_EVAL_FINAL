"""Forecast service shared by the API and offline CLI; no fitting on requests."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from forecasting.features import normalize_logs, serve_features
from forecasting.model import DEFAULT_PATH, ForecastModel
from forecasting.offers import Offer, evaluate_offer, utc


@lru_cache(maxsize=2)
def _load_artifact(path: str, model_mtime: int, manifest_mtime: int):
    return ForecastModel.load(path)


def load_model():
    path = Path(os.environ.get("NBA_EVAL_FORECAST_MODEL_PATH", str(DEFAULT_PATH))).resolve()
    return _load_artifact(str(path), path.stat().st_mtime_ns, path.with_suffix(".json").stat().st_mtime_ns)


def forecast_player(logs: pd.DataFrame, *, model: ForecastModel, player_id: str,
                    event_id: str, starts_at: datetime, team: str, home: bool,
                    as_of: datetime | None = None, offers: list[Offer] | None = None,
                    availability: str = "unknown") -> dict:
    now = utc(as_of or datetime.now(timezone.utc))
    start = utc(starts_at)
    if start <= now:
        raise ValueError("Only future, pregame forecasts are supported")
    if not event_id.strip() or not team.strip():
        raise ValueError("Event identity and current team are required")
    if availability not in ("available", "questionable", "out", "unknown"):
        raise ValueError("Unsupported availability status")
    if availability == "out":
        raise ValueError("Player is out; abstain instead of forecasting an active-player prop")
    game_date = start.astimezone(ZoneInfo("America/New_York")).date()
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    if pd.Timestamp(model.metadata['calibrated_through']).date() >= today:
        raise ValueError('Model calibration includes the forecast as-of date or future outcomes')
    history = normalize_logs(logs, player_id)
    if set(history.PLAYER_ID) != {str(player_id)}:
        raise ValueError("History does not match the requested player")
    # Conservatively exclude all current-day logs: provider rows may be in progress.
    history = history[history.GAME_DATE < pd.Timestamp(today)]
    features = serve_features(history, game_date, team, home, player_id)
    distributions = model.distributions(features, game_date)
    evaluations = []
    for offer in offers or []:
        if offer.stat not in distributions:
            raise ValueError("Unsupported offer stat")
        if utc(offer.starts_at) != start:
            raise ValueError("Offer start time differs from the forecast event")
        evaluations.append(evaluate_offer(distributions[offer.stat], offer,
                           event_id=event_id, player_id=player_id, stat=offer.stat,
                           as_of=now, eligible=availability == "available",
                           betting_validated=False))
    notes = ["Forecasts are conditional on the player participating.",
             "Event, team, and availability context is caller supplied.",
             "No priced betting edge has been validated; outputs are research forecasts."]
    if availability != "available":
        notes.append("Availability is unresolved; do not treat the distribution as an unconditional outcome forecast.")
    if features["long_absence"] or features["team_changed"]:
        notes.append("Long absence or team change: recent role may not represent the upcoming game.")
    return {"model_type": "forecast_v1", "player_id": str(player_id), "event_id": event_id,
            "game_date": str(game_date), "as_of": now.isoformat(),
            "history_through": str(history.GAME_DATE.max().date()),
            "history_games": int(features["history_games"]),
            "baselines": {stat: {"last_10": features[f"{stat}_l10"],
                                  "last_20": features[f"{stat}_l20"]} for stat in distributions},
            "model": model.metadata,
            "predictions": {stat: dist.summary() for stat, dist in distributions.items()},
            "offers": evaluations, "notes": notes}
