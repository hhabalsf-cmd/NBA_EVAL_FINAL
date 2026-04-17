"""
Compute team season stats, standings, and top scorers from Supabase game logs.

Replaces GOAT-tier BDL endpoints (team_season_averages, standings, season_averages)
with aggregations derived from player_game_logs and /v1/games (FREE tier).

All functions write results to Supabase for caching and return the computed data
in the same shape the old BDL callers expect.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Conference membership — changes extremely rarely (only on expansion/relocation)
EAST_TEAMS = frozenset({
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND",
    "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS",
})
WEST_TEAMS = frozenset({
    "DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN",
    "NOP", "OKC", "PHX", "POR", "SAC", "SAS", "UTA",
})


def _safe_float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 1. Team season stats (replaces /v1/team_season_averages)
# ---------------------------------------------------------------------------

def compute_team_season_stats(season: str) -> dict[str, dict]:
    """Compute team-level season averages from player_game_logs in Supabase.

    Aggregates per-game player stats into per-team-per-game totals, joins with
    game results to derive opponent points, then averages across all games.

    Returns dict keyed by team abbreviation with the same shape consumed by
    ``nba_evaluator.get_team_defensive_stats()`` and ``game_predictor._fetch_team_stats()``.
    """
    import db as _db

    try:
        with _db.borrow_conn() as conn:
            with conn.cursor() as cur:
                # Aggregate player stats per team per game
                cur.execute("""
                    SELECT
                        UPPER(LEFT(matchup, 3))  AS team_abbrev,
                        game_id,
                        game_date,
                        wl,
                        SUM(pts)   AS pts,   SUM(reb)  AS reb,  SUM(ast) AS ast,
                        SUM(oreb)  AS oreb,  SUM(dreb) AS dreb,
                        SUM(fgm)   AS fgm,   SUM(fga)  AS fga,
                        SUM(fg3m)  AS fg3m,  SUM(fg3a) AS fg3a,
                        SUM(ftm)   AS ftm,   SUM(fta)  AS fta,
                        SUM(stl)   AS stl,   SUM(blk)  AS blk,
                        SUM(tov)   AS tov,   SUM(min)  AS min,
                        COUNT(*)   AS player_count
                    FROM player_game_logs
                    WHERE season = %s AND pts IS NOT NULL
                    GROUP BY game_id, UPPER(LEFT(matchup, 3)), game_date, wl
                    HAVING COUNT(*) >= 5
                """, (season,))
                rows = cur.fetchall()

        if not rows:
            logger.warning("compute_team_season_stats: no game log data for season %s", season)
            return {}

        # Group rows by game_id to pair opponents
        games_by_id: dict[int, list[dict]] = {}
        for r in rows:
            gid = r["game_id"]
            if gid not in games_by_id:
                games_by_id[gid] = []
            games_by_id[gid].append(dict(r))

        # Accumulate per-team totals
        team_totals: dict[str, dict] = {}

        for gid, sides in games_by_id.items():
            if len(sides) != 2:
                continue  # skip incomplete games

            for i in range(2):
                team = sides[i]
                opp = sides[1 - i]
                abbrev = team["team_abbrev"]

                if abbrev not in team_totals:
                    team_totals[abbrev] = {
                        "games": 0, "wins": 0, "losses": 0,
                        "pts": 0, "reb": 0, "ast": 0,
                        "oreb": 0, "dreb": 0,
                        "fgm": 0, "fga": 0, "fg3m": 0, "fg3a": 0,
                        "ftm": 0, "fta": 0,
                        "stl": 0, "blk": 0, "tov": 0, "min": 0,
                        "opp_pts": 0, "opp_fgm": 0, "opp_fga": 0,
                        "opp_fg3m": 0, "opp_fg3a": 0,
                        "opp_ftm": 0, "opp_fta": 0,
                        "opp_oreb": 0, "opp_dreb": 0, "opp_tov": 0,
                    }

                t = team_totals[abbrev]
                t["games"] += 1
                if str(team.get("wl", "")).upper() == "W":
                    t["wins"] += 1
                else:
                    t["losses"] += 1

                for col in ("pts", "reb", "ast", "oreb", "dreb", "fgm", "fga",
                            "fg3m", "fg3a", "ftm", "fta", "stl", "blk", "tov", "min"):
                    t[col] += _safe_float(team.get(col), 0)

                t["opp_pts"] += _safe_float(opp.get("pts"), 0)
                t["opp_fgm"] += _safe_float(opp.get("fgm"), 0)
                t["opp_fga"] += _safe_float(opp.get("fga"), 0)
                t["opp_fg3m"] += _safe_float(opp.get("fg3m"), 0)
                t["opp_fg3a"] += _safe_float(opp.get("fg3a"), 0)
                t["opp_ftm"] += _safe_float(opp.get("ftm"), 0)
                t["opp_fta"] += _safe_float(opp.get("fta"), 0)
                t["opp_oreb"] += _safe_float(opp.get("oreb"), 0)
                t["opp_dreb"] += _safe_float(opp.get("dreb"), 0)
                t["opp_tov"] += _safe_float(opp.get("tov"), 0)

        # Compute per-game averages and advanced metrics
        result: dict[str, dict] = {}
        for abbrev, t in team_totals.items():
            gp = max(t["games"], 1)

            pts_pg = t["pts"] / gp
            opp_pts_pg = t["opp_pts"] / gp
            fga_pg = t["fga"] / gp
            fta_pg = t["fta"] / gp
            oreb_pg = t["oreb"] / gp
            tov_pg = t["tov"] / gp
            fgm_pg = t["fgm"] / gp
            fg3m_pg = t["fg3m"] / gp

            # Possessions estimate (team-level)
            poss = t["fga"] + 0.44 * t["fta"] - t["oreb"] + t["tov"]
            opp_poss = t["opp_fga"] + 0.44 * t["opp_fta"] - t["opp_oreb"] + t["opp_tov"]
            avg_poss = (poss + opp_poss) / 2 if (poss + opp_poss) > 0 else gp * 100
            pace = (avg_poss / gp) * (48 * 60 / max(t["min"] / gp, 240)) if t["min"] > 0 else 100

            off_rating = (t["pts"] / max(poss, 1)) * 100
            def_rating = (t["opp_pts"] / max(opp_poss, 1)) * 100
            net_rating = off_rating - def_rating

            efg_pct = (fgm_pg + 0.5 * fg3m_pg) / max(fga_pg, 1)
            ts_pct = pts_pg / (2 * (fga_pg + 0.44 * fta_pg)) if (fga_pg + 0.44 * fta_pg) > 0 else 0.56

            oreb_rate = t["oreb"] / max(t["oreb"] + t["opp_dreb"], 1)
            dreb_rate = t["dreb"] / max(t["dreb"] + t["opp_oreb"], 1)

            ast_pg = t["ast"] / gp
            ast_pct = ast_pg / max(fgm_pg, 1) if fgm_pg > 0 else 0.60
            tov_pct = tov_pg / max(fga_pg + 0.44 * fta_pg + tov_pg, 1) * 100

            result[abbrev] = {
                "def_rating": round(def_rating, 1),
                "pace": round(pace, 1),
                "opp_pts": round(opp_pts_pg, 1),
                "pts_rank": 15,  # will be ranked below
                "opp_ast": round(t["opp_pts"] / gp * 0.22, 1),  # estimate opp assists
                "off_rating": round(off_rating, 1),
                "net_rating": round(net_rating, 1),
                "efg_pct": round(efg_pct, 3),
                "ts_pct": round(ts_pct, 3),
                "ast_pct": round(ast_pct, 2),
                "tov_pct": round(tov_pct, 1),
                "oreb_pct": round(oreb_rate, 3),
                "dreb_pct": round(dreb_rate, 3),
                # Base stats for game_predictor enrichment
                "w": t["wins"],
                "l": t["losses"],
                "pts": round(pts_pg, 1),
                "reb": round(t["reb"] / gp, 1),
                "ast": round(ast_pg, 1),
                "stl": round(t["stl"] / gp, 1),
                "blk": round(t["blk"] / gp, 1),
                "tov": round(tov_pg, 1),
                "fg_pct": round(t["fgm"] / max(t["fga"], 1), 3),
                "fg3_pct": round(t["fg3m"] / max(t["fg3a"], 1), 3),
                "ft_pct": round(t["ftm"] / max(t["fta"], 1), 3),
            }

        # Rank teams by defensive rating (lower = better defense → lower rank number)
        sorted_by_def = sorted(result.keys(), key=lambda a: result[a]["def_rating"])
        for rank, abbrev in enumerate(sorted_by_def, 1):
            result[abbrev]["pts_rank"] = rank

        # Persist to Supabase for caching
        _db.upsert_team_stats_to_supabase(result, season)
        logger.info("compute_team_season_stats: computed stats for %d teams (season %s)", len(result), season)
        return result

    except Exception:
        logger.exception("compute_team_season_stats failed for season %s", season)
        return {}


# ---------------------------------------------------------------------------
# 2. Standings (replaces /v1/standings)
# ---------------------------------------------------------------------------

def compute_standings(season: str) -> dict[str, dict]:
    """Derive standings from game results via BDL /v1/games (FREE tier).

    Fetches all finished games for the season, tallies wins/losses per team,
    computes win_pct, and derives conference rank.

    Returns dict keyed by team abbreviation.
    """
    import db as _db

    # Check Supabase cache first (24h TTL)
    cached = _get_standings_from_supabase(season)
    if cached:
        return cached

    try:
        from bdl_client import get_bdl_client
        bdl = get_bdl_client()
        season_int = int(season.split("-")[0])

        raw_games = bdl.get_games(seasons=[season_int])
        if not raw_games:
            logger.warning("compute_standings: no games found for season %s", season)
            return {}

        # Tally wins/losses from final games
        team_records: dict[str, dict] = {}
        team_recent: dict[str, list[str]] = {}  # track W/L sequence for streak

        # Sort games by date for streak calculation
        final_games = [
            g for g in raw_games
            if str(g.get("status", "")).lower() == "final"
        ]
        final_games.sort(key=lambda g: g.get("date", ""))

        for g in final_games:
            home = (g.get("home_team") or {}).get("abbreviation", "")
            away = (g.get("visitor_team") or {}).get("abbreviation", "")
            home_score = int(g.get("home_team_score") or 0)
            away_score = int(g.get("visitor_team_score") or 0)

            if not home or not away or (home_score == 0 and away_score == 0):
                continue

            for abbrev in (home, away):
                if abbrev not in team_records:
                    team_records[abbrev] = {"wins": 0, "losses": 0}
                    team_recent[abbrev] = []

            if home_score > away_score:
                team_records[home]["wins"] += 1
                team_records[away]["losses"] += 1
                team_recent[home].append("W")
                team_recent[away].append("L")
            else:
                team_records[away]["wins"] += 1
                team_records[home]["losses"] += 1
                team_recent[away].append("W")
                team_recent[home].append("L")

        # Build standings dict
        result: dict[str, dict] = {}
        for abbrev, rec in team_records.items():
            wins = rec["wins"]
            losses = rec["losses"]
            total = wins + losses
            win_pct = wins / max(total, 1)

            # Compute current streak from most recent games
            recent = team_recent.get(abbrev, [])
            streak = 0
            if recent:
                last_result = recent[-1]
                for r in reversed(recent):
                    if r == last_result:
                        streak += 1
                    else:
                        break
                if last_result == "L":
                    streak = -streak

            conference = "East" if abbrev in EAST_TEAMS else "West" if abbrev in WEST_TEAMS else "Unknown"

            result[abbrev] = {
                "wins": wins,
                "losses": losses,
                "win_pct": round(win_pct, 3),
                "streak": streak,
                "conference": conference,
                "conf_rank": 15,  # ranked below
            }

        # Rank within each conference
        for conf_teams in (EAST_TEAMS, WEST_TEAMS):
            conf_abbrevs = [a for a in result if a in conf_teams]
            conf_abbrevs.sort(key=lambda a: result[a]["win_pct"], reverse=True)
            for rank, abbrev in enumerate(conf_abbrevs, 1):
                result[abbrev]["conf_rank"] = rank

        _upsert_standings_to_supabase(result, season)
        logger.info("compute_standings: computed for %d teams (season %s)", len(result), season)
        return result

    except Exception:
        logger.exception("compute_standings failed for season %s", season)
        return {}


def _get_standings_from_supabase(season: str) -> dict[str, dict] | None:
    """Load cached standings from Supabase if fresh (< 24h)."""
    import db as _db
    from datetime import datetime, timezone

    try:
        with _db.borrow_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM team_standings WHERE season = %s",
                    (season,),
                )
                rows = cur.fetchall()

        if not rows:
            return None

        fetched_at = rows[0].get("fetched_at")
        if fetched_at is not None:
            if fetched_at.tzinfo is not None:
                age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
            else:
                age_hours = (datetime.now() - fetched_at).total_seconds() / 3600
            if age_hours > 24:
                return None

        return {
            row["team_abbrev"]: {
                "wins": row["wins"],
                "losses": row["losses"],
                "win_pct": float(row["win_pct"]) if row["win_pct"] is not None else 0.0,
                "streak": row["streak"] or 0,
                "conference": row["conference"] or "Unknown",
                "conf_rank": row["conference_rank"] or 15,
            }
            for row in rows
        }
    except Exception:
        logger.exception("_get_standings_from_supabase failed")
        return None


def _upsert_standings_to_supabase(standings: dict[str, dict], season: str) -> None:
    """Persist computed standings to Supabase."""
    import db as _db

    if not standings:
        return

    rows = [
        (abbrev, season, s["wins"], s["losses"], s["conference"],
         s["conf_rank"], s["win_pct"], s["streak"])
        for abbrev, s in standings.items()
    ]

    sql = """
        INSERT INTO team_standings
            (team_abbrev, season, wins, losses, conference,
             conference_rank, win_pct, streak, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_abbrev, season) DO UPDATE SET
            wins = EXCLUDED.wins,
            losses = EXCLUDED.losses,
            conference = EXCLUDED.conference,
            conference_rank = EXCLUDED.conference_rank,
            win_pct = EXCLUDED.win_pct,
            streak = EXCLUDED.streak,
            fetched_at = NOW()
    """

    try:
        with _db.borrow_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
    except Exception:
        logger.exception("_upsert_standings_to_supabase failed")


# ---------------------------------------------------------------------------
# 3. Top scorers per team (replaces /v1/season_averages)
# ---------------------------------------------------------------------------

def compute_top_scorers(season: str) -> dict[str, list[dict]]:
    """Compute top 2 scorers per team from player_game_logs in Supabase.

    Pure SQL — zero BDL API calls.

    Returns dict keyed by team abbreviation:
        ``{'LAL': [{'name': 'LeBron James', 'pts': 25.2, 'player_id': 123}, ...]}``
    """
    import db as _db

    try:
        with _db.borrow_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        UPPER(LEFT(matchup, 3)) AS team_abbrev,
                        player_id,
                        MAX(player_name)        AS player_name,
                        AVG(pts)                AS avg_pts,
                        COUNT(*)                AS games_played
                    FROM player_game_logs
                    WHERE season = %s AND pts IS NOT NULL AND min >= 10
                    GROUP BY UPPER(LEFT(matchup, 3)), player_id
                    HAVING COUNT(*) >= 5
                    ORDER BY UPPER(LEFT(matchup, 3)), AVG(pts) DESC
                """, (season,))
                rows = cur.fetchall()

        # Group by team, take top 2
        team_players: dict[str, list[dict]] = {}
        for r in rows:
            abbrev = r["team_abbrev"]
            if abbrev not in team_players:
                team_players[abbrev] = []
            if len(team_players[abbrev]) < 2:
                team_players[abbrev].append({
                    "name": r["player_name"] or "Unknown",
                    "pts": round(float(r["avg_pts"]), 1),
                    "player_id": r["player_id"],
                })

        logger.info("compute_top_scorers: found scorers for %d teams (season %s)", len(team_players), season)
        return team_players

    except Exception:
        logger.exception("compute_top_scorers failed for season %s", season)
        return {}
