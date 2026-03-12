"""Player search and prediction endpoints."""
import json
import logging
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Optional

from ..limiter import limiter

logger = logging.getLogger(__name__)

import pandas as pd

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
    RollingAverages,
    PlayerResearchResponse,
)
from ..services.prediction_service import PredictionService
from bdl_id_mapper import get_team_mapper

router = APIRouter(prefix="/api/players", tags=["players"])

# Singleton service instance
_prediction_service: Optional[PredictionService] = None


def get_prediction_service() -> PredictionService:
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = PredictionService()
    return _prediction_service


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
async def predict_player_stats(request: Request, body: PredictionRequest):
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
async def predict_player_stats_sync(request: Request, body: PredictionRequest):
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
async def get_team_injuries(request: Request, player_name: str):
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
async def get_player_odds(request: Request, player_name: str):
    """Get today's consensus prop lines for a player (30-min cached)."""
    service = get_prediction_service()
    result = service.get_player_odds(player_name)
    return result


@router.get("/{player_name}/research", response_model=PlayerResearchResponse)
@limiter.limit("20/minute")
async def get_player_research(request: Request, player_name: str):
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

        game_log_entries.append(FullGameLogEntry(
            game_date=gd_str,
            opponent=opp_display,
            is_home=is_home,
            min=_f(row, 'MIN'),
            pts=pts,
            reb=reb,
            ast=ast,
            pra=round(pts + reb + ast, 1),
            fg_pct=round(_f(row, 'FG_PCT') * 100, 1),
            fg3_pct=round(_f(row, 'FG3_PCT') * 100, 1),
            ft_pct=round(_f(row, 'FT_PCT') * 100, 1),
            stl=_f(row, 'STL'),
            blk=_f(row, 'BLK'),
            tov=_f(row, 'TOV'),
            plus_minus=_f(row, 'PLUS_MINUS'),
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
        min_vals = [_f(r, 'MIN') for _, r in sub.iterrows()]
        avg_pts = round(sum(pts_vals) / n, 1)
        avg_reb = round(sum(reb_vals) / n, 1)
        avg_ast = round(sum(ast_vals) / n, 1)
        avg_pra = round(sum(p + r + a for p, r, a in zip(pts_vals, reb_vals, ast_vals)) / n, 1)
        avg_min = round(sum(min_vals) / n, 1)
        return StatSplits(games=n, pts=avg_pts, reb=avg_reb, ast=avg_ast, pra=avg_pra, min=avg_min)

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
        opponent_context=opponent_context,
        vs_stats=vs_stats_obj,
    )


@router.post("/evaluate-line", response_model=LineEvaluation)
@limiter.limit("30/minute")
async def evaluate_line(request: Request, body: LineEvaluationRequest):
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
