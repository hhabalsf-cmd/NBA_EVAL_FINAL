# CLAUDE.md

Full-stack ML-powered NBA player prop betting analysis platform with two modes:
1. **Per-player prop predictions** — PTS/REB/AST/PRA lines vs ML model output
2. **Team-level game predictions** — ELO-based win/loss probabilities

## Commands

### Backend
```bash
pip install -r requirements.txt          # ML core
pip install -r api/requirements.txt      # FastAPI layer

./start_api.sh                           # FastAPI at port 8000 (docs: /api/docs)
python nba_evaluator.py --interactive    # CLI (no API needed)
pytest tests/                            # Test suite
```

### Frontend
```bash
cd frontend && npm run dev   # Dev at http://localhost:5173
npm run build && npm run lint
```

Both servers must run simultaneously. Vite proxies `/api/*` → `localhost:8000`.

---

## Architecture

### ML Core — `nba_evaluator.py`

**`CacheManager`** — TTL caching: 24h player info, 1h game logs, 30min injuries, 1h team_stats.

**`NBADataScraper.get_team_defensive_stats()`** — Returns dict keyed by team abbreviation:
```python
{ 'OKC': {'def_rating': float, 'pace': float, 'opp_pts': float, 'opp_ast': float, 'pts_rank': int} }
```
**CRITICAL:** Always use **lowercase** keys (`def_rating`, `pace`, `opp_ast`). Uppercase (`DEF_RATING`) silently returns fallback. API failure fallback: `def_rating: 110, pace: 100`.

**`FeatureEngineer`** — 82 canonical features (`FEATURE_COLS`): rolling avgs (5/10 + EMA for PTS/MIN), efficiency metrics, opponent defensive features (`OPP_DEF_RATING_NORM`, `OPP_PACE_NORM`), enhanced opponent context (off_rating, net_rating, eFG%, OREB%, DREB%), matchup history, home/away splits, B2B/rest, hot/cold streak, rebound splits (OREB/DREB), 3PT shooting features, FT rate, foul trouble, schedule density, travel, Vegas lines. `extract_opp_stats()` helper extracts all opponent context from team_stats dict. 26 dead/redundant features pruned (see commit `7ab42e3`).

**`OddsAPI`** — Key lookup: function param → `ODDS_API_KEY` env var → `config.json`. Market map: `player_points→PTS`, `player_rebounds→REB`, `player_assists→AST`, `player_points_rebounds_assists→PRA`. **Status: quota exhausted** — replace key in `config.json` to re-enable (only affects line auto-population on PlayerPage).

**`MLPredictor`** — Per-player per-stat models (PTS/REB/AST/PRA):
- TimeSeriesSplit CV (no lookahead bias), stacking ensemble (RF + GB + XGBoost + LightGBM)
- Quantile regression for `range_low`/`range_high`, isotonic probability calibration
- `CONFIDENCE_CAPS`: PTS 88%, REB 82%, AST 78%, PRA 80%
- PRA formula: 85% × component sum + 15% independent PRA model
- Persistence: `models/{PlayerName}_model.pkl`

**`enhanced_predictor.py`** — Bayesian hyperparameter search (Optuna, 40 trials), advanced stacking. `ELITE_DEFENSES`/`WEAK_DEFENSES` are hardcoded binary flags only — not used for display logic.

**`game_predictor.py`** — ELO ratings (MOV-adjusted), Four Factors, stacking ensemble. Persisted at `models/games/game_predictor.pkl`.

---

### API Layer — `api/`

