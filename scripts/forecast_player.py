"""Offline forecast with an explicit future event and optional exact-price offers.

Request JSON uses player_id, event_id, starts_at, team, home and optional
availability/offers. Timestamps must include timezones. Logs are parquet or CSV.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from forecasting.model import DEFAULT_PATH, ForecastModel
from forecasting.offers import Offer
from forecasting.service import forecast_player


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    logs = pd.read_parquet(args.logs) if args.logs.suffix == ".parquet" else pd.read_csv(args.logs)
    request = json.loads(args.request.read_text(encoding="utf-8"))
    player_column = next((c for c in logs.columns if c.upper() == "PLAYER_ID"), None)
    if player_column:
        logs = logs[logs[player_column].astype(str) == str(request["player_id"])]
    for quote in request.get("offers", []):
        for key in ("captured_at", "starts_at"):
            quote[key] = datetime.fromisoformat(quote[key])
    offers = [Offer(**quote) for quote in request.pop("offers", [])]
    request["starts_at"] = datetime.fromisoformat(request["starts_at"])
    if "as_of" in request:
        request["as_of"] = datetime.fromisoformat(request["as_of"])
    result = forecast_player(logs, model=ForecastModel.load(args.model), offers=offers, **request)
    content = json.dumps(result, indent=2, allow_nan=False)
    if args.out:
        args.out.write_text(content, encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    main()
