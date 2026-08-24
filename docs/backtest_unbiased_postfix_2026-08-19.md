# Unbiased Walk-Forward Backtest — Post-fix (2026-08-19)

Measured **after** the model fixes landed. Compare against the baseline report of the same date.

- **Season:** 2024-25
- **Train:** first 60 feature rows per player (single fit, never refit)
- **Test:** every remaining row, predicted one at a time
- **Pipeline:** `full (ensemble + meta-learner)`
- **Stats:** PTS, REB, AST, PRA (PRA = reconciled 0.85·(P+R+A) + 0.15·independent)
- **Players attempted / evaluated / skipped:** 58 / 44 / 14
- **Held-out predictions:** 2424
- **Pseudo-line probability samples:** 16727
- **Wall clock:** 46.1 min

## 1. Per-stat holdout accuracy

`MAE (pooled)` weights every held-out game equally; `MAE (player mean)` is the unweighted mean of per-player MAEs (comparable with `eval_holdout.py`). **MAE gap** is the mean per-player `holdout MAE − train OOF MAE` — the overfitting measure.

| Stat | Players | N test | MAE (pooled) | MAE (player mean) | Bias (pred−actual) | RMSE | Train OOF MAE | MAE gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 44 | 606 | 6.65 | 6.71 | -0.08 | 8.24 | 5.65 | **+1.06** |
| REB | 44 | 606 | 2.58 | 2.57 | +0.12 | 3.32 | 2.28 | **+0.29** |
| AST | 44 | 606 | 1.89 | 1.93 | -0.43 | 2.54 | 1.86 | **+0.07** |
| PRA | 44 | 606 | 7.72 | 7.85 | -0.34 | 9.74 | 6.99 | **+0.86** |

## 2. 80% interval coverage

Raw band is the untouched (q10, q90) quantile pair — target 0.80. The CQR band adds the per-stat conformal correction learned at training time, which targets ~0.90-0.92.

| Stat | Train OOF cov (raw) | Holdout cov RAW (target 0.80) | Mean CQR correction | Holdout cov CQR (target ~0.90) |
|---|---:|---:|---:|---:|
| PTS | 0.63 | 0.55 | 6.24 | 0.86 |
| REB | 0.63 | 0.57 | 2.55 | 0.88 |
| AST | 0.60 | 0.58 | 2.03 | 0.86 |
| PRA | 0.64 | 0.55 | 7.87 | 0.87 |

## 3. Probability calibration (pseudo-lines)

Each held-out prediction is scored against 7 pseudo-lines: prediction ± {0.5, 1.5, 2.5} and the player's season-to-date median (computed only from games before the row being predicted). `prob_over` comes from the production `ProbabilityCalculator.calculate` path — same std from `get_confidence`, same Platt calibrator — and is clipped to [15%, 85%] by `PROB_FLOOR`/`PROB_CEIL`.

### 3a. Overall reliability by predicted-probability decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap (pred − realized) |
|---|---:|---:|---:|---:|
| 10-20% | 689 | 16.5% | 25.4% | -8.9 |
| 20-30% | 1084 | 25.5% | 34.2% | -8.7 |
| 30-40% | 1800 | 35.4% | 39.8% | -4.3 |
| 40-50% | 3185 | 45.3% | 47.4% | -2.1 |
| 50-60% | 3897 | 55.0% | 50.0% | +5.0 |
| 60-70% | 3136 | 64.7% | 54.3% | +10.4 |
| 70-80% | 1765 | 74.5% | 63.1% | +11.3 |
| 80-90% | 1171 | 83.6% | 82.2% | +1.3 |

- **Overall Brier score:** 0.2399

### 3b. By stat

| Stat | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| PTS | 4208 | 53.8% | 49.6% | +4.3 | 0.2633 |
| REB | 4168 | 53.7% | 48.2% | +5.5 | 0.2332 |
| AST | 4127 | 51.6% | 54.4% | -2.8 | 0.1976 |
| PRA | 4224 | 54.6% | 51.1% | +3.4 | 0.2645 |

### 3c. By pseudo-line type

`offset` lines are centred on the prediction (half are near coin-flips by construction); `median` lines sit at the player's season-to-date median and are the closest stand-in for a real market line.

| Line type | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| offset | 14540 | 53.1% | 50.2% | +2.9 | 0.2363 |
| median | 2187 | 55.8% | 55.1% | +0.7 | 0.2634 |

### 3d. Median-line reliability by decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap |
|---|---:|---:|---:|---:|
| 10-20% | 41 | 17.0% | 51.2% | -34.2 |
| 20-30% | 167 | 25.4% | 60.5% | -35.1 |
| 30-40% | 188 | 35.5% | 45.2% | -9.7 |
| 40-50% | 379 | 45.5% | 53.3% | -7.8 |
| 50-60% | 522 | 54.8% | 50.4% | +4.4 |
| 60-70% | 374 | 64.4% | 53.7% | +10.6 |
| 70-80% | 280 | 74.9% | 59.6% | +15.3 |
| 80-90% | 236 | 83.1% | 70.3% | +12.8 |

