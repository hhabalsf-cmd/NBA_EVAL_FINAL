# Patch 1.9 — Final Pre-Season Hardening (2026-08-06)

The last patch before **2.0 — the 2026-27 season**. Executed as the four-phase
pre-season fix plan from the Aug 6 full-codebase audit. Commits `45e7dc8` → `4c8a3ea`.

---

## Phase 1 — Season Blockers

| ID | Fix |
|----|-----|
| B1 | `nightly_sync.py` no longer hardcodes `'2025-26'` — season resolves at call time, so the Oct 1 rollover feeds the new season automatically |
| B2 | **All game-date logic unified on Eastern Time.** `season_utils` gained `ET`, `now_et()`, `today_et()`, `today_et_str()`; every read/write/fallback/grading-gate in `db.py`, bets router, game service, `game_predictor`, `nba_evaluator`, and `daily_best_picks` uses them. UTC servers previously rolled the date at 7-8 PM ET — blanking the site every evening and orphaning evening manual lines. pg_cron grading jobs moved **live** from 04:30/04:35 to 05:30/05:35 UTC so they run past ET midnight in both EST and EDT |
| B3 | Daily picks pool **3 seasons** for the 15-game eligibility gate and training logs (new `db.get_game_logs_multi_season()`) — October no longer generates zero picks. Team derivation uses the most recent matchup, not alphabetical `MAX()` |
| B4 | `SelectiveGZipMiddleware` exempts `text/event-stream` — SSE progress bars no longer freeze at 0% (GZip buffered the whole stream) |
| B5 | Working model-refresh path: `pretrain_all_players.py --force / --max-age-days` (default 7) replaces skip-if-exists; `MLPredictor.load()` checks Supabase Storage for a fresher copy when the local pickle is stale |
| B6 | `api/requirements.txt` is self-sufficient for Railway (nba_api, python-dotenv, xgboost, lightgbm, scientific core; scikit-learn pinned `>=1.6.1,<1.7` for pickle compat). Root `requirements.txt` = dev superset |
| B7 | Env checklist deferred — Railway + Vercel intentionally down for offseason (see “Before 2.0” below) |

## Phase 2 — Security Hardening

| ID | Fix |
|----|-----|
| S1 | Registration cap enforced **server-side**: `BEFORE INSERT` trigger on `profiles` (advisory-locked, cap 10), applied live + committed as `supabase/limit_registrations.sql`. Client check kept as UX |
| S2 | Rate limiting actually enforced (`SlowAPIMiddleware` added — the 120/min default was dead config); limiter key uses the **rightmost** `X-Forwarded-For` entry (leftmost was client-spoofable) |
| S3 | Auth required on all expensive ML endpoints: predict, predict/sync, research, scenarios, odds, team-injuries, evaluate-line, games predict. Frontend already sends Bearer via `apiFetch` on every call site |
| S4 | `require_admin` (403 unless `profiles.role = 'admin'`) on manual-lines POST/DELETE and manual game grading; owner promoted to admin; frontend hides the Lines panel and Grade buttons from non-admins |
| S5 | `CatchAllExceptionMiddleware` registered inside CORS — 500s return JSON **with** CORS headers instead of an opaque browser network error |

## Phase 3 — ML Accuracy

| ID | Fix |
|----|-----|
| M1/M2 | `ALL_STATS = [PTS, REB, AST, PRA]`; `train()`/`update()` default to all four with PRA handled solely by its dedicated blocks — the old 3-stat `update()` default silently dropped PRA artifacts on every 7-day self-heal retrain. Daily picks train all four stats |
| M3 | `GAME_NUM`/`SEASON_PHASE` computed **per season** (concatenated 3-season logs made every current-season game look late-season). New `GAMES_THIS_SEASON` feature (84 total) — takes effect at the October retrain |
| M4 | Early-season transparency: < 10 current-season games → confidence ×0.75-1.0, std ×1.3-1.0 (linear taper); `games_this_season` in the prediction response; “Early-season estimate” badge on prediction cards; October team stats = prior season regressed 50% to league mean, blended by games/10 (was a flat identical 110/100 for all 30 teams) |
| I10 | Season constants resolved at call time inside `nba_evaluator` (import-frozen constants deprecated) |
| I11/I12 | CLI `find_best_bets` routes through `line_sources` (OddsAPI → manual fallback); OddsAPI key resolution delegated to `line_sources._resolve_odds_api_key` so `config.json` works everywhere |
| — | `NBA_EVAL_DISABLE_TF=1` skips the optional TensorFlow import (not installed in production; deadlocks restricted shells) |

Deferred by plan: R7 Four Factors refit (optional), R6 DARKO, R3 PRA copula.

## Phase 4 — Cleanup, Docs, Tests

- **CLAUDE.md** rewritten accurate: 84 features, GBM-only MLPredictor + 3-tier model storage, Supabase schema (SQLite section removed), middleware order + auth surface, ET-date contract, Vite 6
- **`npm run lint` revived** (eslint 9 flat config, `eslint.config.mjs`) — surfaced and fixed a real conditional-`useQuery` bug in `MatchupTab`, 4 `any` casts, a missing hook dep
- **`pyproject.toml`** registers pytest marks (`unit` / `integration` / `slow`); new `tests/test_line_sources.py`, `tests/test_model_storage.py`
- Root React **ErrorBoundary** (crash → reload prompt, not blank page); `theme-color` meta matches `--bg-primary`; last hardcoded hex values tokenized
- `TEAM_TIMEZONE` → IANA zones with DST-aware offsets (Phoenix was wrong half the year); Sleeper NBA-week derives from the current season (was frozen at 2024); dead root `vercel.json` and dead assignments removed
- **348 MB of stale local model pickles pruned** — all 133 verified present in the Supabase `ml-models` bucket first; `load()` re-downloads on demand

## Test State

- 87 tests passing locally (+1 slow model-training test, +2 env-guarded skips)
- New coverage: ET/DST boundary instants, grading-cron timing, gzip-vs-SSE (HTTP + ASGI), `should_skip` matrix, multi-season loader, XFF rate-limit key, 500-with-CORS, admin gate, line-source fallback, model storage keys
- Run on a full-env machine: `tests/test_auth.py`, `tests/test_supabase_auth.py`, `tests/test_scenarios.py`, `tests/test_game_log_cache.py`

## Before 2.0 (Season Launch Checklist)

1. **Revive Railway + Vercel.** Everything (frontend bundle `VITE_API_URL`, Supabase cron jobs 16-21, `frontend/vercel.json` CSP) points at `https://nbaevalfinal-production.up.railway.app` — keep that domain or update all three together. Verify Railway env: `ALLOWED_ORIGINS`, `FASTAPI_SERVICE_KEY`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
2. **Prod smoke test** after revival: SSE progress streams; auth matrix (unauth→401, non-admin→403, admin→200); `/api/bets/today` after 00:00 UTC returns the ET-day picks.
3. **~Oct 15-18:** `python scripts/pretrain_all_players.py --force` so every model embeds the new features + fresh data before opening night (~Oct 21). Then `scripts/eval_holdout.py` + `scripts/audit_calibration.py` — expect no PTS/REB/AST regression and tighter PRA.
4. Decide on an OddsAPI key purchase (manual lines remain the working fallback).
