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
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
import psycopg2

from .middleware import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
    SelectiveGZipMiddleware,
)

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
            ok = await asyncio.get_event_loop().run_in_executor(
                None, model_storage.download_game_model, game_model_path
            )
            if ok:
                _logger.info("Game model pre-downloaded from Supabase")
            else:
                _logger.info("Game model not in Supabase — will train on first prediction request")
    except Exception as exc:
        _logger.info("Game model not available yet — will train on first use")

    yield


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


def _db_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _logger.error("Database error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable. Please retry in a moment."},
    )


def _general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_exception_handler(psycopg2.OperationalError, _db_exception_handler)
app.add_exception_handler(psycopg2.InterfaceError, _db_exception_handler)
app.add_exception_handler(Exception, _general_exception_handler)

# Middleware stack — add_middleware() wraps outside-in, so the LAST one added
# is the OUTERMOST. Intended request path (outermost first):
#   CORS → gzip (SSE-aware) → security headers → body limit → app
# CORS must stay outermost so every response (including errors) carries CORS
# headers for the browser.

# Request body size limit (2 MB)
app.add_middleware(RequestBodyLimitMiddleware)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# GZip compression — skips text/event-stream so SSE progress isn't buffered
app.add_middleware(SelectiveGZipMiddleware, minimum_size=1000)

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
    """Health check endpoint — includes DB connectivity status."""
    db_ok = False
    try:
        import db as _db
        with _db.borrow_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            db_ok = True
    except Exception:
        pass
    return {"status": "healthy" if db_ok else "degraded", "service": "nba-prop-evaluator", "db": db_ok}


@app.post("/api/flush-cache")
async def flush_cache(request: Request):
    """Flush in-memory model and data caches to free RAM.

    Protected by X-Service-Key. Call when Railway memory is high.
    """
    from .routers.auth import verify_service_key
    verify_service_key(request)
    import gc
    try:
        from nba_evaluator import flush_memory_caches
        flush_memory_caches()
    except Exception:
        pass
    gc.collect()
    return {"status": "flushed"}


@app.post("/api/flush-pool")
async def flush_pool(request: Request):
    """Reset the database connection pool.

    Protected by X-Service-Key. Call when DB connections are stale/stuck.
    """
    from .routers.auth import verify_service_key
    verify_service_key(request)
    import db as _db
    _db._reset_pool()
    return {"status": "pool_reset"}


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
