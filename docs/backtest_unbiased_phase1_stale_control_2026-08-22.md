# Unbiased Walk-Forward Backtest — Phase 1 control — pre-Phase-1 stale serve path (2026-08-22)

**Control run for `docs/backtest_unbiased_phase1_2026-08-22.md` — not a baseline.**

Identical code, identical models, identical games, identical schedule context.
The only difference: `get_prediction_features` reads the last **completed**
game's row instead of the synthetic next-game row, reproducing the pre-Phase-1
production serve path exactly (`--stale-serve`). Its whole purpose is to price
the one-game feature staleness, since the Phase 0 harness never reproduced it.
Read the headline of the Phase 1 report for the comparison.

- **Season:** 2024-25
- **Train:** first 60 feature rows per player (single fit, never refit)
- **Test:** every remaining row, predicted one at a time
- **Pipeline:** `full (ensemble + meta-learner)`
- **Stats:** PTS, REB, AST, PRA (PRA = reconciled 0.85·(P+R+A) + 0.15·independent)
- **Players attempted / evaluated / skipped:** 58 / 44 / 14
- **Held-out predictions:** 2424
- **Pseudo-line probability samples:** 16727
- **Model width under test:** 81 of 86 declared `FEATURE_COLS` are actually built by `create_features`; the rest are zero-filled by `predict`
- **Opponent context:** point-in-time via `scripts/team_stats_asof.py` — team aggregates recomputed from games strictly *before* each replay date
- **Serve path:** `get_prediction_features` on a frame whose last row is the **last completed game** — the *pre-Phase-1* production path, i.e. one-game-stale rolling features (`--stale-serve`)
- **Wall clock:** 13.8 min

## 1. Per-stat holdout accuracy

`MAE (pooled)` weights every held-out game equally; `MAE (player mean)` is the unweighted mean of per-player MAEs (comparable with `eval_holdout.py`). **MAE gap** is the mean per-player `holdout MAE − train OOF MAE` — the overfitting measure.

| Stat | Players | N test | MAE (pooled) | MAE (player mean) | Bias (pred−actual) | RMSE | Train OOF MAE | MAE gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 44 | 606 | 6.52 | 6.65 | -0.06 | 8.27 | 5.75 | **+0.91** |
| REB | 44 | 606 | 2.57 | 2.56 | +0.07 | 3.28 | 2.33 | **+0.22** |
| AST | 44 | 606 | 1.89 | 1.94 | -0.43 | 2.56 | 1.89 | **+0.05** |
| PRA | 44 | 606 | 7.65 | 7.83 | -0.40 | 9.75 | 7.12 | **+0.70** |

## 2. 80% interval coverage

Raw band is the untouched (q10, q90) quantile pair — target 0.80. The CQR band adds the per-stat conformal correction learned at training time, which targets ~0.90-0.92.

| Stat | Train OOF cov (raw) | Holdout cov RAW (target 0.80) | Mean CQR correction | Holdout cov CQR (target ~0.90) |
|---|---:|---:|---:|---:|
| PTS | 0.63 | 0.56 | 5.86 | 0.85 |
| REB | 0.64 | 0.57 | 2.42 | 0.86 |
| AST | 0.59 | 0.58 | 2.14 | 0.87 |
| PRA | 0.63 | 0.56 | 8.37 | 0.88 |

## 3. Probability calibration (pseudo-lines)

Each held-out prediction is scored against 7 pseudo-lines: prediction ± {0.5, 1.5, 2.5} and the player's season-to-date median (computed only from games before the row being predicted). `prob_over` comes from the production `ProbabilityCalculator.calculate` path — same std from `get_confidence`, same Platt calibrator — and is clipped to [15%, 85%] by `PROB_FLOOR`/`PROB_CEIL`.

### 3a. Overall reliability by predicted-probability decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap (pred − realized) |
|---|---:|---:|---:|---:|
| 10-20% | 642 | 16.4% | 22.7% | -6.3 |
| 20-30% | 1083 | 25.3% | 33.3% | -8.1 |
| 30-40% | 1789 | 35.4% | 42.9% | -7.5 |
| 40-50% | 2941 | 45.2% | 46.0% | -0.8 |
| 50-60% | 3626 | 55.0% | 49.3% | +5.7 |
| 60-70% | 3494 | 64.8% | 53.4% | +11.4 |
| 70-80% | 2010 | 74.4% | 64.7% | +9.7 |
| 80-90% | 1142 | 83.7% | 80.8% | +2.9 |

