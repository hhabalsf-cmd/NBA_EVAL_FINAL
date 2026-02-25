# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack ML-powered NBA player prop betting analysis platform with two prediction modes:
1. **Per-player prop predictions** — PTS/REB/AST/PRA lines vs ML model output
2. **Team-level game predictions** — ELO-based win/loss probabilities

The system fetches live NBA data, trains per-player ML models, evaluates betting lines, and surfaces edge recommendations via a React frontend with real-time SSE streaming.

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

# Validation: compare new vs old predictions on 10 real picks
python test_fixes.py
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

---

## Architecture

### ML Core — `nba_evaluator.py` (3000+ lines)

**`CacheManager`** — TTL-based caching: 24h player info, 1h game logs, 30min injuries, 1h team_stats.

**`NBADataScraper`** — Fetches NBA API game logs (2-3 seasons), scrapes injury reports, pulls OddsAPI betting lines. NBA API header fix: uses `Referer: www.nba.com` to avoid blocking.

**`NBADataScraper.get_team_defensive_stats(season='2025-26')`** — Two calls to `leaguedashteamstats.LeagueDashTeamStats`: one Advanced (for `DEF_RATING`, `PACE`) and one Base (for `OPP_AST`, `PACE` fallback). Returns dict keyed by team abbreviation with **lowercase** keys:
```python
{ 'OKC': {'def_rating': float, 'pace': float, 'opp_pts': float, 'opp_ast': float, 'pts_rank': int} }
```
**CRITICAL:** Always use lowercase keys (`def_rating`, `pace`, `opp_ast`) when reading this dict. Uppercase (`DEF_RATING`) will silently return the default fallback value. Fallback on API failure: all teams get `def_rating: 110, pace: 100`.

**`FeatureEngineer`** — Produces 60+ features per player per game:
- Rolling averages: 3/5/7/10/15/20 games, EMA
- Efficiency metrics: TS%, EFG%, AST/TOV ratio
- Opponent defensive features (requires `team_stats` arg): `OPP_DEF_RATING_NORM`, `OPP_PACE_NORM`, `OPP_AST_ALLOWED_NORM`, `OPP_DEF_RATING_ROLL10`, `OPP_PACE_ROLL10`
- Pace-adjusted stats: `PTS_PACE_ADJ`, `REB_PACE_ADJ`, `AST_PACE_ADJ` (scaled by 100/opp_pace)
- Opponent matchup history: `VS_OPP_AVG_PTS`, `VS_OPP_AVG_REB`, etc. (expanding window, shift(1), backfilled when missing)
- Home/away splits, B2B/rest days, per-36 stats
- Hot/cold streak detection (`IS_HOT`, `IS_COLD`), season phase indicators
- Interaction features: `B2B_VS_ELITE` (B2B + def_rating < 108), `HOT_VS_WEAK` (hot streak + def_rating > 116), `RESTED_HOME`
- Usage proxy (`USG_PROXY`, `ROLL_5_USG`, `ROLL_10_USG`)
- `FEATURE_COLS`: 57 canonical features used across all models

**`OddsAPI`** — Fetches from The Odds API. Key lookup order: function param → `ODDS_API_KEY` env var → `config.json` (root-level). Market map: `player_points→PTS`, `player_rebounds→REB`, `player_assists→AST`, `player_points_rebounds_assists→PRA`.
- **CURRENT STATUS: Quota exhausted** — free tier 500/500 requests used. Need a new API key in `config.json` to re-enable live odds. Odds are only used for auto-populating line inputs on PlayerPage; all other features work without it.

