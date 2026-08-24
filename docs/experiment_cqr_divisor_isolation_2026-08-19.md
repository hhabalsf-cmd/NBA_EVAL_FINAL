> **EXPERIMENT, not a headline result.** This run is identical to the post-fix
> backtest except `_interval_divisor` was pinned to `DEFAULT_INTERVAL_TO_STD_DIVISOR`
> (2.56) instead of consuming the learned per-stat value. It exists to attribute the
> calibration regression.
>
> **Finding:** overall Brier 0.2389 here vs 0.2388 with the learned divisor — no
> measurable difference. The regression vs baseline is caused by the de-leak
> (honest measurement), not by the divisor wiring. Basis for pinning
> `CONSUME_LEARNED_INTERVAL_DIVISOR = False`.
>
> **Caveat:** predates the Optuna seeding fix, so it carries the ~3% run-to-run
> MAE noise that this pair of runs is what exposed. Its MAE column is not
> comparable at fine resolution; the Brier comparison is (Brier proved stable
> across both unseeded runs).

# Unbiased Walk-Forward Backtest — Baseline (2026-08-19)

Measured **before** any model fixes land. This is the "before" column.

- **Season:** 2024-25
- **Train:** first 60 feature rows per player (single fit, never refit)
- **Test:** every remaining row, predicted one at a time
- **Pipeline:** `full (ensemble + meta-learner)`
- **Stats:** PTS, REB, AST, PRA (PRA = reconciled 0.85·(P+R+A) + 0.15·independent)
- **Players attempted / evaluated / skipped:** 58 / 44 / 14
- **Held-out predictions:** 2424
- **Pseudo-line probability samples:** 16729
- **Wall clock:** 12.0 min

## 1. Per-stat holdout accuracy

`MAE (pooled)` weights every held-out game equally; `MAE (player mean)` is the unweighted mean of per-player MAEs (comparable with `eval_holdout.py`). **MAE gap** is the mean per-player `holdout MAE − train OOF MAE` — the overfitting measure.

| Stat | Players | N test | MAE (pooled) | MAE (player mean) | Bias (pred−actual) | RMSE | Train OOF MAE | MAE gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 44 | 606 | 6.48 | 6.62 | -0.27 | 8.12 | 5.65 | **+0.96** |
| REB | 44 | 606 | 2.55 | 2.56 | +0.22 | 3.27 | 2.29 | **+0.27** |
| AST | 44 | 606 | 1.85 | 1.88 | -0.40 | 2.47 | 1.87 | **+0.01** |
| PRA | 44 | 606 | 7.52 | 7.72 | -0.37 | 9.60 | 6.99 | **+0.73** |

## 2. 80% interval coverage

Raw band is the untouched (q10, q90) quantile pair — target 0.80. The CQR band adds the per-stat conformal correction learned at training time, which targets ~0.90-0.92.

| Stat | Train OOF cov (raw) | Holdout cov RAW (target 0.80) | Mean CQR correction | Holdout cov CQR (target ~0.90) |
|---|---:|---:|---:|---:|
| PTS | 0.64 | 0.57 | 5.75 | 0.83 |
| REB | 0.61 | 0.56 | 2.56 | 0.88 |
| AST | 0.61 | 0.60 | 1.97 | 0.88 |
| PRA | 0.64 | 0.59 | 7.65 | 0.88 |

## 3. Probability calibration (pseudo-lines)

Each held-out prediction is scored against 7 pseudo-lines: prediction ± {0.5, 1.5, 2.5} and the player's season-to-date median (computed only from games before the row being predicted). `prob_over` comes from the production `ProbabilityCalculator.calculate` path — same std from `get_confidence`, same Platt calibrator — and is clipped to [15%, 85%] by `PROB_FLOOR`/`PROB_CEIL`.

### 3a. Overall reliability by predicted-probability decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap (pred − realized) |
|---|---:|---:|---:|---:|
| 10-20% | 680 | 16.4% | 22.8% | -6.4 |
| 20-30% | 1090 | 25.4% | 31.6% | -6.1 |
| 30-40% | 1834 | 35.6% | 41.3% | -5.7 |
| 40-50% | 3007 | 45.2% | 46.9% | -1.7 |
| 50-60% | 4119 | 54.8% | 50.9% | +3.9 |
| 60-70% | 3209 | 64.6% | 55.0% | +9.6 |
| 70-80% | 1750 | 74.6% | 63.5% | +11.1 |
| 80-90% | 1040 | 83.5% | 82.3% | +1.2 |

- **Overall Brier score:** 0.2389

### 3b. By stat

