# Pick-Selection Rule Backtest — 2026-05-04

- **Total graded picks:** 106
- **Wins:** 40
- **Overall win rate:** 37.7%
- **Overall ROI @ −110 juice:** -28.0%
- **Breakeven win rate at −110:** 52.4%

## 1. Calibration of stored `prob_over`

Bucket each pick by *prob_pick_wins* (= prob_over if direction=OVER else 100 − prob_over).
Calibration gap > 0 ⇒ model is *underconfident* in that bucket; < 0 ⇒ *overconfident*.

| prob_pick_wins bucket | N | Wins | Win % | Avg Predicted % | Calibration gap |
|---|---:|---:|---:|---:|---:|
| < 50% | 0 | 0 | — | — | — |
| 50–55% | 1 | 0 | 0.0 | 54.5 | -54.5 |
| 55–60% | 7 | 1 | 14.3 | 57.7 | -43.4 |
| 60–65% | 13 | 4 | 30.8 | 62.9 | -32.1 |
| 65–70% | 21 | 6 | 28.6 | 66.9 | -38.3 |
| 70–75% | 25 | 16 | 64.0 | 73.0 | -9.0 |
| 75–80% | 16 | 6 | 37.5 | 76.9 | -39.4 |
| 80%+ | 23 | 7 | 30.4 | 83.2 | -52.7 |

## 2. Sweep — `prob_pick_wins ≥ T`

Replaces the current ``diff_pct > 8`` rule with one based on the calibrated probability.

| Rule | N | Wins | Win % | ROI @ −110 |
|---|---:|---:|---:|---:|
| prob_pick_wins ≥ 50 | 106 | 40 | 37.7 | -28.0 |
| prob_pick_wins ≥ 52 | 106 | 40 | 37.7 | -28.0 |
| prob_pick_wins ≥ 54 | 106 | 40 | 37.7 | -28.0 |
| prob_pick_wins ≥ 55 | 105 | 40 | 38.1 | -27.3 |
| prob_pick_wins ≥ 56 | 104 | 40 | 38.5 | -26.6 |
| prob_pick_wins ≥ 58 | 101 | 39 | 38.6 | -26.3 |
| prob_pick_wins ≥ 60 | 98 | 39 | 39.8 | -24.0 |
| prob_pick_wins ≥ 62 | 95 | 38 | 40.0 | -23.6 |
| prob_pick_wins ≥ 64 | 88 | 35 | 39.8 | -24.1 |
| prob_pick_wins ≥ 65 | 85 | 35 | 41.2 | -21.4 |
| prob_pick_wins ≥ 66 | 81 | 33 | 40.7 | -22.2 |
| prob_pick_wins ≥ 68 | 69 | 30 | 43.5 | -17.0 |
| prob_pick_wins ≥ 70 | 64 | 29 | 45.3 | -13.5 |
| prob_pick_wins ≥ 72 | 59 | 25 | 42.4 | -19.1 |
| prob_pick_wins ≥ 75 | 39 | 13 | 33.3 | -36.4 |

## 3. Sweep — current `|edge|` rule

Edge magnitude in pp. This is roughly what production uses today.

| Rule | N | Wins | Win % | ROI @ −110 |
|---|---:|---:|---:|---:|
| |edge| ≥ 0 | 106 | 40 | 37.7 | -28.0 |
| |edge| ≥ 5 | 106 | 40 | 37.7 | -28.0 |
| |edge| ≥ 8 | 105 | 40 | 38.1 | -27.3 |
| |edge| ≥ 10 | 104 | 40 | 38.5 | -26.6 |
| |edge| ≥ 12 | 103 | 40 | 38.8 | -25.9 |
| |edge| ≥ 15 | 103 | 40 | 38.8 | -25.9 |
| |edge| ≥ 20 | 101 | 40 | 39.6 | -24.4 |
| |edge| ≥ 25 | 84 | 34 | 40.5 | -22.7 |
| |edge| ≥ 30 | 15 | 5 | 33.3 | -36.4 |

## 4. Sweep — displayed `confidence`

Sanity check: does the heuristic confidence cap correlate with hit rate?

| Rule | N | Wins | Win % | ROI @ −110 |
|---|---:|---:|---:|---:|
| confidence ≥ 60 | 106 | 40 | 37.7 | -28.0 |
| confidence ≥ 65 | 98 | 39 | 39.8 | -24.0 |
| confidence ≥ 70 | 76 | 29 | 38.2 | -27.2 |
| confidence ≥ 72 | 62 | 23 | 37.1 | -29.2 |
| confidence ≥ 75 | 39 | 13 | 33.3 | -36.4 |
| confidence ≥ 78 | 5 | 3 | 60.0 | +14.5 |

## 5. Combined `prob ∧ |edge|` rule

Does adding an edge requirement on top of a probability threshold help or hurt?