**`MLPredictor`** — Per-player, per-stat (PTS/REB/AST/PRA) models:
- **CV:** TimeSeriesSplit to prevent lookahead bias
- **Algorithms:** Random Forest, Gradient Boosting, XGBoost, LightGBM, stacking ensemble
- **`GB_STAT_PARAMS`:** Dict of per-stat GradientBoosting hyperparameters (max_depth, learning_rate, n_estimators)
- **Feature pruning:** Top features by 95% cumulative importance; cross-stat pruning prevents e.g. AST features dominating a PTS model
- **Quantile regression:** Separate 10th/90th percentile models for confidence intervals
- **Post-prediction corrections:** Learned residual correction (clipped), OVER-dampening, rolling feedback, injury-based minute scaling, minutes-based output scaling
- **`CONFIDENCE_CAPS`:** PTS 88%, REB 82%, AST 78%, PRA 80%
- **`BIAS_CORRECTION_BY_STAT`** and **`OVER_DAMPENING_BY_STAT`:** Asymmetric per-stat correction dicts
- **PRA formula:** 85% × (PTS_pred + REB_pred + AST_pred) + 15% × independent_PRA_model (combats composite error)
- **Persistence:** `models/{PlayerName}_model.pkl`

**`LineEvaluator`** — Compares prediction vs. betting line. Outputs: edge%, OVER/UNDER probability, recommendation strength (STRONG/MODERATE/SLIGHT).

### Extended ML Files

**`enhanced_predictor.py`** — Advanced ensemble and hyperparameter optimization:
- Stacking: XGBoost + LightGBM + RF + HistGB with meta-learner
- Bayesian hyperparameter search via Optuna (40 trials, 60s timeout)
- Probability calibration via isotonic regression
- `ELITE_DEFENSES = ['BOS', 'CLE', 'OKC', 'MIN', 'MEM']` / `WEAK_DEFENSES = ['WAS', 'UTA', 'POR', 'SAS', 'DET']` — **hardcoded from prior season, used only as binary flags in enhanced features, not for display logic**
- All optional deps (XGBoost, LightGBM, Optuna) have graceful fallback

**`game_predictor.py`** — Team-level win probability:
- Self-computed ELO ratings (MOV-adjusted)
- Four Factors: eFG%, TOV%, OREB%, FT rate
- Multi-window rolling + EMA features, travel/timezone effects, strength of schedule
- Stacking ensemble + isotonic calibration
- Persisted as `models/games/game_predictor.pkl`

---

### API Layer — `api/`

**`main.py`** — FastAPI app, CORS (localhost:5173, :3000), docs at `/api/docs`.

