# Unbiased Walk-Forward Backtest — Baseline (2026-08-19)

Measured **before** any model fixes land. This is the "before" column.

- **Season:** 2024-25
- **Train:** first 60 feature rows per player (single fit, never refit)
- **Test:** every remaining row, predicted one at a time
- **Pipeline:** `full (ensemble + meta-learner)`
- **Stats:** PTS, REB, AST, PRA (PRA = reconciled 0.85·(P+R+A) + 0.15·independent)
- **Players attempted / evaluated / skipped:** 58 / 44 / 14
- **Held-out predictions:** 2424
- **Pseudo-line probability samples:** 16728
- **Wall clock:** 11.5 min

## 1. Per-stat holdout accuracy

`MAE (pooled)` weights every held-out game equally; `MAE (player mean)` is the unweighted mean of per-player MAEs (comparable with `eval_holdout.py`). **MAE gap** is the mean per-player `holdout MAE − train OOF MAE` — the overfitting measure.

| Stat | Players | N test | MAE (pooled) | MAE (player mean) | Bias (pred−actual) | RMSE | Train OOF MAE | MAE gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 44 | 606 | 6.25 | 6.35 | -0.27 | 7.87 | 5.98 | **+0.37** |
| REB | 44 | 606 | 2.49 | 2.49 | +0.13 | 3.21 | 2.38 | **+0.10** |
| AST | 44 | 606 | 1.44 | 1.50 | -0.39 | 2.06 | 1.52 | **-0.02** |
| PRA | 44 | 606 | 7.42 | 7.57 | -0.50 | 9.43 | 7.47 | **+0.10** |

## 2. 80% interval coverage

Raw band is the untouched (q10, q90) quantile pair — target 0.80. The CQR band adds the per-stat conformal correction learned at training time, which targets ~0.90-0.92.

| Stat | Train OOF cov (raw) | Holdout cov RAW (target 0.80) | Mean CQR correction | Holdout cov CQR (target ~0.90) |
|---|---:|---:|---:|---:|
| PTS | 0.62 | 0.54 | 5.94 | 0.86 |
| REB | 0.59 | 0.55 | 2.66 | 0.88 |
| AST | 0.57 | 0.59 | 1.69 | 0.89 |
| PRA | 0.58 | 0.56 | 8.14 | 0.87 |

## 3. Probability calibration (pseudo-lines)

Each held-out prediction is scored against 7 pseudo-lines: prediction ± {0.5, 1.5, 2.5} and the player's season-to-date median (computed only from games before the row being predicted). `prob_over` comes from the production `ProbabilityCalculator.calculate` path — same std from `get_confidence`, same Platt calibrator — and is clipped to [15%, 85%] by `PROB_FLOOR`/`PROB_CEIL`.

### 3a. Overall reliability by predicted-probability decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap (pred − realized) |
|---|---:|---:|---:|---:|
| 10-20% | 983 | 16.0% | 18.6% | -2.6 |
| 20-30% | 1189 | 25.3% | 30.3% | -5.0 |
| 30-40% | 2092 | 35.3% | 39.5% | -4.2 |
| 40-50% | 3052 | 45.2% | 46.5% | -1.3 |
| 50-60% | 3618 | 54.9% | 51.5% | +3.4 |
| 60-70% | 3043 | 64.5% | 58.1% | +6.5 |
| 70-80% | 1595 | 74.4% | 72.8% | +1.6 |
| 80-90% | 1156 | 83.8% | 88.5% | -4.7 |

- **Overall Brier score:** 0.2244

### 3b. By stat

| Stat | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| PTS | 4208 | 53.2% | 50.5% | +2.7 | 0.2536 |
| REB | 4169 | 51.6% | 47.9% | +3.7 | 0.2283 |
| AST | 4127 | 50.0% | 55.5% | -5.5 | 0.1592 |
| PRA | 4224 | 52.7% | 51.8% | +0.8 | 0.2550 |

### 3c. By pseudo-line type

`offset` lines are centred on the prediction (half are near coin-flips by construction); `median` lines sit at the player's season-to-date median and are the closest stand-in for a real market line.