| Rule | N | Wins | Win % | ROI @ −110 |
|---|---:|---:|---:|---:|
| prob ≥ 55 AND |edge| ≥ 0 | 105 | 40 | 38.1 | -27.3 |
| prob ≥ 55 AND |edge| ≥ 5 | 105 | 40 | 38.1 | -27.3 |
| prob ≥ 55 AND |edge| ≥ 10 | 104 | 40 | 38.5 | -26.6 |
| prob ≥ 60 AND |edge| ≥ 0 | 98 | 39 | 39.8 | -24.0 |
| prob ≥ 60 AND |edge| ≥ 5 | 98 | 39 | 39.8 | -24.0 |
| prob ≥ 60 AND |edge| ≥ 10 | 98 | 39 | 39.8 | -24.0 |
| prob ≥ 62 AND |edge| ≥ 0 | 95 | 38 | 40.0 | -23.6 |
| prob ≥ 62 AND |edge| ≥ 5 | 95 | 38 | 40.0 | -23.6 |
| prob ≥ 62 AND |edge| ≥ 10 | 95 | 38 | 40.0 | -23.6 |
| prob ≥ 65 AND |edge| ≥ 0 | 85 | 35 | 41.2 | -21.4 |
| prob ≥ 65 AND |edge| ≥ 5 | 85 | 35 | 41.2 | -21.4 |
| prob ≥ 65 AND |edge| ≥ 10 | 85 | 35 | 41.2 | -21.4 |
| prob ≥ 70 AND |edge| ≥ 0 | 64 | 29 | 45.3 | -13.5 |
| prob ≥ 70 AND |edge| ≥ 5 | 64 | 29 | 45.3 | -13.5 |
| prob ≥ 70 AND |edge| ≥ 10 | 64 | 29 | 45.3 | -13.5 |

## 6. Window rules — keep only the middle of the prob distribution

Calibration table shows the 80%+ bucket only hits 30%; tail picks lose money. A windowed rule isolates the calibrated middle (~60–78%). 

| Rule | N | Wins | Win % | ROI @ −110 |
|---|---:|---:|---:|---:|
| 60 ≤ prob < 80 | 75 | 32 | 42.7 | -18.5 |
| 60 ≤ prob < 78 | 71 | 29 | 40.8 | -22.0 |
| 60 ≤ prob < 75 | 59 | 26 | 44.1 | -15.9 |
| 62 ≤ prob < 78 | 68 | 28 | 41.2 | -21.4 |
| 62 ≤ prob < 75 | 56 | 25 | 44.6 | -14.8 |
| 65 ≤ prob < 80 | 62 | 28 | 45.2 | -13.8 |
| 65 ≤ prob < 78 | 58 | 25 | 43.1 | -17.7 |
| 65 ≤ prob < 75 | 46 | 22 | 47.8 | -8.7 |
| 68 ≤ prob < 78 | 42 | 20 | 47.6 | -9.1 |
| 68 ≤ prob < 76 | 34 | 18 | 52.9 | +1.1 |
| 70 ≤ prob < 80 | 41 | 22 | 53.7 | +2.4 |
| 70 ≤ prob < 78 | 37 | 19 | 51.4 | -2.0 |
| 70 ≤ prob < 76 | 29 | 17 | 58.6 | +11.9 |
| 70 ≤ prob < 75 | 25 | 16 | 64.0 | +22.2 |

## 7. Cap-high-prob rule — exclude extreme tails

Simpler than a window: just refuse picks where prob_pick_wins is suspiciously high.

| Rule | N | Wins | Win % | ROI @ −110 |
|---|---:|---:|---:|---:|
| prob ≤ 95 (no extreme tails) | 106 | 40 | 37.7 | -28.0 |
| prob ≤ 90 (no extreme tails) | 106 | 40 | 37.7 | -28.0 |
| prob ≤ 85 (no extreme tails) | 106 | 40 | 37.7 | -28.0 |
| prob ≤ 80 (no extreme tails) | 84 | 33 | 39.3 | -25.0 |
| prob ≤ 78 (no extreme tails) | 80 | 30 | 37.5 | -28.4 |
| prob ≤ 75 (no extreme tails) | 67 | 27 | 40.3 | -23.1 |

## Reading guide

- **Volume cliff matters.** A rule that hits 80% on 4 picks is statistically meaningless.
  Look for the rule with the highest win rate at ≥30 picks.
- **Calibration gap signals model behaviour.** Persistently negative gap means lower the
  caps in `CONFIDENCE_CAPS`. Persistently positive means the model is too humble — but
  with N=106 we cannot distinguish that from noise.
- **ROI > 0 at −110 needs win rate > 52.4%.** Anything below is a losing strategy at
  standard juice, regardless of how confident the model sounds.

## Selection-bias caveat

All picks here came from the existing rule (high `|edge|`, high heuristic confidence).
Sweeping a *stricter* rule across this dataset is fair because every candidate rule's
kept-set is a subset of what we already saw graded. Sweeping a *looser* rule is **not**
fair — those picks were never made, so we don't know how they would have graded.