**All routes:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/players/search?q=` | Fuzzy player name match |
| POST | `/api/players/predict` | SSE streaming prediction |
| POST | `/api/players/predict/sync` | Blocking (non-streaming) alternative |
| POST | `/api/players/evaluate-line` | Single stat/line evaluation |
| GET | `/api/players/{name}/research` | Research data: game log, rolling avgs, splits, matchup context |
| GET | `/api/bets/today?min_edge=5.0&limit=10` | **SUNSETTED** — returns empty immediately |
| GET | `/api/bets/quick` | Returns empty (placeholder) |
| GET | `/api/picks?days=30&pending_only=false` | Pick history |
| POST | `/api/picks` | Create pick |
| PUT | `/api/picks/{id}/grade` | Grade a pick (won/lost) |
| DELETE | `/api/picks/{id}` | Remove pick |
| POST | `/api/picks/auto-grade` | Auto-grade ungraded picks via live scores |
| GET | `/api/picks/stats/performance` | Win rate, avg edge, ROI, by-stat breakdown |
| GET | `/api/picks/stats/profit` | Cumulative profit over time |
| GET | `/api/games/today` | Cached game predictions |
| POST | `/api/games/predict` | SSE streaming game predictions |
| GET | `/api/games/history?days=7` | Past predictions with results |
| POST | `/api/games/auto-grade` | Grade predictions against live scores |
| GET | `/api/games/stats/accuracy` | Accuracy by confidence bucket |

**SSE event shape:** `{stage, progress (0–100), message, data?}`

**Player predict SSE stages:** `fetching_data → engineering_features → predicting → evaluating_line → complete`

**Game predict SSE stages:** `fetching_games → loading_stats → building_features → predicting → complete`

**Services (all singletons):**
- `PredictionService` — wraps NBADataScraper + FeatureEngineer + MLPredictor + LineEvaluator. Has `get_team_stats()` (1h in-memory cache) and `get_player_odds()` (30min cache).
- `BestBetsService` — runs predictions across all today's players, ranks by edge%. Currently sunsetted.
- `GamePredictionService` — lazy-loads GamePredictor, trains if model not found

**Key schemas (`api/schemas/prediction.py`):**
- `PredictionRequest` — `{player_name, model_type, use_ensemble, retrain}`
- `StatPrediction` — `{stat, prediction, confidence, range_low, range_high, uncertainty_std, recent_avg}` (recent_avg = L10)
- `PredictionResponse` — full result with `game_info`, `opponent_context`, `vs_stats`
- `LineEvaluation` — `{stat, line, prediction, difference, recommendation, strength, prob_over, confidence, range, high_edge_warning}`
- `Pick` — includes `voided`, `void_reason`, `prob_over` fields
- `PlayerResearchResponse` — `{player_info, game_log, rolling_averages, splits, vs_elite_def, vs_weak_def, next_game, opponent_context}`
- `GamePredictionHistoryItem`, `GameAccuracyStats`

**Research endpoint (`api/routers/players.py` — `GET /api/players/{name}/research`):**
- Fetches game log (last 40 games), computes rolling avgs (L3/5/10/15/20), home/away/b2b/rest splits
- Elite/weak defense splits: top-10 and bottom-10 teams by `def_rating` (lowercase) from `get_team_stats()`
- Opponent context for next game: `def_rating`, `pace`, rank label (Elite/Strong/Average/Weak)
- Rank thresholds: ≤5 → "Elite Defense (Top 5)", ≤10 → "Strong Defense (#N)", ≤20 → "Average Defense (#N)", else → "Weak Defense (#N)"

---

### Frontend — `frontend/src/`

**Stack:** React 18, TypeScript, Vite 5, Tailwind CSS 3, React Query 5, Zustand 4, Recharts 2, Lucide React

**React Query config:** `staleTime: 5min`, `retry: 2`, `refetchOnWindowFocus: false`

**Query keys:** `['performance-stats']`, `['picks', pendingOnly]`, `['player-odds', name]`, `['team-injuries', name]`, `['todays-games']`, `['game-accuracy']`, `['pending-picks']`

#### Pages
- **`HomePage.tsx`** — dashboard: player search, live performance stats (win rate/ROI/record), Top Picks section (**sunsetted placeholder**), performance by stat breakdown
- **`PlayerPage.tsx`** — core prediction UI: SSE progress bar via `usePrediction`, 4 stat cards (PTS/REB/AST/PRA), confidence meters, L10 trend indicator, percentile range, line inputs (auto-populated from odds when available), evaluate-line button, save pick, "Research" button → `/research/{name}`
- **`ResearchPage.tsx`** — deep player research: 5 tabs — Overview (hit rate cards + rolling avg table), Game Log (last 20 games), Chart (stat trend over time), Splits (home/away/b2b/rest/vs-elite/vs-weak), Matchup (next game opponent context). Entry: "Research" button on PlayerPage or Research nav link.
- **`HistoryPage.tsx`** — pick history: Recharts line chart (cumulative profit), manual + auto grading, by-stat breakdown (PTS/REB/AST/PRA win record)
- **`ParlayPage.tsx`** — parlay builder: multi-pick selection from pending picks, dynamic odds calc, 6 sort options (edge, team, stat; bidirectional)
- **`GamesPage.tsx`** — game win/loss predictions: ELO probabilities, team records, two-bar probability gauge, collapsible key factors (MAJOR/MODERATE/MINOR), accuracy tracker
- **`LandingPage.tsx`** — public page: hero copy, CTA, Highest Edge Plays section (**sunsetted placeholder**), live performance metrics, How It Works, Track Record by stat
- **`SettingsPage.tsx`** — protected route stub

#### Components
- **`PlayerSearch.tsx`** — debounced autocomplete (300ms), keyboard nav (↑↓/Enter/Esc), headshots via `utils/nba.ts getNbaHeadshotUrl(player_id)`
- **`PredictionCard.tsx`** — single stat card: prediction number, confidence color (green ≥80%, orange ≥65%, red <65%), L10 trend arrow, range low–high
- **`BetCard.tsx`** — ranked best bet: green/red left border (OVER/UNDER), prob_over fill bar, click → `/player/{name}`
- **`GameCard.tsx`** — game prediction: team abbrev + record + net rating, two-bar win% gauge, collapsible key factors
- **`AccuracyTracker.tsx`** — record (W-L), streak, accuracy by confidence bucket (50–60%, 60–70%, 70–80%, 80%+)
- **`auth/`** — LoginForm, SignupForm, ProtectedRoute

#### Hooks & Stores
- **`hooks/usePrediction.ts`** — streaming lifecycle: `isLoading`, `progress` (0–100%), `stage`, `message`, `result`, `error`
- **`store/authStore.ts`** (Zustand) — mock auth (TODO: replace with real API). State: `user`, `isAuthenticated`. Actions: `login/signup/logout/clearError`
- **`store/parlayStore.ts`** (Zustand) — max 8 legs, no duplicate player+stat. Actions: `addLeg/removeLeg/clearParlay/hasLeg`
- **`store/themeStore.ts`** (Zustand, persisted to localStorage) — dark/light theme toggle. Toggle button (Sun/Moon icon) in `App.tsx` nav. CSS variables in `index.css` under `:root` (dark) and `:root.light`. Tailwind config uses CSS vars so `bg-bg-primary`, `text-text-primary` etc. respond dynamically.

#### API Client — `api/client.ts`
- `API_BASE = '/api'` (Vite proxies to localhost:8000)
- SSE functions: `predictPlayer(playerName, onProgress, options)`, `predictTodaysGames(onProgress)`
- `getPlayerResearch(playerName)` → `GET /api/players/{name}/research`
- `getPlayerOdds(playerName)` → `GET /api/players/{name}/odds` (returns `{found: false}` when quota exhausted)
- Parlay odds formula:
  ```ts
  const hitProb = (pick) => Math.min(85, Math.max(15,
    pick.prob_over ? (isOver ? pick.prob_over : 100 - pick.prob_over)
                   : (50 + Math.abs(pick.edge) * 1.5)
  ))
  const parlayOdds = legs.reduce((acc, leg) => acc * 1.909 * (hitProb(leg) / 100), 1)
  // 1.909 = standard -110 American odds decimal
  ```

#### Theme — `index.css`
CSS variables (dark theme default):
- `--accent: #C9A87C` (warm tan/gold — primary actions)
- `--bg-primary: #09090B`, `--bg-secondary: #131316`, `--bg-tertiary: #1A1A1F`, `--bg-elevated: #232329`
- `--accent-success: #6BBF8A` (green), `--accent-danger: #D4736E` (red)
- `--text-primary: #EDEDEC`, `--text-secondary: #8F8B87`, `--text-muted: #5C5955`
- Fonts: **Inter** (body), **JetBrains Mono** (stats/numbers)
- Light theme overrides under `:root.light` — class toggled by themeStore on `<html>`
- Responsive: bottom nav on mobile, top nav at `sm` breakpoint; safe area padding for notched phones
- **Always use `var(--x)` CSS variables, never hardcoded hex values**

