# Handoff — NBA Prediction Model: Overfitting/Leakage Remediation + Unbiased Backtest

**Date:** 2026-08-18 · **Repo:** `/Users/hhabal/Downloads/Projects/NBA/EVAL` (git, branch `main`, DO NOT commit/push — pushing `main` triggers Vercel redeploy; leave everything in the working tree until the user asks)

**Kickoff prompt for the new session:**
> Read `docs/plans/2026-08-18-model-remediation-handoff.md` and continue from "Where to resume". Use Opus subagents for implementation, verify each stage, and don't commit or push.

---

## Why this work exists

Deep-dive audit (2026-08-18) of the per-player prop model (`MLPredictor` in `nba_evaluator.py`, ~5460 lines) concluded: point-estimate overfitting is NOT the main problem (holdout MAE ≈ train OOF per `docs/holdout_eval_with_coverage.md`), but these defects corrupt accuracy and calibration:

1. **Target leakage (HIGH):** 5 features computed from the current game's own box score, no `.shift(1)`: `AST_TOV_RATIO` (`nba_evaluator.py:1265` — leaks AST into the AST model), `OREB_RATE` (`:1280`), `FG3_RATE` (`:1288`), `FT_RATE` (`:1296`), `PF_PER_MIN` (`:1304`), plus derived `OREB_RATE_x_OPP_OREB` (`:1590`). Serve time reads the *previous* game (`get_prediction_features:1748`) → leakage in training AND train/serve skew at inference.
2. **CV hygiene (MED):** `StandardScaler.fit_transform` on full data before CV (`:2574`; also `game_predictor.py:1748`); residual/calibrator/ensemble OOF use un-purged `TimeSeriesSplit` (`:2363,:2400,:2464,:2699,:2708`) while `_weighted_cv_mae` ignores its `tscv` arg (`:2179`); feature selection fit on full data then re-scored on the same folds (`:2285,:2629-2632`); Optuna final models silently drop early stopping (`:2601-2603,:2770-2772`); Optuna objective uses only the last fold's MAE (`:2239`).
3. **Calibration gap (MED):** CQR correction + `interval_to_std_divisor` computed and persisted (`:2475-2503`) but never consumed — `get_confidence`/`_quantile_band` hardcode 2.56 (`:3488`). Raw 80% intervals actually cover ~0.51–0.67.
4. **Residual model train/serve skew (MED):** serve vector passes `recent_avg` twice + hardcoded std 3.0 (`:3115-3120`) vs real shifted rolling features at train (`:2379-2387`).
5. **Selection contradiction (HIGH — FIXED, see below):** `scripts/daily_best_picks.py` ranked by `abs(edge)`, the rule `docs/backtest_pick_rules.md` (N=106, 37.7% WR overall) proved loses.
6. **No unbiased evidence:** only 106 graded picks (selection-biased). An unbiased walk-forward backtest was built (see below).

