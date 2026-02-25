"""
NBA Prop Evaluator API
FastAPI backend for player prop analysis.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import players_router, bets_router, picks_router, games_router, auth_router

# Create app
app = FastAPI(
    title="NBA Prop Evaluator API",
    description="ML-powered player prop analysis for NBA betting",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded avatars
_UPLOADS_DIR = Path(__file__).parent.parent / "uploads" / "avatars"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/avatars", StaticFiles(directory=str(_UPLOADS_DIR)), name="avatars")

# Include routers
app.include_router(players_router)
app.include_router(bets_router)
app.include_router(picks_router)
app.include_router(games_router)
app.include_router(auth_router)


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
    uvicorn.run(app, host="0.0.0.0", port=8000)
