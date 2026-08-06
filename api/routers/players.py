"""Player search and prediction endpoints."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Optional

from ..limiter import limiter
from ..routers.auth import get_current_user

logger = logging.getLogger(__name__)

import pandas as pd

import statistics as _statistics
from ..schemas.prediction import (
    PlayerSearchResult,
    PlayerInfo,
    PredictionRequest,
    PredictionResponse,
    LineEvaluationRequest,
    LineEvaluation,
    GameInfo,
    OpponentContext,
    VsStats,
    FullGameLogEntry,
    StatSplits,
    StatAnalysis,
    RollingAverages,
    PlayerResearchResponse,
    PlayerScenario,
    ScenariosResponse,
)
from ..services.prediction_service import PredictionService
from bdl_id_mapper import get_team_mapper, get_player_mapper
from bdl_client import get_bdl_client

router = APIRouter(prefix="/api/players", tags=["players"])

# Singleton service instance
_prediction_service: Optional[PredictionService] = None


def get_prediction_service() -> PredictionService:
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = PredictionService()
    return _prediction_service


# Scenarios cache: player_id → (timestamp, ScenariosResponse). 1-hour TTL, max 50 entries.
_scenarios_cache: dict = {}
_SCENARIOS_CACHE_MAX = 50


@router.get("/search", response_model=PlayerSearchResult)
@limiter.limit("60/minute")
async def search_players(request: Request, q: str = Query(..., min_length=2, description="Search query")):
    """Search for players by name."""
    service = get_prediction_service()
    players = service.search_players(q)

    return PlayerSearchResult(
        players=[
            PlayerInfo(
                player_id=p['id'],
                player_name=p['full_name'],
                team_id=p.get('team_id'),
                team_abbrev=p.get('team_abbreviation'),
                team_name=p.get('team_name'),
                headshot_url=p.get('headshot_url'),
            )
            for p in players
        ]
    )


@router.post("/predict")
@limiter.limit("10/minute")
async def predict_player_stats(request: Request, body: PredictionRequest, current_user: dict = Depends(get_current_user)):
    """
    Get ML predictions for a player's stats.
    Returns Server-Sent Events for progress updates.
    """
    service = get_prediction_service()

    async def event_generator():
        async for event in service.predict_with_progress(
            player_name=body.player_name,
            model_type=body.model_type,
            use_ensemble=body.use_ensemble,
            retrain=body.retrain
        ):
            if await request.is_disconnected():
                logger.info("Client disconnected during player prediction for %s", body.player_name)
                return
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/predict/sync", response_model=PredictionResponse)
@limiter.limit("10/minute")
async def predict_player_stats_sync(request: Request, body: PredictionRequest, current_user: dict = Depends(get_current_user)):
    """
    Get ML predictions for a player's stats (non-streaming).
    Useful for programmatic access.
    """
    service = get_prediction_service()

    result = None
    error = None

    async for event in service.predict_with_progress(
        player_name=body.player_name,
        model_type=body.model_type,
        use_ensemble=body.use_ensemble,
        retrain=body.retrain
    ):
        if event['stage'] == 'complete':
            result = event['data']
        elif event['stage'] == 'error':
            error = event['message']

    if error:
        raise HTTPException(status_code=404, detail=error)

    if not result:
        raise HTTPException(status_code=500, detail="Prediction failed")

    return PredictionResponse(**result)


@router.get("/{player_name}/team-injuries")
@limiter.limit("30/minute")
async def get_team_injuries(request: Request, player_name: str, current_user: dict = Depends(get_current_user)):
    """Get injury report for a player's team and their next opponent (30-min cached)."""
    service = get_prediction_service()

    player_info = service.get_player_info(player_name)
    if not player_info:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")

    team_abbrev = player_info.get('team_abbrev', '')
    game_info = service.scraper.get_player_next_game(player_info)
    opponent = game_info.get('opponent', '') if game_info else ''

    injuries = service.get_injuries()

    def extract_team(abbrev: str):
        if not abbrev:
            return None
        team_data = injuries.get(abbrev, {})
        players = team_data.get('players', [])
        return {
            "abbrev": abbrev,
            "out": [p for p in players if p.get('status') == 'out'],
            "questionable": [p for p in players if p.get('status') == 'questionable'],
        }

    return {
        "team": extract_team(team_abbrev),
        "opponent": extract_team(opponent) if opponent else None,
    }


