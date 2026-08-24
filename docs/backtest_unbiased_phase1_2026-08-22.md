# Unbiased Walk-Forward Backtest — Phase 1 — synthetic next-game row (2026-08-22)

**Headline: the one-game feature staleness was costing almost nothing measurable,
and it did not move the 60–80% reliability band at all.**

Phase 1 made production serve the *upcoming* game instead of the last completed
one. Two things follow, and they are easy to conflate:

1. **Against the Phase 0 baseline this run is numerically identical** (PTS/REB/AST
   MAE, all coverage numbers, and overall Brier match to the reported precision;
   only PRA moves, by +0.01 MAE (player mean) and +0.01 RMSE). That is *not*
   because the fix did nothing. It is because **the Phase 0 harness never had the
   staleness bug**: it read the feature row of the game being predicted directly
   out of a full-log frame, and that row already carried correct lag-1 values.
   The bug lived only in `get_prediction_features`, which the harness never
   called. Phase 1 aligns production *to* the harness, not the other way round —
   so the harness cannot show the bug being fixed, because it never showed the
   bug.
   *(The PRA drift is a small lookahead the Phase 0 harness had and this one does
   not: its `prediction_row()` stripped PTS/REB/AST but not the derived `PRA`
   column, so `predict`'s dynamic floor read `max(4.0, 0.5 × the realized PRA of
   the game being predicted`). The served vector has no `PRA` column at all, so
   the floor is now the constant 4.0. Phase 1's PRA is very slightly worse and
   very slightly more honest.)*

2. **The cost of the staleness is measured by `--stale-serve`**, which reproduces
   the pre-Phase-1 production path exactly — identical schedule context, frame
   rolled back to the last completed game — over the same games and the same
   fitted models. That comparison is below.

### Staleness cost: pre-Phase-1 serve path → Phase 1 serve path

| Stat | MAE pooled (stale → fresh) | MAE player-mean | RMSE | Brier |
|---|---|---|---|---|
| PTS | 6.52 → 6.52 (**0.00**) | 6.65 → 6.62 (−0.03) | 8.27 → 8.31 (**+0.04**) | 0.2649 → 0.2650 (+0.0001) |
| REB | 2.57 → 2.55 (−0.02) | 2.56 → 2.54 (−0.02) | 3.28 → 3.23 (−0.05) | 0.2336 → 0.2346 (**+0.0010**) |
| AST | 1.89 → 1.89 (**0.00**) | 1.94 → 1.93 (−0.01) | 2.56 → 2.54 (−0.02) | 0.1960 → 0.1958 (−0.0002) |
| PRA | 7.65 → 7.64 (−0.01) | 7.83 → 7.83 (0.00) | 9.75 → 9.75 (0.00) | 0.2668 → 0.2665 (−0.0003) |

Overall Brier: **0.2406 → 0.2407**. Held-out coverage: 58 / 44 / 14 in both.

Point accuracy improves in the right direction on 7 of the 8 MAE cells, but by
**0.00–0.03**, i.e. under 0.8% relative — and PTS RMSE moves the *wrong* way.
This is a paired comparison (same games, same fitted models, only the served row
differs), so the sign is probably real; the magnitude is not material.

### Did the 60–80% reliability band move? **No.**

| Decile | Gap, stale serve | Gap, Phase 1 serve |
|---|---:|---:|
| 60-70% | +11.4 | +10.9 |
| 70-80% | +9.7 | +10.3 |

The 60-70% bucket tightens by 0.5pp and the 70-80% bucket loosens by 0.6pp — a
wash. The median-line low deciles, the failure the plan flagged as *only*
plausibly fixable here, are essentially unchanged: 20-30% goes from −29.1 to
−25.6 and 30-40% from −22.1 to −21.8, both still catastrophic. **Phase 1 was the
plausible lever for the median-line resolution failure and it did not move it.**
Per the plan's own decision rule, the next question is feature/model quality, not
calibration.

What Phase 1 *does* buy is correctness rather than accuracy: production no longer
serves a one-game-stale vector, `POSITION_x_OPP_DEF` / `POSITION_x_OPP_PACE` no
longer multiply against last night's opponent, `SEASON_PHASE` is no longer off by
one, `estimate_minutes` reads a current `ROLL_20_MIN_NUMERIC`, and `DAYS_REST` /
travel / head-to-head are correct by construction instead of by a
`datetime.now()` approximation. None of that shows up in a harness that was
already serving the correct row.


- **Season:** 2024-25
- **Train:** first 60 feature rows per player (single fit, never refit)
- **Test:** every remaining row, predicted one at a time
- **Pipeline:** `full (ensemble + meta-learner)`
- **Stats:** PTS, REB, AST, PRA (PRA = reconciled 0.85·(P+R+A) + 0.15·independent)
- **Players attempted / evaluated / skipped:** 58 / 44 / 14
- **Held-out predictions:** 2424
- **Pseudo-line probability samples:** 16729
- **Model width under test:** 81 of 86 declared `FEATURE_COLS` are actually built by `create_features`; the rest are zero-filled by `predict`
- **Opponent context:** point-in-time via `scripts/team_stats_asof.py` — team aggregates recomputed from games strictly *before* each replay date
- **Serve path:** `get_prediction_features` on a frame whose last row is the **synthetic next-game row** — production's post-Phase-1 path
- **Wall clock:** 13.6 min

## 1. Per-stat holdout accuracy

`MAE (pooled)` weights every held-out game equally; `MAE (player mean)` is the unweighted mean of per-player MAEs (comparable with `eval_holdout.py`). **MAE gap** is the mean per-player `holdout MAE − train OOF MAE` — the overfitting measure.

| Stat | Players | N test | MAE (pooled) | MAE (player mean) | Bias (pred−actual) | RMSE | Train OOF MAE | MAE gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 44 | 606 | 6.52 | 6.62 | -0.08 | 8.31 | 5.75 | **+0.88** |
| REB | 44 | 606 | 2.55 | 2.54 | +0.07 | 3.23 | 2.33 | **+0.20** |
| AST | 44 | 606 | 1.89 | 1.93 | -0.43 | 2.54 | 1.89 | **+0.04** |
| PRA | 44 | 606 | 7.64 | 7.83 | -0.41 | 9.75 | 7.12 | **+0.70** |

## 2. 80% interval coverage

Raw band is the untouched (q10, q90) quantile pair — target 0.80. The CQR band adds the per-stat conformal correction learned at training time, which targets ~0.90-0.92.

| Stat | Train OOF cov (raw) | Holdout cov RAW (target 0.80) | Mean CQR correction | Holdout cov CQR (target ~0.90) |
|---|---:|---:|---:|---:|
| PTS | 0.63 | 0.58 | 5.86 | 0.85 |
| REB | 0.64 | 0.57 | 2.42 | 0.87 |
| AST | 0.59 | 0.57 | 2.14 | 0.87 |
| PRA | 0.63 | 0.56 | 8.37 | 0.89 |

## 3. Probability calibration (pseudo-lines)

Each held-out prediction is scored against 7 pseudo-lines: prediction ± {0.5, 1.5, 2.5} and the player's season-to-date median (computed only from games before the row being predicted). `prob_over` comes from the production `ProbabilityCalculator.calculate` path — same std from `get_confidence`, same Platt calibrator — and is clipped to [15%, 85%] by `PROB_FLOOR`/`PROB_CEIL`.

### 3a. Overall reliability by predicted-probability decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap (pred − realized) |
|---|---:|---:|---:|---:|
| 10-20% | 632 | 16.4% | 23.7% | -7.3 |
| 20-30% | 1072 | 25.3% | 31.5% | -6.3 |
| 30-40% | 1800 | 35.3% | 42.8% | -7.5 |
| 40-50% | 2950 | 45.1% | 46.3% | -1.1 |
| 50-60% | 3634 | 55.0% | 49.4% | +5.6 |
| 60-70% | 3502 | 64.8% | 53.9% | +10.9 |
| 70-80% | 1998 | 74.4% | 64.1% | +10.3 |
| 80-90% | 1141 | 83.7% | 80.2% | +3.5 |

- **Overall Brier score:** 0.2407

### 3b. By stat

| Stat | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| PTS | 4208 | 54.8% | 48.8% | +6.0 | 0.2650 |
| REB | 4170 | 54.3% | 49.0% | +5.2 | 0.2346 |
| AST | 4127 | 51.8% | 54.1% | -2.3 | 0.1958 |
| PRA | 4224 | 55.6% | 51.4% | +4.1 | 0.2665 |

### 3c. By pseudo-line type

`offset` lines are centred on the prediction (half are near coin-flips by construction); `median` lines sit at the player's season-to-date median and are the closest stand-in for a real market line.

| Line type | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| offset | 14542 | 53.7% | 50.2% | +3.5 | 0.2371 |
| median | 2187 | 56.7% | 55.1% | +1.6 | 0.2648 |

### 3d. Median-line reliability by decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap |
|---|---:|---:|---:|---:|
| 10-20% | 39 | 16.5% | 48.7% | -32.2 |
| 20-30% | 113 | 25.7% | 51.3% | -25.6 |
| 30-40% | 198 | 35.3% | 57.1% | -21.8 |
| 40-50% | 376 | 45.5% | 51.3% | -5.9 |
| 50-60% | 487 | 54.8% | 53.4% | +1.4 |
| 60-70% | 448 | 64.9% | 53.6% | +11.3 |
| 70-80% | 371 | 74.8% | 59.3% | +15.5 |
| 80-90% | 155 | 83.4% | 66.5% | +17.0 |

## 4. Per-player appendix

| Player | Games | N test | Stat | Holdout MAE | Bias | RMSE | Train OOF MAE | MAE gap | Cov RAW | Cov CQR |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Alperen Sengun | 76 | 16 | PTS | 5.80 | +1.96 | 7.08 | 5.23 | +0.57 | 0.50 | 0.75 |
| Alperen Sengun | 76 | 16 | REB | 3.48 | -0.05 | 4.15 | 2.27 | +1.21 | 0.62 | 0.81 |
| Alperen Sengun | 76 | 16 | AST | 1.72 | +0.10 | 2.21 | 1.69 | +0.02 | 0.62 | 0.88 |
| Alperen Sengun | 76 | 16 | PRA | 5.49 | +2.19 | 7.23 | 6.65 | -1.16 | 0.75 | 0.88 |
| Amen Thompson | 69 | 9 | PTS | 3.96 | +0.58 | 4.98 | 5.77 | -1.81 | 0.67 | 1.00 |
| Amen Thompson | 69 | 9 | REB | 2.95 | +2.95 | 3.31 | 2.68 | +0.27 | 0.44 | 1.00 |
| Amen Thompson | 69 | 9 | AST | 1.87 | -0.91 | 2.58 | 2.28 | -0.41 | 0.56 | 1.00 |
| Amen Thompson | 69 | 9 | PRA | 4.72 | +2.65 | 6.53 | 8.06 | -3.33 | 0.78 | 1.00 |
| Anfernee Simons | 70 | 10 | PTS | 8.14 | +1.33 | 9.72 | 6.90 | +1.24 | 0.60 | 0.90 |
| Anfernee Simons | 70 | 10 | REB | 1.29 | +0.69 | 1.50 | 1.21 | +0.08 | 0.50 | 0.70 |
| Anfernee Simons | 70 | 10 | AST | 1.88 | +1.21 | 2.34 | 1.74 | +0.13 | 0.40 | 0.80 |
| Anfernee Simons | 70 | 10 | PRA | 7.13 | +3.08 | 8.27 | 7.91 | -0.79 | 0.50 | 1.00 |
| Anthony Edwards | 79 | 19 | PTS | 8.18 | -1.51 | 10.61 | 8.17 | +0.01 | 0.58 | 1.00 |
| Anthony Edwards | 79 | 19 | REB | 2.33 | +0.76 | 2.94 | 1.98 | +0.36 | 0.37 | 0.79 |
| Anthony Edwards | 79 | 19 | AST | 1.58 | +1.10 | 1.86 | 1.99 | -0.41 | 0.84 | 1.00 |
| Anthony Edwards | 79 | 19 | PRA | 7.99 | +1.05 | 10.21 | 8.07 | -0.08 | 0.58 | 1.00 |
| Austin Reaves | 73 | 13 | PTS | 5.51 | +0.56 | 6.72 | 6.18 | -0.67 | 0.54 | 1.00 |
| Austin Reaves | 73 | 13 | REB | 1.94 | +0.72 | 2.28 | 2.15 | -0.21 | 0.62 | 0.85 |
| Austin Reaves | 73 | 13 | AST | 1.85 | +1.28 | 2.08 | 2.68 | -0.83 | 0.46 | 1.00 |
| Austin Reaves | 73 | 13 | PRA | 6.76 | +2.50 | 8.04 | 7.89 | -1.13 | 0.69 | 1.00 |
| Bam Adebayo | 78 | 18 | PTS | 7.01 | -2.06 | 8.93 | 5.28 | +1.73 | 0.33 | 0.89 |
| Bam Adebayo | 78 | 18 | REB | 3.13 | +2.17 | 3.52 | 2.58 | +0.55 | 0.44 | 0.94 |
| Bam Adebayo | 78 | 18 | AST | 1.89 | +0.24 | 2.30 | 2.45 | -0.55 | 0.50 | 0.94 |
| Bam Adebayo | 78 | 18 | PRA | 9.30 | +0.68 | 10.94 | 7.06 | +2.24 | 0.50 | 0.94 |
| Cade Cunningham | 70 | 10 | PTS | 7.14 | +0.26 | 8.55 | 6.50 | +0.64 | 0.80 | 0.90 |
| Cade Cunningham | 70 | 10 | REB | 2.86 | -0.89 | 3.13 | 2.14 | +0.71 | 0.20 | 0.80 |
| Cade Cunningham | 70 | 10 | AST | 2.08 | +0.92 | 2.62 | 2.68 | -0.60 | 0.60 | 0.90 |
| Cade Cunningham | 70 | 10 | PRA | 6.31 | -0.41 | 7.96 | 7.78 | -1.47 | 0.50 | 0.90 |
| Coby White | 74 | 14 | PTS | 11.20 | -6.05 | 12.30 | 5.60 | +5.60 | 0.50 | 0.64 |
| Coby White | 74 | 14 | REB | 2.14 | -1.35 | 3.15 | 1.88 | +0.26 | 0.50 | 0.86 |
| Coby White | 74 | 14 | AST | 1.48 | -0.14 | 1.98 | 2.06 | -0.57 | 0.50 | 0.86 |
| Coby White | 74 | 14 | PRA | 11.82 | -6.31 | 12.89 | 7.01 | +4.81 | 0.21 | 0.86 |
| Darius Garland | 75 | 15 | PTS | 4.89 | +0.11 | 6.21 | 5.57 | -0.68 | 0.67 | 0.93 |
| Darius Garland | 75 | 15 | REB | 1.80 | -1.49 | 2.18 | 1.22 | +0.58 | 0.53 | 0.80 |
| Darius Garland | 75 | 15 | AST | 1.88 | -1.58 | 2.62 | 1.74 | +0.14 | 0.80 | 0.93 |
| Darius Garland | 75 | 15 | PRA | 5.61 | -3.13 | 7.18 | 5.40 | +0.20 | 0.73 | 1.00 |
| DeMar DeRozan | 77 | 17 | PTS | 5.14 | -0.60 | 7.27 | 6.36 | -1.22 | 0.53 | 0.94 |
| DeMar DeRozan | 77 | 17 | REB | 1.94 | +1.20 | 2.39 | 1.53 | +0.41 | 0.59 | 0.88 |
| DeMar DeRozan | 77 | 17 | AST | 3.07 | -2.22 | 3.67 | 1.94 | +1.13 | 0.41 | 0.71 |
| DeMar DeRozan | 77 | 17 | PRA | 6.34 | -1.41 | 8.21 | 7.91 | -1.57 | 0.76 | 1.00 |
| Deni Avdija | 72 | 12 | PTS | 10.48 | -10.18 | 12.87 | 6.48 | +4.00 | 0.50 | 0.92 |
| Deni Avdija | 72 | 12 | REB | 3.89 | -2.93 | 4.78 | 2.57 | +1.32 | 0.50 | 0.75 |
| Deni Avdija | 72 | 12 | AST | 2.12 | -1.32 | 2.77 | 1.64 | +0.47 | 0.50 | 0.83 |
| Deni Avdija | 72 | 12 | PRA | 15.63 | -14.57 | 18.34 | 8.88 | +6.75 | 0.42 | 0.83 |
| Derrick White | 76 | 16 | PTS | 3.66 | -0.34 | 4.35 | 5.03 | -1.36 | 0.94 | 1.00 |
| Derrick White | 76 | 16 | REB | 2.25 | -1.38 | 2.68 | 1.75 | +0.51 | 0.56 | 0.81 |
| Derrick White | 76 | 16 | AST | 2.03 | -1.57 | 2.56 | 1.98 | +0.04 | 0.38 | 0.81 |
| Derrick White | 76 | 16 | PRA | 4.20 | -3.17 | 5.58 | 6.24 | -2.05 | 0.94 | 1.00 |
| Devin Booker | 75 | 15 | PTS | 9.05 | +3.83 | 10.07 | 6.76 | +2.29 | 0.53 | 0.80 |
| Devin Booker | 75 | 15 | REB | 1.72 | -0.01 | 1.94 | 1.44 | +0.27 | 0.60 | 0.67 |
| Devin Booker | 75 | 15 | AST | 3.25 | -1.02 | 3.74 | 2.05 | +1.20 | 0.40 | 0.53 |
| Devin Booker | 75 | 15 | PRA | 7.52 | +2.75 | 9.99 | 6.52 | +1.00 | 0.47 | 0.87 |
| Domantas Sabonis | 70 | 10 | PTS | 3.92 | +0.64 | 4.85 | 4.14 | -0.22 | 0.60 | 0.80 |
| Domantas Sabonis | 70 | 10 | REB | 2.80 | +2.12 | 3.49 | 3.36 | -0.55 | 0.70 | 1.00 |
| Domantas Sabonis | 70 | 10 | AST | 2.06 | +0.83 | 2.85 | 2.47 | -0.41 | 0.60 | 0.70 |
| Domantas Sabonis | 70 | 10 | PRA | 5.15 | +2.68 | 7.29 | 6.48 | -1.33 | 0.80 | 1.00 |
| Evan Mobley | 71 | 11 | PTS | 5.73 | +1.60 | 6.60 | 5.50 | +0.23 | 0.64 | 0.82 |
| Evan Mobley | 71 | 11 | REB | 2.68 | -0.88 | 3.02 | 2.49 | +0.19 | 0.91 | 1.00 |
| Evan Mobley | 71 | 11 | AST | 1.34 | -0.36 | 1.68 | 1.70 | -0.37 | 0.64 | 0.91 |
| Evan Mobley | 71 | 11 | PRA | 6.92 | +0.60 | 8.01 | 7.36 | -0.44 | 0.45 | 0.91 |
| Giannis Antetokounmpo | 67 | 7 | PTS | 5.25 | -3.52 | 5.92 | 4.81 | +0.44 | 0.57 | 0.57 |
| Giannis Antetokounmpo | 67 | 7 | REB | 3.11 | +0.02 | 3.82 | 2.41 | +0.70 | 0.57 | 0.86 |
| Giannis Antetokounmpo | 67 | 7 | AST | 5.68 | -5.24 | 7.28 | 2.37 | +3.31 | 0.29 | 0.43 |
| Giannis Antetokounmpo | 67 | 7 | PRA | 9.58 | -8.79 | 13.22 | 5.42 | +4.15 | 0.57 | 0.57 |
| Ivica Zubac | 80 | 20 | PTS | 3.44 | +0.90 | 4.06 | 5.11 | -1.67 | 0.85 | 1.00 |
| Ivica Zubac | 80 | 20 | REB | 2.79 | -0.41 | 3.69 | 2.95 | -0.16 | 0.70 | 0.85 |
| Ivica Zubac | 80 | 20 | AST | 1.81 | -0.72 | 2.61 | 1.16 | +0.65 | 0.60 | 0.75 |
| Ivica Zubac | 80 | 20 | PRA | 6.34 | -0.82 | 7.27 | 7.23 | -0.89 | 0.70 | 0.90 |
| Jaden McDaniels | 82 | 22 | PTS | 5.76 | +4.01 | 7.34 | 5.16 | +0.60 | 0.77 | 0.95 |
| Jaden McDaniels | 82 | 22 | REB | 2.93 | +2.00 | 3.56 | 2.29 | +0.64 | 0.45 | 0.91 |
| Jaden McDaniels | 82 | 22 | AST | 1.53 | -0.03 | 1.91 | 1.14 | +0.39 | 0.23 | 0.82 |
| Jaden McDaniels | 82 | 22 | PRA | 8.50 | +5.70 | 10.25 | 6.41 | +2.08 | 0.59 | 0.91 |
| Jalen Brunson | 65 | 5 | PTS | 8.43 | +1.26 | 9.55 | 7.03 | +1.39 | 0.40 | 0.80 |
| Jalen Brunson | 65 | 5 | REB | 1.38 | +0.94 | 1.47 | 1.34 | +0.05 | 0.60 | 1.00 |
| Jalen Brunson | 65 | 5 | AST | 2.65 | +0.54 | 2.87 | 1.99 | +0.66 | 0.20 | 0.40 |
| Jalen Brunson | 65 | 5 | PRA | 11.70 | +2.83 | 12.71 | 8.02 | +3.68 | 0.40 | 0.80 |
| Jalen Duren | 78 | 18 | PTS | 3.49 | +1.05 | 4.67 | 4.08 | -0.59 | 0.44 | 0.83 |
| Jalen Duren | 78 | 18 | REB | 3.50 | -0.70 | 4.24 | 2.83 | +0.66 | 0.44 | 0.83 |
| Jalen Duren | 78 | 18 | AST | 1.85 | -0.53 | 2.36 | 1.36 | +0.49 | 0.56 | 0.89 |
| Jalen Duren | 78 | 18 | PRA | 5.43 | -0.24 | 7.96 | 6.42 | -0.99 | 0.56 | 0.89 |
| Jalen Green | 82 | 22 | PTS | 10.19 | +3.48 | 12.18 | 7.00 | +3.19 | 0.50 | 0.77 |
| Jalen Green | 82 | 22 | REB | 2.32 | -1.23 | 2.89 | 1.64 | +0.68 | 0.50 | 0.82 |
| Jalen Green | 82 | 22 | AST | 1.88 | -1.04 | 2.81 | 1.63 | +0.25 | 0.64 | 0.91 |
| Jalen Green | 82 | 22 | PRA | 11.05 | +0.86 | 12.99 | 7.36 | +3.69 | 0.59 | 0.77 |
| Jalen Williams | 69 | 9 | PTS | 5.95 | -0.86 | 7.01 | 5.03 | +0.92 | 0.67 | 0.67 |
| Jalen Williams | 69 | 9 | REB | 1.44 | +0.96 | 1.77 | 1.58 | -0.14 | 0.67 | 0.78 |
| Jalen Williams | 69 | 9 | AST | 1.69 | +1.59 | 1.95 | 1.61 | +0.08 | 0.78 | 1.00 |
| Jalen Williams | 69 | 9 | PRA | 6.28 | +1.55 | 7.53 | 5.53 | +0.75 | 0.44 | 0.78 |
| Jarrett Allen | 82 | 22 | PTS | 6.68 | -0.85 | 8.13 | 4.10 | +2.59 | 0.45 | 0.50 |
| Jarrett Allen | 82 | 22 | REB | 3.58 | +1.25 | 4.22 | 2.97 | +0.62 | 0.27 | 0.95 |
| Jarrett Allen | 82 | 22 | AST | 1.14 | +0.34 | 1.34 | 1.31 | -0.17 | 0.77 | 1.00 |
| Jarrett Allen | 82 | 22 | PRA | 8.83 | +0.83 | 11.34 | 6.76 | +2.08 | 0.45 | 0.64 |
| Jayson Tatum | 72 | 12 | PTS | 4.84 | +1.42 | 6.06 | 7.27 | -2.43 | 0.75 | 1.00 |
| Jayson Tatum | 72 | 12 | REB | 2.46 | +1.26 | 3.21 | 3.14 | -0.68 | 0.58 | 0.75 |
| Jayson Tatum | 72 | 12 | AST | 1.77 | -0.46 | 1.98 | 2.41 | -0.64 | 0.67 | 1.00 |
| Jayson Tatum | 72 | 12 | PRA | 4.75 | +2.22 | 6.64 | 8.12 | -3.37 | 0.58 | 1.00 |
| Josh Hart | 77 | 17 | PTS | 5.52 | +3.94 | 6.78 | 4.08 | +1.44 | 0.47 | 0.94 |
| Josh Hart | 77 | 17 | REB | 3.06 | +0.80 | 3.63 | 3.66 | -0.60 | 0.65 | 0.94 |
| Josh Hart | 77 | 17 | AST | 2.44 | -1.44 | 3.03 | 2.55 | -0.10 | 0.53 | 0.76 |
| Josh Hart | 77 | 17 | PRA | 6.37 | +3.72 | 7.97 | 6.81 | -0.43 | 0.47 | 1.00 |
| Julius Randle | 69 | 9 | PTS | 8.10 | -5.08 | 9.74 | 4.46 | +3.64 | 0.44 | 0.67 |
| Julius Randle | 69 | 9 | REB | 1.81 | -0.06 | 2.10 | 1.96 | -0.15 | 0.44 | 1.00 |
| Julius Randle | 69 | 9 | AST | 1.28 | +0.33 | 1.46 | 1.88 | -0.60 | 0.78 | 1.00 |
| Julius Randle | 69 | 9 | PRA | 8.44 | -4.65 | 10.49 | 5.59 | +2.86 | 0.44 | 0.78 |
| Karl-Anthony Towns | 72 | 12 | PTS | 6.74 | -2.10 | 7.85 | 7.10 | -0.37 | 0.83 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | REB | 2.79 | +1.25 | 3.59 | 3.98 | -1.19 | 0.83 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | AST | 1.83 | -0.16 | 2.76 | 1.66 | +0.17 | 0.58 | 0.92 |
| Karl-Anthony Towns | 72 | 12 | PRA | 7.92 | -1.51 | 9.27 | 9.32 | -1.40 | 0.83 | 1.00 |
| Kyle Kuzma | 65 | 5 | PTS | 4.36 | -0.56 | 4.79 | 4.90 | -0.54 | 0.60 | 1.00 |
| Kyle Kuzma | 65 | 5 | REB | 2.45 | +2.45 | 2.67 | 2.48 | -0.03 | 0.60 | 1.00 |
| Kyle Kuzma | 65 | 5 | AST | 1.26 | +0.39 | 1.43 | 1.45 | -0.19 | 0.80 | 1.00 |
| Kyle Kuzma | 65 | 5 | PRA | 5.50 | +2.29 | 6.32 | 6.14 | -0.64 | 0.60 | 1.00 |
| LeBron James | 70 | 10 | PTS | 6.84 | +5.66 | 8.73 | 5.95 | +0.89 | 0.60 | 0.80 |
| LeBron James | 70 | 10 | REB | 2.84 | +1.58 | 4.02 | 2.87 | -0.03 | 0.60 | 0.90 |
| LeBron James | 70 | 10 | AST | 2.56 | -0.39 | 3.16 | 2.27 | +0.29 | 0.60 | 1.00 |
| LeBron James | 70 | 10 | PRA | 7.65 | +6.73 | 9.01 | 7.08 | +0.57 | 0.50 | 0.90 |
| Michael Porter Jr. | 77 | 17 | PTS | 4.55 | +3.20 | 5.86 | 5.15 | -0.60 | 0.82 | 1.00 |
| Michael Porter Jr. | 77 | 17 | REB | 2.64 | -0.82 | 3.21 | 2.47 | +0.16 | 0.76 | 0.94 |
| Michael Porter Jr. | 77 | 17 | AST | 1.16 | -0.25 | 1.56 | 1.30 | -0.13 | 0.76 | 0.94 |
| Michael Porter Jr. | 77 | 17 | PRA | 5.69 | +2.06 | 6.90 | 5.99 | -0.30 | 0.65 | 1.00 |
| Mikal Bridges | 82 | 21 | PTS | 5.85 | +0.68 | 7.14 | 6.48 | -0.63 | 0.57 | 0.95 |
| Mikal Bridges | 82 | 21 | REB | 1.29 | -0.64 | 1.62 | 1.45 | -0.16 | 0.76 | 0.95 |
| Mikal Bridges | 82 | 21 | AST | 2.50 | -2.30 | 3.14 | 1.55 | +0.94 | 0.24 | 0.62 |
| Mikal Bridges | 82 | 21 | PRA | 5.99 | -2.49 | 7.75 | 6.89 | -0.90 | 0.52 | 0.95 |
| Myles Turner | 72 | 12 | PTS | 5.08 | -1.23 | 6.07 | 3.93 | +1.15 | 0.42 | 0.58 |
| Myles Turner | 72 | 12 | REB | 3.36 | -2.27 | 3.89 | 2.24 | +1.13 | 0.58 | 0.92 |
| Myles Turner | 72 | 12 | AST | 0.71 | +0.60 | 0.80 | 0.86 | -0.15 | 0.75 | 0.92 |
| Myles Turner | 72 | 12 | PRA | 6.36 | -2.66 | 7.29 | 5.34 | +1.03 | 0.58 | 0.75 |
| Naz Reid | 80 | 20 | PTS | 5.88 | +3.70 | 6.81 | 6.40 | -0.52 | 0.70 | 0.90 |
| Naz Reid | 80 | 20 | REB | 2.34 | -1.81 | 2.85 | 2.93 | -0.59 | 0.80 | 1.00 |
| Naz Reid | 80 | 20 | AST | 1.12 | +0.20 | 1.43 | 1.26 | -0.14 | 0.55 | 0.95 |
| Naz Reid | 80 | 20 | PRA | 4.97 | +2.92 | 6.32 | 8.27 | -3.30 | 0.90 | 0.95 |
| Nikola Jokic | 70 | 10 | PTS | 9.32 | -7.31 | 13.09 | 7.26 | +2.07 | 0.50 | 0.90 |
| Nikola Jokic | 70 | 10 | REB | 2.59 | +1.18 | 3.27 | 3.95 | -1.36 | 0.80 | 1.00 |
| Nikola Jokic | 70 | 10 | AST | 2.94 | -0.01 | 3.40 | 3.16 | -0.22 | 0.70 | 1.00 |
| Nikola Jokic | 70 | 10 | PRA | 11.49 | -6.05 | 14.02 | 9.07 | +2.42 | 0.60 | 0.90 |
| Nikola Vucevic | 73 | 13 | PTS | 8.08 | -7.74 | 10.11 | 5.80 | +2.28 | 0.77 | 0.92 |
| Nikola Vucevic | 73 | 13 | REB | 2.03 | -0.06 | 2.34 | 2.54 | -0.50 | 0.62 | 1.00 |
| Nikola Vucevic | 73 | 13 | AST | 2.48 | -0.93 | 2.89 | 1.44 | +1.04 | 0.46 | 0.85 |
| Nikola Vucevic | 73 | 13 | PRA | 10.00 | -7.82 | 11.97 | 7.99 | +2.00 | 0.38 | 1.00 |
| OG Anunoby | 74 | 14 | PTS | 10.22 | -7.10 | 11.52 | 6.24 | +3.98 | 0.43 | 0.86 |
| OG Anunoby | 74 | 14 | REB | 1.63 | +0.16 | 2.07 | 1.98 | -0.34 | 0.64 | 1.00 |
| OG Anunoby | 74 | 14 | AST | 1.17 | -0.25 | 1.53 | 1.22 | -0.06 | 0.43 | 0.93 |
| OG Anunoby | 74 | 14 | PRA | 10.70 | -7.10 | 12.15 | 7.60 | +3.11 | 0.43 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PTS | 5.26 | -0.60 | 6.86 | 4.56 | +0.70 | 0.57 | 0.71 |
| Onyeka Okongwu | 74 | 14 | REB | 3.11 | +0.78 | 3.63 | 2.72 | +0.39 | 0.50 | 0.86 |
| Onyeka Okongwu | 74 | 14 | AST | 1.10 | -0.06 | 1.45 | 1.35 | -0.25 | 0.36 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PRA | 8.68 | +0.09 | 10.33 | 6.69 | +1.99 | 0.36 | 0.93 |
| Pascal Siakam | 78 | 18 | PTS | 7.50 | +0.87 | 8.25 | 4.43 | +3.07 | 0.11 | 0.67 |
| Pascal Siakam | 78 | 18 | REB | 2.90 | +1.84 | 3.70 | 2.19 | +0.71 | 0.56 | 0.89 |
| Pascal Siakam | 78 | 18 | AST | 1.55 | -0.83 | 1.80 | 1.59 | -0.04 | 0.44 | 0.78 |
| Pascal Siakam | 78 | 18 | PRA | 8.62 | +1.87 | 9.48 | 5.20 | +3.42 | 0.17 | 0.78 |
| Rudy Gobert | 72 | 12 | PTS | 6.98 | -5.46 | 8.93 | 3.97 | +3.00 | 0.25 | 0.58 |
| Rudy Gobert | 72 | 12 | REB | 4.42 | -3.28 | 5.91 | 3.15 | +1.26 | 0.58 | 0.58 |
| Rudy Gobert | 72 | 12 | AST | 1.01 | +0.05 | 1.19 | 1.38 | -0.37 | 0.92 | 0.92 |
| Rudy Gobert | 72 | 12 | PRA | 11.04 | -9.00 | 12.88 | 6.50 | +4.54 | 0.17 | 0.58 |
| Scottie Barnes | 65 | 5 | PTS | 9.98 | -2.28 | 11.42 | 4.72 | +5.26 | 0.40 | 0.60 |
| Scottie Barnes | 65 | 5 | REB | 3.28 | +0.09 | 3.48 | 3.01 | +0.26 | 0.20 | 0.80 |
| Scottie Barnes | 65 | 5 | AST | 1.51 | +0.60 | 1.77 | 2.07 | -0.56 | 0.60 | 1.00 |
| Scottie Barnes | 65 | 5 | PRA | 13.35 | -1.20 | 15.27 | 6.68 | +6.67 | 0.40 | 0.40 |
| Shai Gilgeous-Alexander | 76 | 16 | PTS | 6.09 | +2.32 | 7.14 | 6.68 | -0.59 | 0.69 | 1.00 |
| Shai Gilgeous-Alexander | 76 | 16 | REB | 1.97 | +0.69 | 2.47 | 2.10 | -0.12 | 0.81 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | AST | 1.81 | -0.94 | 2.27 | 1.88 | -0.07 | 0.81 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | PRA | 5.75 | +1.98 | 6.95 | 7.23 | -1.48 | 0.75 | 1.00 |
| Stephen Curry | 70 | 10 | PTS | 11.29 | -2.14 | 14.01 | 7.46 | +3.84 | 0.30 | 0.80 |
| Stephen Curry | 70 | 10 | REB | 2.47 | -1.86 | 3.38 | 1.76 | +0.71 | 0.40 | 0.80 |
| Stephen Curry | 70 | 10 | AST | 1.16 | -0.58 | 1.50 | 2.36 | -1.20 | 0.80 | 1.00 |
| Stephen Curry | 70 | 10 | PRA | 12.58 | -4.44 | 15.90 | 8.29 | +4.29 | 0.40 | 0.90 |
| Trae Young | 76 | 16 | PTS | 5.47 | +2.02 | 6.80 | 7.62 | -2.15 | 1.00 | 1.00 |
| Trae Young | 76 | 16 | REB | 1.64 | -0.49 | 1.94 | 1.31 | +0.33 | 0.75 | 0.88 |
| Trae Young | 76 | 16 | AST | 2.19 | -0.62 | 3.01 | 3.67 | -1.49 | 0.81 | 1.00 |
| Trae Young | 76 | 16 | PRA | 5.80 | +1.11 | 7.97 | 7.77 | -1.97 | 0.62 | 0.94 |
| Tyrese Haliburton | 73 | 13 | PTS | 4.37 | +3.10 | 5.72 | 6.56 | -2.19 | 0.85 | 1.00 |
| Tyrese Haliburton | 73 | 13 | REB | 2.21 | -0.05 | 2.60 | 1.41 | +0.81 | 0.38 | 0.46 |
| Tyrese Haliburton | 73 | 13 | AST | 3.19 | -1.01 | 3.98 | 2.35 | +0.84 | 0.38 | 0.77 |
| Tyrese Haliburton | 73 | 13 | PRA | 4.08 | +1.56 | 5.09 | 8.49 | -4.40 | 0.92 | 1.00 |

## 5. Skipped players

- **Aaron Gordon** (203932): only 51 games available (need >= 65)
- **Cameron Johnson** (1629661): only 57 games available (need >= 65)
- **Collin Sexton** (1629012): only 63 games available (need >= 65)
- **Daniel Gafford** (1629655): only 57 games available (need >= 65)
- **Franz Wagner** (1630532): only 60 games available (need >= 65)
- **Immanuel Quickley** (1630193): only 33 games available (need >= 65)
- **Isaiah Hartenstein** (1628392): only 57 games available (need >= 65)
- **Jerami Grant** (203924): only 47 games available (need >= 65)
- **Lauri Markkanen** (1628374): only 47 games available (need >= 65)
- **Norman Powell** (1626181): only 60 games available (need >= 65)
- **Paolo Banchero** (1631094): only 46 games available (need >= 65)
- **RJ Barrett** (1629628): only 58 games available (need >= 65)
- **Tyrese Maxey** (1630178): only 52 games available (need >= 65)
- **Walker Kessler** (1631117): only 58 games available (need >= 65)

## 6. Caveats

1. **Opponent context is point-in-time (fixed in Phase 0).** The feature frame is rebuilt at every replay step with `team_stats` aggregated by `scripts/team_stats_asof.py` from team-games played **strictly before** that step's date — same-day games excluded. The training frame is built once, as of the first held-out game, so nothing from the test period reaches the fit. A team with no prior games on a given date is omitted from the dict, which lets `extract_opp_stats` fall back to its league-average defaults rather than emitting NaN. Rolling features remain `shift(1)`-safe: row *i* only summarizes rows `0..i-1`. Earlier reports carried a caveat about season-aggregate opponent leakage; that caveat was vacuous, because the harness passed `team_stats=None` and built no opponent aggregate at all — it is now genuinely satisfied instead.
2. **The model is frozen after the initial fit.** Production retrains nightly; here a single fit on the first 60 rows predicts every later game. Late-season holdout rows are therefore predicted by an increasingly stale model, which inflates holdout MAE relative to production.
3. **L10 / season anchors are refreshed, the GBM is not.** `_update_recent_averages` is called on the pre-row history before every prediction (production does the same), so the regression-to-mean and deviation-cap anchors stay current with no lookahead.
4. **Early-season damping neutralized.** `_current_season_games` compares the log against the *calendar* current season, so a 2024-25 backtest would trip the <10-games damping (confidence ×0.75, std ×1.3) on every row. The history frame passed to `get_confidence` is stamped with the current season string so damping stays neutral, matching a mid-season production run.
5. **No serve-time context adjustments.** `estimated_minutes` is not supplied (so the rate-model blend and minutes scaling never fire), and the injury boost, blowout discount and questionable dampener are all skipped. This isolates the core model from the context layer.
6. **The serve path is now exercised (Phase 1), and the harness was never where the staleness lived.** Each step truncates the raw log to games played strictly before the test game, appends a synthetic row built from that game's schedule facts alone (matchup + date — published months ahead), rebuilds features, and calls `get_prediction_features`. A per-player probe rewrites every realized number from the test game onward and requires a bit-identical served vector; any player failing it is skipped with a `LOOKAHEAD:` reason. Reports up to and including Phase 0 read the feature row of the game being predicted **directly**, and that row already carried correct lag-1 values — so the harness never reproduced the one-game staleness that production served. `--stale-serve` reproduces the pre-Phase-1 production path exactly (identical schedule context; frame rolled back to the last completed game) and is the only way to measure what that staleness cost.
7. **Head-to-head is re-scoped to the replay history.** Production calls `NBADataScraper.get_vs_team_stats`, which re-reads the player's full multi-season log; used verbatim in a walk-forward replay it would pull the rest of the season into every step. The harness computes the same shape from games strictly before the test game.
8. **Pseudo-lines are model-derived, not market lines.** The ±0.5/1.5/2.5 family is centred on the prediction, so it measures the *internal* consistency of prediction + std + calibrator, not edge against a bookmaker. The season-to-date median line is the closest stand-in for a market line — read 3c/3d for that view. **Every calibration number in this report is against synthetic pseudo-lines, not real sportsbook lines. Beating a player's season-to-date median is not evidence of beating a sportsbook.** `manual_lines` is empty and there is no historical odds source, so real-line validation can only come from a forward test.
9. **PRA's train-OOF MAE is not the served quantity.** `training_metrics['PRA']` is computed from the *independent* PRA model's OOF predictions, while the holdout column evaluates the reconciled 85/15 blend. The PRA MAE gap therefore compares two slightly different estimators; the PTS/REB/AST gaps are apples-to-apples.
10. **Probabilities are hard-clipped to [15%, 85%]** by `ProbabilityCalculator.PROB_FLOOR/PROB_CEIL`, so the 0-10% and 90-100% deciles are structurally empty and the Brier score is floored by that clipping.
11. **Ties are dropped.** When a realized value lands exactly on a pseudo-line (possible for integer median lines) the sample is excluded rather than scored as an under.
12. **Sample size.** One season, ~50 players, and per-player holdout sets of roughly 5-25 games. Per-player rows in the appendix are noisy; the pooled per-stat numbers are the ones to act on.

## 7. Reading guide

- **MAE gap > 0** ⇒ the OOF metrics stored on the pickle are optimistic (overfitting).
- **Bias > 0** ⇒ the model over-predicts held-out games; **< 0** ⇒ under-predicts.
- **Holdout cov RAW ≪ 0.80** ⇒ quantile intervals are too narrow before CQR.
- **Calibration gap > 0** in a decile ⇒ the model claims more OVER probability than it delivers.
- **Brier** is the headline probability score (lower is better; 0.25 = always saying 50%).