**Vite alias:** `@` → `./src`

---

### Data Storage

**`picks_history.db`** (SQLite, auto-migrates missing columns):

`picks` table columns:
```
id, timestamp, player, player_id, team_abbrev, stat, line, prediction,
direction (OVER|UNDER), edge, confidence, opponent, is_home,
actual_result, won, model_type, game_date, graded_at,
voided (0/1), void_reason, prob_over
```

`game_predictions` table columns:
```
id, timestamp, game_date, home_team, away_team, home_team_id, away_team_id,
predicted_winner, home_win_prob, away_win_prob, confidence,
actual_winner, correct, key_factors (JSON), model_version, graded_at, extended_data (JSON)
```

- Picks are never hard-deleted — use `voided=1` + `void_reason` for soft-delete
- `won` is NULL until graded; `prob_over` stored for parlay/analysis use
- Excel mirror: `nba_picks_tracker.xlsx` (openpyxl)
- `config.json` — `{"odds_api_key": "..."}` — also reads `ODDS_API_KEY` env var

**Cache dirs (gitignored):** `./cache/`, `./data/`, `./history/`

**Models (gitignored):** `models/*.pkl`, `models/games/game_predictor.pkl`

---

### Current Player Models (50 active, as of 2026-02-24)

Alperen_Sengun, Andrew_Nembhard, Anthony_Edwards, Ausar_Thompson, Bilal_Coulibaly, Brandon_Ingram, Bryce_McGowens, Cade_Cunningham, Chet_Holmgren, De'Aaron_Fox, De'Anthony_Melton, Desmond_Bane, Devin_Vassell, Dyson_Daniels, GG_Jackson, Gui_Santos, Isaiah_Hartenstein, Isaiah_Joe, Jalen_Brunson, Jalen_Duren, Jalen_Johnson, Jamal_Shead, James_Harden, Jared_McCain, Jarrett_Allen, Jay_Huff, Julian_Champagnie, Julius_Randle, Karl-Anthony_Towns, Kevin_Durant, Lauri_Markkanen, LeBron_James, Luguentz_Dort, Max_Christie, Nickeil_Alexander-Walker, Nolan_Traore, OG_Anunoby, Onyeka_Okongwu, Payton_Pritchard, RJ_Barrett, Russell_Westbrook, Saddiq_Bey, Scottie_Barnes, Stephon_Castle, Tobias_Harris, Tristan_Vukcevic, Tyler_Herro, Tyrese_Maxey, Victor_Wembanyama, Zion_Williamson