@router.get("/{player_name}/odds")
@limiter.limit("30/minute")
async def get_player_odds(request: Request, player_name: str, current_user: dict = Depends(get_current_user)):
    """Get today's consensus prop lines for a player (30-min cached)."""
    service = get_prediction_service()
    result = service.get_player_odds(player_name)
    return result


@router.get("/{player_name}/research", response_model=PlayerResearchResponse)
@limiter.limit("20/minute")
async def get_player_research(request: Request, player_name: str, current_user: dict = Depends(get_current_user)):
    """
    Get comprehensive research stats for a player.
    Returns game log, rolling averages, home/away/B2B/defense splits, and matchup context.
    No ML prediction is run — pure raw data for manual analysis.
    """
    service = get_prediction_service()

    # --- Player info ---
    player_info = service.get_player_info(player_name)
    if not player_info:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")

    player_id = player_info.get('id') or player_info.get('player_id')
    team_abbrev = player_info.get('team_abbrev', '') or player_info.get('team_abbreviation', '')

    # --- Game log ---
    try:
        raw_df = service.scraper.get_player_game_log(player_id)
    except Exception as e:
        logger.error("Failed to fetch game log for player %s: %s", player_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch player game log. Please try again.")

    if raw_df is None or raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No game log found for '{player_name}'")

    # Ensure sorted ascending by actual date (must parse to datetime — string sort of
    # NBA API's "DEC 25, 2024" format gives wrong chronological order because month
    # abbreviations sort alphabetically: APR < DEC < FEB < JAN < ... < NOV < OCT).
    # get_player_game_log() already sorts correctly, but re-sort defensively here.
    if 'GAME_DATE' in raw_df.columns:
        raw_df = raw_df.copy()
        raw_df['_sort_dt'] = pd.to_datetime(raw_df['GAME_DATE'], format='mixed')
        raw_df = raw_df.sort_values('_sort_dt', ascending=True).drop(columns=['_sort_dt']).reset_index(drop=True)
    df = raw_df.tail(40).copy()

    # Helper to safely get float from row
    def _f(row, col, default=0.0):
        v = row.get(col, default)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)

    # Build home/away flag from MATCHUP col (e.g. "LAL vs. DEN" = home, "LAL @ DEN" = away)
    def _is_home(matchup: str) -> bool:
        return 'vs.' in matchup if matchup else True

    # Detect B2B: sort by date and check 1-day gap
    dates = []
    for _, row in df.iterrows():
        gd = row.get('GAME_DATE', '')
        try:
            dates.append(pd.to_datetime(gd))
        except Exception:
            dates.append(None)
    df = df.copy()
    df['_parsed_date'] = dates
    df['_b2b'] = False
    prev_date = None
    for idx in df.index:
        cur_date = df.at[idx, '_parsed_date']
        if cur_date is not None and prev_date is not None:
            delta = (cur_date - prev_date).days
            if delta == 1:
                df.at[idx, '_b2b'] = True
        if cur_date is not None:
            prev_date = cur_date

    # --- Team defensive stats for elite/weak classification ---
    try:
        team_stats = service.get_team_stats()
    except Exception:
        team_stats = {}

    # Sort teams by DEF_RATING (lower = better defense)
    if team_stats:
        sorted_teams = sorted(team_stats.items(), key=lambda x: x[1].get('def_rating', 999))
        elite_teams = {t for t, _ in sorted_teams[:10]}
        weak_teams = {t for t, _ in sorted_teams[-10:]}
    else:
        elite_teams, weak_teams = set(), set()

    # Extract opponent abbreviation from MATCHUP (e.g. "LAL vs. DEN" or "LAL @ DEN" → "DEN")
    def _opp_abbrev(matchup: str) -> str:
        if not matchup:
            return ''
        parts = matchup.replace('vs.', '@').split('@')
        if len(parts) >= 2:
            return parts[-1].strip().upper()
        return ''

    # --- Build full game log entries (last 20 for display) ---
    game_log_entries = []
    for _, row in df.tail(20).iterrows():
        matchup = str(row.get('MATCHUP', ''))
        gd_raw = row.get('GAME_DATE', '')
        try:
            gd_dt = pd.to_datetime(gd_raw)
            gd_str = gd_dt.strftime('%b %-d')
        except Exception:
            gd_str = str(gd_raw)

        pts = _f(row, 'PTS')
        reb = _f(row, 'REB')
        ast = _f(row, 'AST')
        opp_raw = _opp_abbrev(matchup)
        is_home = _is_home(matchup)
        opp_display = f"vs {opp_raw}" if is_home else f"@ {opp_raw}"
        wl = str(row.get('WL', '')).strip().upper()

        game_log_entries.append(FullGameLogEntry(
            game_date=gd_str,
            opponent=opp_display,
            is_home=is_home,
            min=_f(row, 'MIN'),
            pts=pts,
            reb=reb,
            ast=ast,
            pra=round(pts + reb + ast, 1),
            pr=round(pts + reb, 1),
            pa=round(pts + ast, 1),
            fg_pct=round(_f(row, 'FG_PCT') * 100, 1),
            fg3_pct=round(_f(row, 'FG3_PCT') * 100, 1),
            ft_pct=round(_f(row, 'FT_PCT') * 100, 1),
            fg3m=_f(row, 'FG3M'),
            stl=_f(row, 'STL'),
            blk=_f(row, 'BLK'),
            tov=_f(row, 'TOV'),
            plus_minus=_f(row, 'PLUS_MINUS'),
            result=wl if wl in ('W', 'L') else None,
        ))
    game_log_entries = list(reversed(game_log_entries))  # most recent first

    # --- Helper: compute StatSplits from a sub-DataFrame ---
    def _splits(sub: pd.DataFrame) -> StatSplits:
        n = len(sub)
        if n == 0:
            return StatSplits(games=0, pts=0.0, reb=0.0, ast=0.0, pra=0.0, min=0.0)
        pts_vals = [_f(r, 'PTS') for _, r in sub.iterrows()]
        reb_vals = [_f(r, 'REB') for _, r in sub.iterrows()]
        ast_vals = [_f(r, 'AST') for _, r in sub.iterrows()]
        stl_vals = [_f(r, 'STL') for _, r in sub.iterrows()]
        blk_vals = [_f(r, 'BLK') for _, r in sub.iterrows()]
        tov_vals = [_f(r, 'TOV') for _, r in sub.iterrows()]
        fg3m_vals = [_f(r, 'FG3M') for _, r in sub.iterrows()]
        min_vals = [_f(r, 'MIN') for _, r in sub.iterrows()]
        avg_pts = round(sum(pts_vals) / n, 1)
        avg_reb = round(sum(reb_vals) / n, 1)
        avg_ast = round(sum(ast_vals) / n, 1)
        avg_pra = round(sum(p + r + a for p, r, a in zip(pts_vals, reb_vals, ast_vals)) / n, 1)
        avg_pr = round(sum(p + r for p, r in zip(pts_vals, reb_vals)) / n, 1)
        avg_pa = round(sum(p + a for p, a in zip(pts_vals, ast_vals)) / n, 1)
        avg_min = round(sum(min_vals) / n, 1)
        return StatSplits(
            games=n, pts=avg_pts, reb=avg_reb, ast=avg_ast,
            pra=avg_pra, pr=avg_pr, pa=avg_pa,
            stl=round(sum(stl_vals) / n, 1),
            blk=round(sum(blk_vals) / n, 1),
            tov=round(sum(tov_vals) / n, 1),
            fg3m=round(sum(fg3m_vals) / n, 1),
            min=avg_min,
        )

    # --- Season averages (all 40 games) ---
    season_averages = _splits(df)

    # --- Rolling averages ---
    rolling_averages = RollingAverages(
        L3=_splits(df.tail(3)),
        L5=_splits(df.tail(5)),
        L10=_splits(df.tail(10)),
        L15=_splits(df.tail(15)),
        L20=_splits(df.tail(20)),
    )

    # --- Splits ---
    home_mask = df['MATCHUP'].apply(lambda m: _is_home(str(m)))
    home_splits = _splits(df[home_mask])
    away_splits = _splits(df[~home_mask])
    b2b_splits = _splits(df[df['_b2b'] == True])  # noqa: E712
    rest_splits = _splits(df[df['_b2b'] == False])  # noqa: E712

    # vs elite / weak defense
    elite_mask = df['MATCHUP'].apply(lambda m: _opp_abbrev(str(m)) in elite_teams)
    weak_mask = df['MATCHUP'].apply(lambda m: _opp_abbrev(str(m)) in weak_teams)
    vs_elite_def = _splits(df[elite_mask])
    vs_weak_def = _splits(df[weak_mask])

    # Win / Loss splits
    win_splits = None
    loss_splits = None
    if 'WL' in df.columns:
        win_mask = df['WL'].apply(lambda w: str(w).strip().upper() == 'W')
        loss_mask = df['WL'].apply(lambda w: str(w).strip().upper() == 'L')
        if win_mask.sum() > 0:
            win_splits = _splits(df[win_mask])
        if loss_mask.sum() > 0:
            loss_splits = _splits(df[loss_mask])

    # --- Analysis: per-stat deviation, consistency, ceiling/floor/median, streaks ---
    def _compute_analysis(sub_df: pd.DataFrame, season_avg: StatSplits) -> dict:
        """Compute StatAnalysis for each stat from last 20 games."""
        last20 = sub_df.tail(20)
        stat_cols = {
            'PTS': ('PTS', season_avg.pts),
            'REB': ('REB', season_avg.reb),
            'AST': ('AST', season_avg.ast),
            'PRA': (None, season_avg.pra),
            'PR': (None, season_avg.pr),
            'PA': (None, season_avg.pa),
            'STL': ('STL', season_avg.stl),
            'BLK': ('BLK', season_avg.blk),
            'TOV': ('TOV', season_avg.tov),
            'FG3M': ('FG3M', season_avg.fg3m),
        }
        result = {}
        for stat_name, (col, avg) in stat_cols.items():
            if col is not None:
                vals = [_f(r, col) for _, r in last20.iterrows()]
            elif stat_name == 'PRA':
                vals = [_f(r, 'PTS') + _f(r, 'REB') + _f(r, 'AST') for _, r in last20.iterrows()]
            elif stat_name == 'PR':
                vals = [_f(r, 'PTS') + _f(r, 'REB') for _, r in last20.iterrows()]
            else:  # PA
                vals = [_f(r, 'PTS') + _f(r, 'AST') for _, r in last20.iterrows()]

            if len(vals) < 2:
                continue

            std = round(_statistics.stdev(vals), 2)
            mean = sum(vals) / len(vals)
            cv = (std / mean) if mean > 0 else 1.0
            consistency = round(max(0, 100 - cv * 100), 1)

            # Streaks (most recent first — last20 is chronological, reverse)
            over_streak = 0
            under_streak = 0
            for v in reversed(vals):
                if v >= avg:
                    over_streak += 1
                else:
                    break
            if over_streak == 0:
                for v in reversed(vals):
                    if v < avg:
                        under_streak += 1
                    else:
                        break

            result[stat_name] = StatAnalysis(
                std_dev=std,
                consistency_score=consistency,
                ceiling=round(max(vals), 1),
                floor=round(min(vals), 1),
                median=round(_statistics.median(vals), 1),
                over_streak=over_streak,
                under_streak=under_streak,
            )
        return result

    analysis = _compute_analysis(df, season_averages)

    # --- Enrich player_info with team data from game log if team_id is missing ---
    # CommonPlayerInfo NBA API call can silently fail; MATCHUP column always has team data
    if not player_info.get('team_id') and not df.empty:
        recent_matchup = str(df.tail(1).iloc[0].get('MATCHUP', ''))
        team_abbrev_from_log = recent_matchup.split(' ')[0].strip().upper()
        if team_abbrev_from_log:
            if not team_abbrev:
                team_abbrev = team_abbrev_from_log
            try:
                team_mapper = get_team_mapper()
                bdl_team_id = team_mapper.abbrev_to_bdl_id(team_abbrev_from_log)
                if bdl_team_id is not None:
                    player_info = dict(player_info)
                    player_info['team_id'] = bdl_team_id
                    if not player_info.get('team_abbrev'):
                        player_info['team_abbrev'] = team_abbrev_from_log
            except Exception as e:
                logger.debug("Team ID enrichment failed for %s: %s", team_abbrev_from_log, e)

    # --- Next game + matchup context ---
    next_game_info = None
    opponent_context = None
    vs_stats_obj = None

    try:
        game_info_raw = service.scraper.get_player_next_game(player_info)
        if game_info_raw:
            raw_gd = game_info_raw.get('game_date', '')
            if hasattr(raw_gd, 'strftime'):
                game_date_str = raw_gd.strftime('%b %-d')
            else:
                game_date_str = str(raw_gd) if raw_gd else ''
            next_game_info = GameInfo(
                matchup=game_info_raw.get('matchup', ''),
                game_date=game_date_str,
                is_home=game_info_raw.get('is_home', True),
                opponent=game_info_raw.get('opponent', ''),
                opponent_name=game_info_raw.get('opponent_name', game_info_raw.get('opponent', '')),
            )

            opp_abbrev = game_info_raw.get('opponent', '')
            if opp_abbrev and team_stats and opp_abbrev in team_stats:
                opp_data = team_stats[opp_abbrev]
                def_rating = opp_data.get('def_rating', 110.0)
                pace = opp_data.get('pace', 98.0)
                # Rank description
                sorted_by_def = sorted(team_stats.items(), key=lambda x: x[1].get('def_rating', 999))
                rank_num = next((i + 1 for i, (t, _) in enumerate(sorted_by_def) if t == opp_abbrev), 15)
                if rank_num <= 5:
                    def_rank = "Elite Defense (Top 5)"
                elif rank_num <= 10:
                    def_rank = f"Strong Defense (#{rank_num})"
                elif rank_num <= 20:
                    def_rank = f"Average Defense (#{rank_num})"
                else:
                    def_rank = f"Weak Defense (#{rank_num})"
                pace_desc = "Fast" if pace > 100 else ("Average" if pace > 96 else "Slow")
                opponent_context = OpponentContext(
                    def_rating=round(def_rating, 1),
                    pace=round(pace, 1),
                    def_rank=def_rank,
                    pace_desc=pace_desc,
                    off_rating=round(opp_data.get('off_rating', 110.0), 1),
                    net_rating=round(opp_data.get('net_rating', 0.0), 1),
                    efg_pct=round(opp_data.get('efg_pct', 0.50), 3),
                    ts_pct=round(opp_data.get('ts_pct', 0.56), 3),
                    ast_pct=round(opp_data.get('ast_pct', 0.60), 3),
                    tov_pct=round(opp_data.get('tov_pct', 14.0), 1),
                    oreb_pct=round(opp_data.get('oreb_pct', 0.27), 3),
                    dreb_pct=round(opp_data.get('dreb_pct', 0.73), 3),
                )

            # vs_stats: H2H history
            try:
                vs_raw = service.scraper.get_vs_team_stats(player_id, opp_abbrev)
                if vs_raw and vs_raw.get('games', 0) > 0:
                    vs_stats_obj = VsStats(
                        games=vs_raw.get('games', 0),
                        avg_pts=round(vs_raw.get('avg_pts', 0.0), 1),
                        avg_reb=round(vs_raw.get('avg_reb', 0.0), 1),
                        avg_ast=round(vs_raw.get('avg_ast', 0.0), 1),
                    )
            except Exception as e:
                logger.debug("vs-team stats fetch failed for player %s vs %s: %s", player_id, opp_abbrev, e)
    except Exception as e:
        logger.warning("Next game context unavailable for player %s: %s", player_id, e)

    return PlayerResearchResponse(
        player_name=player_info.get('full_name', player_name),
        player_id=player_id,
        team_abbrev=team_abbrev or None,
        next_game=next_game_info,
        game_log=game_log_entries,
        season_averages=season_averages,
        rolling_averages=rolling_averages,
        home_splits=home_splits,
        away_splits=away_splits,
        b2b_splits=b2b_splits,
        rest_splits=rest_splits,
        vs_elite_def=vs_elite_def,
        vs_weak_def=vs_weak_def,
        win_splits=win_splits,
        loss_splits=loss_splits,
        opponent_context=opponent_context,
        vs_stats=vs_stats_obj,
        analysis=analysis,
    )


