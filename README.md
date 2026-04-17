# NBA Prop Evaluator

Full-stack ML platform for evaluating NBA player prop bets and game outcomes. Predicts PTS/REB/AST/PRA player lines with a stacking ensemble and surfaces the highest-edge picks each day.

- **Live app:** https://nba-eval-final.vercel.app
- **API:** https://nbaevalfinal-production.up.railway.app
- **API docs:** https://nbaevalfinal-production.up.railway.app/api/docs

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS 3, React Query, Zustand, Recharts |
| Backend | FastAPI, Python 3.11, psycopg2 |
| ML | scikit-learn, XGBoost, LightGBM, Optuna (stacking ensemble with isotonic calibration) |
| Data | Supabase (Postgres + Auth + Storage + Realtime + Edge Functions), BallDontLie API |
| Infra | Railway (API), Vercel (frontend), pg_cron + Supabase Edge Functions (nightly jobs) |
| Media | Remotion (programmatic video), ElevenLabs (voiceover) |

## What it does

- **Per-player props** — predicts PTS/REB/AST/PRA for every active NBA player, compares to sportsbook lines, and returns OVER/UNDER recommendations with calibrated probabilities and a prediction range.
- **Game predictions** — team-level win probabilities from an ELO + Four Factors stacking ensemble.
- **Best bets feed** — nightly pipeline ranks the day's top 20 picks by model edge, filtered on minutes, confidence, and historical edge-performance caps.
- **Research** — game logs, rolling averages, home/away and matchup splits, defensive context, teammate/opponent absence scenarios.
- **Picks tracker** — authenticated users can save picks, auto-grade against live scores, and track ROI over time.

## ML pipeline

- **100 engineered features** per player-game: multi-window rolling averages (5/10/20 + EMA), opponent defensive context (def_rating, pace, eFG%, TS%, OREB/DREB%), home/away splits, matchup history, rest/travel, 3PT and FT rate rolling features, usage/minutes stability, recent-form trends.
- **Stacking ensemble** — Random Forest + Gradient Boosting + XGBoost + LightGBM + HistGradientBoosting with meta-learner, per-player per-stat.
- **Validation** — TimeSeriesSplit CV (no lookahead), Optuna Bayesian hyperparameter search, isotonic probability calibration, quantile regression for prediction ranges.
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