---

## Key Patterns

- **SSE streaming:** `POST /api/players/predict` and `/api/games/predict` return Server-Sent Events. Frontend `usePrediction` hook drives real-time progress bar.
- **Per-player model caching:** MLPredictor saves/loads `.pkl` files on demand. Pass `retrain=True` in request body to force retraining from scratch.
- **Cross-stat feature pruning:** Prevents stat-contamination (e.g. AST-correlated features bleeding into PTS model).
- **95% cumulative importance threshold:** Features below this contribution are pruned before final training.
- **Quantile regression:** Dual 10th/90th percentile models produce `range_low`/`range_high` confidence bounds.
- **TimeSeriesSplit CV:** All models use temporal cross-validation — no lookahead bias.
- **Isotonic probability calibration:** Converts raw model outputs to calibrated true probabilities.
- **PRA reconciliation:** 85% component sum + 15% independent model to reduce composite drift.
- **Mutation-driven invalidation:** Grading a pick cascades `invalidateQueries` on `['picks']`, `['performance-stats']`, and `['cumulative-profit']`.
- **Singleton API services:** `PredictionService`, `BestBetsService`, `GamePredictionService` are module-level singletons.
- **Injury adjustments:** Usage redistribution applied when teammates are out; opponent weakening when key opponent players are out.
- **Defense flows into predictions via features:** `OPP_DEF_RATING_NORM` and `OPP_PACE_NORM` are fed into every model. The model learns weights from training data — defense is one signal among 57. VS_OPP head-to-head history can override the season-level defensive rating signal.

## Known Issues / Sunsetted Features

- **Best Bets (`/api/bets/today`, `/api/bets/quick`):** Both endpoints return empty responses immediately. Frontend shows static "Coming Soon" placeholder cards on HomePage and LandingPage. To re-enable: restore the `BestBetsService` call in `bets.py` and restore the query + `BetCard` rendering in both pages.
- **Live Odds (OddsAPI):** Free tier quota exhausted (500/500 requests used). Replace `odds_api_key` in `config.json` with a new key to re-enable. Only affects auto-population of line inputs on PlayerPage — all predictions work without it.
- **Research mode defensive classification bug (FIXED 2026-02-24):** `api/routers/players.py` was reading team stats with uppercase keys (`DEF_RATING`, `PACE`) but `get_team_defensive_stats()` stores them with lowercase keys (`def_rating`, `pace`). Fixed to use lowercase throughout.

## test_fixes.py

Validation script for ML changes. Loads 10 real stored picks (player, stat, line, old_pred, actual_result, won), runs full prediction pipeline, and prints a comparison table: old pred → new pred, delta, new edge%, edge cap filter hits, and net result changes. Run after any significant ML modification to verify predictions don't regress.

## batch_compare.py

Additional comparison/batch analysis script at root level (untracked).
