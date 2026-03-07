"""
NBA Prop Evaluator API
FastAPI backend for player prop analysis.
"""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded

from .limiter import limiter
from .routers import players_router, bets_router, picks_router, games_router, auth_router, parlays_router


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
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co;"
        )
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


# Create app
app = FastAPI(
    title="NBA Prop Evaluator API",
    description="ML-powered player prop analysis for NBA betting",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
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

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

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


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "nba-prop-evaluator"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "NBA Prop Evaluator API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "endpoints": {
            "players": {
                "search": "GET /api/players/search?q=<query>",
                "predict": "POST /api/players/predict",
                "predict_sync": "POST /api/players/predict/sync",
                "evaluate_line": "POST /api/players/evaluate-line"
            },
            "bets": {
                "today": "GET /api/bets/today",
                "quick": "GET /api/bets/quick"
            },
            "picks": {
                "list": "GET /api/picks",
                "create": "POST /api/picks",
                "get": "GET /api/picks/{id}",
                "grade": "PUT /api/picks/{id}/grade",
                "delete": "DELETE /api/picks/{id}",
                "auto_grade": "POST /api/picks/auto-grade",
                "stats": "GET /api/picks/stats/performance",
                "profit": "GET /api/picks/stats/profit"
            },
            "games": {
                "today": "GET /api/games/today",
                "predict": "POST /api/games/predict",
                "history": "GET /api/games/history",
                "auto_grade": "POST /api/games/auto-grade",
                "accuracy": "GET /api/games/stats/accuracy"
            }
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
