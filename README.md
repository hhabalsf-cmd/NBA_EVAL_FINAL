# NBA Prop Evaluator

Full-stack NBA research platform with player-prop forecasts, exact-price offer
evaluation, game research, and pick tracking.

## Personal local app — free ESPN data

For single-user use, double-click **Start NBA Eval.cmd** and open
**http://127.0.0.1:8765**. This standalone mode needs no paid API key, Supabase,
or login. The original Bettin' Jrys interface is already built locally. It provides verified ESPN game logs, the rebuilt
player-prop forecasts, manual price evaluation and local saved history.
See [personal setup, stat reconciliation and limitations](docs/PERSONAL_LOCAL.md).
The existing hosted stack below remains separate from this personal mode.

## Predictor rebuild

The new **Forecasts** page uses a league-wide player-prop engine with chronological
validation, empirical outcome distributions, and exact-price offer evaluation.
See [rebuild results and run instructions](docs/PREDICTOR_REBUILD_2026-09-27.md).
The held-out forecast improvements are modest; profitable betting has not been
validated. Model artifacts must be provisioned separately from this source tree.

- **Live app:** https://nba-eval-final.vercel.app
- **API:** https://nbaevalfinal-production.up.railway.app
- **API docs:** https://nbaevalfinal-production.up.railway.app/api/docs

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18, TypeScript, Vite 6, Tailwind CSS 3, React Query, Zustand, Recharts |
| Backend | FastAPI, Python 3.11, psycopg2 |
| ML | scikit-learn, XGBoost, LightGBM, Optuna (stacking ensemble with isotonic calibration) |
| Data | Supabase (Postgres + Auth + Storage + Realtime + Edge Functions), BallDontLie API |
| Infra | Railway (API), Vercel (frontend), pg_cron + Supabase Edge Functions (nightly jobs) |
| Media | Remotion (programmatic video), ElevenLabs (voiceover) |

## What it does

- **Forecasts** — pooled PTS/REB/AST/PRA forecasts for players with at least ten prior appearances, outcome ranges, and exact-price over/under/push evaluation. Betting recommendations remain disabled pending priced validation.
- **Legacy props** — the older per-player prediction and daily-pick paths remain available behind their existing release flags; they do not use the new forecasting engine.
- **Game predictions** — team-level win probabilities from an ELO + Four Factors stacking ensemble.
- **Best bets feed** — nightly pipeline ranks the day's top 20 picks by model edge, filtered on minutes, confidence, and historical edge-performance caps.
- **Research** — game logs, rolling averages, home/away and matchup splits, defensive context, teammate/opponent absence scenarios.
- **Picks tracker** — authenticated users can save picks, auto-grade against live scores, and track ROI over time.

## New forecast pipeline

- **50 causal features** built identically for historical replay and serving, including minutes, production rates, recent levels, rest and team changes.
- **League-wide regularized regression** selected against rolling/exponential baselines, pooled ridge, boosting and minutes/rate models on an earlier validation season.
- **Later-period residual calibration** produces integer outcome distributions and explicit push probabilities. Fitting never runs inside a forecast request.
- **Versioned artifacts** with source hashes and separate frozen-evaluation/current-use fits. See the rebuild report for measured performance and limitations.

## Legacy ML pipeline

- **81 canonical features** per player-game, including rolling statistics, opponent context, schedule and role features.
- **Per-player gradient boosting** is the default; optional ensemble/neural paths and the earlier pooled model also exist.
- **Validation** — purged walk-forward CV, optional hyperparameter search, probability calibration and quantile ranges. See the audit for unresolved defects and limits of the historical evidence.
- **Confidence caps** enforced per stat based on historical hit-rate: PTS 88%, REB 82%, AST 78%, PRA 80%.
- **Model storage** — pickles stored in Supabase Storage, cached in-process with LRU.

## Architecture

```
┌──────────────────┐      ┌────────────────┐      ┌──────────────────────┐
│ React (Vercel)   │────▶│ FastAPI         │────▶│ BallDontLie API       │
│                  │      │ (Railway)       │      │ (game logs, schedule)│
│ - supabase-js    │◀──┐ │                 │      └──────────────────────┘
│   direct reads   │   │ │ - ML inference  │
│   (PostgREST,    │   │ │ - SSE streams   │
│    RLS enforced) │   │ │ - cron jobs     │
│ - Auth + realtime│   │ └────────┬────────┘
└──────────────────┘   │          │
                       │          ▼
                       │ ┌──────────────────────────────────────┐
                       └─│ Supabase                              │
                         │ Postgres + Auth + Storage + Realtime  │
                         │ Edge Functions (pick grading)         │
                         │ pg_cron (nightly picks + regrading)   │
                         └──────────────────────────────────────┘
```

- The frontend reads directly from Supabase (PostgREST) for all user-owned data (picks, parlays, profile), with Row-Level Security enforcing per-user access.
- Write paths and ML inference go through FastAPI, which verifies Supabase JWTs via `SUPABASE_JWT_SECRET`.
- Nightly jobs (daily picks generation, pick grading) run as pg_cron triggers against protected FastAPI endpoints or Supabase Edge Functions.

## Local development

Backend:
```bash
pip install -r requirements.txt
pip install -r api/requirements.txt
cp .env.example .env   # fill in Supabase + DB credentials
./start_api.sh         # FastAPI at http://localhost:8000 (docs at /api/docs)
```

Frontend:
```bash
cd frontend
cp .env.example .env.local   # fill in VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
npm install
npm run dev                  # http://localhost:5173
```

Vite proxies `/api/*` to `localhost:8000`.

## Project layout

```
EVAL/
├── api/                  FastAPI routers, schemas, services
├── frontend/             React app (feature-folder layout)
├── scripts/              Nightly sync, picks generation, migrations
├── supabase/             Edge functions, SQL migrations
├── tests/                pytest suite
├── video/                Remotion compositions for promo/recap videos
├── nba_evaluator.py      ML core (feature engineering, predictor, scraper)
├── game_predictor.py     Team-level game outcome model
├── bdl_client.py         BallDontLie HTTP client (token-bucket rate limiter)
├── stats_aggregator.py   Computes team stats from game logs
└── db.py                 Supabase/Postgres data layer
```

## Tests

```bash
pytest tests/
```

## Disclaimer

For educational and research purposes only. Sports betting involves risk.