- **Overall Brier score:** 0.2406

### 3b. By stat

| Stat | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| PTS | 4208 | 54.8% | 49.4% | +5.4 | 0.2649 |
| REB | 4168 | 54.2% | 48.9% | +5.3 | 0.2336 |
| AST | 4127 | 51.8% | 54.0% | -2.2 | 0.1960 |
| PRA | 4224 | 55.5% | 51.2% | +4.4 | 0.2668 |

### 3c. By pseudo-line type

`offset` lines are centred on the prediction (half are near coin-flips by construction); `median` lines sit at the player's season-to-date median and are the closest stand-in for a real market line.

| Line type | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| offset | 14540 | 53.7% | 50.2% | +3.5 | 0.2367 |
| median | 2187 | 56.7% | 55.1% | +1.6 | 0.2664 |

### 3d. Median-line reliability by decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap |
|---|---:|---:|---:|---:|
| 10-20% | 44 | 16.7% | 50.0% | -33.3 |
| 20-30% | 113 | 25.8% | 54.9% | -29.1 |
| 30-40% | 190 | 35.3% | 57.4% | -22.1 |
| 40-50% | 383 | 45.5% | 53.3% | -7.7 |
| 50-60% | 484 | 54.9% | 51.9% | +3.1 |
| 60-70% | 444 | 64.8% | 50.2% | +14.5 |
| 70-80% | 374 | 74.7% | 61.2% | +13.5 |
| 80-90% | 155 | 83.5% | 68.4% | +15.1 |

## 4. Per-player appendix