| Stat | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| PTS | 4208 | 54.0% | 50.7% | +3.3 | 0.2625 |
| REB | 4170 | 53.2% | 47.3% | +5.9 | 0.2334 |
| AST | 4127 | 51.5% | 54.1% | -2.6 | 0.1965 |
| PRA | 4224 | 54.3% | 51.0% | +3.2 | 0.2623 |

### 3c. By pseudo-line type

`offset` lines are centred on the prediction (half are near coin-flips by construction); `median` lines sit at the player's season-to-date median and are the closest stand-in for a real market line.

| Line type | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| offset | 14542 | 52.9% | 50.1% | +2.8 | 0.2357 |
| median | 2187 | 55.7% | 55.1% | +0.6 | 0.2602 |

### 3d. Median-line reliability by decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap |
|---|---:|---:|---:|---:|
| 10-20% | 32 | 16.3% | 53.1% | -36.8 |
| 20-30% | 123 | 25.3% | 48.0% | -22.7 |
| 30-40% | 214 | 35.9% | 56.1% | -20.2 |
| 40-50% | 402 | 45.0% | 52.0% | -7.0 |
| 50-60% | 531 | 54.9% | 51.6% | +3.3 |
| 60-70% | 412 | 64.4% | 53.6% | +10.7 |
| 70-80% | 301 | 74.6% | 62.1% | +12.5 |
| 80-90% | 172 | 83.4% | 69.2% | +14.2 |

## 4. Per-player appendix