## 4. Per-player appendix

| Player | Games | N test | Stat | Holdout MAE | Bias | RMSE | Train OOF MAE | MAE gap | Cov RAW | Cov CQR |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Alperen Sengun | 76 | 16 | PTS | 6.34 | +3.69 | 7.18 | 5.03 | +1.30 | 0.44 | 0.88 |
| Alperen Sengun | 76 | 16 | REB | 4.36 | +0.13 | 5.56 | 2.35 | +2.01 | 0.50 | 0.88 |
| Alperen Sengun | 76 | 16 | AST | 1.64 | +0.04 | 2.15 | 1.75 | -0.11 | 0.06 | 0.75 |
| Alperen Sengun | 76 | 16 | PRA | 6.30 | +3.83 | 8.31 | 6.59 | -0.29 | 0.81 | 0.88 |
| Amen Thompson | 69 | 9 | PTS | 4.29 | +4.04 | 5.27 | 6.16 | -1.87 | 1.00 | 1.00 |
| Amen Thompson | 69 | 9 | REB | 3.97 | +3.97 | 4.50 | 2.55 | +1.42 | 0.56 | 1.00 |
| Amen Thompson | 69 | 9 | AST | 1.49 | -0.50 | 2.10 | 2.06 | -0.57 | 0.67 | 1.00 |
| Amen Thompson | 69 | 9 | PRA | 7.15 | +7.15 | 8.91 | 8.10 | -0.96 | 0.78 | 1.00 |
| Anfernee Simons | 70 | 10 | PTS | 8.42 | +2.76 | 9.78 | 6.65 | +1.77 | 0.50 | 0.80 |
| Anfernee Simons | 70 | 10 | REB | 1.38 | +0.82 | 1.56 | 1.22 | +0.16 | 0.40 | 0.90 |
| Anfernee Simons | 70 | 10 | AST | 1.73 | +0.79 | 2.26 | 1.43 | +0.30 | 0.50 | 0.80 |
| Anfernee Simons | 70 | 10 | PRA | 7.09 | +4.14 | 8.33 | 7.49 | -0.40 | 0.80 | 0.90 |
| Anthony Edwards | 79 | 19 | PTS | 8.30 | -1.49 | 10.04 | 7.62 | +0.68 | 0.74 | 0.95 |
| Anthony Edwards | 79 | 19 | REB | 2.31 | +0.71 | 2.92 | 2.00 | +0.31 | 0.37 | 0.95 |
| Anthony Edwards | 79 | 19 | AST | 1.60 | +1.26 | 1.92 | 2.00 | -0.40 | 0.89 | 1.00 |
| Anthony Edwards | 79 | 19 | PRA | 7.80 | +1.50 | 9.87 | 8.08 | -0.28 | 0.47 | 1.00 |
| Austin Reaves | 73 | 13 | PTS | 5.56 | +1.05 | 6.78 | 5.71 | -0.15 | 0.38 | 1.00 |
| Austin Reaves | 73 | 13 | REB | 1.95 | +0.37 | 2.32 | 2.22 | -0.27 | 0.46 | 0.92 |
| Austin Reaves | 73 | 13 | AST | 2.02 | +1.01 | 2.20 | 2.96 | -0.94 | 1.00 | 1.00 |
| Austin Reaves | 73 | 13 | PRA | 6.25 | +2.37 | 7.74 | 7.84 | -1.60 | 0.69 | 1.00 |
| Bam Adebayo | 78 | 18 | PTS | 6.86 | +3.22 | 8.27 | 5.24 | +1.63 | 0.78 | 0.94 |
| Bam Adebayo | 78 | 18 | REB | 2.90 | +1.19 | 3.24 | 2.42 | +0.49 | 0.44 | 0.94 |
| Bam Adebayo | 78 | 18 | AST | 2.17 | +0.95 | 2.67 | 2.19 | -0.03 | 0.50 | 0.89 |
| Bam Adebayo | 78 | 18 | PRA | 9.68 | +5.03 | 11.19 | 6.61 | +3.07 | 0.11 | 0.78 |
| Cade Cunningham | 70 | 10 | PTS | 7.33 | -1.45 | 9.20 | 6.59 | +0.75 | 0.40 | 1.00 |
| Cade Cunningham | 70 | 10 | REB | 3.17 | -2.42 | 3.84 | 2.09 | +1.08 | 0.40 | 0.90 |
| Cade Cunningham | 70 | 10 | AST | 2.23 | +1.22 | 2.84 | 2.68 | -0.44 | 0.70 | 1.00 |
| Cade Cunningham | 70 | 10 | PRA | 7.95 | -2.48 | 9.23 | 7.64 | +0.32 | 0.50 | 1.00 |
| Coby White | 74 | 14 | PTS | 11.17 | -4.94 | 12.54 | 5.60 | +5.57 | 0.57 | 0.79 |
| Coby White | 74 | 14 | REB | 2.42 | -1.79 | 3.37 | 1.58 | +0.84 | 0.71 | 0.79 |
| Coby White | 74 | 14 | AST | 1.46 | -0.56 | 1.94 | 1.95 | -0.49 | 0.36 | 0.93 |
| Coby White | 74 | 14 | PRA | 12.04 | -6.41 | 13.20 | 7.46 | +4.59 | 0.50 | 0.86 |
| Darius Garland | 75 | 15 | PTS | 5.70 | +1.45 | 6.91 | 4.88 | +0.83 | 0.53 | 0.80 |
| Darius Garland | 75 | 15 | REB | 1.58 | -1.17 | 1.87 | 1.22 | +0.36 | 0.60 | 0.67 |
| Darius Garland | 75 | 15 | AST | 1.80 | -0.97 | 2.36 | 2.04 | -0.24 | 0.60 | 0.93 |
| Darius Garland | 75 | 15 | PRA | 5.69 | -0.93 | 7.26 | 4.88 | +0.81 | 0.67 | 0.93 |
| DeMar DeRozan | 77 | 17 | PTS | 5.62 | -1.30 | 7.24 | 6.07 | -0.45 | 0.65 | 1.00 |
| DeMar DeRozan | 77 | 17 | REB | 1.90 | +1.16 | 2.36 | 1.61 | +0.29 | 0.76 | 0.88 |
| DeMar DeRozan | 77 | 17 | AST | 2.64 | -1.93 | 3.32 | 1.86 | +0.79 | 0.29 | 0.59 |
| DeMar DeRozan | 77 | 17 | PRA | 6.43 | -1.67 | 8.56 | 7.90 | -1.47 | 0.65 | 1.00 |
| Deni Avdija | 72 | 12 | PTS | 7.62 | -4.94 | 8.69 | 5.96 | +1.66 | 0.42 | 0.83 |
| Deni Avdija | 72 | 12 | REB | 3.45 | -1.80 | 4.13 | 2.35 | +1.09 | 0.33 | 0.75 |
| Deni Avdija | 72 | 12 | AST | 1.74 | -0.62 | 2.20 | 1.64 | +0.09 | 0.75 | 0.92 |
| Deni Avdija | 72 | 12 | PRA | 11.12 | -8.09 | 13.17 | 7.51 | +3.61 | 0.42 | 0.67 |
| Derrick White | 76 | 16 | PTS | 3.57 | +0.21 | 4.28 | 5.22 | -1.64 | 1.00 | 1.00 |
| Derrick White | 76 | 16 | REB | 2.09 | -1.46 | 2.62 | 1.79 | +0.30 | 0.56 | 0.94 |
| Derrick White | 76 | 16 | AST | 2.17 | -1.71 | 2.71 | 1.90 | +0.27 | 0.31 | 0.62 |
| Derrick White | 76 | 16 | PRA | 3.84 | -2.80 | 5.11 | 6.25 | -2.42 | 0.81 | 1.00 |
| Devin Booker | 75 | 15 | PTS | 8.21 | +3.04 | 9.69 | 6.78 | +1.44 | 0.33 | 0.73 |
| Devin Booker | 75 | 15 | REB | 1.57 | -0.13 | 1.85 | 1.50 | +0.07 | 0.67 | 0.67 |
| Devin Booker | 75 | 15 | AST | 3.27 | -0.92 | 3.75 | 2.03 | +1.24 | 0.27 | 0.33 |
| Devin Booker | 75 | 15 | PRA | 7.96 | +2.03 | 10.32 | 6.83 | +1.13 | 0.47 | 0.87 |
| Domantas Sabonis | 70 | 10 | PTS | 5.32 | +4.49 | 6.44 | 4.96 | +0.37 | 0.30 | 0.60 |
| Domantas Sabonis | 70 | 10 | REB | 2.76 | +2.02 | 3.55 | 3.40 | -0.64 | 0.60 | 1.00 |
| Domantas Sabonis | 70 | 10 | AST | 2.16 | +0.63 | 3.13 | 2.39 | -0.23 | 0.70 | 0.80 |
| Domantas Sabonis | 70 | 10 | PRA | 6.03 | +5.06 | 8.29 | 6.92 | -0.90 | 0.80 | 1.00 |
| Evan Mobley | 71 | 11 | PTS | 5.53 | -0.13 | 6.45 | 5.52 | +0.00 | 0.36 | 0.82 |
| Evan Mobley | 71 | 11 | REB | 3.42 | -2.84 | 4.09 | 2.19 | +1.23 | 0.45 | 1.00 |
| Evan Mobley | 71 | 11 | AST | 1.27 | -0.29 | 1.60 | 1.65 | -0.39 | 0.36 | 1.00 |
| Evan Mobley | 71 | 11 | PRA | 6.84 | -2.67 | 7.81 | 7.38 | -0.54 | 0.64 | 0.91 |
| Giannis Antetokounmpo | 67 | 7 | PTS | 6.15 | -3.43 | 7.18 | 4.97 | +1.18 | 0.71 | 1.00 |
| Giannis Antetokounmpo | 67 | 7 | REB | 2.87 | -0.11 | 3.75 | 2.49 | +0.38 | 0.71 | 1.00 |
| Giannis Antetokounmpo | 67 | 7 | AST | 5.35 | -4.77 | 6.81 | 2.63 | +2.72 | 0.29 | 0.43 |
| Giannis Antetokounmpo | 67 | 7 | PRA | 10.27 | -8.42 | 13.77 | 5.89 | +4.38 | 0.43 | 0.57 |
| Ivica Zubac | 80 | 20 | PTS | 3.97 | -2.62 | 5.21 | 4.83 | -0.86 | 0.85 | 1.00 |
| Ivica Zubac | 80 | 20 | REB | 3.02 | -0.30 | 3.98 | 2.90 | +0.12 | 0.75 | 0.90 |
| Ivica Zubac | 80 | 20 | AST | 1.81 | -0.72 | 2.60 | 1.22 | +0.58 | 0.65 | 0.80 |
| Ivica Zubac | 80 | 20 | PRA | 6.67 | -3.76 | 8.01 | 6.78 | -0.11 | 0.75 | 0.95 |
| Jaden McDaniels | 82 | 22 | PTS | 5.71 | +3.96 | 7.27 | 5.29 | +0.41 | 0.77 | 1.00 |
| Jaden McDaniels | 82 | 22 | REB | 2.66 | +1.48 | 3.23 | 2.36 | +0.30 | 0.36 | 1.00 |
| Jaden McDaniels | 82 | 22 | AST | 1.42 | -0.12 | 1.73 | 1.19 | +0.22 | 0.55 | 0.91 |
| Jaden McDaniels | 82 | 22 | PRA | 8.23 | +5.30 | 10.03 | 6.98 | +1.25 | 0.50 | 0.86 |
| Jalen Brunson | 65 | 5 | PTS | 7.24 | +1.32 | 8.31 | 7.33 | -0.10 | 0.60 | 0.80 |
| Jalen Brunson | 65 | 5 | REB | 1.46 | +1.01 | 1.56 | 1.30 | +0.16 | 0.60 | 1.00 |
| Jalen Brunson | 65 | 5 | AST | 2.83 | +0.33 | 3.13 | 2.29 | +0.55 | 0.20 | 0.80 |
| Jalen Brunson | 65 | 5 | PRA | 10.67 | +2.57 | 11.66 | 7.78 | +2.89 | 0.40 | 0.80 |
| Jalen Duren | 78 | 18 | PTS | 3.86 | +1.87 | 4.94 | 3.65 | +0.21 | 0.44 | 0.94 |
| Jalen Duren | 78 | 18 | REB | 4.24 | -0.04 | 5.10 | 2.63 | +1.61 | 0.28 | 0.89 |
| Jalen Duren | 78 | 18 | AST | 1.74 | -0.05 | 2.13 | 1.33 | +0.41 | 0.56 | 0.89 |
| Jalen Duren | 78 | 18 | PRA | 6.05 | +1.55 | 8.61 | 6.05 | +0.01 | 0.78 | 0.89 |
| Jalen Green | 82 | 22 | PTS | 11.55 | -2.62 | 12.64 | 6.49 | +5.06 | 0.27 | 0.91 |
| Jalen Green | 82 | 22 | REB | 2.37 | -0.65 | 2.81 | 1.82 | +0.56 | 0.45 | 0.82 |
| Jalen Green | 82 | 22 | AST | 2.16 | -0.46 | 2.82 | 1.53 | +0.63 | 0.77 | 0.91 |
| Jalen Green | 82 | 22 | PRA | 12.44 | -3.70 | 14.51 | 7.62 | +4.82 | 0.55 | 0.86 |
| Jalen Williams | 69 | 9 | PTS | 5.03 | -2.45 | 6.34 | 4.78 | +0.25 | 0.67 | 0.78 |
| Jalen Williams | 69 | 9 | REB | 1.53 | +1.10 | 1.87 | 1.58 | -0.04 | 0.56 | 0.78 |
| Jalen Williams | 69 | 9 | AST | 0.97 | +0.53 | 1.24 | 1.48 | -0.51 | 0.78 | 1.00 |
| Jalen Williams | 69 | 9 | PRA | 5.41 | -0.43 | 6.74 | 5.81 | -0.40 | 0.44 | 0.78 |
| Jarrett Allen | 82 | 22 | PTS | 6.66 | -0.14 | 8.07 | 4.48 | +2.18 | 0.50 | 0.64 |
| Jarrett Allen | 82 | 22 | REB | 3.58 | +1.25 | 4.24 | 3.00 | +0.58 | 0.32 | 0.68 |
| Jarrett Allen | 82 | 22 | AST | 1.14 | +0.27 | 1.29 | 1.34 | -0.20 | 0.95 | 1.00 |
| Jarrett Allen | 82 | 22 | PRA | 9.01 | +1.45 | 11.43 | 7.01 | +2.00 | 0.41 | 0.68 |
| Jayson Tatum | 72 | 12 | PTS | 6.46 | -3.01 | 6.98 | 7.06 | -0.60 | 0.75 | 1.00 |
| Jayson Tatum | 72 | 12 | REB | 2.27 | +0.98 | 3.06 | 2.72 | -0.45 | 0.50 | 0.83 |
| Jayson Tatum | 72 | 12 | AST | 2.27 | -1.70 | 2.61 | 2.44 | -0.17 | 0.58 | 0.83 |
| Jayson Tatum | 72 | 12 | PRA | 6.58 | -3.14 | 7.78 | 8.14 | -1.56 | 0.67 | 1.00 |
| Josh Hart | 77 | 17 | PTS | 5.10 | +3.37 | 6.36 | 4.36 | +0.73 | 0.53 | 0.88 |
| Josh Hart | 77 | 17 | REB | 2.97 | +0.88 | 3.38 | 3.46 | -0.49 | 0.65 | 0.88 |
| Josh Hart | 77 | 17 | AST | 2.39 | -1.31 | 2.99 | 2.34 | +0.05 | 0.47 | 0.76 |
| Josh Hart | 77 | 17 | PRA | 6.94 | +3.65 | 8.42 | 6.79 | +0.15 | 0.47 | 0.88 |
| Julius Randle | 69 | 9 | PTS | 7.31 | -3.08 | 8.20 | 4.35 | +2.96 | 0.33 | 0.56 |
| Julius Randle | 69 | 9 | REB | 1.70 | +0.19 | 2.03 | 2.03 | -0.33 | 0.89 | 1.00 |
| Julius Randle | 69 | 9 | AST | 1.19 | +0.07 | 1.43 | 1.88 | -0.69 | 0.89 | 1.00 |
| Julius Randle | 69 | 9 | PRA | 7.67 | -3.03 | 9.03 | 5.59 | +2.08 | 0.33 | 0.67 |
| Karl-Anthony Towns | 72 | 12 | PTS | 8.16 | -5.58 | 9.67 | 6.51 | +1.66 | 0.75 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | REB | 2.04 | +1.45 | 2.30 | 3.98 | -1.93 | 0.92 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | AST | 2.03 | +0.06 | 2.87 | 1.61 | +0.41 | 0.75 | 0.92 |
| Karl-Anthony Towns | 72 | 12 | PRA | 8.00 | -3.74 | 9.45 | 7.87 | +0.13 | 0.58 | 1.00 |
| Kyle Kuzma | 65 | 5 | PTS | 4.24 | -0.79 | 4.59 | 5.32 | -1.09 | 0.20 | 1.00 |
| Kyle Kuzma | 65 | 5 | REB | 2.55 | +2.55 | 2.74 | 2.44 | +0.11 | 0.80 | 1.00 |
| Kyle Kuzma | 65 | 5 | AST | 1.31 | +0.61 | 1.52 | 1.46 | -0.16 | 0.40 | 1.00 |
| Kyle Kuzma | 65 | 5 | PRA | 5.31 | +2.38 | 6.11 | 7.17 | -1.86 | 0.60 | 1.00 |
| LeBron James | 70 | 10 | PTS | 6.60 | +2.77 | 7.66 | 6.06 | +0.53 | 0.60 | 0.80 |
| LeBron James | 70 | 10 | REB | 3.50 | +2.83 | 4.49 | 2.70 | +0.80 | 0.40 | 0.90 |
| LeBron James | 70 | 10 | AST | 2.07 | +0.67 | 2.87 | 2.23 | -0.17 | 0.60 | 0.70 |
| LeBron James | 70 | 10 | PRA | 7.60 | +6.32 | 9.04 | 7.11 | +0.48 | 0.50 | 0.70 |
| Michael Porter Jr. | 77 | 17 | PTS | 5.02 | +3.49 | 5.97 | 5.50 | -0.48 | 0.82 | 0.94 |
| Michael Porter Jr. | 77 | 17 | REB | 2.87 | -1.95 | 3.83 | 2.31 | +0.55 | 0.29 | 0.88 |
| Michael Porter Jr. | 77 | 17 | AST | 1.34 | -0.66 | 1.69 | 1.31 | +0.03 | 0.71 | 0.94 |
| Michael Porter Jr. | 77 | 17 | PRA | 5.81 | +0.67 | 6.66 | 6.26 | -0.45 | 0.94 | 1.00 |
| Mikal Bridges | 82 | 21 | PTS | 5.85 | -0.70 | 7.02 | 6.08 | -0.23 | 0.33 | 0.86 |
| Mikal Bridges | 82 | 21 | REB | 1.45 | -0.50 | 1.70 | 1.77 | -0.32 | 0.86 | 1.00 |
| Mikal Bridges | 82 | 21 | AST | 1.84 | -1.39 | 2.43 | 1.52 | +0.33 | 0.43 | 0.67 |
| Mikal Bridges | 82 | 21 | PRA | 6.85 | -2.87 | 8.03 | 6.16 | +0.69 | 0.38 | 0.86 |
| Myles Turner | 72 | 12 | PTS | 5.03 | +0.37 | 6.16 | 3.41 | +1.62 | 0.50 | 0.75 |
| Myles Turner | 72 | 12 | REB | 2.74 | -1.27 | 3.17 | 2.09 | +0.65 | 0.33 | 0.67 |
| Myles Turner | 72 | 12 | AST | 0.73 | +0.68 | 0.83 | 0.78 | -0.05 | 0.92 | 1.00 |
| Myles Turner | 72 | 12 | PRA | 5.58 | -0.44 | 6.61 | 4.04 | +1.54 | 0.42 | 0.75 |
| Naz Reid | 80 | 20 | PTS | 5.07 | +0.09 | 5.72 | 6.53 | -1.46 | 0.50 | 0.85 |
| Naz Reid | 80 | 20 | REB | 2.22 | +0.58 | 2.61 | 2.75 | -0.53 | 0.80 | 1.00 |
| Naz Reid | 80 | 20 | AST | 1.12 | +0.20 | 1.43 | 1.20 | -0.07 | 0.75 | 0.90 |
| Naz Reid | 80 | 20 | PRA | 4.27 | +1.19 | 5.45 | 8.27 | -4.00 | 0.85 | 0.95 |
| Nikola Jokic | 70 | 10 | PTS | 9.22 | -6.61 | 12.65 | 6.76 | +2.46 | 0.60 | 0.90 |
| Nikola Jokic | 70 | 10 | REB | 2.67 | +1.48 | 3.29 | 3.76 | -1.09 | 0.90 | 1.00 |
| Nikola Jokic | 70 | 10 | AST | 2.22 | +0.19 | 2.65 | 2.86 | -0.64 | 0.90 | 1.00 |
| Nikola Jokic | 70 | 10 | PRA | 11.19 | -4.74 | 14.09 | 8.46 | +2.73 | 0.40 | 0.90 |
| Nikola Vucevic | 73 | 13 | PTS | 7.97 | -7.57 | 9.93 | 5.68 | +2.29 | 0.62 | 0.92 |
| Nikola Vucevic | 73 | 13 | REB | 1.88 | +0.51 | 2.29 | 2.39 | -0.50 | 0.85 | 1.00 |
| Nikola Vucevic | 73 | 13 | AST | 2.41 | -0.39 | 2.78 | 1.33 | +1.08 | 0.38 | 0.69 |
| Nikola Vucevic | 73 | 13 | PRA | 9.45 | -6.62 | 11.29 | 7.52 | +1.94 | 0.31 | 1.00 |
| OG Anunoby | 74 | 14 | PTS | 9.08 | -5.57 | 9.94 | 6.64 | +2.44 | 0.50 | 0.86 |
| OG Anunoby | 74 | 14 | REB | 1.56 | +0.27 | 2.07 | 1.79 | -0.24 | 0.71 | 1.00 |
| OG Anunoby | 74 | 14 | AST | 1.19 | -0.03 | 1.48 | 1.43 | -0.25 | 0.29 | 0.79 |
| OG Anunoby | 74 | 14 | PRA | 9.54 | -5.28 | 10.54 | 8.30 | +1.23 | 0.29 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PTS | 6.06 | +1.43 | 7.20 | 4.46 | +1.60 | 0.57 | 0.86 |
| Onyeka Okongwu | 74 | 14 | REB | 2.93 | +1.17 | 3.51 | 3.00 | -0.07 | 0.57 | 0.93 |
| Onyeka Okongwu | 74 | 14 | AST | 1.21 | -0.70 | 1.60 | 1.24 | -0.03 | 0.64 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PRA | 8.57 | +1.70 | 10.31 | 7.03 | +1.54 | 0.57 | 0.93 |
| Pascal Siakam | 78 | 18 | PTS | 7.32 | +0.61 | 8.24 | 4.28 | +3.04 | 0.22 | 0.67 |
| Pascal Siakam | 78 | 18 | REB | 2.90 | +1.63 | 3.66 | 2.06 | +0.84 | 0.50 | 0.67 |
| Pascal Siakam | 78 | 18 | AST | 1.85 | -1.52 | 2.21 | 1.53 | +0.32 | 0.44 | 0.89 |
| Pascal Siakam | 78 | 18 | PRA | 8.53 | +0.87 | 9.43 | 5.04 | +3.49 | 0.17 | 0.72 |
| Rudy Gobert | 72 | 12 | PTS | 7.68 | -6.39 | 9.58 | 4.41 | +3.27 | 0.42 | 0.67 |
| Rudy Gobert | 72 | 12 | REB | 4.25 | -3.40 | 5.83 | 3.00 | +1.25 | 0.58 | 0.58 |
| Rudy Gobert | 72 | 12 | AST | 1.05 | -0.09 | 1.29 | 1.21 | -0.17 | 0.50 | 1.00 |
| Rudy Gobert | 72 | 12 | PRA | 11.58 | -10.07 | 13.57 | 6.12 | +5.45 | 0.25 | 0.50 |
| Scottie Barnes | 65 | 5 | PTS | 10.01 | +2.27 | 11.12 | 4.46 | +5.55 | 0.40 | 0.40 |
| Scottie Barnes | 65 | 5 | REB | 3.15 | +0.35 | 3.52 | 2.92 | +0.23 | 0.60 | 0.80 |
| Scottie Barnes | 65 | 5 | AST | 1.41 | +0.21 | 1.85 | 1.91 | -0.50 | 0.60 | 1.00 |
| Scottie Barnes | 65 | 5 | PRA | 12.34 | +3.11 | 15.06 | 5.99 | +6.35 | 0.40 | 0.40 |
| Shai Gilgeous-Alexander | 76 | 16 | PTS | 8.45 | +7.20 | 10.12 | 5.60 | +2.85 | 0.62 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | REB | 2.14 | +0.45 | 2.47 | 2.08 | +0.05 | 0.50 | 1.00 |
| Shai Gilgeous-Alexander | 76 | 16 | AST | 2.36 | -1.84 | 2.86 | 1.86 | +0.49 | 0.19 | 0.81 |
| Shai Gilgeous-Alexander | 76 | 16 | PRA | 6.62 | +5.00 | 8.21 | 6.29 | +0.33 | 0.81 | 1.00 |
| Stephen Curry | 70 | 10 | PTS | 10.45 | -0.89 | 14.09 | 7.12 | +3.34 | 0.30 | 0.80 |
| Stephen Curry | 70 | 10 | REB | 2.38 | -1.79 | 3.35 | 1.83 | +0.55 | 0.50 | 0.80 |
| Stephen Curry | 70 | 10 | AST | 1.22 | -0.47 | 1.63 | 2.37 | -1.15 | 0.80 | 1.00 |
| Stephen Curry | 70 | 10 | PRA | 11.74 | -2.68 | 15.82 | 8.05 | +3.68 | 0.60 | 0.80 |
| Trae Young | 76 | 16 | PTS | 5.06 | +0.72 | 6.10 | 7.28 | -2.22 | 0.69 | 1.00 |
| Trae Young | 76 | 16 | REB | 1.71 | -0.77 | 2.10 | 1.27 | +0.44 | 0.50 | 0.88 |
| Trae Young | 76 | 16 | AST | 2.23 | -1.01 | 2.97 | 3.63 | -1.40 | 0.94 | 1.00 |
| Trae Young | 76 | 16 | PRA | 5.20 | -0.57 | 7.20 | 7.49 | -2.29 | 0.56 | 1.00 |
| Tyrese Haliburton | 73 | 13 | PTS | 5.11 | +2.08 | 5.90 | 6.76 | -1.65 | 0.92 | 1.00 |
| Tyrese Haliburton | 73 | 13 | REB | 2.19 | -0.58 | 2.62 | 1.45 | +0.74 | 0.38 | 0.46 |
| Tyrese Haliburton | 73 | 13 | AST | 4.51 | -2.42 | 5.21 | 2.14 | +2.37 | 0.46 | 0.69 |
| Tyrese Haliburton | 73 | 13 | PRA | 5.33 | -0.89 | 6.68 | 8.65 | -3.32 | 0.92 | 1.00 |

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