**User decisions (already made — do not re-ask):** fix HIGH+MED only; **delete the player-model fleet now, retrain at a later date** (it's the offseason); build + run the unbiased backtest before AND after fixes; Fable plans, **Opus subagents write the code**, final audit at the end; auto mode (proceed without pausing between stages).

Full plan with all task details: `/Users/hhabal/.claude/plans/do-a-deep-dive-stateful-charm.md` (read it — it is the authoritative task spec; its file:line references were verified against the code).

## State of the working tree (uncommitted, on `main`)

- **`scripts/daily_best_picks.py` (modified — Task 3 DONE):** selection now goes through the real `LineEvaluator.evaluate`; accepts only TARGET band [70, 80) (`SELECT_PROB_MIN/MAX` imported from `LineEvaluator.PROB_PICK_WINS_TARGET_LO/HI`); ranks by `abs(prob_pick_wins − SELECT_PROB_SWEET_SPOT)` with sweet spot 73.0 (matches `BestBetsService`, `api/services/prediction_service.py:869`); edge kept as display metadata only; output schema (21 keys → `db.save_daily_picks`) unchanged. Verified: offline harness + band/ranking smoke test passed; pytest failures are pre-existing network/sandbox ones only (98 pass / 20 network-fail / 3 skip of 121).
- **`scripts/backtest_unbiased.py` (new — Task 1 script DONE):** unbiased walk-forward backtest generalizing `scripts/eval_holdout.py`. 58 curated players, `--players/--limit/--train-games/--workers` flags, all 4 stats incl. reconciled PRA, per-stat N/MAE/bias/RMSE/train-OOF-gap, 80% coverage raw+CQR, pseudo-line calibration (pred ± 0.5/1.5/2.5 + no-lookahead season median) with decile reliability + Brier. Three deliberate fidelity choices (documented in its caveats output): drops actual-stat columns pre-predict (removes eval_holdout's dynamic-floor lookahead), calls `_update_recent_averages(history)` per step (mirrors production), stamps history with the current season string to neutralize spurious early-season damping in historical replay.

## Where to resume

**Step 0 — collect the baseline report.** A background run was in flight at handoff: `python3 scripts/backtest_unbiased.py --train-games 60 --workers 5` (PID 97988). Check for `docs/backtest_unbiased_baseline_2026-08-18.md`; if absent, check the process, and if dead re-run (~15 min, set `NBA_EVAL_DISABLE_TF=1`). Early 2-player signal matched the audit: raw 80% coverage 0.40–0.70, CQR over-corrects to 0.90–0.95, predicted OVER prob exceeded realized in every decile, Brier ≈ 0.236. Record the full-run headline numbers — this is the "before" measurement and MUST predate any `nba_evaluator.py` change.

**Step 1 — Tasks 2+4+5+6+6b in ONE Opus agent** (all in `nba_evaluator.py`; single agent avoids edit conflicts). Per the plan file: de-leak the 5 ratio features via shift with identical train/serve definitions; CV hygiene (per-fold scaler, `_purged_splits` everywhere OOF is produced, fix `_weighted_cv_mae`, Optuna keeps early stopping + mean-fold objective, selection on fold-train only); wire persisted `interval_to_std_divisor`/`cqr_correction` into `get_confidence`/`_quantile_band`/`ProbabilityCalculator` with fallback guards; residual-model serve parity (skip correction rather than fabricate inputs); trade awareness (`GAMES_WITH_CURRENT_TEAM`, `TEAM_CHANGED_RECENT` from MATCHUP column, shifted, + confidence damping when < 7 games with current team, analogous to `_early_season_damping:3517`). ALSO: add `PROB_PICK_WINS_SWEET_SPOT = 73.0` to `LineEvaluator` and switch `prediction_service.py:869` and `daily_best_picks.py` (`SELECT_PROB_SWEET_SPOT`) to import it.

**Step 2 — Task 7 tests** (`tests/test_leakage_guards.py` + extensions): leakage guards per ratio feature (synthetic log, extreme game-N values must not move row-N features), train/serve parity, purged-split assertions, Optuna early-stopping presence, CQR wiring (not 2.56), trade features + damping, daily-picks band/ranking. Suite: `NBA_EVAL_DISABLE_TF=1 python3 -m pytest` — 121 collected today; 98 pass; the 20 failures are pre-existing Supabase DNS/auth sandbox failures (test_game_log_cache, test_supabase_auth, test_scenarios) — do not chase them, but do not add new failures. Canary: `tests/test_ml_season.py::TestAllStatsTrained`.

**Step 3 — Task 8 post-fix backtest:** re-run `scripts/backtest_unbiased.py` (same flags) → `docs/backtest_unbiased_postfix_<date>.md` + comparison vs baseline. Acceptance: OOF-vs-holdout MAE gap not wider; AST MAE improves or holds; coverage moves toward 0.80; calibration deciles flatten; Brier improves.

**Step 4 — Task 9 fleet deletion (destructive — LAST, only after Steps 2–3 pass):** enumerate `model_storage.list_player_models()` (~133 expected, bucket `ml-models`, prefix `players/`), record count, delete objects under `players/` only. Leave `games/` prefix and local `models/games/game_predictor.pkl`. Do NOT run `pretrain_all_players.py` — retraining deferred per user. Note to user: first prediction per player will cold-train.

**Step 5 — Task 10 final audit:** full pytest counts; code-review agent over `git diff` (focus: shift semantics, fold indexing, CQR fallback guards); smoke `scripts/eval_holdout.py` on 2 players to prove train→save→load→predict→confidence; fix CRITICAL/HIGH findings; re-run tests; summarize before/after metrics for the user.

## Environment facts

- System `python3` (3.9.6) has all deps (sklearn 1.6.1, pandas 2.3.3, nba_api); no venv. Always set `NBA_EVAL_DISABLE_TF=1`.
- Offseason: live endpoints return nothing; nba_api historical 2025-26 data is complete. Network to Supabase may be sandbox-blocked in subagents (source of the 20 pre-existing test failures).
- Deferred/out of scope (do not fix now): 5 dead features (`INJURIES_*`, `VEGAS_*_NORM`), missing-feature zero-fill, `update()` importance-zip bug, unreachable `line_predictor.py` + 74 stale pkls, drift-detection wiring, historical opponent-stat snapshots (season-aggregate opponent stats contaminate historical rows — documented caveat in both backtest harnesses), stale `~/.claude/skills/model-accuracy-audit` + `~/.claude/agents/loss-investigator.md` definitions (57-feature era), fleet retrain.