**`main.py`** — FastAPI, CORS (localhost:5173, :3000), docs at `/api/docs`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/players/search?q=` | Fuzzy player name match |
| POST | `/api/players/predict` | SSE streaming prediction |
| POST | `/api/players/predict/sync` | Blocking alternative |
| POST | `/api/players/evaluate-line` | Single stat/line evaluation |
| GET | `/api/players/{name}/research` | Game log, rolling avgs, splits, matchup context |
| GET | `/api/bets/today` | Daily best bets |
| GET | `/api/picks?days=30&pending_only=false` | Pick history |
| POST | `/api/picks` | Create pick |
| PUT | `/api/picks/{id}/grade` | Grade a pick |
| DELETE | `/api/picks/{id}` | Soft-delete (sets `voided=1`) |
| POST | `/api/picks/auto-grade` | Auto-grade via live scores |
| GET | `/api/picks/stats/performance` | Win rate, ROI, by-stat breakdown |
| GET | `/api/picks/stats/profit` | Cumulative profit |
| GET | `/api/games/today` | Cached game predictions |
| POST | `/api/games/predict` | SSE streaming game predictions |
| GET | `/api/games/history?days=7` | Past predictions with results |
| POST | `/api/games/auto-grade` | Grade predictions vs live scores |
| GET | `/api/games/stats/accuracy` | Accuracy by confidence bucket |

**SSE shape:** `{stage, progress (0–100), message, data?}`

**Services (singletons):** `PredictionService`, `BestBetsService`, `GamePredictionService`

**Key schemas (`api/schemas/prediction.py`):**
- `PredictionRequest` — `{player_name, model_type, use_ensemble, retrain}`
- `StatPrediction` — `{stat, prediction, confidence, range_low, range_high, uncertainty_std, recent_avg}` (recent_avg = L10)
- `LineEvaluation` — `{stat, line, prediction, difference, recommendation, strength, prob_over, confidence, range, high_edge_warning}`
- `Pick` — includes `voided`, `void_reason`, `prob_over`
- `PlayerResearchResponse` — `{player_info, game_log, rolling_averages, splits, vs_elite_def, vs_weak_def, next_game, opponent_context}`

**Research endpoint defense rank thresholds:** ≤5 → "Elite Defense (Top 5)", ≤10 → "Strong Defense (#N)", ≤20 → "Average Defense (#N)", else → "Weak Defense (#N)"

---

### Frontend — `frontend/src/`

**Stack:** React 18, TypeScript, Vite 5, Tailwind CSS 3, React Query 5, Zustand 4, Recharts 2

Organized by **feature**, not file type. Each feature folder contains its page, components, hooks, and API functions.

#### Feature Folders (`features/`)
| Folder | Contents | Key Files |
|--------|----------|-----------|
| `predictions/` | Player prop predictions | `PlayerPage.tsx`, `PredictionCard.tsx`, `StatChartModal.tsx`, `usePrediction.ts`, `api.ts` |
| `research/` | Player research & analysis | `ResearchPage.tsx`, 6 tab components (`OverviewTab`, `GameLogTab`, `ChartTab`, `SplitsTab`, `AnalysisTab`, `MatchupTab`), `ModelEdgeCard.tsx`, `types.ts`, `api.ts` |
| `games/` | Game predictions | `GamesPage.tsx`, `GameCard.tsx`, `AccuracyTracker.tsx`, `api.ts` |
| `picks/` | Pick history & tracking | `PicksPage.tsx`, `usePicksRealtime.ts`, `api.ts` |
| `home/` | Home & best bets | `HomePage.tsx`, `BetCard.tsx`, `api.ts` |
| `auth/` | Authentication | `LoginPage.tsx`, `SignupPage.tsx`, `LoginForm.tsx`, `SignupForm.tsx`, `ProtectedRoute.tsx`, `authStore.ts`, `types.ts` |
| `social/` | Profiles & leaderboard | `LeaderboardPage.tsx`, `PublicProfilePage.tsx`, `api.ts` |
| `settings/` | User settings | `SettingsPage.tsx`, `AvatarCropModal.tsx` |
| `landing/` | Marketing landing | `LandingPage.tsx` |

#### Shared (`shared/`)
- **`components/PlayerSearch.tsx`** — debounced (300ms) autocomplete, used by predictions, research, home
- **`components/UserMenu.tsx`** — nav auth menu (App.tsx)
- **`components/TermsModal.tsx`** — TOS acceptance modal
- **`utils/nba.ts`** — headshot URLs, team mappings
- **`lib/supabase.ts`** — Supabase client singleton
- **`store/themeStore.ts`** — dark/light toggle, persisted to localStorage

#### API Layer (`api/`)
- **`client.ts`** — `apiFetch` wrapper with auth token injection (~50 lines). All feature API functions import from here.
- **`types.ts`** — all shared TypeScript interfaces (PlayerInfo, Pick, GamePrediction, etc.)
- Each feature has its own `api.ts` that imports `apiFetch` from `../../api/client` and exports feature-specific functions.

#### Theme
- **Always use `var(--x)` CSS variables — never hardcoded hex values**
- Dark default, light overrides under `:root.light` in `index.css`
- `--accent: #C9A87C` (primary), `--accent-success` (green), `--accent-danger` (red)
- Fonts: Inter (body), JetBrains Mono (stats/numbers)

---

### Data Storage

**`picks_history.db`** (SQLite):
```
picks: id, timestamp, player, player_id, team_abbrev, stat, line, prediction,
       direction, edge, confidence, opponent, is_home, actual_result, won,
       model_type, game_date, graded_at, voided, void_reason, prob_over

game_predictions: id, timestamp, game_date, home_team, away_team, home/away_team_id,
                  predicted_winner, home/away_win_prob, confidence, actual_winner,
                  correct, key_factors (JSON), model_version, graded_at, extended_data (JSON)
```
- Never hard-delete picks — use `voided=1` + `void_reason`
- `config.json` — `{"odds_api_key": "..."}` (also reads `ODDS_API_KEY` env var)
- Cache dirs (gitignored): `./cache/`, `./data/`, `./history/`

---

## Key Patterns

- **SSE streaming:** `usePrediction` hook drives progress bar for player + game predictions
- **Per-player models:** Pass `retrain=True` to force retraining from scratch
- **Defense via features:** `OPP_DEF_RATING_NORM`/`OPP_PACE_NORM` fed into all models — one signal among 57. VS_OPP history can override season-level defensive signal
- **Mutation invalidation:** Grading cascades `invalidateQueries` on `['picks']`, `['performance-stats']`, `['cumulative-profit']`
- **Injury adjustments:** Usage redistribution when teammates out; opponent weakening when key opponents out

## Known Issues / Sunsetted Features

- **Live Odds**: Quota exhausted (500/500). Replace `odds_api_key` in `config.json`. Only affects line auto-population on PlayerPage.

## Security Policy

When you find a security vulnerability, flag it immediately with a WARNING comment and suggest a secure alternative. Never implement insecure patterns even if asked.