---

# 5. Comparison vs baseline

Baseline: `docs/backtest_unbiased_baseline_2026-08-19.md`. Same 58-player set, same flags, same 2424 held-out predictions.

## 5.1 Accuracy — degradation here is the fix working

| Stat | MAE before | MAE after | Δ | Brier before | Brier after |
|---|---:|---:|---:|---:|---:|
| PTS | 6.25 | 6.65 | +6.4% | 0.2536 | 0.2633 |
| REB | 2.49 | 2.58 | +3.6% | 0.2283 | 0.2332 |
| **AST** | **1.44** | **1.89** | **+31%** | **0.1592** | **0.1976** |
| PRA | 7.42 | 7.72 | +4.0% | 0.2550 | 0.2645 |

The baseline was **not** a fair reference. `prediction_row()` strips only PTS/REB/AST, so the derived ratio columns carried the current game's own box score into the *test* row — the baseline measured a model reading the answer off its own feature vector at inference time.

AST is the proof. `AST_TOV_RATIO = AST / max(TOV, 2)` fed the AST model directly, and AST is the only stat that:

- had a **negative** MAE gap at baseline (holdout 1.44 *better* than train OOF 1.52 — impossible without leakage),
- had a Brier ~38% better than every other stat (0.159 vs 0.23–0.26),
- degraded ~8x more than the others once de-leaked (+31% vs +3.6–6.4%).

