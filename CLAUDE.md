# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack ML-powered NBA player prop betting analysis platform. The system fetches live NBA data, trains per-player ML models, evaluates betting lines, and surfaces edge recommendations via a React frontend.

## Commands

### Backend
```bash
# Install Python dependencies
pip install -r requirements.txt          # Root-level (ML core)
pip install -r api/requirements.txt      # FastAPI layer

# Start FastAPI server (port 8000)
./start_api.sh
# or: cd api && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Docs at: http://localhost:8000/api/docs

# CLI usage (no API needed)
python nba_evaluator.py --interactive
python nba_evaluator.py --player "Nikola Jokic" --stat PTS --line 26.5
python nba_evaluator.py --player "LeBron James" --pts-line 25.5 --reb-line 7.5
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Dev server at http://localhost:5173
npm run build    # Production build
npm run lint     # ESLint
```

Both servers must run simultaneously. Vite proxies `/api/*` requests to `localhost:8000`.

## Architecture

### ML Pipeline (nba_evaluator.py — 3000+ lines, core engine)

1. **NBADataScraper** — fetches from NBA API (player logs, 2-3 seasons), scrapes injury reports, pulls OddsAPI lines. Caches: 24h player info, 1h game logs, 30min injuries.
2. **FeatureEngineer** — produces ~200+ features: rolling averages (3/5/7/10/15/20 games), EMA, efficiency metrics (TS%, EFG%, AST/TOV), opponent matchup history, home/away splits, B2B/rest days, ELO opponent strength.
3. **MLPredictor** — trains per-player, per-stat (PTS/REB/AST/PRA) models using Time-Series cross-validation. Supports Random Forest, Gradient Boosting, XGBoost, LightGBM, and stacking ensembles. Models persisted as `models/{PlayerName}_model.pkl`.
4. **LineEvaluator** — compares ML prediction to betting line, calculates edge %, probability of OVER/UNDER, and outputs STRONG/MODERATE/SLIGHT recommendation.

`enhanced_predictor.py` extends the core with XGBoost/LightGBM stacking and Optuna hyperparameter search. `game_predictor.py` handles team-level ELO-based win probability.

### API Layer (`api/`)

- **`main.py`** — FastAPI app with CORS, mounts routers under `/api`
- **`services/prediction_service.py`** — wraps `nba_evaluator.py` for async use
- **`routers/players.py`** — player search, streaming predictions (SSE), line evaluation
- **`routers/bets.py`** — today's best bets discovery
- **`routers/picks.py`** — CRUD for saved picks with auto-grading
- **`routers/games.py`** — game-level predictions and accuracy tracking

Predictions use **Server-Sent Events (SSE)** for streaming progress updates. The sync endpoint (`POST /api/players/predict/sync`) is the non-streaming alternative.

### Frontend (`frontend/src/`)

- **`api/client.ts`** — typed API client; handles both SSE streaming and regular fetch
- **`store/authStore.ts`** — Zustand store for auth state
- **`store/parlayStore.ts`** — Zustand store for parlay legs
- **`hooks/usePrediction.ts`** — manages streaming prediction lifecycle (progress, result, error)
- **`pages/PlayerPage.tsx`** — primary page: triggers predictions, shows line evaluations, saves picks
- **`pages/HomePage.tsx`** — player search entry point and top picks dashboard
- **`pages/ParlayPage.tsx`** — parlay builder using parlayStore legs
- **`components/BetCard.tsx`** — renders individual best-bet recommendations

React Query (`@tanstack/react-query`) manages server state (player search, odds, best bets, performance stats). Zustand manages client UI state (auth, parlay selection).

### Data Storage

- **`picks_history.db`** — SQLite; tables: `picks`, `game_predictions`, performance metrics
- **`models/`** — per-player `.pkl` files (~100 players); `models/games/` for game models
- **`cache/`**, **`data/`** — API response and player data caches (gitignored)
- **`config.json`** — OddsAPI key

## Key Patterns

- **Streaming predictions**: `POST /api/players/predict` returns SSE events with `{stage, progress, message, data}`. The frontend's `usePrediction` hook reads this stream and drives the UI progress bar.
- **Per-player model caching**: `MLPredictor` saves/loads `.pkl` files; pass `retrain=True` in requests to force retraining.
- **Feature importance pruning**: Models select top-N features by cumulative importance threshold to reduce overfitting.
- **Quantile regression**: 10th/90th percentile models run alongside the main predictor to produce confidence intervals.
