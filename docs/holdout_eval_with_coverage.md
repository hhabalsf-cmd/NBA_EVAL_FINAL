# Holdout Evaluation — 2026-05-04

- **Season:** 2024-25
- **Train games:** first 60 per player
- **Test games:** remainder (per-player; varies)
- **Pipeline:** `quick (no ensemble)`
- **Players attempted:** 20
- **Players evaluated:** 12
- **Players skipped:** 8

## Aggregate (mean across evaluated players)

| Stat | Players | N test | Holdout MAE | Holdout Bias | Holdout RMSE | Train OOF MAE | Train OOF Bias | Train OOF 80% Cov |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 12 | 139 | 6.86 | -0.71 | 8.32 | 6.90 | +0.19 | 0.65 |
| REB | 12 | 139 | 2.24 | +0.44 | 2.73 | 2.29 | +0.09 | 0.59 |
| AST | 12 | 139 | 2.04 | -0.21 | 2.58 | 1.94 | +0.08 | 0.56 |

## Quantile interval coverage (holdout test sets)

Target for the 80% interval (q10, q90) is 0.80; the CQR correction is tuned to push it to ~0.92 at training time.

| Stat | Mean CQR correction | Holdout Cov RAW (target 0.80) | Holdout Cov CQR (target 0.92) |
|---|---:|---:|---:|
| PTS | 6.10 | 0.62 | 0.86 |
| REB | 2.24 | 0.67 | 0.85 |
| AST | 2.10 | 0.51 | 0.80 |

## Per-player breakdown

| Player | N total | N test | Stat | Holdout MAE | Holdout Bias | Train MAE | Train Bias |
|---|---:|---:|---|---:|---:|---:|---:|
| LeBron James | 70 | 10 | PTS | 4.71 | +3.13 | 6.04 | -1.06 |
| LeBron James | 70 | 10 | REB | 3.73 | +2.93 | 2.94 | +0.32 |
| LeBron James | 70 | 10 | AST | 1.72 | +0.76 | 2.14 | +1.19 |
| Stephen Curry | 70 | 10 | PTS | 11.44 | -0.20 | 7.55 | -1.02 |
| Stephen Curry | 70 | 10 | REB | 2.15 | -0.93 | 2.03 | +0.75 |
| Stephen Curry | 70 | 10 | AST | 1.01 | +0.11 | 2.11 | +0.55 |
| Giannis Antetokounmpo | 67 | 7 | PTS | 6.06 | -5.09 | 5.07 | +1.92 |
| Giannis Antetokounmpo | 67 | 7 | REB | 3.13 | -0.07 | 2.38 | +0.07 |
| Giannis Antetokounmpo | 67 | 7 | AST | 4.09 | -4.02 | 2.15 | -0.05 |
| Jayson Tatum | 72 | 12 | PTS | 4.18 | -0.99 | 7.48 | +2.84 |
| Jayson Tatum | 72 | 12 | REB | 2.87 | +2.07 | 2.77 | +0.22 |
| Jayson Tatum | 72 | 12 | AST | 0.97 | +0.02 | 1.54 | -0.21 |
| Nikola Jokic | 70 | 10 | PTS | 9.66 | -6.35 | 7.98 | +1.27 |
| Nikola Jokic | 70 | 10 | REB | 2.93 | +1.07 | 3.68 | -0.21 |
| Nikola Jokic | 70 | 10 | AST | 1.87 | +0.70 | 3.12 | +0.22 |
| Trae Young | 76 | 16 | PTS | 4.99 | +1.49 | 8.04 | -2.14 |
| Trae Young | 76 | 16 | REB | 1.28 | -0.80 | 1.27 | +0.35 |
| Trae Young | 76 | 16 | AST | 2.93 | +2.62 | 3.18 | -0.25 |
| Donovan Mitchell | 71 | 11 | PTS | 5.33 | +0.80 | 7.10 | +0.83 |
| Donovan Mitchell | 71 | 11 | REB | 1.81 | -1.34 | 2.19 | +0.43 |
| Donovan Mitchell | 71 | 11 | AST | 2.11 | -0.56 | 1.19 | -0.19 |
| Devin Booker | 75 | 15 | PTS | 8.46 | -0.02 | 7.49 | -1.41 |
| Devin Booker | 75 | 15 | REB | 1.67 | -0.22 | 1.45 | -0.40 |
| Devin Booker | 75 | 15 | AST | 2.82 | -0.19 | 1.76 | -0.43 |
| Karl-Anthony Towns | 72 | 12 | PTS | 6.90 | -4.08 | 6.66 | +0.64 |
| Karl-Anthony Towns | 72 | 12 | REB | 1.39 | +0.65 | 4.05 | +0.52 |
| Karl-Anthony Towns | 72 | 12 | AST | 1.13 | -0.86 | 1.38 | +0.19 |
| Pascal Siakam | 78 | 18 | PTS | 8.22 | +1.40 | 4.58 | +0.52 |
| Pascal Siakam | 78 | 18 | REB | 2.48 | +1.60 | 2.17 | -1.14 |
| Pascal Siakam | 78 | 18 | AST | 0.95 | -0.87 | 1.07 | -0.02 |
| Jalen Brunson | 65 | 5 | PTS | 8.14 | +1.78 | 7.59 | +0.45 |
| Jalen Brunson | 65 | 5 | REB | 1.39 | +0.95 | 1.31 | -0.04 |
| Jalen Brunson | 65 | 5 | AST | 2.34 | -0.10 | 2.08 | +0.29 |
| Tyrese Haliburton | 73 | 13 | PTS | 4.24 | -0.40 | 7.16 | -0.59 |
| Tyrese Haliburton | 73 | 13 | REB | 2.02 | -0.62 | 1.28 | +0.20 |
| Tyrese Haliburton | 73 | 13 | AST | 2.51 | -0.16 | 1.60 | -0.35 |

## Skipped players

- **Kevin Durant** (201142): only 62 games available (need ≥ 65)
- **Luka Doncic** (1629029): only 50 games available (need ≥ 65)
- **Joel Embiid** (203954): only 19 games available (need ≥ 65)
- **Damian Lillard** (203081): only 58 games available (need ≥ 65)
- **Anthony Davis** (203076): only 51 games available (need ≥ 65)
- **Jimmy Butler** (202710): only 55 games available (need ≥ 65)
- **De'Aaron Fox** (1628368): only 62 games available (need ≥ 65)
- **Jaylen Brown** (1627759): only 63 games available (need ≥ 65)

## Reading guide

- **Holdout MAE vs Train OOF MAE.** Large gap ⇒ overfitting. Roughly equal ⇒ training metrics are honest.
- **Holdout bias.** Persistent positive bias = model over-predicts the stat on held-out games; negative = under-predicts. This is the *unbiased* version of the bias seen on graded picks.
- **Holdout RMSE.** Heavier penalty on large misses than MAE; comparing the two surfaces fat-tail behaviour.
- **Train OOF 80% Coverage.** Should be ~0.80 if quantile models are well-calibrated. Lower ⇒ intervals too narrow; higher ⇒ too wide.