Post-fix, AST's gap is +0.07 and its Brier sits in line with the rest. Feature/target correlation collapsed: `|corr(AST_TOV_RATIO, AST)|` 0.71 → 0.07, `|corr(OREB_RATE, OREB)|` 0.92 → 0.08.

**These are the first trustworthy accuracy numbers this model has produced.** They are not a regression.

## 5.2 The MAE gap is not comparable across the two runs

| Stat | Gap before | Gap after | Train OOF before → after |
|---|---:|---:|---|
| PTS | +0.37 | +1.07 | 5.98 → 5.65 |
| REB | +0.10 | +0.29 | 2.38 → 2.28 |
| AST | −0.02 | +0.07 | 1.52 → 1.86 |
| PRA | +0.10 | +0.85 | 7.47 → 6.99 |

Both terms moved for different reasons: holdout MAE rose (leak removed at inference) while train OOF MAE *fell* for PTS/REB/PRA, because the Optuna objective now scores mean-fold MAE instead of only the last fold and selects hyperparameters that generalise. AST train OOF rose, as expected — that is where the leak lived.

The widened gap is **not** new overfitting. It is what a generalisation gap looks like once neither term is flattered. Treat the post-fix gaps as the new reference; do not difference them against the old ones.

## 5.3 Calibration — the real finding, and it is bad