@router.get("/{player_name}/scenarios", response_model=ScenariosResponse)
@limiter.limit("20/minute")
async def get_player_scenarios(request: Request, player_name: str, current_user: dict = Depends(get_current_user)):
    """
    Get 'with/without' absence splits for teammates and opponents.
    Shows how the player's stats change when specific teammates or opponent
    players are absent. Loaded separately from /research for performance.
    """
    import time as _time

    service = get_prediction_service()

    # --- Player info ---
    player_info = service.get_player_info(player_name)
    if not player_info:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")

    player_id = player_info.get('id') or player_info.get('player_id')
    team_abbrev = (player_info.get('team_abbrev', '')
                   or player_info.get('team_abbreviation', ''))

    # --- Check cache ---
    cache_key = f"scenarios_{player_id}"
    cached = _scenarios_cache.get(cache_key)
    if cached is not None:
        ts, result = cached
        if (_time.time() - ts) < 3600:  # 1-hour TTL
            return result

    # --- Game log ---
    try:
        raw_df = service.scraper.get_player_game_log(player_id)
    except Exception as e:
        logger.error("Scenarios: failed to fetch game log for %s: %s", player_id, e)
        return ScenariosResponse(teammate_scenarios=[], opponent_scenarios=[])

    if raw_df is None or raw_df.empty:
        return ScenariosResponse(teammate_scenarios=[], opponent_scenarios=[])

    # Use last 40 games (same window as research endpoint)
    if 'GAME_DATE' in raw_df.columns:
        raw_df = raw_df.copy()
        raw_df['_sort_dt'] = pd.to_datetime(raw_df['GAME_DATE'], format='mixed')
        raw_df = (raw_df.sort_values('_sort_dt', ascending=True)
                  .drop(columns=['_sort_dt']).reset_index(drop=True))
    df = raw_df.tail(40).copy()

    # Extract Game_ID list (BDL game IDs)
    if 'Game_ID' not in df.columns:
        return ScenariosResponse(teammate_scenarios=[], opponent_scenarios=[])

    game_ids = [int(gid) for gid in df['Game_ID'].dropna().unique().tolist()]
    if not game_ids:
        return ScenariosResponse(teammate_scenarios=[], opponent_scenarios=[])

    # --- Fetch all player stats for these games (batched) ---
    bdl = get_bdl_client()

    all_stats = []
    batch_size = 15
    for i in range(0, len(game_ids), batch_size):
        chunk = game_ids[i:i + batch_size]
        try:
            all_stats.extend(bdl.get_player_stats(game_ids=chunk))
        except Exception as e:
            logger.warning("Scenarios: BDL batch %d failed: %s", i, e)

    if not all_stats:
        return ScenariosResponse(teammate_scenarios=[], opponent_scenarios=[])

    # --- Build player -> set(game_ids_played) mapping ---
    player_games: dict = {}       # bdl_player_id -> set of game_ids
    player_names: dict = {}       # bdl_player_id -> full name
    player_team_per_game: dict = {}  # (bdl_player_id, game_id) -> team_abbrev

    for stat in all_stats:
        p_obj = stat.get('player') or {}
        p_id = p_obj.get('id')
        g_obj = stat.get('game') or {}
        g_id = g_obj.get('id')
        if p_id is None or g_id is None:
            continue

        player_games.setdefault(p_id, set()).add(g_id)

        if p_id not in player_names:
            first = (p_obj.get('first_name') or '').strip()
            last = (p_obj.get('last_name') or '').strip()
            player_names[p_id] = f"{first} {last}".strip()

        # Resolve team abbreviation for this stat line
        stat_team = stat.get('team') or {}
        t_abbrev = str(stat_team.get('abbreviation') or '').upper()
        if not t_abbrev:
            p_team = p_obj.get('team') or {}
            t_abbrev = str(p_team.get('abbreviation') or '').upper()
        player_team_per_game[(p_id, g_id)] = t_abbrev

    # --- Identify target player's BDL ID ---
    player_mapper = get_player_mapper()
    bdl_player_id = player_mapper.nba_to_bdl(int(player_id), player_name)
    if bdl_player_id is None:
        bdl_player_id = int(player_id)

    target_game_id_set = set(game_ids)

    # --- Helper: compute StatSplits from a sub-DataFrame ---
    def _f(row, col, default=0.0):
        v = row.get(col, default)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)

    def _splits_from_df(sub: pd.DataFrame):
        n = len(sub)
        if n == 0:
            return StatSplits(games=0, pts=0, reb=0, ast=0, pra=0, min=0)
        pts = [_f(r, 'PTS') for _, r in sub.iterrows()]
        reb = [_f(r, 'REB') for _, r in sub.iterrows()]
        ast = [_f(r, 'AST') for _, r in sub.iterrows()]
        stl = [_f(r, 'STL') for _, r in sub.iterrows()]
        blk = [_f(r, 'BLK') for _, r in sub.iterrows()]
        tov = [_f(r, 'TOV') for _, r in sub.iterrows()]
        fg3m = [_f(r, 'FG3M') for _, r in sub.iterrows()]
        mins = [_f(r, 'MIN') for _, r in sub.iterrows()]
        avg = lambda vals: round(sum(vals) / n, 1)
        return StatSplits(
            games=n,
            pts=avg(pts), reb=avg(reb), ast=avg(ast),
            pra=avg([p + r + a for p, r, a in zip(pts, reb, ast)]),
            pr=avg([p + r for p, r in zip(pts, reb)]),
            pa=avg([p + a for p, a in zip(pts, ast)]),
            stl=avg(stl), blk=avg(blk), tov=avg(tov),
            fg3m=avg(fg3m), min=avg(mins),
        )

    # --- Injuries (for currently_out flag) ---
    try:
        injuries = service.get_injuries()
    except Exception:
        injuries = {}

    injured_names = set()
    for _team_abbr, team_data in injuries.items():
        for p in team_data.get('players', []):
            if p.get('status') == 'out':
                injured_names.add(p.get('name', '').strip().lower())

    # --- Teammate scenarios ---
    teammate_scenarios = []

    for p_id, games_played in player_games.items():
        if p_id == bdl_player_id:
            continue  # skip self

        # Check if this player was on the same team in any game
        same_team_games = set()
        for gid in games_played:
            if player_team_per_game.get((p_id, gid), '') == team_abbrev:
                same_team_games.add(gid)

        # Must have played 5+ games WITH the target (trade filter)
        games_with = same_team_games & target_game_id_set
        if len(games_with) < 5:
            continue

        games_without = target_game_id_set - same_team_games
        if len(games_without) < 3:
            continue  # not enough absence data

        # Compute splits
        with_df = df[df['Game_ID'].isin(games_with)]
        without_df = df[df['Game_ID'].isin(games_without)]

        with_splits = _splits_from_df(with_df)
        without_splits = _splits_from_df(without_df)

        name = player_names.get(p_id, f"Player {p_id}")
        is_out = name.strip().lower() in injured_names

        teammate_scenarios.append(PlayerScenario(
            player_name=name,
            player_id=p_id,
            role="teammate",
            with_splits=with_splits,
            without_splits=without_splits,
            currently_out=is_out,
        ))

    # Sort by PTS impact (descending absolute delta)
    teammate_scenarios.sort(
        key=lambda s: abs(s.without_splits.pts - s.with_splits.pts),
        reverse=True,
    )
    teammate_scenarios = teammate_scenarios[:8]  # cap at 8

    # --- Opponent scenarios ---
    opponent_scenarios = []

    # Only compute for next game opponent
    try:
        game_info_raw = service.scraper.get_player_next_game(player_info)
    except Exception:
        game_info_raw = None

    if game_info_raw:
        opp_abbrev = game_info_raw.get('opponent', '')
        if opp_abbrev:
            def _opp_abbrev(matchup: str) -> str:
                if not matchup:
                    return ''
                parts = matchup.replace('vs.', '@').split('@')
                return parts[-1].strip().upper() if len(parts) >= 2 else ''

            # Filter target player's games vs this opponent
            vs_opp_mask = df['MATCHUP'].apply(
                lambda m: _opp_abbrev(str(m)) == opp_abbrev
            )
            vs_opp_game_ids = set(
                df[vs_opp_mask]['Game_ID'].dropna().astype(int).tolist()
            )

            if vs_opp_game_ids:
                for p_id, games_played in player_games.items():
                    opp_games = set()
                    for gid in games_played:
                        if (player_team_per_game.get((p_id, gid), '')
                                == opp_abbrev):
                            opp_games.add(gid)

                    opp_h2h_present = opp_games & vs_opp_game_ids
                    opp_h2h_absent = vs_opp_game_ids - opp_games

                    if not opp_h2h_present or not opp_h2h_absent:
                        continue  # need both present and absent games

                    with_df = df[df['Game_ID'].isin(opp_h2h_present)]
                    without_df = df[df['Game_ID'].isin(opp_h2h_absent)]

                    with_splits = _splits_from_df(with_df)
                    without_splits = _splits_from_df(without_df)

                    name = player_names.get(p_id, f"Player {p_id}")
                    is_out = name.strip().lower() in injured_names

                    opponent_scenarios.append(PlayerScenario(
                        player_name=name,
                        player_id=p_id,
                        role="opponent",
                        with_splits=with_splits,
                        without_splits=without_splits,
                        currently_out=is_out,
                    ))

            opponent_scenarios.sort(
                key=lambda s: abs(s.without_splits.pts - s.with_splits.pts),
                reverse=True,
            )
            opponent_scenarios = opponent_scenarios[:8]

    response = ScenariosResponse(
        teammate_scenarios=teammate_scenarios,
        opponent_scenarios=opponent_scenarios,
    )
    now = _time.time()
    # Prune expired entries before inserting
    expired = [k for k, (ts, _) in _scenarios_cache.items() if now - ts >= 3600]
    for k in expired:
        del _scenarios_cache[k]
    # LRU eviction if still over limit
    while len(_scenarios_cache) >= _SCENARIOS_CACHE_MAX:
        oldest_key = min(_scenarios_cache, key=lambda k: _scenarios_cache[k][0])
        del _scenarios_cache[oldest_key]
    _scenarios_cache[cache_key] = (now, response)
    return response


