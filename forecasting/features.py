"""One causal feature function shared by historical replay and live forecasts."""
from __future__ import annotations

from collections import deque
import numpy as np
import pandas as pd

STATS = ("PTS", "REB", "AST", "PRA")
MIN_HISTORY = 10
WINDOW = 60
BASE_FEATURES = ("home", "rest_days", "long_absence", "team_changed",
                 "team_games", "season_games", "history_games")
SUMMARY_KINDS = ("l5", "l10", "l20", "mean", "median", "ewma5", "std")
FEATURES = BASE_FEATURES + tuple(
    f"{stat}_{kind}" for stat in ("MIN",) + STATS for kind in SUMMARY_KINDS
) + tuple(f"{stat}_rate{n}" for stat in STATS for n in (5, 20))


def season_start(date) -> int:
    value = pd.Timestamp(date)
    return value.year if value.month >= 10 else value.year - 1


def minutes(value) -> float:
    if isinstance(value, str) and ":" in value:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Minutes must be a number or MM:SS")
        return float(parts[0]) + float(parts[1]) / 60
    return float(value)


def normalize_logs(frame: pd.DataFrame, player_id=None) -> pd.DataFrame:
    """Validate completed box scores; never synthesize missing outcome fields."""
    df = frame.copy()
    df.columns = [str(c).upper() for c in df.columns]
    aliases = {"MIN_NUMERIC": "MIN", "MINUTES_PLAYED": "MIN", "MINUTES": "MIN",
               "REBOUNDER": "REB", "ASSISTER": "AST", "TEAM_ABBREVIATION": "TEAM"}
    for source, dest in aliases.items():
        if source in df and dest not in df:
            df[dest] = df[source]
    if "PLAYER_ID" not in df and player_id is not None:
        df["PLAYER_ID"] = str(player_id)
    required = {"PLAYER_ID", "GAME_DATE", "MIN", "PTS", "REB", "AST"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing game-log fields: {sorted(missing)}")
    for flag in ("IS_UPCOMING", "IS_UPCOMING_GAME"):
        if flag in df:
            df = df[df[flag].fillna(0) == 0].copy()
    df["GAME_DATE"] = pd.to_datetime(df.GAME_DATE, errors="raise").dt.normalize()
    if df.GAME_DATE.isna().any() or df.PLAYER_ID.isna().any():
        raise ValueError("Game date and player ID must be present")
    df["PLAYER_ID"] = df.PLAYER_ID.astype(str)
    df["MIN"] = df.MIN.map(minutes)
    for stat in STATS[:3]:
        df[stat] = pd.to_numeric(df[stat], errors="raise")
    numeric = df[["MIN", "PTS", "REB", "AST"]].to_numpy(float)
    if not np.isfinite(numeric).all() or (numeric < 0).any():
        raise ValueError("Box-score counts and minutes must be finite and nonnegative")
    if not np.equal(numeric[:, 1:], np.floor(numeric[:, 1:])).all():
        raise ValueError("Box-score outcomes must be integer counts")
    df = df[df.MIN > 0].copy()  # Conditional on participation; DNPs are not zero scores.
    if "TEAM" not in df:
        df["TEAM"] = df.MATCHUP.str.split().str[0] if "MATCHUP" in df else ""
    df["TEAM"] = df.TEAM.fillna("").astype(str)
    if "HOME" not in df:
        df["HOME"] = df.MATCHUP.str.contains("vs.", regex=False).astype(int) if "MATCHUP" in df else 0
    df["HOME"] = pd.to_numeric(df.HOME, errors="raise")
    if not df.HOME.isin([0, 1]).all():
        raise ValueError("HOME must be 0 or 1")
    if df.duplicated(["PLAYER_ID", "GAME_DATE"]).any():
        raise ValueError("Ambiguous duplicate player/date rows; reconcile before forecasting")
    df["PRA"] = df.PTS + df.REB + df.AST
    df["SEASON_START"] = df.GAME_DATE.map(season_start)
    return df.sort_values(["GAME_DATE", "PLAYER_ID"], kind="stable").reset_index(drop=True)


def history_features(history: list[dict], game_date, team: str, home: bool) -> dict:
    """All summaries stop strictly before the target calendar date."""
    date = pd.Timestamp(game_date).normalize()
    prior = [row for row in history if row["GAME_DATE"] < date][-WINDOW:]
    if len(prior) < MIN_HISTORY:
        raise ValueError(f"Need {MIN_HISTORY} prior appearances; have {len(prior)}")
    rest = (date - prior[-1]["GAME_DATE"]).days
    target_season = season_start(date)
    team_games = 0
    for row in reversed(prior):
        if row["TEAM"] != team:
            break
        team_games += 1
    out = {"home": float(home), "rest_days": float(min(rest, 14)),
           "long_absence": float(rest > 14),
           "team_changed": float(bool(team) and prior[-1]["TEAM"] != team),
           "team_games": float(team_games),
           "season_games": float(sum(row["SEASON_START"] == target_season for row in prior)),
           "history_games": float(len(prior))}
    mins = np.array([row["MIN"] for row in prior], dtype=float)
    for stat in ("MIN",) + STATS:
        values = np.array([row[stat] for row in prior], dtype=float)
        weights = (2 / 3) ** np.arange(len(values) - 1, -1, -1)
        values_by_kind = [values[-5:].mean(), values[-10:].mean(), values[-20:].mean(),
                          values.mean(), np.median(values), np.average(values, weights=weights),
                          values[-20:].std(ddof=1)]
        out.update({f"{stat}_{k}": float(v) for k, v in zip(SUMMARY_KINDS, values_by_kind)})
        weights10 = (9 / 11) ** np.arange(len(values) - 1, -1, -1)
        out[f"{stat}_ewma10"] = float(np.average(values, weights=weights10))
        if stat != "MIN":
            for n in (5, 20):
                out[f"{stat}_rate{n}"] = float(values[-n:].sum() / mins[-n:].sum())
    return out


def serve_features(logs: pd.DataFrame, game_date, team: str, home: bool, player_id=None) -> dict:
    data = normalize_logs(logs, player_id)
    if data.PLAYER_ID.nunique() != 1:
        raise ValueError("Serving requires exactly one player's history")
    return history_features(data.to_dict("records"), game_date, team, home)


def build_panel(logs: pd.DataFrame) -> pd.DataFrame:
    """Emit before updating history: training and serving use identical inputs."""
    data = normalize_logs(logs)
    records = []
    for player, group in data.groupby("PLAYER_ID", sort=False):
        history = deque(maxlen=WINDOW)
        for row in group.to_dict("records"):
            if len(history) >= MIN_HISTORY:
                item = history_features(list(history), row["GAME_DATE"], row["TEAM"], row["HOME"])
                item.update({"player_id": player, "game_date": row["GAME_DATE"],
                             "season": row["SEASON_START"], "game_id": str(row.get("GAME_ID", "")),
                             "team": row["TEAM"]})
                item.update({f"{stat}_actual": float(row[stat]) for stat in ("MIN",) + STATS})
                records.append(item)
            history.append(row)
    if not records:
        raise ValueError("No player has enough historical appearances")
    return pd.DataFrame(records).sort_values(["game_date", "player_id"]).reset_index(drop=True)