| Decile | Gap before | Gap after |
|---|---:|---:|
| 10–20% | −2.6 | −8.9 |
| 50–60% | +3.4 | +5.0 |
| 60–70% | +6.5 | **+10.4** |
| 70–80% | +1.6 | **+11.3** |
| 80–90% | −4.7 | +1.3 |

Overall Brier 0.2244 → 0.2399.

The model is **systematically overconfident in the 60–80% band**: it says ~74% and delivers ~63%. On median-line pseudo-lines — the closest stand-in for a real market line — the low deciles are worse still.

This was always true; the baseline's flatter curve was leakage, not calibration. Confirmed by isolation: pinning the interval divisor back to 2.56 moved overall Brier by 0.0001 (`docs/experiment_cqr_divisor_isolation_2026-08-19.md`), so none of it comes from the divisor wiring. `CONSUME_LEARNED_INTERVAL_DIVISOR` is therefore pinned to the conservative constant.

## 5.4 Interval coverage — unchanged, and the likely root cause

| Stat | Raw cov before | Raw cov after | Target |
|---|---:|---:|---:|
| PTS | 0.54 | 0.55 | 0.80 |
| REB | 0.55 | 0.57 | 0.80 |
| AST | 0.59 | 0.58 | 0.80 |
| PRA | 0.56 | 0.55 | 0.80 |