| Player | Games | N test | Stat | Holdout MAE | Bias | RMSE | Train OOF MAE | MAE gap | Cov RAW | Cov CQR |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Alperen Sengun | 76 | 16 | PTS | 6.40 | +3.88 | 7.42 | 5.09 | +1.31 | 0.56 | 0.75 |
| Alperen Sengun | 76 | 16 | REB | 3.77 | +0.14 | 4.87 | 2.43 | +1.34 | 0.44 | 0.62 |
| Alperen Sengun | 76 | 16 | AST | 1.66 | +0.10 | 2.15 | 1.77 | -0.11 | 0.44 | 0.81 |
| Alperen Sengun | 76 | 16 | PRA | 5.96 | +4.03 | 7.86 | 6.65 | -0.69 | 0.75 | 0.81 |
| Amen Thompson | 69 | 9 | PTS | 3.85 | +3.61 | 5.06 | 6.12 | -2.27 | 1.00 | 1.00 |
| Amen Thompson | 69 | 9 | REB | 4.31 | +4.31 | 4.81 | 2.60 | +1.71 | 0.67 | 1.00 |
| Amen Thompson | 69 | 9 | AST | 1.43 | -0.41 | 2.02 | 2.10 | -0.67 | 0.78 | 1.00 |
| Amen Thompson | 69 | 9 | PRA | 7.11 | +7.11 | 8.92 | 8.16 | -1.05 | 0.78 | 1.00 |
| Anfernee Simons | 70 | 10 | PTS | 8.16 | -0.31 | 9.91 | 6.71 | +1.45 | 0.50 | 0.90 |
| Anfernee Simons | 70 | 10 | REB | 1.38 | +0.87 | 1.56 | 1.27 | +0.12 | 0.40 | 0.90 |
| Anfernee Simons | 70 | 10 | AST | 1.83 | +0.99 | 2.33 | 1.51 | +0.32 | 0.60 | 0.70 |
| Anfernee Simons | 70 | 10 | PRA | 6.35 | +1.58 | 7.80 | 7.31 | -0.96 | 0.70 | 0.80 |
| Anthony Edwards | 79 | 19 | PTS | 8.13 | -1.80 | 9.98 | 7.75 | +0.37 | 0.68 | 0.95 |
| Anthony Edwards | 79 | 19 | REB | 2.39 | +0.77 | 3.02 | 1.91 | +0.47 | 0.21 | 0.84 |
| Anthony Edwards | 79 | 19 | AST | 1.58 | +1.20 | 1.88 | 2.00 | -0.43 | 0.89 | 1.00 |
| Anthony Edwards | 79 | 19 | PRA | 7.75 | +0.90 | 9.91 | 8.10 | -0.35 | 0.68 | 1.00 |
| Austin Reaves | 73 | 13 | PTS | 4.87 | +1.63 | 6.22 | 5.73 | -0.85 | 0.54 | 1.00 |
| Austin Reaves | 73 | 13 | REB | 1.89 | +0.19 | 2.26 | 2.16 | -0.28 | 0.46 | 0.85 |
| Austin Reaves | 73 | 13 | AST | 2.03 | +1.02 | 2.23 | 2.88 | -0.85 | 0.92 | 1.00 |
| Austin Reaves | 73 | 13 | PRA | 6.28 | +2.87 | 7.56 | 8.03 | -1.75 | 0.62 | 1.00 |
| Bam Adebayo | 78 | 18 | PTS | 6.37 | -1.16 | 7.23 | 5.26 | +1.11 | 0.72 | 0.94 |
| Bam Adebayo | 78 | 18 | REB | 3.07 | +1.65 | 3.34 | 2.30 | +0.76 | 0.33 | 0.94 |
| Bam Adebayo | 78 | 18 | AST | 2.14 | +0.65 | 2.51 | 2.23 | -0.09 | 0.44 | 1.00 |
| Bam Adebayo | 78 | 18 | PRA | 8.72 | +1.55 | 9.84 | 6.60 | +2.12 | 0.50 | 0.78 |
| Cade Cunningham | 70 | 10 | PTS | 7.36 | -0.78 | 8.43 | 6.53 | +0.84 | 0.60 | 0.90 |
| Cade Cunningham | 70 | 10 | REB | 3.20 | -2.40 | 3.82 | 2.17 | +1.03 | 0.50 | 0.90 |
| Cade Cunningham | 70 | 10 | AST | 2.27 | +1.39 | 2.90 | 2.70 | -0.44 | 0.70 | 1.00 |
| Cade Cunningham | 70 | 10 | PRA | 6.76 | -1.88 | 7.84 | 7.71 | -0.95 | 0.70 | 1.00 |
| Coby White | 74 | 14 | PTS | 10.00 | -1.31 | 12.06 | 5.51 | +4.49 | 0.64 | 0.64 |
| Coby White | 74 | 14 | REB | 2.48 | -1.93 | 3.49 | 1.61 | +0.87 | 0.64 | 0.79 |
| Coby White | 74 | 14 | AST | 1.44 | -0.23 | 1.97 | 1.94 | -0.50 | 0.57 | 0.93 |
| Coby White | 74 | 14 | PRA | 10.82 | -2.94 | 12.19 | 7.28 | +3.54 | 0.57 | 1.00 |
| Darius Garland | 75 | 15 | PTS | 6.39 | +3.07 | 7.59 | 4.85 | +1.54 | 0.60 | 0.80 |
| Darius Garland | 75 | 15 | REB | 1.58 | -1.30 | 1.93 | 1.20 | +0.38 | 0.47 | 0.87 |
| Darius Garland | 75 | 15 | AST | 1.79 | -0.94 | 2.34 | 1.94 | -0.15 | 0.93 | 0.93 |
| Darius Garland | 75 | 15 | PRA | 5.95 | +0.29 | 7.32 | 4.70 | +1.25 | 0.67 | 0.93 |
| DeMar DeRozan | 77 | 17 | PTS | 5.73 | -1.81 | 7.40 | 6.28 | -0.55 | 0.71 | 0.94 |
| DeMar DeRozan | 77 | 17 | REB | 1.89 | +1.14 | 2.36 | 1.58 | +0.30 | 0.82 | 0.94 |
| DeMar DeRozan | 77 | 17 | AST | 2.79 | -1.94 | 3.42 | 1.87 | +0.92 | 0.12 | 0.76 |
| DeMar DeRozan | 77 | 17 | PRA | 6.15 | -2.12 | 8.38 | 7.76 | -1.61 | 0.59 | 1.00 |
| Deni Avdija | 72 | 12 | PTS | 9.83 | -9.61 | 12.14 | 5.67 | +4.15 | 0.33 | 0.58 |
| Deni Avdija | 72 | 12 | REB | 3.92 | -2.71 | 4.81 | 2.46 | +1.46 | 0.58 | 0.67 |
| Deni Avdija | 72 | 12 | AST | 1.78 | -0.70 | 2.22 | 1.65 | +0.13 | 0.42 | 0.83 |
| Deni Avdija | 72 | 12 | PRA | 13.46 | -12.33 | 16.28 | 7.79 | +5.67 | 0.42 | 0.58 |
| Derrick White | 76 | 16 | PTS | 3.60 | +0.28 | 4.34 | 5.27 | -1.67 | 1.00 | 1.00 |
| Derrick White | 76 | 16 | REB | 2.17 | -1.58 | 2.69 | 1.86 | +0.31 | 0.50 | 0.88 |
| Derrick White | 76 | 16 | AST | 2.03 | -1.49 | 2.59 | 1.90 | +0.13 | 0.38 | 0.56 |
| Derrick White | 76 | 16 | PRA | 3.76 | -2.62 | 5.12 | 6.23 | -2.47 | 0.88 | 1.00 |
| Devin Booker | 75 | 15 | PTS | 8.03 | +2.02 | 10.13 | 6.64 | +1.38 | 0.60 | 0.73 |
| Devin Booker | 75 | 15 | REB | 1.52 | -0.06 | 1.78 | 1.50 | +0.02 | 0.53 | 0.73 |
| Devin Booker | 75 | 15 | AST | 3.25 | -0.98 | 3.74 | 2.08 | +1.17 | 0.33 | 0.40 |
| Devin Booker | 75 | 15 | PRA | 8.30 | +1.06 | 10.64 | 6.52 | +1.78 | 0.53 | 0.93 |
| Domantas Sabonis | 70 | 10 | PTS | 4.42 | +0.67 | 4.79 | 5.01 | -0.59 | 0.70 | 1.00 |
| Domantas Sabonis | 70 | 10 | REB | 2.68 | +1.67 | 3.37 | 3.50 | -0.82 | 0.90 | 1.00 |
| Domantas Sabonis | 70 | 10 | AST | 2.04 | +0.26 | 2.76 | 2.37 | -0.34 | 0.70 | 0.90 |
| Domantas Sabonis | 70 | 10 | PRA | 4.77 | +1.07 | 6.31 | 6.86 | -2.08 | 0.80 | 1.00 |
| Evan Mobley | 71 | 11 | PTS | 5.51 | +0.73 | 6.40 | 5.46 | +0.05 | 0.55 | 0.82 |
| Evan Mobley | 71 | 11 | REB | 3.00 | -0.85 | 3.35 | 2.18 | +0.81 | 0.45 | 1.00 |
| Evan Mobley | 71 | 11 | AST | 1.39 | -0.26 | 1.71 | 1.68 | -0.30 | 0.64 | 1.00 |
| Evan Mobley | 71 | 11 | PRA | 6.61 | -0.23 | 7.85 | 7.37 | -0.76 | 0.64 | 1.00 |
| Giannis Antetokounmpo | 67 | 7 | PTS | 5.60 | -4.81 | 6.77 | 4.93 | +0.67 | 0.43 | 0.43 |
| Giannis Antetokounmpo | 67 | 7 | REB | 2.85 | +0.23 | 3.69 | 2.47 | +0.39 | 0.57 | 0.86 |
| Giannis Antetokounmpo | 67 | 7 | AST | 5.32 | -4.50 | 6.69 | 2.58 | +2.74 | 0.29 | 0.57 |
| Giannis Antetokounmpo | 67 | 7 | PRA | 9.59 | -8.96 | 13.76 | 5.97 | +3.62 | 0.43 | 0.57 |
| Ivica Zubac | 80 | 20 | PTS | 3.96 | -1.70 | 5.00 | 4.74 | -0.78 | 0.80 | 1.00 |
| Ivica Zubac | 80 | 20 | REB | 2.95 | -0.35 | 3.67 | 2.99 | -0.04 | 0.65 | 0.90 |
| Ivica Zubac | 80 | 20 | AST | 1.81 | -0.75 | 2.62 | 1.22 | +0.59 | 0.45 | 0.75 |
| Ivica Zubac | 80 | 20 | PRA | 6.19 | -2.99 | 7.39 | 6.78 | -0.59 | 0.70 | 0.95 |
| Jaden McDaniels | 82 | 22 | PTS | 4.51 | +2.56 | 6.16 | 5.19 | -0.68 | 0.45 | 0.95 |
| Jaden McDaniels | 82 | 22 | REB | 2.65 | +1.45 | 3.26 | 2.24 | +0.41 | 0.32 | 0.91 |
| Jaden McDaniels | 82 | 22 | AST | 1.42 | -0.15 | 1.73 | 1.21 | +0.21 | 0.55 | 0.95 |
| Jaden McDaniels | 82 | 22 | PRA | 7.13 | +4.07 | 9.09 | 7.24 | -0.11 | 0.50 | 0.95 |
| Jalen Brunson | 65 | 5 | PTS | 8.20 | -0.15 | 9.55 | 7.09 | +1.11 | 0.40 | 0.80 |
| Jalen Brunson | 65 | 5 | REB | 1.56 | +1.10 | 1.64 | 1.31 | +0.24 | 0.60 | 1.00 |
| Jalen Brunson | 65 | 5 | AST | 2.55 | -0.40 | 3.02 | 2.30 | +0.25 | 0.20 | 0.60 |
| Jalen Brunson | 65 | 5 | PRA | 11.36 | +0.87 | 12.79 | 7.80 | +3.56 | 0.40 | 0.80 |
| Jalen Duren | 78 | 18 | PTS | 3.50 | +1.18 | 4.81 | 3.65 | -0.16 | 0.56 | 0.83 |
| Jalen Duren | 78 | 18 | REB | 3.82 | -0.15 | 4.72 | 2.64 | +1.18 | 0.44 | 0.83 |
| Jalen Duren | 78 | 18 | AST | 1.69 | -0.11 | 2.11 | 1.35 | +0.34 | 0.50 | 0.78 |
| Jalen Duren | 78 | 18 | PRA | 5.64 | +0.80 | 8.09 | 6.02 | -0.37 | 0.67 | 0.89 |
| Jalen Green | 82 | 22 | PTS | 9.77 | +1.23 | 11.02 | 6.60 | +3.17 | 0.50 | 0.82 |
| Jalen Green | 82 | 22 | REB | 2.47 | -1.10 | 3.00 | 1.76 | +0.72 | 0.32 | 0.77 |
| Jalen Green | 82 | 22 | AST | 2.18 | -0.51 | 2.84 | 1.51 | +0.66 | 0.77 | 0.95 |
| Jalen Green | 82 | 22 | PRA | 10.98 | -0.81 | 12.82 | 7.52 | +3.45 | 0.45 | 0.68 |
| Jalen Williams | 69 | 9 | PTS | 6.27 | -0.64 | 7.19 | 4.59 | +1.68 | 0.67 | 0.89 |
| Jalen Williams | 69 | 9 | REB | 1.61 | +1.14 | 1.94 | 1.64 | -0.03 | 0.67 | 0.89 |
| Jalen Williams | 69 | 9 | AST | 1.08 | +0.42 | 1.22 | 1.56 | -0.48 | 0.89 | 1.00 |
| Jalen Williams | 69 | 9 | PRA | 6.55 | +0.96 | 7.62 | 5.61 | +0.94 | 0.67 | 0.89 |
| Jarrett Allen | 82 | 22 | PTS | 6.91 | +0.31 | 8.17 | 4.52 | +2.39 | 0.14 | 0.32 |
| Jarrett Allen | 82 | 22 | REB | 3.38 | +0.98 | 4.14 | 2.90 | +0.48 | 0.45 | 0.77 |
| Jarrett Allen | 82 | 22 | AST | 1.06 | +0.21 | 1.23 | 1.33 | -0.27 | 0.77 | 0.95 |
| Jarrett Allen | 82 | 22 | PRA | 8.94 | +1.64 | 11.47 | 7.04 | +1.90 | 0.41 | 0.64 |
| Jayson Tatum | 72 | 12 | PTS | 5.00 | -1.80 | 5.85 | 7.16 | -2.17 | 0.83 | 1.00 |
| Jayson Tatum | 72 | 12 | REB | 2.38 | +1.17 | 3.13 | 2.85 | -0.48 | 0.58 | 0.92 |
| Jayson Tatum | 72 | 12 | AST | 2.06 | -1.26 | 2.28 | 2.41 | -0.35 | 0.83 | 1.00 |
| Jayson Tatum | 72 | 12 | PRA | 5.34 | -1.66 | 6.63 | 7.97 | -2.63 | 0.58 | 1.00 |
| Josh Hart | 77 | 17 | PTS | 5.08 | +3.25 | 6.30 | 4.39 | +0.69 | 0.59 | 0.88 |
| Josh Hart | 77 | 17 | REB | 2.91 | +0.80 | 3.31 | 3.51 | -0.60 | 0.76 | 0.94 |
| Josh Hart | 77 | 17 | AST | 2.40 | -1.47 | 3.01 | 2.33 | +0.07 | 0.65 | 1.00 |
| Josh Hart | 77 | 17 | PRA | 6.71 | +3.16 | 8.23 | 6.82 | -0.11 | 0.65 | 1.00 |
| Julius Randle | 69 | 9 | PTS | 7.65 | -3.95 | 8.60 | 4.35 | +3.30 | 0.22 | 0.67 |
| Julius Randle | 69 | 9 | REB | 1.83 | -0.49 | 2.09 | 2.17 | -0.34 | 0.89 | 1.00 |
| Julius Randle | 69 | 9 | AST | 1.21 | +0.09 | 1.44 | 1.87 | -0.67 | 1.00 | 1.00 |
| Julius Randle | 69 | 9 | PRA | 7.83 | -4.37 | 9.67 | 5.65 | +2.18 | 0.44 | 0.78 |
| Karl-Anthony Towns | 72 | 12 | PTS | 8.19 | -3.76 | 9.02 | 6.32 | +1.87 | 0.75 | 0.92 |
| Karl-Anthony Towns | 72 | 12 | REB | 1.82 | +1.53 | 2.19 | 4.03 | -2.20 | 0.92 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | AST | 2.03 | +0.17 | 2.90 | 1.68 | +0.35 | 0.50 | 0.92 |
| Karl-Anthony Towns | 72 | 12 | PRA | 8.38 | -2.02 | 9.54 | 8.03 | +0.35 | 0.83 | 1.00 |
| Kyle Kuzma | 65 | 5 | PTS | 4.20 | -0.65 | 4.55 | 5.58 | -1.38 | 0.40 | 1.00 |
| Kyle Kuzma | 65 | 5 | REB | 2.54 | +2.54 | 2.73 | 2.43 | +0.11 | 0.60 | 1.00 |
| Kyle Kuzma | 65 | 5 | AST | 1.28 | +0.59 | 1.49 | 1.55 | -0.27 | 0.20 | 1.00 |
| Kyle Kuzma | 65 | 5 | PRA | 5.33 | +2.47 | 6.16 | 7.08 | -1.75 | 0.40 | 1.00 |
| LeBron James | 70 | 10 | PTS | 6.43 | +2.66 | 7.42 | 5.92 | +0.51 | 0.40 | 0.60 |
| LeBron James | 70 | 10 | REB | 3.31 | +2.52 | 4.10 | 2.73 | +0.57 | 0.40 | 0.80 |
| LeBron James | 70 | 10 | AST | 2.13 | +0.22 | 2.79 | 2.21 | -0.08 | 0.60 | 1.00 |
| LeBron James | 70 | 10 | PRA | 6.93 | +5.61 | 8.18 | 7.03 | -0.10 | 0.60 | 0.70 |
| Michael Porter Jr. | 77 | 17 | PTS | 4.59 | +2.37 | 5.58 | 5.54 | -0.95 | 0.71 | 1.00 |
| Michael Porter Jr. | 77 | 17 | REB | 2.63 | +0.35 | 3.21 | 2.38 | +0.26 | 0.35 | 0.94 |
| Michael Porter Jr. | 77 | 17 | AST | 1.27 | -0.66 | 1.61 | 1.29 | -0.02 | 0.47 | 0.82 |
| Michael Porter Jr. | 77 | 17 | PRA | 5.98 | +1.69 | 7.00 | 6.31 | -0.33 | 0.82 | 1.00 |
| Mikal Bridges | 82 | 21 | PTS | 5.77 | +1.66 | 6.86 | 6.11 | -0.34 | 0.48 | 0.90 |
| Mikal Bridges | 82 | 21 | REB | 1.33 | -0.45 | 1.60 | 1.61 | -0.28 | 0.52 | 0.90 |
| Mikal Bridges | 82 | 21 | AST | 1.95 | -1.45 | 2.56 | 1.50 | +0.44 | 0.48 | 0.81 |
| Mikal Bridges | 82 | 21 | PRA | 5.46 | -0.85 | 7.03 | 6.07 | -0.61 | 0.24 | 0.81 |
| Myles Turner | 72 | 12 | PTS | 5.78 | -2.83 | 7.32 | 3.55 | +2.23 | 0.42 | 0.67 |
| Myles Turner | 72 | 12 | REB | 2.76 | -1.31 | 3.21 | 2.09 | +0.67 | 0.33 | 0.83 |
| Myles Turner | 72 | 12 | AST | 0.72 | +0.68 | 0.83 | 0.77 | -0.05 | 0.58 | 0.92 |
| Myles Turner | 72 | 12 | PRA | 6.87 | -3.23 | 8.04 | 4.03 | +2.83 | 0.58 | 0.75 |
| Naz Reid | 80 | 20 | PTS | 4.74 | +0.45 | 5.47 | 6.63 | -1.89 | 0.55 | 0.90 |
| Naz Reid | 80 | 20 | REB | 2.47 | +1.93 | 2.98 | 2.67 | -0.20 | 0.80 | 1.00 |
| Naz Reid | 80 | 20 | AST | 1.12 | +0.19 | 1.42 | 1.13 | -0.01 | 0.70 | 0.95 |
| Naz Reid | 80 | 20 | PRA | 4.32 | +2.78 | 5.98 | 8.16 | -3.84 | 0.90 | 0.95 |
| Nikola Jokic | 70 | 10 | PTS | 9.70 | -6.04 | 13.25 | 6.75 | +2.95 | 0.70 | 0.90 |
| Nikola Jokic | 70 | 10 | REB | 2.65 | +1.42 | 3.33 | 3.84 | -1.19 | 0.90 | 1.00 |
| Nikola Jokic | 70 | 10 | AST | 2.28 | +0.27 | 2.74 | 2.98 | -0.70 | 0.90 | 1.00 |
| Nikola Jokic | 70 | 10 | PRA | 12.36 | -4.22 | 15.15 | 8.60 | +3.75 | 0.40 | 0.80 |
| Nikola Vucevic | 73 | 13 | PTS | 8.19 | -7.85 | 10.20 | 5.60 | +2.59 | 0.46 | 0.92 |
| Nikola Vucevic | 73 | 13 | REB | 1.70 | +0.23 | 2.08 | 2.46 | -0.76 | 0.85 | 1.00 |
| Nikola Vucevic | 73 | 13 | AST | 2.47 | -0.31 | 2.85 | 1.33 | +1.15 | 0.46 | 0.69 |
| Nikola Vucevic | 73 | 13 | PRA | 9.46 | -7.08 | 11.38 | 7.50 | +1.96 | 0.38 | 1.00 |
| OG Anunoby | 74 | 14 | PTS | 9.20 | -5.73 | 10.08 | 6.69 | +2.51 | 0.43 | 0.86 |
| OG Anunoby | 74 | 14 | REB | 1.63 | +0.45 | 2.22 | 1.75 | -0.13 | 0.57 | 0.93 |
| OG Anunoby | 74 | 14 | AST | 1.25 | -0.35 | 1.60 | 1.33 | -0.08 | 0.43 | 0.93 |
| OG Anunoby | 74 | 14 | PRA | 9.81 | -5.60 | 10.93 | 8.13 | +1.68 | 0.57 | 1.00 |
| Onyeka Okongwu | 74 | 14 | PTS | 6.03 | +1.40 | 7.15 | 4.62 | +1.41 | 0.50 | 0.86 |
| Onyeka Okongwu | 74 | 14 | REB | 2.93 | +1.17 | 3.51 | 2.97 | -0.04 | 0.57 | 1.00 |
| Onyeka Okongwu | 74 | 14 | AST | 1.10 | -0.55 | 1.49 | 1.30 | -0.19 | 0.64 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PRA | 8.49 | +1.83 | 10.21 | 7.43 | +1.05 | 0.57 | 0.86 |
| Pascal Siakam | 78 | 18 | PTS | 7.20 | -0.76 | 8.16 | 4.45 | +2.75 | 0.28 | 0.67 |
| Pascal Siakam | 78 | 18 | REB | 2.78 | +1.59 | 3.58 | 2.15 | +0.64 | 0.50 | 0.67 |
| Pascal Siakam | 78 | 18 | AST | 1.93 | -1.63 | 2.30 | 1.53 | +0.40 | 0.39 | 0.89 |
| Pascal Siakam | 78 | 18 | PRA | 8.39 | -0.42 | 9.27 | 4.87 | +3.52 | 0.22 | 0.78 |
| Rudy Gobert | 72 | 12 | PTS | 7.79 | -6.56 | 9.70 | 4.34 | +3.45 | 0.33 | 0.75 |
| Rudy Gobert | 72 | 12 | REB | 4.80 | -3.82 | 6.33 | 3.11 | +1.69 | 0.50 | 0.58 |
| Rudy Gobert | 72 | 12 | AST | 1.02 | -0.13 | 1.27 | 1.25 | -0.23 | 0.92 | 1.00 |
| Rudy Gobert | 72 | 12 | PRA | 12.19 | -10.66 | 14.21 | 6.18 | +6.01 | 0.42 | 0.58 |
| Scottie Barnes | 65 | 5 | PTS | 9.98 | +2.17 | 11.10 | 4.46 | +5.52 | 0.40 | 0.40 |
| Scottie Barnes | 65 | 5 | REB | 3.30 | -0.17 | 3.53 | 2.82 | +0.47 | 0.60 | 0.80 |
| Scottie Barnes | 65 | 5 | AST | 1.49 | +0.45 | 1.80 | 1.90 | -0.42 | 0.60 | 1.00 |
| Scottie Barnes | 65 | 5 | PRA | 12.55 | +2.79 | 15.14 | 5.98 | +6.57 | 0.40 | 0.60 |
| Shai Gilgeous-Alexander | 76 | 16 | PTS | 7.26 | +4.33 | 8.44 | 5.51 | +1.75 | 0.62 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | REB | 2.01 | +0.60 | 2.33 | 1.95 | +0.05 | 0.62 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | AST | 1.94 | -1.33 | 2.56 | 1.89 | +0.06 | 0.44 | 0.81 |
| Shai Gilgeous-Alexander | 76 | 16 | PRA | 6.66 | +3.17 | 7.74 | 6.40 | +0.26 | 0.75 | 1.00 |
| Stephen Curry | 70 | 10 | PTS | 10.89 | -0.51 | 14.28 | 7.34 | +3.55 | 0.30 | 0.80 |
| Stephen Curry | 70 | 10 | REB | 2.35 | -1.22 | 3.03 | 1.76 | +0.60 | 0.50 | 0.90 |
| Stephen Curry | 70 | 10 | AST | 1.02 | -0.18 | 1.41 | 2.46 | -1.44 | 1.00 | 1.00 |
| Stephen Curry | 70 | 10 | PRA | 11.31 | -1.59 | 15.79 | 8.17 | +3.14 | 0.60 | 0.80 |
| Trae Young | 76 | 16 | PTS | 4.91 | +0.41 | 5.93 | 7.43 | -2.52 | 0.94 | 1.00 |
| Trae Young | 76 | 16 | REB | 1.68 | -0.43 | 1.94 | 1.37 | +0.31 | 0.50 | 0.88 |
| Trae Young | 76 | 16 | AST | 2.01 | -0.45 | 2.90 | 3.58 | -1.57 | 0.88 | 1.00 |
| Trae Young | 76 | 16 | PRA | 5.35 | -0.18 | 7.16 | 7.40 | -2.05 | 0.50 | 1.00 |
| Tyrese Haliburton | 73 | 13 | PTS | 5.26 | +2.19 | 6.01 | 6.83 | -1.57 | 0.92 | 1.00 |
| Tyrese Haliburton | 73 | 13 | REB | 2.19 | -0.44 | 2.61 | 1.43 | +0.77 | 0.38 | 0.62 |
| Tyrese Haliburton | 73 | 13 | AST | 3.58 | -1.63 | 4.19 | 2.17 | +1.41 | 0.54 | 0.77 |
| Tyrese Haliburton | 73 | 13 | PRA | 4.96 | +0.23 | 6.11 | 8.76 | -3.80 | 0.92 | 1.00 |

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

