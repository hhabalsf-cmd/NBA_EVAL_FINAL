"""Local website. Intentionally independent of the hosted app and its credentials."""
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from forecasting.offers import Offer, decimal_odds
from forecasting.service import forecast_player, load_model
from personal.espn import ESPN, DataUnavailable, instant
from personal.store import Store

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


class Quote(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    stat: Literal['PTS', 'REB', 'AST', 'PRA']
    side: Literal['OVER', 'UNDER']
    line: float = Field(ge=0, le=300)
    american_odds: float = Field(ge=-100000, le=100000)
    book: str = Field(min_length=1, max_length=80)


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    team_id: str = Field(pattern=r'^\d{1,10}$')
    player_id: str = Field(pattern=r'^\d{1,10}$')
    event_id: str = Field(pattern=r'^\d{1,15}$')
    availability: Literal['available', 'questionable', 'unknown', 'out'] = 'unknown'
    quote: Quote | None = None


class PersonalFrontend(StaticFiles):
    async def get_response(self, path, scope):
        if path in ('.', '', 'app', 'games', 'research', 'forecasts', 'picks', 'leaderboard', 'settings') or path.startswith('player/'):
            path = 'personal.html'
        return await super().get_response(path, scope)


def create_app(store=None, provider=None, frontend_dir=None):
    store = store or Store(ROOT / 'cache' / 'personal' / 'nba.sqlite3')
    provider = provider or ESPN(store)
    app = FastAPI(title='NBA Eval Personal', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        if not request.client or request.client.host not in ('127.0.0.1', '::1'):
            return JSONResponse({'detail': 'This app only accepts connections from this computer.'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-site requests are disabled.'}, status_code=403)
        if request.method not in ('GET', 'HEAD'):
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': 'JSON is required.'}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 8192:
                    return JSONResponse({'detail': 'Request too large.'}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://a.espncdn.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(DataUnavailable)
    async def unavailable(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    @app.exception_handler(KeyError)
    @app.exception_handler(TypeError)
    @app.exception_handler(IndexError)
    @app.exception_handler(ValueError)
    async def schema_error(request, exc):
        logger.exception('Unexpected source data format', exc_info=exc)
        return JSONResponse({'detail': 'ESPN returned an unexpected data format. No forecast was saved.'}, status_code=503)

    @app.get('/api/status')
    def status():
        try:
            metadata = load_model().metadata
            error = None
        except (OSError, ValueError) as exc:
            metadata, error = None, f'Forecast model unavailable: {exc}. See docs/PERSONAL_LOCAL.md.'
        return dict(mode='local', source='ESPN', model=metadata, model_error=error)

    @app.get('/api/teams')
    def teams():
        return provider.teams()

    @app.get('/api/teams/{team_id}/roster')
    def roster(team_id: int):
        return provider.roster(str(team_id))

    @app.get('/api/teams/{team_id}/schedule')
    def schedule(team_id: int):
        return provider.schedule(str(team_id))

    @app.get('/api/players/{player_id}/history')
    def history(player_id: int):
        data, quality = provider.history(str(player_id))
        return dict(games=data.iloc[::-1].to_dict('records'), quality=quality)

    @app.get('/api/players/search')
    def search(q: str = Query(min_length=2, max_length=80)):
        return provider.search(q)

    @app.get('/api/history')
    def saved():
        return dict(forecasts=store.forecasts(), corrections=store.corrections())

    @app.post('/api/forecast')
    def forecast(body: ForecastRequest):
        now = datetime.now(timezone.utc)
        if body.availability == 'out':
            raise HTTPException(422, 'Player is out. An active-player forecast would be misleading.')
        roster = provider.roster(body.team_id)
        player = next((p for p in roster['players'] if p['id'] == body.player_id), None)
        if player is None:
            raise HTTPException(422, 'Player is not on the selected ESPN roster. Refresh and select their current team.')
        events = provider.schedule(body.team_id, now=now)
        event = next((e for e in events['events'] if e['id'] == body.event_id), None)
        if event is None:
            raise HTTPException(422, 'This is no longer a supported upcoming regular-season game. Refresh the schedule.')
        injury_states = {str(i.get('status', '')).strip().lower() for i in player['injuries']}
        if injury_states & {'out', 'suspension', 'suspended'}:
            raise HTTPException(422, 'ESPN lists this player as out or suspended. No active-player forecast is available.')
        availability = 'questionable' if player['injuries'] else body.availability
        try:
            model = load_model()
        except (OSError, ValueError) as exc:
            raise HTTPException(503, 'Forecast model unavailable. See docs/PERSONAL_LOCAL.md for setup.') from exc
        # Fetching history can take time on the first visit. Stamp the quote at submission,
        # then evaluate against the actual current time so expired quotes cannot look fresh.
        offers = []
        if body.quote:
            try:
                odds = decimal_odds(body.quote.american_odds)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            offers = [Offer(event_id=f'espn:{event["id"]}', player_id=f'espn:{body.player_id}',
                            stat=body.quote.stat, side=body.quote.side, line=body.quote.line,
                            decimal_odds=odds, book=body.quote.book.strip(),
                            captured_at=now, starts_at=instant(event['starts_at']))]
        data, quality = provider.history(body.player_id, now=now)
        try:
            result = forecast_player(data, model=model, player_id=f'espn:{body.player_id}',
                    event_id=f'espn:{event["id"]}', starts_at=instant(event['starts_at']),
                    team=event['team'], home=event['home'], availability=availability, offers=offers)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result.update(player_name=player['name'], event=event, data_quality=quality,
                      availability=availability, injuries=player['injuries'])
        result['notes'][1] = 'Matchup and current roster come from ESPN; participation still needs confirmation.'
        if quality.get('quarantined_games'):
            result['notes'].append(f"{len(quality['quarantined_games'])} older games excluded because ESPN's box-score counts were inconsistent; see the verified history details.")
        if (instant(event['starts_at']) - now).days > 3:
            result['notes'].append('Early preview: refresh near tipoff after lineups and roles are clearer.')
        result['saved_id'] = store.save_forecast(result)
        return result

    frontend = Path(frontend_dir) if frontend_dir else ROOT / 'frontend' / 'dist-personal'
    if (frontend / 'personal.html').exists():
        app.mount('/', PersonalFrontend(directory=frontend), name='website')
    else:
        @app.get('/')
        def setup_needed():
            return HTMLResponse('<h1>Build the personal frontend</h1><p>Run npm install and npm run build:personal in the frontend directory, then restart NBA Eval.</p>', status_code=503)
    return app


app = create_app()