The raw quantile bands cover **~56% where they claim 80%** — essentially untouched, because nothing in this pass addressed the quantile models themselves. An 80% band covering 56% means the implied std is understated by roughly 40%, which fully explains the overconfidence in 5.3. The CQR-corrected band behaves as designed (0.86–0.88 against a ~0.90 target); the raw band is the broken component.

**This is the highest-value next piece of work** — larger than anything fixed in this pass.

## 5.5 Reproducibility

This run is reproducible; the pre-seeding runs were not. `optuna.create_study()` had no seeded sampler and used a wall-clock `timeout=60`, so identical code selected different hyperparameters run to run: a divisor-only change — which cannot touch `predict()` — moved PTS MAE 6.70 → 6.48, a **~3% noise floor** that exceeded most effects worth measuring.

Fixed with `TPESampler(seed=42)` and no timeout. Verified: this run and the previous seeded run produce **identical MAE to reported precision** across all four stats, and Brier within ±0.0002, despite four behavioural fixes landing between them (quantile-band ordering + std floor, trade damping on the post-trade debut game, residual-model serve population, Optuna param reset on retrain). Those fixes are therefore metric-neutral at this resolution — they close correctness holes that this player sample does not happen to exercise.

Runtime note: 46 min vs ~11 min earlier, but that is **not** the removed Optuna timeout — 33 of those minutes were the serial, rate-limited game-log fetch running against a cold cache. Training was ~13 min at 4 workers, in line with ~9 min at 5 workers previously.

## 5.6 What this backtest does NOT cover

`prediction_row()` feeds `predict()` a **training-frame row** with realized stats dropped. It never calls `FeatureEngineer.get_prediction_features`, so the serve half of the de-leak and the trade features sits outside these numbers:

- the `_<NAME>_CURR` mirror reads at serve,
- `_tenure_next` and the roster-team trade override,
- the minutes/rate blend, injury boost and blowout discount (no `estimated_minutes` is supplied).

What it *does* exercise: `create_features` (so the training-side de-leak is measured), `_update_recent_averages` → `_residual_serve_inputs` → `predict`, and `get_confidence`/`_interval_divisor` — which is why the divisor decision is genuinely supported here.

**Do not read these numbers as train/serve parity evidence.** That rests on `tests/test_leakage_guards.py` (`TestTrainServeParity`, `TestTradeFeatures`). Closing this gap belongs with the deferred lag-2 serve P0 — both concern the same path.