| Player | Games | N test | Stat | Holdout MAE | Bias | RMSE | Train OOF MAE | MAE gap | Cov RAW | Cov CQR |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Alperen Sengun | 76 | 16 | PTS | 5.75 | +1.84 | 7.02 | 5.23 | +0.51 | 0.38 | 0.75 |
| Alperen Sengun | 76 | 16 | REB | 3.37 | -0.09 | 4.08 | 2.27 | +1.10 | 0.56 | 0.81 |
| Alperen Sengun | 76 | 16 | AST | 1.73 | +0.12 | 2.23 | 1.69 | +0.03 | 0.69 | 0.88 |
| Alperen Sengun | 76 | 16 | PRA | 5.53 | +2.08 | 7.21 | 6.65 | -1.12 | 0.56 | 0.81 |
| Amen Thompson | 69 | 9 | PTS | 3.80 | +0.92 | 4.41 | 5.77 | -1.97 | 0.56 | 1.00 |
| Amen Thompson | 69 | 9 | REB | 3.17 | +2.98 | 3.73 | 2.68 | +0.49 | 0.44 | 1.00 |
| Amen Thompson | 69 | 9 | AST | 1.70 | -1.15 | 2.34 | 2.28 | -0.58 | 0.56 | 1.00 |
| Amen Thompson | 69 | 9 | PRA | 4.85 | +2.86 | 6.34 | 8.06 | -3.21 | 0.78 | 1.00 |
| Anfernee Simons | 70 | 10 | PTS | 8.15 | +1.24 | 9.76 | 6.90 | +1.25 | 0.60 | 0.80 |
| Anfernee Simons | 70 | 10 | REB | 1.31 | +0.70 | 1.51 | 1.21 | +0.10 | 0.60 | 0.70 |
| Anfernee Simons | 70 | 10 | AST | 1.89 | +1.22 | 2.34 | 1.74 | +0.15 | 0.40 | 0.80 |
| Anfernee Simons | 70 | 10 | PRA | 7.03 | +3.02 | 8.27 | 7.91 | -0.89 | 0.50 | 0.90 |
| Anthony Edwards | 79 | 19 | PTS | 7.40 | -1.12 | 9.65 | 8.17 | -0.77 | 0.63 | 1.00 |
| Anthony Edwards | 79 | 19 | REB | 2.33 | +0.76 | 2.93 | 1.98 | +0.35 | 0.32 | 0.79 |
| Anthony Edwards | 79 | 19 | AST | 1.58 | +1.09 | 1.88 | 1.99 | -0.41 | 0.89 | 1.00 |
| Anthony Edwards | 79 | 19 | PRA | 7.52 | +1.29 | 9.49 | 8.07 | -0.56 | 0.63 | 1.00 |
| Austin Reaves | 73 | 13 | PTS | 5.46 | +0.89 | 6.58 | 6.18 | -0.72 | 0.54 | 1.00 |
| Austin Reaves | 73 | 13 | REB | 1.94 | +0.71 | 2.30 | 2.15 | -0.21 | 0.62 | 0.85 |
| Austin Reaves | 73 | 13 | AST | 2.04 | +1.28 | 2.23 | 2.68 | -0.64 | 0.54 | 1.00 |
| Austin Reaves | 73 | 13 | PRA | 6.82 | +2.84 | 7.92 | 7.89 | -1.07 | 0.69 | 1.00 |
| Bam Adebayo | 78 | 18 | PTS | 6.97 | -1.89 | 8.63 | 5.28 | +1.69 | 0.39 | 0.89 |
| Bam Adebayo | 78 | 18 | REB | 3.13 | +2.20 | 3.52 | 2.58 | +0.54 | 0.44 | 0.94 |
| Bam Adebayo | 78 | 18 | AST | 1.88 | +0.21 | 2.30 | 2.45 | -0.56 | 0.56 | 0.94 |
| Bam Adebayo | 78 | 18 | PRA | 9.12 | +0.82 | 10.66 | 7.06 | +2.07 | 0.44 | 0.89 |
| Cade Cunningham | 70 | 10 | PTS | 6.99 | +0.29 | 8.40 | 6.50 | +0.49 | 0.70 | 0.90 |
| Cade Cunningham | 70 | 10 | REB | 2.65 | -0.78 | 3.00 | 2.14 | +0.51 | 0.30 | 0.80 |
| Cade Cunningham | 70 | 10 | AST | 2.09 | +0.99 | 2.65 | 2.68 | -0.59 | 0.60 | 0.90 |
| Cade Cunningham | 70 | 10 | PRA | 6.18 | -0.21 | 8.09 | 7.78 | -1.61 | 0.50 | 0.90 |
| Coby White | 74 | 14 | PTS | 11.51 | -6.29 | 12.72 | 5.60 | +5.91 | 0.50 | 0.79 |
| Coby White | 74 | 14 | REB | 2.21 | -1.43 | 3.23 | 1.88 | +0.33 | 0.57 | 0.86 |
| Coby White | 74 | 14 | AST | 1.46 | -0.15 | 2.00 | 2.06 | -0.60 | 0.50 | 0.86 |
| Coby White | 74 | 14 | PRA | 12.20 | -6.54 | 13.26 | 7.01 | +5.20 | 0.29 | 0.86 |
| Darius Garland | 75 | 15 | PTS | 4.91 | +0.26 | 6.18 | 5.57 | -0.66 | 0.60 | 0.80 |
| Darius Garland | 75 | 15 | REB | 1.81 | -1.50 | 2.18 | 1.22 | +0.59 | 0.47 | 0.80 |
| Darius Garland | 75 | 15 | AST | 2.15 | -1.69 | 2.87 | 1.74 | +0.41 | 0.87 | 0.93 |
| Darius Garland | 75 | 15 | PRA | 5.41 | -3.10 | 7.10 | 5.40 | +0.01 | 0.67 | 0.93 |
| DeMar DeRozan | 77 | 17 | PTS | 5.23 | -0.55 | 7.43 | 6.36 | -1.14 | 0.65 | 0.94 |
| DeMar DeRozan | 77 | 17 | REB | 1.94 | +1.20 | 2.39 | 1.53 | +0.41 | 0.59 | 0.82 |
| DeMar DeRozan | 77 | 17 | AST | 3.04 | -2.28 | 3.71 | 1.94 | +1.10 | 0.41 | 0.82 |
| DeMar DeRozan | 77 | 17 | PRA | 6.48 | -1.38 | 8.35 | 7.91 | -1.43 | 0.71 | 1.00 |
| Deni Avdija | 72 | 12 | PTS | 10.49 | -10.24 | 12.87 | 6.48 | +4.01 | 0.58 | 0.83 |
| Deni Avdija | 72 | 12 | REB | 3.83 | -2.90 | 4.72 | 2.57 | +1.26 | 0.50 | 0.75 |
| Deni Avdija | 72 | 12 | AST | 2.15 | -1.37 | 2.77 | 1.64 | +0.51 | 0.58 | 0.83 |
| Deni Avdija | 72 | 12 | PRA | 15.60 | -14.59 | 18.29 | 8.88 | +6.72 | 0.42 | 0.92 |
| Derrick White | 76 | 16 | PTS | 3.72 | -0.39 | 4.30 | 5.03 | -1.31 | 0.94 | 1.00 |
| Derrick White | 76 | 16 | REB | 2.32 | -1.40 | 2.73 | 1.75 | +0.58 | 0.62 | 0.81 |
| Derrick White | 76 | 16 | AST | 2.12 | -1.55 | 2.64 | 1.98 | +0.13 | 0.38 | 0.81 |
| Derrick White | 76 | 16 | PRA | 4.40 | -3.24 | 5.66 | 6.24 | -1.84 | 0.94 | 1.00 |
| Devin Booker | 75 | 15 | PTS | 8.87 | +3.61 | 9.92 | 6.76 | +2.12 | 0.53 | 0.80 |
| Devin Booker | 75 | 15 | REB | 1.62 | +0.08 | 1.87 | 1.44 | +0.17 | 0.60 | 0.73 |
| Devin Booker | 75 | 15 | AST | 3.28 | -1.03 | 3.78 | 2.05 | +1.23 | 0.33 | 0.47 |
| Devin Booker | 75 | 15 | PRA | 7.65 | +2.57 | 10.00 | 6.52 | +1.13 | 0.40 | 0.73 |
| Domantas Sabonis | 70 | 10 | PTS | 4.07 | +0.63 | 4.90 | 4.14 | -0.07 | 0.50 | 0.80 |
| Domantas Sabonis | 70 | 10 | REB | 2.80 | +2.05 | 3.43 | 3.36 | -0.56 | 0.70 | 1.00 |
| Domantas Sabonis | 70 | 10 | AST | 2.06 | +0.82 | 2.87 | 2.47 | -0.41 | 0.60 | 0.70 |
| Domantas Sabonis | 70 | 10 | PRA | 4.88 | +2.53 | 7.04 | 6.48 | -1.61 | 0.80 | 1.00 |
| Evan Mobley | 71 | 11 | PTS | 5.65 | +1.48 | 6.66 | 5.50 | +0.15 | 0.45 | 0.91 |
| Evan Mobley | 71 | 11 | REB | 2.69 | -0.87 | 3.05 | 2.49 | +0.19 | 0.82 | 1.00 |
| Evan Mobley | 71 | 11 | AST | 1.31 | -0.35 | 1.64 | 1.70 | -0.39 | 0.73 | 0.91 |
| Evan Mobley | 71 | 11 | PRA | 7.03 | +0.49 | 8.15 | 7.36 | -0.34 | 0.55 | 0.91 |
| Giannis Antetokounmpo | 67 | 7 | PTS | 5.22 | -3.54 | 5.83 | 4.81 | +0.41 | 0.57 | 0.57 |
| Giannis Antetokounmpo | 67 | 7 | REB | 3.13 | +0.12 | 3.90 | 2.41 | +0.71 | 0.71 | 0.86 |
| Giannis Antetokounmpo | 67 | 7 | AST | 5.65 | -5.25 | 7.24 | 2.37 | +3.28 | 0.29 | 0.43 |
| Giannis Antetokounmpo | 67 | 7 | PRA | 9.31 | -8.71 | 12.94 | 5.42 | +3.89 | 0.43 | 0.57 |
| Ivica Zubac | 80 | 20 | PTS | 3.63 | +1.11 | 4.29 | 5.11 | -1.48 | 0.85 | 1.00 |
| Ivica Zubac | 80 | 20 | REB | 3.25 | -0.44 | 4.44 | 2.95 | +0.30 | 0.60 | 0.80 |
| Ivica Zubac | 80 | 20 | AST | 1.80 | -0.73 | 2.59 | 1.16 | +0.63 | 0.55 | 0.75 |
| Ivica Zubac | 80 | 20 | PRA | 6.53 | -0.70 | 7.83 | 7.23 | -0.70 | 0.70 | 0.90 |
| Jaden McDaniels | 82 | 22 | PTS | 5.79 | +4.05 | 7.39 | 5.16 | +0.63 | 0.77 | 0.91 |
| Jaden McDaniels | 82 | 22 | REB | 2.93 | +2.00 | 3.56 | 2.29 | +0.64 | 0.45 | 0.91 |
| Jaden McDaniels | 82 | 22 | AST | 1.51 | -0.02 | 1.87 | 1.14 | +0.37 | 0.36 | 0.86 |
| Jaden McDaniels | 82 | 22 | PRA | 8.61 | +5.75 | 10.38 | 6.41 | +2.19 | 0.55 | 0.95 |
| Jalen Brunson | 65 | 5 | PTS | 8.19 | +0.33 | 9.21 | 7.03 | +1.16 | 0.40 | 1.00 |
| Jalen Brunson | 65 | 5 | REB | 1.39 | +0.93 | 1.47 | 1.34 | +0.05 | 0.60 | 1.00 |
| Jalen Brunson | 65 | 5 | AST | 2.91 | +0.78 | 3.16 | 1.99 | +0.92 | 0.00 | 0.60 |
| Jalen Brunson | 65 | 5 | PRA | 10.59 | +2.07 | 11.83 | 8.02 | +2.56 | 0.40 | 0.80 |
| Jalen Duren | 78 | 18 | PTS | 3.43 | +1.04 | 4.48 | 4.08 | -0.65 | 0.56 | 0.83 |
| Jalen Duren | 78 | 18 | REB | 3.55 | -0.75 | 4.30 | 2.83 | +0.71 | 0.39 | 0.83 |
| Jalen Duren | 78 | 18 | AST | 1.81 | -0.50 | 2.33 | 1.36 | +0.45 | 0.56 | 0.89 |
| Jalen Duren | 78 | 18 | PRA | 5.26 | -0.31 | 7.82 | 6.42 | -1.16 | 0.56 | 0.89 |
| Jalen Green | 82 | 22 | PTS | 9.87 | +3.21 | 11.62 | 7.00 | +2.87 | 0.50 | 0.82 |
| Jalen Green | 82 | 22 | REB | 2.31 | -1.27 | 2.98 | 1.64 | +0.67 | 0.50 | 0.82 |
| Jalen Green | 82 | 22 | AST | 1.94 | -1.01 | 2.80 | 1.63 | +0.31 | 0.64 | 0.86 |
| Jalen Green | 82 | 22 | PRA | 10.50 | +0.60 | 12.46 | 7.36 | +3.14 | 0.59 | 0.82 |
| Jalen Williams | 69 | 9 | PTS | 5.95 | -0.88 | 7.00 | 5.03 | +0.92 | 0.67 | 0.67 |
| Jalen Williams | 69 | 9 | REB | 1.42 | +0.91 | 1.71 | 1.58 | -0.16 | 0.67 | 0.78 |
| Jalen Williams | 69 | 9 | AST | 1.67 | +1.55 | 1.93 | 1.61 | +0.06 | 0.67 | 1.00 |
| Jalen Williams | 69 | 9 | PRA | 6.17 | +1.42 | 7.41 | 5.53 | +0.64 | 0.33 | 0.89 |
| Jarrett Allen | 82 | 22 | PTS | 6.66 | -0.80 | 8.04 | 4.10 | +2.56 | 0.41 | 0.45 |
| Jarrett Allen | 82 | 22 | REB | 3.60 | +1.24 | 4.25 | 2.97 | +0.63 | 0.36 | 0.91 |
| Jarrett Allen | 82 | 22 | AST | 1.18 | +0.36 | 1.37 | 1.31 | -0.14 | 0.73 | 1.00 |
| Jarrett Allen | 82 | 22 | PRA | 8.88 | +0.88 | 11.36 | 6.76 | +2.13 | 0.41 | 0.64 |
| Jayson Tatum | 72 | 12 | PTS | 6.20 | +1.67 | 7.24 | 7.27 | -1.07 | 0.58 | 1.00 |
| Jayson Tatum | 72 | 12 | REB | 2.44 | +1.27 | 3.20 | 3.14 | -0.70 | 0.58 | 0.83 |
| Jayson Tatum | 72 | 12 | AST | 1.65 | -0.45 | 1.94 | 2.41 | -0.77 | 0.75 | 1.00 |
| Jayson Tatum | 72 | 12 | PRA | 6.12 | +2.51 | 7.93 | 8.12 | -2.00 | 0.75 | 1.00 |
| Josh Hart | 77 | 17 | PTS | 5.32 | +4.08 | 6.59 | 4.08 | +1.24 | 0.47 | 1.00 |
| Josh Hart | 77 | 17 | REB | 2.88 | +0.87 | 3.50 | 3.66 | -0.78 | 0.65 | 0.94 |
| Josh Hart | 77 | 17 | AST | 2.60 | -1.39 | 3.21 | 2.55 | +0.05 | 0.53 | 0.82 |
| Josh Hart | 77 | 17 | PRA | 7.26 | +3.96 | 8.74 | 6.81 | +0.45 | 0.41 | 1.00 |
| Julius Randle | 69 | 9 | PTS | 8.78 | -5.37 | 10.21 | 4.46 | +4.32 | 0.22 | 0.67 |
| Julius Randle | 69 | 9 | REB | 1.76 | -0.02 | 2.01 | 1.96 | -0.20 | 0.56 | 1.00 |
| Julius Randle | 69 | 9 | AST | 1.38 | +0.37 | 1.60 | 1.88 | -0.50 | 0.78 | 1.00 |
| Julius Randle | 69 | 9 | PRA | 8.66 | -4.87 | 10.78 | 5.59 | +3.08 | 0.44 | 0.78 |
| Karl-Anthony Towns | 72 | 12 | PTS | 6.66 | -2.19 | 7.81 | 7.10 | -0.45 | 0.83 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | REB | 3.32 | +1.87 | 3.93 | 3.98 | -0.66 | 0.92 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | AST | 1.86 | -0.17 | 2.79 | 1.66 | +0.20 | 0.58 | 0.92 |
| Karl-Anthony Towns | 72 | 12 | PRA | 7.43 | -1.11 | 9.07 | 9.32 | -1.90 | 0.83 | 1.00 |
| Kyle Kuzma | 65 | 5 | PTS | 4.07 | -0.37 | 4.57 | 4.90 | -0.83 | 0.40 | 1.00 |
| Kyle Kuzma | 65 | 5 | REB | 2.41 | +2.41 | 2.65 | 2.48 | -0.07 | 0.40 | 1.00 |
| Kyle Kuzma | 65 | 5 | AST | 1.11 | +0.36 | 1.35 | 1.45 | -0.34 | 0.60 | 1.00 |
| Kyle Kuzma | 65 | 5 | PRA | 5.38 | +2.39 | 6.33 | 6.14 | -0.76 | 0.60 | 0.80 |
| LeBron James | 70 | 10 | PTS | 6.82 | +5.60 | 8.64 | 5.95 | +0.87 | 0.60 | 0.80 |
| LeBron James | 70 | 10 | REB | 2.83 | +1.48 | 3.72 | 2.87 | -0.04 | 0.50 | 0.90 |
| LeBron James | 70 | 10 | AST | 2.60 | -0.64 | 3.19 | 2.27 | +0.33 | 0.60 | 0.90 |
| LeBron James | 70 | 10 | PRA | 7.25 | +6.33 | 8.70 | 7.08 | +0.17 | 0.60 | 0.90 |
| Michael Porter Jr. | 77 | 17 | PTS | 5.22 | +3.02 | 6.28 | 5.15 | +0.07 | 0.76 | 1.00 |
| Michael Porter Jr. | 77 | 17 | REB | 2.69 | -0.76 | 3.23 | 2.47 | +0.21 | 0.76 | 0.94 |
| Michael Porter Jr. | 77 | 17 | AST | 1.15 | -0.25 | 1.54 | 1.30 | -0.14 | 0.76 | 0.94 |
| Michael Porter Jr. | 77 | 17 | PRA | 6.03 | +1.90 | 7.50 | 5.99 | +0.04 | 0.65 | 1.00 |
| Mikal Bridges | 82 | 21 | PTS | 5.50 | +0.96 | 6.84 | 6.48 | -0.98 | 0.57 | 0.95 |
| Mikal Bridges | 82 | 21 | REB | 1.31 | -0.66 | 1.64 | 1.45 | -0.15 | 0.76 | 0.90 |
| Mikal Bridges | 82 | 21 | AST | 2.42 | -2.19 | 3.13 | 1.55 | +0.86 | 0.29 | 0.67 |
| Mikal Bridges | 82 | 21 | PRA | 5.98 | -2.17 | 7.56 | 6.89 | -0.91 | 0.62 | 0.95 |
| Myles Turner | 72 | 12 | PTS | 4.97 | -1.16 | 6.05 | 3.93 | +1.04 | 0.42 | 0.67 |
| Myles Turner | 72 | 12 | REB | 3.49 | -2.35 | 4.05 | 2.24 | +1.25 | 0.50 | 0.92 |
| Myles Turner | 72 | 12 | AST | 0.68 | +0.60 | 0.77 | 0.86 | -0.18 | 0.83 | 0.92 |
| Myles Turner | 72 | 12 | PRA | 6.26 | -2.67 | 7.20 | 5.34 | +0.92 | 0.58 | 0.83 |
| Naz Reid | 80 | 20 | PTS | 5.95 | +3.77 | 7.05 | 6.40 | -0.45 | 0.70 | 0.90 |
| Naz Reid | 80 | 20 | REB | 2.30 | -1.91 | 2.85 | 2.93 | -0.63 | 0.80 | 1.00 |
| Naz Reid | 80 | 20 | AST | 1.12 | +0.20 | 1.43 | 1.26 | -0.14 | 0.60 | 1.00 |
| Naz Reid | 80 | 20 | PRA | 5.18 | +2.90 | 6.51 | 8.27 | -3.08 | 0.90 | 0.95 |
| Nikola Jokic | 70 | 10 | PTS | 9.92 | -7.30 | 13.80 | 7.26 | +2.66 | 0.70 | 0.90 |
| Nikola Jokic | 70 | 10 | REB | 2.59 | +1.22 | 3.32 | 3.95 | -1.35 | 0.80 | 1.00 |
| Nikola Jokic | 70 | 10 | AST | 2.81 | +0.13 | 3.36 | 3.16 | -0.36 | 0.70 | 1.00 |
| Nikola Jokic | 70 | 10 | PRA | 12.00 | -5.87 | 14.43 | 9.07 | +2.93 | 0.70 | 0.90 |
| Nikola Vucevic | 73 | 13 | PTS | 8.20 | -7.82 | 10.21 | 5.80 | +2.40 | 0.77 | 0.92 |
| Nikola Vucevic | 73 | 13 | REB | 1.92 | -0.06 | 2.24 | 2.54 | -0.62 | 0.77 | 1.00 |
| Nikola Vucevic | 73 | 13 | AST | 2.48 | -0.94 | 2.91 | 1.44 | +1.04 | 0.46 | 0.77 |
| Nikola Vucevic | 73 | 13 | PRA | 9.87 | -7.85 | 11.84 | 7.99 | +1.87 | 0.46 | 1.00 |
| OG Anunoby | 74 | 14 | PTS | 9.50 | -7.34 | 10.96 | 6.24 | +3.26 | 0.36 | 0.79 |
| OG Anunoby | 74 | 14 | REB | 1.51 | +0.18 | 1.97 | 1.98 | -0.46 | 0.64 | 1.00 |
| OG Anunoby | 74 | 14 | AST | 1.17 | -0.25 | 1.52 | 1.22 | -0.06 | 0.50 | 0.93 |
| OG Anunoby | 74 | 14 | PRA | 10.09 | -7.24 | 11.76 | 7.60 | +2.49 | 0.50 | 1.00 |
| Onyeka Okongwu | 74 | 14 | PTS | 5.29 | -0.61 | 6.86 | 4.56 | +0.72 | 0.57 | 0.71 |
| Onyeka Okongwu | 74 | 14 | REB | 3.16 | +0.71 | 3.61 | 2.72 | +0.44 | 0.57 | 0.71 |
| Onyeka Okongwu | 74 | 14 | AST | 1.08 | -0.08 | 1.44 | 1.35 | -0.27 | 0.29 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PRA | 8.67 | +0.05 | 10.36 | 6.69 | +1.98 | 0.43 | 0.86 |
| Pascal Siakam | 78 | 18 | PTS | 7.59 | +0.85 | 8.37 | 4.43 | +3.16 | 0.11 | 0.72 |
| Pascal Siakam | 78 | 18 | REB | 2.99 | +1.79 | 3.71 | 2.19 | +0.80 | 0.50 | 0.89 |
| Pascal Siakam | 78 | 18 | AST | 1.54 | -0.84 | 1.79 | 1.59 | -0.05 | 0.44 | 0.83 |
| Pascal Siakam | 78 | 18 | PRA | 8.64 | +1.74 | 9.52 | 5.20 | +3.43 | 0.17 | 0.78 |
| Rudy Gobert | 72 | 12 | PTS | 6.97 | -5.34 | 8.90 | 3.97 | +3.00 | 0.17 | 0.58 |
| Rudy Gobert | 72 | 12 | REB | 4.47 | -3.15 | 5.95 | 3.15 | +1.32 | 0.50 | 0.58 |
| Rudy Gobert | 72 | 12 | AST | 1.05 | +0.09 | 1.22 | 1.38 | -0.33 | 0.83 | 0.92 |
| Rudy Gobert | 72 | 12 | PRA | 11.02 | -8.84 | 12.85 | 6.50 | +4.52 | 0.17 | 0.50 |
| Scottie Barnes | 65 | 5 | PTS | 10.70 | -1.36 | 12.15 | 4.72 | +5.98 | 0.40 | 0.60 |
| Scottie Barnes | 65 | 5 | REB | 3.12 | -0.16 | 3.34 | 3.01 | +0.10 | 0.20 | 0.80 |
| Scottie Barnes | 65 | 5 | AST | 1.49 | +0.56 | 1.77 | 2.07 | -0.58 | 0.60 | 1.00 |
| Scottie Barnes | 65 | 5 | PRA | 13.70 | -0.76 | 15.58 | 6.68 | +7.02 | 0.40 | 0.40 |
| Shai Gilgeous-Alexander | 76 | 16 | PTS | 6.11 | +2.23 | 7.14 | 6.68 | -0.57 | 0.69 | 1.00 |
| Shai Gilgeous-Alexander | 76 | 16 | REB | 2.16 | +0.55 | 2.60 | 2.10 | +0.06 | 0.75 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | AST | 1.79 | -0.97 | 2.26 | 1.88 | -0.09 | 0.75 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | PRA | 5.89 | +1.78 | 7.13 | 7.23 | -1.35 | 0.75 | 1.00 |
| Stephen Curry | 70 | 10 | PTS | 11.38 | -2.12 | 14.07 | 7.46 | +3.92 | 0.30 | 0.80 |
| Stephen Curry | 70 | 10 | REB | 2.52 | -1.93 | 3.50 | 1.76 | +0.76 | 0.50 | 0.70 |
| Stephen Curry | 70 | 10 | AST | 1.21 | -0.59 | 1.53 | 2.36 | -1.15 | 0.90 | 1.00 |
| Stephen Curry | 70 | 10 | PRA | 12.90 | -4.66 | 16.15 | 8.29 | +4.61 | 0.50 | 0.90 |
| Trae Young | 76 | 16 | PTS | 5.38 | +2.07 | 6.57 | 7.62 | -2.24 | 0.88 | 1.00 |
| Trae Young | 76 | 16 | REB | 1.66 | -0.51 | 1.99 | 1.31 | +0.35 | 0.62 | 0.81 |
| Trae Young | 76 | 16 | AST | 2.00 | -0.48 | 2.91 | 3.67 | -1.67 | 0.88 | 1.00 |
| Trae Young | 76 | 16 | PRA | 5.51 | +1.24 | 7.52 | 7.77 | -2.26 | 0.56 | 1.00 |
| Tyrese Haliburton | 73 | 13 | PTS | 4.51 | +3.18 | 5.76 | 6.56 | -2.05 | 0.85 | 1.00 |
| Tyrese Haliburton | 73 | 13 | REB | 2.25 | -0.05 | 2.64 | 1.41 | +0.84 | 0.38 | 0.38 |
| Tyrese Haliburton | 73 | 13 | AST | 3.27 | -1.05 | 4.08 | 2.35 | +0.91 | 0.46 | 0.77 |
| Tyrese Haliburton | 73 | 13 | PRA | 4.10 | +1.61 | 5.37 | 8.49 | -4.39 | 0.92 | 1.00 |

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