| Line type | N | Mean predicted | Realized over-rate | Gap | Brier |
|---|---:|---:|---:|---:|---:|
| offset | 14541 | 51.5% | 50.9% | +0.7 | 0.2227 |
| median | 2187 | 54.3% | 55.1% | -0.8 | 0.2351 |

### 3d. Median-line reliability by decile

| Predicted bucket | N | Mean predicted | Realized over-rate | Gap |
|---|---:|---:|---:|---:|
| 10-20% | 52 | 16.5% | 25.0% | -8.5 |
| 20-30% | 140 | 25.7% | 32.1% | -6.4 |
| 30-40% | 290 | 35.3% | 45.9% | -10.6 |
| 40-50% | 426 | 45.2% | 49.5% | -4.4 |
| 50-60% | 416 | 54.7% | 53.1% | +1.6 |
| 60-70% | 371 | 64.8% | 60.1% | +4.7 |
| 70-80% | 339 | 75.0% | 72.0% | +3.0 |
| 80-90% | 153 | 83.0% | 75.8% | +7.2 |

## 4. Per-player appendix

| Player | Games | N test | Stat | Holdout MAE | Bias | RMSE | Train OOF MAE | MAE gap | Cov RAW | Cov CQR |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Alperen Sengun | 76 | 16 | PTS | 5.36 | +2.76 | 6.08 | 5.04 | +0.32 | 0.56 | 0.88 |
| Alperen Sengun | 76 | 16 | REB | 3.13 | +0.60 | 3.74 | 2.47 | +0.66 | 0.38 | 0.75 |
| Alperen Sengun | 76 | 16 | AST | 1.46 | +0.56 | 1.79 | 1.36 | +0.11 | 0.62 | 0.94 |
| Alperen Sengun | 76 | 16 | PRA | 5.68 | +4.01 | 7.17 | 6.77 | -1.09 | 0.69 | 0.88 |
| Amen Thompson | 69 | 9 | PTS | 2.96 | +0.98 | 3.59 | 6.21 | -3.24 | 0.78 | 1.00 |
| Amen Thompson | 69 | 9 | REB | 2.29 | +1.90 | 2.78 | 2.76 | -0.47 | 0.44 | 1.00 |
| Amen Thompson | 69 | 9 | AST | 1.18 | -0.84 | 1.67 | 1.56 | -0.37 | 0.78 | 1.00 |
| Amen Thompson | 69 | 9 | PRA | 3.63 | +1.83 | 5.11 | 9.50 | -5.87 | 0.78 | 0.89 |
| Anfernee Simons | 70 | 10 | PTS | 7.45 | +0.16 | 8.81 | 6.47 | +0.99 | 0.50 | 0.90 |
| Anfernee Simons | 70 | 10 | REB | 1.43 | +0.91 | 1.62 | 1.21 | +0.22 | 0.50 | 0.80 |
| Anfernee Simons | 70 | 10 | AST | 1.22 | +0.38 | 1.64 | 1.44 | -0.22 | 0.50 | 0.90 |
| Anfernee Simons | 70 | 10 | PRA | 6.35 | +1.83 | 7.37 | 7.79 | -1.44 | 0.60 | 1.00 |
| Anthony Edwards | 79 | 19 | PTS | 7.90 | -2.01 | 9.92 | 8.13 | -0.22 | 0.58 | 0.95 |
| Anthony Edwards | 79 | 19 | REB | 2.38 | +0.82 | 2.99 | 2.02 | +0.36 | 0.32 | 1.00 |
| Anthony Edwards | 79 | 19 | AST | 1.19 | +0.78 | 1.65 | 1.48 | -0.28 | 0.68 | 1.00 |
| Anthony Edwards | 79 | 19 | PRA | 7.79 | +0.40 | 10.04 | 8.82 | -1.03 | 0.58 | 1.00 |
| Austin Reaves | 73 | 13 | PTS | 4.94 | +1.74 | 6.46 | 6.23 | -1.29 | 0.46 | 1.00 |
| Austin Reaves | 73 | 13 | REB | 1.76 | +0.31 | 2.12 | 2.27 | -0.52 | 0.69 | 1.00 |
| Austin Reaves | 73 | 13 | AST | 1.66 | +0.81 | 1.95 | 2.18 | -0.52 | 0.46 | 1.00 |
| Austin Reaves | 73 | 13 | PRA | 6.48 | +2.97 | 7.79 | 7.44 | -0.96 | 0.69 | 1.00 |
| Bam Adebayo | 78 | 18 | PTS | 6.84 | +2.97 | 8.40 | 5.16 | +1.68 | 0.67 | 0.94 |
| Bam Adebayo | 78 | 18 | REB | 2.98 | +1.68 | 3.28 | 2.62 | +0.36 | 0.22 | 0.67 |
| Bam Adebayo | 78 | 18 | AST | 1.40 | +0.38 | 1.68 | 1.64 | -0.24 | 0.61 | 1.00 |
| Bam Adebayo | 78 | 18 | PRA | 9.52 | +4.71 | 10.92 | 7.32 | +2.20 | 0.22 | 0.78 |
| Cade Cunningham | 70 | 10 | PTS | 6.85 | -1.86 | 8.14 | 6.22 | +0.63 | 0.50 | 0.90 |
| Cade Cunningham | 70 | 10 | REB | 3.61 | -1.97 | 4.20 | 2.14 | +1.47 | 0.20 | 0.90 |
| Cade Cunningham | 70 | 10 | AST | 2.16 | +1.07 | 2.79 | 2.72 | -0.57 | 0.70 | 1.00 |
| Cade Cunningham | 70 | 10 | PRA | 6.52 | -2.11 | 7.65 | 8.31 | -1.78 | 0.70 | 0.90 |
| Coby White | 74 | 14 | PTS | 12.70 | -9.71 | 14.34 | 5.82 | +6.88 | 0.50 | 0.64 |
| Coby White | 74 | 14 | REB | 2.07 | -0.75 | 2.98 | 1.83 | +0.23 | 0.71 | 0.86 |
| Coby White | 74 | 14 | AST | 1.07 | -0.71 | 1.57 | 1.66 | -0.60 | 0.57 | 0.93 |
| Coby White | 74 | 14 | PRA | 14.13 | -10.34 | 15.00 | 7.65 | +6.48 | 0.57 | 1.00 |
| Darius Garland | 75 | 15 | PTS | 4.69 | -0.12 | 6.09 | 5.97 | -1.28 | 0.53 | 0.87 |
| Darius Garland | 75 | 15 | REB | 1.67 | -1.39 | 2.02 | 1.38 | +0.29 | 0.33 | 0.80 |
| Darius Garland | 75 | 15 | AST | 2.21 | -2.16 | 2.67 | 1.67 | +0.54 | 0.67 | 0.80 |
| Darius Garland | 75 | 15 | PRA | 5.60 | -3.55 | 7.16 | 6.45 | -0.85 | 0.47 | 0.93 |
| DeMar DeRozan | 77 | 17 | PTS | 5.29 | -1.87 | 7.21 | 6.44 | -1.15 | 0.76 | 0.94 |
| DeMar DeRozan | 77 | 17 | REB | 1.92 | +1.17 | 2.39 | 1.67 | +0.26 | 0.59 | 0.94 |
| DeMar DeRozan | 77 | 17 | AST | 1.59 | -0.83 | 2.09 | 0.95 | +0.64 | 0.76 | 0.94 |
| DeMar DeRozan | 77 | 17 | PRA | 6.15 | -1.55 | 8.22 | 8.98 | -2.83 | 0.71 | 0.88 |
| Deni Avdija | 72 | 12 | PTS | 9.01 | -8.32 | 11.27 | 6.53 | +2.47 | 0.33 | 0.58 |
| Deni Avdija | 72 | 12 | REB | 4.19 | -3.59 | 5.36 | 2.70 | +1.48 | 0.67 | 0.75 |
| Deni Avdija | 72 | 12 | AST | 1.75 | -0.68 | 2.21 | 1.26 | +0.49 | 0.58 | 0.92 |
| Deni Avdija | 72 | 12 | PRA | 13.87 | -12.81 | 16.77 | 9.29 | +4.59 | 0.50 | 0.83 |
| Derrick White | 76 | 16 | PTS | 3.71 | +2.06 | 4.42 | 5.17 | -1.46 | 1.00 | 1.00 |
| Derrick White | 76 | 16 | REB | 2.00 | -1.38 | 2.54 | 1.97 | +0.04 | 0.56 | 0.94 |
| Derrick White | 76 | 16 | AST | 1.76 | -1.16 | 2.20 | 1.39 | +0.37 | 0.62 | 0.81 |
| Derrick White | 76 | 16 | PRA | 3.30 | -0.80 | 4.28 | 6.14 | -2.84 | 0.88 | 1.00 |
| Devin Booker | 75 | 15 | PTS | 8.17 | +0.36 | 9.52 | 7.61 | +0.56 | 0.33 | 0.73 |
| Devin Booker | 75 | 15 | REB | 1.51 | -0.22 | 1.85 | 1.39 | +0.12 | 0.53 | 0.73 |
| Devin Booker | 75 | 15 | AST | 3.09 | -0.08 | 3.44 | 1.80 | +1.29 | 0.40 | 0.47 |
| Devin Booker | 75 | 15 | PRA | 7.52 | +0.16 | 9.41 | 8.11 | -0.59 | 0.60 | 0.87 |
| Domantas Sabonis | 70 | 10 | PTS | 4.60 | -0.41 | 5.23 | 4.97 | -0.37 | 0.70 | 1.00 |
| Domantas Sabonis | 70 | 10 | REB | 2.59 | +1.29 | 3.19 | 3.58 | -0.99 | 0.70 | 1.00 |
| Domantas Sabonis | 70 | 10 | AST | 1.78 | +0.38 | 2.28 | 2.04 | -0.26 | 0.50 | 0.90 |
| Domantas Sabonis | 70 | 10 | PRA | 5.38 | +0.91 | 6.58 | 7.32 | -1.94 | 0.60 | 0.90 |
| Evan Mobley | 71 | 11 | PTS | 5.07 | -0.21 | 6.25 | 5.37 | -0.29 | 0.45 | 0.91 |
| Evan Mobley | 71 | 11 | REB | 2.31 | +0.36 | 2.84 | 2.56 | -0.26 | 0.45 | 1.00 |
| Evan Mobley | 71 | 11 | AST | 1.07 | -0.88 | 1.39 | 1.47 | -0.40 | 0.82 | 1.00 |
| Evan Mobley | 71 | 11 | PRA | 6.47 | -0.39 | 7.84 | 7.30 | -0.83 | 0.73 | 1.00 |
| Giannis Antetokounmpo | 67 | 7 | PTS | 5.36 | -3.89 | 5.94 | 5.02 | +0.34 | 0.57 | 0.86 |
| Giannis Antetokounmpo | 67 | 7 | REB | 2.97 | +0.95 | 3.72 | 2.42 | +0.56 | 0.57 | 0.86 |
| Giannis Antetokounmpo | 67 | 7 | AST | 4.61 | -4.09 | 6.11 | 2.12 | +2.49 | 0.29 | 0.57 |
| Giannis Antetokounmpo | 67 | 7 | PRA | 8.94 | -7.34 | 11.75 | 6.79 | +2.15 | 0.57 | 0.71 |
| Ivica Zubac | 80 | 20 | PTS | 3.21 | -1.06 | 4.15 | 5.60 | -2.39 | 0.75 | 0.95 |
| Ivica Zubac | 80 | 20 | REB | 2.94 | -1.41 | 3.97 | 2.94 | -0.01 | 0.70 | 0.80 |
| Ivica Zubac | 80 | 20 | AST | 1.23 | -0.72 | 2.08 | 0.85 | +0.38 | 0.75 | 0.85 |
| Ivica Zubac | 80 | 20 | PRA | 6.08 | -3.84 | 7.86 | 7.96 | -1.88 | 0.85 | 1.00 |
| Jaden McDaniels | 82 | 22 | PTS | 5.05 | +3.16 | 6.72 | 4.32 | +0.73 | 0.64 | 0.86 |
| Jaden McDaniels | 82 | 22 | REB | 2.69 | +1.50 | 3.15 | 2.21 | +0.48 | 0.32 | 0.82 |
| Jaden McDaniels | 82 | 22 | AST | 0.98 | -0.50 | 1.40 | 0.61 | +0.37 | 0.59 | 0.91 |
| Jaden McDaniels | 82 | 22 | PRA | 7.54 | +4.24 | 9.14 | 5.42 | +2.12 | 0.23 | 0.82 |
| Jalen Brunson | 65 | 5 | PTS | 7.98 | +3.46 | 8.99 | 7.00 | +0.98 | 0.20 | 0.80 |
| Jalen Brunson | 65 | 5 | REB | 1.13 | +0.58 | 1.25 | 1.39 | -0.26 | 0.60 | 1.00 |
| Jalen Brunson | 65 | 5 | AST | 2.45 | +0.71 | 2.67 | 2.00 | +0.45 | 0.20 | 0.40 |
| Jalen Brunson | 65 | 5 | PRA | 10.63 | +4.45 | 11.94 | 8.42 | +2.21 | 0.40 | 0.60 |
| Jalen Duren | 78 | 18 | PTS | 4.51 | -2.24 | 5.50 | 4.57 | -0.07 | 0.44 | 0.83 |
| Jalen Duren | 78 | 18 | REB | 3.26 | +0.11 | 4.18 | 3.26 | -0.00 | 0.44 | 0.83 |
| Jalen Duren | 78 | 18 | AST | 1.22 | -0.67 | 1.71 | 0.90 | +0.32 | 0.56 | 0.89 |
| Jalen Duren | 78 | 18 | PRA | 6.46 | -2.21 | 8.39 | 7.19 | -0.73 | 0.61 | 0.83 |
| Jalen Green | 82 | 22 | PTS | 9.83 | -0.45 | 10.93 | 7.38 | +2.45 | 0.50 | 0.86 |
| Jalen Green | 82 | 22 | REB | 2.53 | -1.75 | 3.13 | 1.83 | +0.70 | 0.45 | 0.77 |
| Jalen Green | 82 | 22 | AST | 1.44 | -0.58 | 2.41 | 0.97 | +0.47 | 0.45 | 0.86 |
| Jalen Green | 82 | 22 | PRA | 11.07 | -2.74 | 12.68 | 8.29 | +2.78 | 0.45 | 0.77 |
| Jalen Williams | 69 | 9 | PTS | 5.61 | -0.03 | 6.90 | 5.20 | +0.40 | 0.56 | 0.67 |
| Jalen Williams | 69 | 9 | REB | 1.72 | +1.25 | 2.05 | 1.64 | +0.08 | 0.78 | 0.89 |
| Jalen Williams | 69 | 9 | AST | 0.95 | +0.95 | 1.09 | 1.39 | -0.43 | 0.89 | 1.00 |
| Jalen Williams | 69 | 9 | PRA | 6.60 | +2.11 | 7.90 | 5.61 | +0.99 | 0.44 | 0.89 |
| Jarrett Allen | 82 | 22 | PTS | 7.05 | -0.57 | 8.30 | 4.35 | +2.71 | 0.50 | 0.55 |
| Jarrett Allen | 82 | 22 | REB | 3.70 | +1.49 | 4.34 | 3.09 | +0.61 | 0.55 | 0.95 |
| Jarrett Allen | 82 | 22 | AST | 0.73 | -0.04 | 0.85 | 0.85 | -0.12 | 0.77 | 1.00 |
| Jarrett Allen | 82 | 22 | PRA | 8.94 | +0.87 | 11.30 | 6.73 | +2.21 | 0.50 | 0.55 |
| Jayson Tatum | 72 | 12 | PTS | 5.11 | -2.13 | 5.78 | 7.56 | -2.45 | 0.83 | 1.00 |
| Jayson Tatum | 72 | 12 | REB | 2.32 | +1.20 | 3.09 | 2.71 | -0.39 | 0.75 | 0.92 |
| Jayson Tatum | 72 | 12 | AST | 0.99 | -0.04 | 1.28 | 1.79 | -0.79 | 0.67 | 1.00 |
| Jayson Tatum | 72 | 12 | PRA | 4.97 | -0.69 | 6.23 | 8.12 | -3.15 | 0.75 | 0.92 |
| Josh Hart | 77 | 17 | PTS | 4.55 | +3.28 | 6.00 | 4.27 | +0.28 | 0.47 | 0.82 |
| Josh Hart | 77 | 17 | REB | 2.94 | +0.94 | 3.37 | 3.66 | -0.73 | 0.65 | 1.00 |
| Josh Hart | 77 | 17 | AST | 2.26 | -1.98 | 2.81 | 2.04 | +0.21 | 0.76 | 0.94 |
| Josh Hart | 77 | 17 | PRA | 5.97 | +2.56 | 7.45 | 7.13 | -1.16 | 0.53 | 0.94 |
| Julius Randle | 69 | 9 | PTS | 7.27 | -2.03 | 7.91 | 5.00 | +2.27 | 0.22 | 0.78 |
| Julius Randle | 69 | 9 | REB | 1.84 | -0.07 | 2.11 | 2.03 | -0.19 | 0.89 | 1.00 |
| Julius Randle | 69 | 9 | AST | 1.70 | -1.58 | 2.06 | 1.84 | -0.14 | 0.56 | 1.00 |
| Julius Randle | 69 | 9 | PRA | 7.66 | -3.59 | 9.13 | 6.04 | +1.62 | 0.33 | 0.67 |
| Karl-Anthony Towns | 72 | 12 | PTS | 6.83 | -2.38 | 7.92 | 6.55 | +0.28 | 0.75 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | REB | 1.67 | +0.79 | 1.92 | 4.55 | -2.88 | 0.83 | 1.00 |
| Karl-Anthony Towns | 72 | 12 | AST | 1.48 | -0.43 | 2.50 | 1.06 | +0.42 | 0.50 | 0.83 |
| Karl-Anthony Towns | 72 | 12 | PRA | 7.63 | -2.05 | 9.08 | 9.62 | -1.99 | 0.58 | 1.00 |
| Kyle Kuzma | 65 | 5 | PTS | 4.40 | -0.93 | 4.79 | 6.04 | -1.64 | 0.00 | 1.00 |
| Kyle Kuzma | 65 | 5 | REB | 2.91 | +2.91 | 3.11 | 2.35 | +0.56 | 0.60 | 1.00 |
| Kyle Kuzma | 65 | 5 | AST | 0.96 | +0.40 | 1.06 | 1.10 | -0.15 | 0.00 | 0.80 |
| Kyle Kuzma | 65 | 5 | PRA | 5.17 | +2.05 | 5.89 | 7.56 | -2.39 | 0.60 | 1.00 |
| LeBron James | 70 | 10 | PTS | 6.37 | +3.88 | 7.75 | 6.37 | +0.00 | 0.60 | 0.80 |
| LeBron James | 70 | 10 | REB | 2.94 | +2.06 | 3.76 | 2.82 | +0.12 | 0.60 | 0.90 |
| LeBron James | 70 | 10 | AST | 1.78 | +0.46 | 2.46 | 2.24 | -0.45 | 0.60 | 0.80 |
| LeBron James | 70 | 10 | PRA | 7.65 | +6.65 | 8.84 | 7.79 | -0.14 | 0.30 | 0.80 |
| Michael Porter Jr. | 77 | 17 | PTS | 4.00 | +1.62 | 4.92 | 6.05 | -2.05 | 0.59 | 1.00 |
| Michael Porter Jr. | 77 | 17 | REB | 2.67 | -0.21 | 3.12 | 2.73 | -0.07 | 0.29 | 0.94 |
| Michael Porter Jr. | 77 | 17 | AST | 1.02 | -0.55 | 1.26 | 0.91 | +0.11 | 0.53 | 0.94 |
| Michael Porter Jr. | 77 | 17 | PRA | 5.21 | +0.41 | 6.18 | 6.16 | -0.96 | 0.65 | 1.00 |
| Mikal Bridges | 82 | 21 | PTS | 5.72 | +1.35 | 6.67 | 6.16 | -0.44 | 0.48 | 0.81 |
| Mikal Bridges | 82 | 21 | REB | 1.54 | -0.38 | 1.76 | 1.52 | +0.03 | 0.67 | 1.00 |
| Mikal Bridges | 82 | 21 | AST | 1.38 | -1.18 | 1.87 | 1.36 | +0.02 | 0.52 | 0.71 |
| Mikal Bridges | 82 | 21 | PRA | 5.62 | -0.67 | 7.14 | 6.57 | -0.95 | 0.33 | 0.90 |
| Myles Turner | 72 | 12 | PTS | 5.18 | -0.27 | 6.08 | 3.48 | +1.70 | 0.50 | 0.67 |
| Myles Turner | 72 | 12 | REB | 3.00 | -1.19 | 3.47 | 2.14 | +0.86 | 0.58 | 0.75 |
| Myles Turner | 72 | 12 | AST | 0.42 | +0.35 | 0.46 | 0.77 | -0.34 | 0.92 | 0.92 |
| Myles Turner | 72 | 12 | PRA | 6.14 | -1.46 | 7.12 | 4.87 | +1.27 | 0.50 | 0.75 |
| Naz Reid | 80 | 20 | PTS | 5.74 | +3.83 | 6.86 | 7.13 | -1.39 | 0.40 | 0.90 |
| Naz Reid | 80 | 20 | REB | 2.28 | +1.69 | 2.86 | 2.86 | -0.58 | 0.60 | 1.00 |
| Naz Reid | 80 | 20 | AST | 0.76 | -0.30 | 1.08 | 0.67 | +0.10 | 0.90 | 1.00 |
| Naz Reid | 80 | 20 | PRA | 5.90 | +5.58 | 7.72 | 8.19 | -2.29 | 0.75 | 0.95 |
| Nikola Jokic | 70 | 10 | PTS | 9.67 | -2.00 | 12.43 | 8.09 | +1.58 | 0.50 | 0.90 |
| Nikola Jokic | 70 | 10 | REB | 2.67 | +1.19 | 3.35 | 3.66 | -1.00 | 0.80 | 1.00 |
| Nikola Jokic | 70 | 10 | AST | 2.39 | +0.87 | 2.96 | 3.43 | -1.04 | 0.70 | 1.00 |
| Nikola Jokic | 70 | 10 | PRA | 11.06 | -0.36 | 13.66 | 9.45 | +1.61 | 0.60 | 1.00 |
| Nikola Vucevic | 73 | 13 | PTS | 5.84 | -0.36 | 6.70 | 7.34 | -1.50 | 0.62 | 0.92 |
| Nikola Vucevic | 73 | 13 | REB | 1.96 | -0.39 | 2.24 | 2.38 | -0.42 | 0.85 | 1.00 |
| Nikola Vucevic | 73 | 13 | AST | 1.54 | -0.96 | 2.18 | 0.93 | +0.60 | 0.31 | 0.92 |
| Nikola Vucevic | 73 | 13 | PRA | 7.55 | -2.13 | 8.76 | 7.55 | -0.00 | 0.46 | 1.00 |
| OG Anunoby | 74 | 14 | PTS | 7.36 | -3.61 | 8.30 | 7.90 | -0.53 | 0.43 | 1.00 |
| OG Anunoby | 74 | 14 | REB | 1.54 | +0.21 | 1.98 | 1.94 | -0.40 | 0.71 | 1.00 |
| OG Anunoby | 74 | 14 | AST | 0.84 | -0.56 | 1.18 | 0.83 | +0.01 | 0.50 | 0.93 |
| OG Anunoby | 74 | 14 | PRA | 7.91 | -3.79 | 8.92 | 9.20 | -1.29 | 0.50 | 0.93 |
| Onyeka Okongwu | 74 | 14 | PTS | 5.56 | -3.33 | 7.37 | 4.49 | +1.06 | 0.50 | 0.93 |
| Onyeka Okongwu | 74 | 14 | REB | 2.93 | +1.00 | 3.47 | 2.65 | +0.28 | 0.29 | 0.64 |
| Onyeka Okongwu | 74 | 14 | AST | 0.59 | -0.25 | 0.98 | 0.52 | +0.06 | 0.57 | 1.00 |
| Onyeka Okongwu | 74 | 14 | PRA | 8.01 | -2.23 | 9.63 | 6.72 | +1.29 | 0.43 | 0.86 |
| Pascal Siakam | 78 | 18 | PTS | 6.50 | +0.79 | 7.46 | 4.48 | +2.02 | 0.50 | 0.78 |
| Pascal Siakam | 78 | 18 | REB | 2.69 | +1.19 | 3.46 | 2.28 | +0.40 | 0.50 | 0.72 |
| Pascal Siakam | 78 | 18 | AST | 0.78 | -0.52 | 0.96 | 1.22 | -0.44 | 0.61 | 0.83 |
| Pascal Siakam | 78 | 18 | PRA | 7.70 | +1.60 | 9.04 | 4.91 | +2.79 | 0.28 | 0.83 |
| Rudy Gobert | 72 | 12 | PTS | 7.98 | -7.14 | 9.84 | 4.28 | +3.70 | 0.25 | 0.75 |
| Rudy Gobert | 72 | 12 | REB | 5.00 | -4.35 | 6.80 | 2.95 | +2.05 | 0.42 | 0.67 |
| Rudy Gobert | 72 | 12 | AST | 0.56 | -0.12 | 0.79 | 1.09 | -0.52 | 0.75 | 1.00 |
| Rudy Gobert | 72 | 12 | PRA | 12.66 | -11.69 | 14.83 | 6.30 | +6.36 | 0.33 | 0.58 |
| Scottie Barnes | 65 | 5 | PTS | 9.08 | -0.46 | 10.81 | 4.48 | +4.60 | 0.40 | 0.60 |
| Scottie Barnes | 65 | 5 | REB | 3.42 | +0.28 | 3.72 | 3.51 | -0.09 | 0.40 | 0.80 |
| Scottie Barnes | 65 | 5 | AST | 1.25 | +0.14 | 1.60 | 2.06 | -0.81 | 0.40 | 0.80 |
| Scottie Barnes | 65 | 5 | PRA | 12.44 | +0.21 | 14.87 | 7.14 | +5.30 | 0.40 | 0.60 |
| Shai Gilgeous-Alexander | 76 | 16 | PTS | 6.70 | +4.24 | 7.80 | 6.14 | +0.56 | 0.62 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | REB | 2.00 | +0.43 | 2.32 | 2.06 | -0.06 | 0.75 | 0.94 |
| Shai Gilgeous-Alexander | 76 | 16 | AST | 1.83 | -1.29 | 2.27 | 1.73 | +0.09 | 0.56 | 0.88 |
| Shai Gilgeous-Alexander | 76 | 16 | PRA | 6.34 | +3.43 | 7.52 | 6.83 | -0.49 | 0.75 | 0.94 |
| Stephen Curry | 70 | 10 | PTS | 12.31 | -3.31 | 14.77 | 7.52 | +4.79 | 0.60 | 0.80 |
| Stephen Curry | 70 | 10 | REB | 2.34 | -1.53 | 3.33 | 1.94 | +0.39 | 0.70 | 0.70 |
| Stephen Curry | 70 | 10 | AST | 1.06 | -0.73 | 1.42 | 2.17 | -1.11 | 0.80 | 1.00 |
| Stephen Curry | 70 | 10 | PRA | 13.49 | -5.18 | 16.35 | 9.03 | +4.45 | 0.60 | 0.80 |
| Trae Young | 76 | 16 | PTS | 4.78 | +1.62 | 5.83 | 7.83 | -3.05 | 0.62 | 1.00 |
| Trae Young | 76 | 16 | REB | 1.69 | -0.75 | 2.06 | 1.39 | +0.30 | 0.31 | 0.88 |
| Trae Young | 76 | 16 | AST | 2.06 | +0.90 | 2.38 | 3.38 | -1.32 | 0.75 | 1.00 |
| Trae Young | 76 | 16 | PRA | 5.46 | +1.56 | 6.93 | 7.88 | -2.42 | 0.69 | 1.00 |
| Tyrese Haliburton | 73 | 13 | PTS | 4.33 | +1.07 | 5.16 | 7.12 | -2.79 | 0.85 | 1.00 |
| Tyrese Haliburton | 73 | 13 | REB | 2.27 | -0.42 | 2.66 | 1.32 | +0.95 | 0.46 | 0.62 |
| Tyrese Haliburton | 73 | 13 | AST | 2.27 | -0.45 | 3.07 | 1.50 | +0.77 | 0.15 | 0.69 |
| Tyrese Haliburton | 73 | 13 | PRA | 3.86 | +0.24 | 4.79 | 7.85 | -3.99 | 1.00 | 1.00 |

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
