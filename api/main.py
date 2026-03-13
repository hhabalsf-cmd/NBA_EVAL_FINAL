"""
NBA Prop Evaluator API
FastAPI backend for player prop analysis.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded

_is_prod = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))

from .limiter import limiter
from .routers import players_router, bets_router, picks_router, games_router, auth_router, parlays_router, sync_router, live_router, social_router

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm expensive singletons at startup so first requests are fast."""
    # 1. DB connection pool
    try:
        import db as _db
        _db._get_pool()
        _logger.info("DB connection pool initialized")
    except Exception as exc:
        _logger.warning("DB pool warm-up failed (non-fatal): %s", exc)

    # 2. Supabase client singleton
    try:
        from .routers.auth import _get_supa_client
        _get_supa_client()
        _logger.info("Supabase client initialized")
    except Exception as exc:
        _logger.warning("Supabase warm-up failed (non-fatal): %s", exc)

    # 3. GamePredictionService (loads game_predictor model)
    try:
        from .routers.games import get_game_service
        get_game_service()
        _logger.info("GamePredictionService initialized")
    except Exception as exc:
        _logger.warning("GamePredictionService warm-up failed (non-fatal): %s", exc)

    # 4. Player list cache (NBA API call — run in thread so it doesn't block startup)
    try:
        from .routers.players import get_prediction_service
        _svc = get_prediction_service()
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _svc._refresh_players_sync)
        _logger.info("Player cache refresh scheduled in background")
    except Exception as exc:
        _logger.warning("Player cache warm-up failed (non-fatal): %s", exc)

    # 5. Pre-download game model from Supabase if not on local disk
    try:
        import model_storage
        from nba_evaluator import MODEL_DIR
        game_model_path = MODEL_DIR / "games" / "game_predictor.pkl"
        if not game_model_path.exists():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, model_storage.download_game_model, game_model_path
            )
            _logger.info("Game model pre-downloaded from Supabase")
    except Exception as exc:
        _logger.warning("Game model pre-download failed (non-fatal): %s", exc)

    yield


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies larger than the configured limit (default 2 MB)."""

    MAX_BODY_SIZE = 2 * 1024 * 1024  # 2 MB

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-relevant HTTP response headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co;"
        )
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


# Create app
app = FastAPI(
    title="Bettin' Jrys API",
    description="ML-powered player prop analysis for NBA betting",
    version="1.0.0",
    docs_url=None if _is_prod else "/api/docs",
    redoc_url=None if _is_prod else "/api/redoc",
    openapi_url=None if _is_prod else "/api/openapi.json",
    lifespan=lifespan,
)

def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please wait a moment and try again."},
        headers={"Retry-After": "60"},
    )

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Request body size limit (2 MB)
app.add_middleware(RequestBodyLimitMiddleware)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# GZip compression (auto-skips SSE responses)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware for frontend
_default_origins = "http://localhost:5173,http://localhost:5174,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:3000"
_allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Include routers
app.include_router(players_router)
app.include_router(bets_router)
app.include_router(picks_router)
app.include_router(games_router)
app.include_router(auth_router)
app.include_router(parlays_router)
app.include_router(sync_router)
app.include_router(live_router)
app.include_router(social_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "nba-prop-evaluator"}


@app.get("/")
async def root():
    """Root endpoint — health check only in production."""
    if _is_prod:
        return {"status": "healthy", "service": "bettin-jrys-api"}
    return {
        "name": "NBA Prop Evaluator API",
        "version": "1.0.0",
        "docs": "/api/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