@router.post("/evaluate-line", response_model=LineEvaluation)
@limiter.limit("30/minute")
async def evaluate_line(request: Request, body: LineEvaluationRequest, current_user: dict = Depends(get_current_user)):
    """Evaluate a betting line against a prediction."""
    service = get_prediction_service()

    # If prediction not provided, we need to fetch it
    prediction = body.prediction
    if prediction is None:
        # Get prediction from model
        result = None
        async for event in service.predict_with_progress(body.player_name):
            if event['stage'] == 'complete':
                result = event['data']
            elif event['stage'] == 'error':
                raise HTTPException(status_code=404, detail=event['message'])

        if not result or body.stat not in result['predictions']:
            raise HTTPException(status_code=404, detail=f"Could not get prediction for {body.stat}")

        prediction = result['predictions'][body.stat]['prediction']

    # Evaluate the line
    # Use per-stat CV (coefficient of variation) reflecting real NBA game-to-game variance.
    # NBA stats typically vary 35-50% around the mean each game; using the tight
    # ±15% / 1.645 estimate produced unrealistically high probabilities (90-100%).
    _stat_cv = {'PTS': 0.40, 'REB': 0.45, 'AST': 0.50, 'PRA': 0.35}
    cv = _stat_cv.get(body.stat, 0.40)
    estimated_std = prediction * cv
    confidence_info = {
        'confidence': 75,
        'low': prediction * (1 - cv),
        'high': prediction * (1 + cv),
        'std': estimated_std,
    }

    evaluation = service.evaluate_line(prediction, body.line, body.stat, confidence_info)

    return LineEvaluation(**evaluation)