1. **Season-aggregate leakage into historical rows (known, not fixed).** Features are built once over the whole game log, so any season-level aggregate baked into a feature — notably opponent defensive/pace context — reflects the full season rather than what was knowable on that date. This is the same limitation documented in `scripts/eval_holdout.py` (~line 178) and is deliberately left alone here. Rolling features themselves are `shift(1)`-safe: row *i* only summarizes rows `0..i-1`.
2. **The model is frozen after the initial fit.** Production retrains nightly; here a single fit on the first 60 rows predicts every later game. Late-season holdout rows are therefore predicted by an increasingly stale model, which inflates holdout MAE relative to production.
3. **L10 / season anchors are refreshed, the GBM is not.** `_update_recent_averages` is called on the pre-row history before every prediction (production does the same), so the regression-to-mean and deviation-cap anchors stay current with no lookahead.
4. **Early-season damping neutralized.** `_current_season_games` compares the log against the *calendar* current season, so a 2024-25 backtest would trip the <10-games damping (confidence ×0.75, std ×1.3) on every row. The history frame passed to `get_confidence` is stamped with the current season string so damping stays neutral, matching a mid-season production run.
5. **No serve-time context adjustments.** `estimated_minutes` is not supplied (so the rate-model blend and minutes scaling never fire), and the injury boost, blowout discount and questionable dampener are all skipped. This isolates the core model from the context layer.
6. **Pseudo-lines are model-derived, not market lines.** The ±0.5/1.5/2.5 family is centred on the prediction, so it measures the *internal* consistency of prediction + std + calibrator, not edge against a bookmaker. The season-to-date median line is the closest stand-in for a market line — read 3c/3d for that view.
7. **PRA's train-OOF MAE is not the served quantity.** `training_metrics['PRA']` is computed from the *independent* PRA model's OOF predictions, while the holdout column evaluates the reconciled 85/15 blend. The PRA MAE gap therefore compares two slightly different estimators; the PTS/REB/AST gaps are apples-to-apples.
8. **Probabilities are hard-clipped to [15%, 85%]** by `ProbabilityCalculator.PROB_FLOOR/PROB_CEIL`, so the 0-10% and 90-100% deciles are structurally empty and the Brier score is floored by that clipping.
9. **Ties are dropped.** When a realized value lands exactly on a pseudo-line (possible for integer median lines) the sample is excluded rather than scored as an under.
10. **Sample size.** One season, ~50 players, and per-player holdout sets of roughly 5-25 games. Per-player rows in the appendix are noisy; the pooled per-stat numbers are the ones to act on.

## 7. Reading guide

- **MAE gap > 0** ⇒ the OOF metrics stored on the pickle are optimistic (overfitting).
- **Bias > 0** ⇒ the model over-predicts held-out games; **< 0** ⇒ under-predicts.
- **Holdout cov RAW ≪ 0.80** ⇒ quantile intervals are too narrow before CQR.
- **Calibration gap > 0** in a decile ⇒ the model claims more OVER probability than it delivers.
- **Brier** is the headline probability score (lower is better; 0.25 = always saying 50%).
