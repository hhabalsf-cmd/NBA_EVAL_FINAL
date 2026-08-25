# Pooled cross-player model — holdout scorecard

44 players / 606 held-out games / 2424 rows. Training: 25327 pooled rows from 439 players, every game strictly before the holdout (through 2025-02-27).

Lookahead control: 36 pooled features rebuilt independently and matched to the harness's own baselines with a maximum absolute difference of 0.0.


## MAE — pooled model vs production vs every trivial baseline

| Stat | pooled | production (81f) | l3 | l5 | l10 | l20 | median | mean | last | ewma5 | best baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PTS | **6.000** | 6.517 | 6.688 | 6.412 | 6.159 | 6.114 | 6.121 | 6.088 | 8.031 | 6.065 | 6.065 (ewma5) |
| REB | **2.419** | 2.546 | 2.696 | 2.595 | 2.483 | 2.460 | 2.439 | 2.427 | 3.411 | 2.459 | 2.427 (mean) |
| AST | **1.792** | 1.885 | 2.079 | 1.894 | 1.813 | 1.775 | 1.812 | 1.806 | 2.510 | 1.801 | 1.775 (l20) |
| PRA | **7.249** | 7.637 | 7.968 | 7.523 | 7.335 | 7.444 | 7.422 | 7.394 | 9.823 | 7.267 | 7.267 (ewma5) |

## Paired bootstrap — mean|pooled| − mean|baseline|, 95% CI

Negative = the pooled model wins. Resampled over the 44 players, 2000 draws.

| Stat | baseline | Δ MAE | 95% CI | verdict |
|---|---|---:|---|---|
| PTS | l3 | -0.688 | [-0.912, -0.474] | **pooled wins** |
| PTS | l5 | -0.413 | [-0.599, -0.239] | **pooled wins** |
| PTS | l10 | -0.160 | [-0.289, -0.033] | **pooled wins** |
| PTS | l20 | -0.114 | [-0.202, -0.034] | **pooled wins** |
| PTS | median | -0.122 | [-0.300, +0.030] | tie |
| PTS | mean | -0.088 | [-0.231, +0.042] | tie |
| PTS | last | -2.032 | [-2.452, -1.600] | **pooled wins** |
| PTS | ewma5 | -0.065 | [-0.131, +0.004] | tie |
| REB | l3 | -0.277 | [-0.374, -0.183] | **pooled wins** |
| REB | l5 | -0.176 | [-0.228, -0.124] | **pooled wins** |
| REB | l10 | -0.064 | [-0.108, -0.023] | **pooled wins** |
| REB | l20 | -0.041 | [-0.102, +0.011] | tie |
| REB | median | -0.020 | [-0.102, +0.049] | tie |
| REB | mean | -0.008 | [-0.063, +0.039] | tie |
| REB | last | -0.992 | [-1.158, -0.816] | **pooled wins** |
| REB | ewma5 | -0.040 | [-0.059, -0.022] | **pooled wins** |
| AST | l3 | -0.287 | [-0.345, -0.231] | **pooled wins** |
| AST | l5 | -0.102 | [-0.145, -0.059] | **pooled wins** |
| AST | l10 | -0.021 | [-0.055, +0.012] | tie |
| AST | l20 | +0.017 | [-0.002, +0.036] | tie |
| AST | median | -0.020 | [-0.078, +0.030] | tie |
| AST | mean | -0.014 | [-0.058, +0.022] | tie |
| AST | last | -0.718 | [-0.832, -0.606] | **pooled wins** |
| AST | ewma5 | -0.010 | [-0.024, +0.007] | tie |
| PRA | l3 | -0.718 | [-0.938, -0.498] | **pooled wins** |
| PRA | l5 | -0.273 | [-0.469, -0.075] | **pooled wins** |
| PRA | l10 | -0.086 | [-0.255, +0.075] | tie |
| PRA | l20 | -0.195 | [-0.412, -0.003] | **pooled wins** |
| PRA | median | -0.173 | [-0.535, +0.099] | tie |
| PRA | mean | -0.144 | [-0.443, +0.097] | tie |
| PRA | last | -2.574 | [-3.101, -2.083] | **pooled wins** |
| PRA | ewma5 | -0.018 | [-0.096, +0.056] | tie |

## Exit criterion 1 — beat EWMA5 / L10 / season median on all four stats

The plan names those three. The stricter bar — the best of ALL eight trivial baselines — is reported beside it, because a model that only clears the three it was asked about has not cleared the field.

| Stat | pooled | EWMA5 | L10 | season median | worst of the 3 | criterion 1 | best of all 8 | margin vs best | bootstrap |
|---|---:|---:|---:|---:|---:|---|---|---:|---|
| PTS | 6.000 | 6.065 | 6.159 | 6.121 | -0.065 | PASS | 6.065 (ewma5) | -0.065 | tie [-0.131, +0.004] |
| REB | 2.419 | 2.459 | 2.483 | 2.439 | -0.020 | PASS | 2.427 (mean) | -0.008 | tie [-0.063, +0.039] |
| AST | 1.792 | 1.801 | 1.813 | 1.812 | -0.010 | PASS | 1.775 (l20) | +0.017 | tie [-0.002, +0.036] |
| PRA | 7.249 | 7.267 | 7.335 | 7.422 | -0.018 | PASS | 7.267 (ewma5) | -0.018 | tie [-0.096, +0.056] |

## Exit criterion 2 — median-line AUC >= 0.58

| Stat | pooled AUC | 95% CI | production AUC | L10 signal | PASS? |
|---|---:|---|---:|---:|---|
| PTS | **0.5760** | [0.5227, 0.6270] | 0.5115 | 0.5774 | **FAIL** |
| REB | **0.5829** | [0.5198, 0.6393] | 0.5372 | 0.5759 | PASS |
| AST | **0.6318** | [0.5695, 0.6823] | 0.5628 | 0.6210 | PASS |
| PRA | **0.5610** | [0.4966, 0.6188] | 0.5505 | 0.5770 | **FAIL** |

## Exit criterion 3 — unclipped 60-80% reliability gap within ±5 points

Positive = the probability claims more than it delivers (overconfident); negative = it delivers more than it claims.

| Probability source | band | N | predicted | realized | gap | PASS? |
|---|---|---:|---:|---:|---:|---|
| pooled (shrunk) | 60-80% | 212 | 63.4 | 77.4 | -13.9 | **FAIL** |
| pooled (shrunk) | 40-60% | 1905 | 49.9 | 53.0 | -3.1 | — |
| production (81f, reference) | 60-80% | 780 | 69.4 | 55.1 | +14.3 | — |

### Full reliability table, pooled, unclipped

| Bucket | N | predicted | realized | gap |
|---|---:|---:|---:|---:|
| [20, 30) | 1 | 29.8 | 100.0 | -70.2 |
| [30, 40) | 69 | 37.7 | 44.9 | -7.2 |
| [40, 50) | 961 | 46.0 | 48.6 | -2.6 |
| [50, 60) | 944 | 54.0 | 57.5 | -3.5 |
| [60, 70) | 205 | 63.1 | 76.6 | -13.4 |
| [70, 80) | 7 | 71.7 | 100.0 | -28.3 |

## Reference variants on the identical holdout

| Variant | features/stat | train rows | PTS | REB | AST | PRA |
|---|---:|---:|---:|---:|---:|---:|
| 9-feature ridge, 2023-24 only (diagnosis 10.2) | 9 | 16323 | 6.003 | 2.429 | 1.794 | 7.258 |
