# Prop Model Investigation — Consolidated Summary (2026-08-19 → 2026-08-23)

**Verdict: the per-player prop model has no usable edge. It is measurably worse than a
ten-game rolling average on every stat. Do not stake money on it.**

Four reports feed this summary. Read them for detail; this is the through-line.

| Report | What it establishes |
|---|---|
| `backtest_unbiased_phase0_2026-08-22.md` | New reference baseline — the harness now measures the model production actually serves |
| `backtest_unbiased_phase1_2026-08-22.md` (+ `_stale_control_`) | Serve path corrected; the staleness it fixed was costing ~nothing |
| `backtest_unbiased_phase2_2026-08-22.md` | Calibrator trained on the served quantity; invariant 1.398 → 1.0000 |
| `diagnosis_resolution_failure_2026-08-23.md` | Why none of it mattered |

---

## 1. The evidence

All figures below are on the same 44 players / 606 held-out games / 2,424 rows.
Baselines use `.shift(1)`, so they contain no lookahead. **Independently reproduced
outside the diagnostic agent, matching to three decimals.**

| Stat | Model | L10 mean | Season median | Season mean | EWMA5 |
|---|---:|---:|---:|---:|---:|
| PTS | **6.517** | 6.159 | 6.121 | 6.088 | **6.065** |
| REB | **2.546** | 2.483 | 2.439 | **2.427** | 2.459 |
| AST | **1.885** | 1.813 | 1.812 | 1.806 | 1.801 |
| PRA | **7.637** | 7.335 | 7.422 | 7.394 | **7.267** |

> **Correction (2026-08-25):** the AST/EWMA5 cell above read **1.775** until this
> date. That is **L20's** figure, not EWMA5's — AST EWMA5 is **1.801**. When this
> table was condensed from `diagnosis_resolution_failure_2026-08-23.md` §3 the L20
> column was dropped and its bolded value carried into the EWMA5 slot. PTS, REB and
> PRA transcribe correctly; AST was the only affected cell. The diagnosis §3 table
> was right all along. This matters because Track B's exit criterion is stated
> against EWMA5 / L10 / season median, and the wrong number made the pooled model
> look like it failed that criterion on AST when it passes it (1.792 vs 1.801). The
> pooled model does still lose to **L20** on AST — see
> `docs/pooled_model_2026-08-25.md` §1.

The model loses on all four. Paired bootstrap: **15 of 20 comparisons are
statistically distinguishable losses, 5 ties, 0 wins.** Per player, the model beats
the best trivial baseline on **4 of 44** for PTS.

**Directionally it is worse than a coin weighted by base rate.** Median-line AUC
**0.536** vs L10's 0.583. Sign accuracy 53.3% — below *always betting the over*
(55.1%). Staking at −110 on 2,187 median-line samples: model 53.3%, always-over
55.1%, L10 rolling mean 57.4%. The model finishes last.

## 2. Root cause: p/n = 1.35

**Eighty-one features fit on sixty training rows — more parameters than
observations.** A ridge on a *single* feature (`ROLL_10_<stat>`) beats the full
81-feature production ensemble on MAE for every stat (PTS 6.100 vs 6.517), and
accuracy degrades monotonically as features are added. Importance is diffuse: top
feature 17.2%, ~22 features above 1%, and for PTS **no rolling mean of points is in
the top twelve** — `GAMES_THIS_SEASON` and `TRAVEL_MILES_NORM` outrank the player's
own scoring level.

Within-player correlation of prediction with outcome, against a 2,000-draw
permutation null, is **−0.128 for PTS (significantly negative)** and ~0 elsewhere.
There is no resolution to recover.

## 3. The three phases each fixed a real bug and moved nothing

That is not a contradiction — it is the diagnosis confirming itself. None of the
defects were the binding constraint.

**Phase 0 — the instrument was wrong.** The backtest called `create_features` with
`team_stats=None`, so 17 declared features were absent and silently zero-filled at
`nba_evaluator.py:3266`. It had been measuring a **69-feature** model while
production served 81. Fixed via point-in-time opponent context
(`scripts/team_stats_asof.py`, exact team box scores from one `leaguegamelog` call)
and a disk-cached game-log fetch (~33 min → **0.15 s**).
*Result: PTS MAE 6.65 → 6.52, Brier flat.*

**Phase 1 — the serve path was one game stale.** `get_prediction_features` read
`iloc[-1]` of an already-shifted column, serving mean(*n−k−1..n−2*) where
mean(*n−k..n−1*) was correct — an 8.6-point error on `ROLL_5_PTS` for Jokic. Fixed
with a synthetic next-game row through `create_features`'s unused `game_info` hook.

The plan assumed the backtest would price this. **It could not** — the harness read
the row of the game being predicted, which already carried correct lag-1 values, so
it never had the bug. A purpose-built `--stale-serve` control gave the real answer:
**staleness was costing ~0** (<0.8% relative MAE, mixed signs; overall Brier
marginally *worse*).
*Result: correctness, not accuracy.*

**Phase 2 — the calibrator was trained on the wrong quantity.** Offsets of ±2σ over a
divisor of σ+0.1 meant **σ cancelled**, leaving a fixed 9-point lattice identical for
every player and stat (verified: max spread 0.0089 across σ ∈ [1, 25]). Serve then
passed a quantity ~1.4× larger. Fixed by resequencing to quantile OOF → CQR → Platt
and fitting against the per-row CQR-corrected quantile std.
*Result: invariant 1.398 → **1.0000**, Brier 0.2407 → 0.2387, raw 80% coverage
~0.57 → 0.66–0.70. The 60–80% reliability band did not move.*

Phase 2 predicted its own epitaph: probabilities got **more** confident, not less,
because a correctly-fitted Platt map must sharpen a too-wide std. The calibrator was
sharpening a prediction with AUC ≈ 0.50 — manufacturing confidence out of noise.

## 4. The benign explanation was tested and rejected

The most plausible defence was that the season-median pseudo-line is simply
adversarial. It is the opposite. League-wide on 33,414 rows, the median line is
**generous** to a form-tracker: over-rate climbs monotonically 29% → 72% (PTS) and
24% → 77% (AST) as `(L5 − median)/σ` moves from −1 to +1. On the model's own sub-30%
picks (N=171), realized 50.9%, with form saying *over* by +0.058σ while the model
said under by −0.625σ. It takes a large short position against a signal a one-line
rolling average captures.

## 5. What remains unknown — and it is larger than previously stated

**Every calibration number in all four reports is against synthetic pseudo-lines.**
`manual_lines` is empty. Beating a player's season-to-date median is not evidence of
beating a sportsbook.

Worse: move the pseudo-line from a season median to a merely **L10-aware** line and
the recent-form signal collapses from AUC ~0.60 to **0.51–0.56**. Essentially all
apparent signal at the median line is line staleness — an artifact of how the
benchmark is built. That artifact is what invited three phases of chasing.

## 6. Recommendations, ranked

1. **Acquire real closing lines.** Log to `manual_lines` daily via
   `POST /api/bets/lines`. Hard precondition — every number above is uninterpretable
   without it. Low cost.
2. **Replace per-player fitting with one pooled cross-player model.** Demonstrated:
   a ridge on 9 recency features trained on 2023-24 league data alone scores PTS
   **6.004** / REB 2.430 / AST 1.792 / PRA 7.252 on the same holdout (vs 6.517 /
   2.546 / 1.885 / 7.637), AUC 0.574–0.628 (vs 0.532–0.555). Turns n=60 into
   n≈33,000 and fixes p/n directly. **Highest EV, already measured.**
3. **Cut 81 features to under 10.** Best EV per unit effort; composes with (2).
4. **Shrink probabilities toward the 51–53% base rate.** Fixes Brier and reliability
   mechanically. A truthfulness fix, not an edge fix.
5. **Real minutes projection.** Oracle minutes are worth 13.6% (PTS) to 20.2% (PRA)
   MAE — but L10-minutes recovers **exactly zero** of it, so it needs injury/rotation
   data not currently ingested. Highest ceiling, high cost.
6. **Stop investing in the uncertainty/calibration path.** Three phases, three real
   bugs, no movement. Negative EV to continue.
7. **Retire or relabel the pseudo-line calibration section** in the reports — its ROI
   is a pure function of how the pseudo-line is constructed.

## 7. State of the tree

**Nothing committed, nothing pushed.** `HEAD` is still `b8f9ac7`; `main`
auto-deploys to Vercel, so all work is deliberately uncommitted.

Test suite: **449 passed, 20 failed, 3 skipped** — the 20 are pre-existing
(`test_auth`, `test_game_log_cache`, `test_scenarios`, `test_supabase_auth`) and
predate this work.

**Production code changed:** `nba_evaluator.py` (81 features declared and built —
5 dead declarations removed, 6 built-but-undeclared computations removed; synthetic
next-game row; resequenced calibrator; stats.nba.com fallback),
`api/services/prediction_service.py`, `scripts/daily_best_picks.py`, `CLAUDE.md`.

**New:** `scripts/team_stats_asof.py`, `scripts/check_calibrator_invariant.py`,
`scripts/diagnose_{dump,analyze,league,tiny}.py`,
`scripts/_prewarm_backtest_cache.py`, `tests/test_{upcoming_game_row,
probability_calibration, team_stats_asof, backtest_opponent_context,
backtest_serve_path}.py`.

**Also fixed en route:** BallDontLie returns 401 for the current season, which was
silently dropping 2025-26 entirely. `get_player_game_log` now falls back
BDL → stats.nba.com → Supabase (Jokic 190 → 269 rows). Note `bdl_to_nba` is
degenerate — it echoes its input — so ids resolve via the game-log mirror plus
nba_api's static roster.

`models/Stephen_Curry_model.pkl` is a single complete model from the abandoned
retrain; the fleet is otherwise empty and cold-trains on demand.

### Two harness bugs worth remembering

- Phase 0's harness had a **real lookahead**: `prediction_row()` stripped PTS/REB/AST
  but not the derived `PRA`, so `predict`'s dynamic floor read the realized PRA of
  the game being predicted. Phase 0's PRA figures were optimistic.
- Production pools 3 seasons while the harness trains on 60 rows. A paired
  multi-season run (60 → median 139 rows) improved MAE 2.3–3.9% and **still lost to
  every trivial baseline**; median-line AUC got *worse*, 0.536 → 0.493.
