# Diagnosis — the resolution failure is real, and the point model has no edge (2026-08-23)

**Scope:** read-only diagnostic investigation of why Phases 0–2 could not re-rank
probability buckets. No production code was modified. New analysis scripts:
`scripts/diagnose_dump.py`, `scripts/diagnose_analyze.py`, `scripts/diagnose_tiny.py`,
`scripts/diagnose_league.py`. Test suite unchanged at **449 passed / 20 failed /
3 skipped**.

---

## 1. Verdict

**The point model has no usable edge. It is measurably worse than a rolling
average.** On the identical 606 held-out games the Phase-2 report scored, the
production model's pooled MAE is worse than the player's own season-to-date
mean, season-to-date median, 10-game rolling mean, 20-game rolling mean *and* a
5-game EWMA — on all four stats. It beats the best of those trivial baselines on
**4 of 44 players for PTS** (7/44 REB, 6/44 AST, 10/44 PRA). Its held-out RMSE is
**1.10–1.17× the player's own game-to-game σ**, and its R² measured against the
player's own running mean is **negative for all four stats** — it explains less
variance than a constant. At the median pseudo-line it ranks outcomes at
**AUC 0.536** versus **0.583** for a plain 10-game rolling mean (pooled difference
−0.047, 95% CI [−0.085, −0.010], bootstrap clustered by player), and its
directional call is right **53.3%** of the time against **55.1%** for simply always
taking the over.

**The low-decile inversion is a genuine model failure, not a benchmark artifact.**
H3 is decisively rejected. League-wide over 79,811 game logs, the season-to-date
median line is *generous* to a form-tracking predictor, not adversarial: the
realized over-rate rises monotonically from ~27% to ~73% as recent form moves
from −1σ to +1σ relative to the season median. A one-line rolling average
captures that signal at AUC ≈ 0.60. The production model does not — it is on the
wrong side of it, and the buckets where it is most confident of an under
(10–30%) are the buckets where it is closest to a coin flip.

**Standing caveat, and it is larger than previously stated.** Every probability
number here and in Phases 0–2 is measured against **synthetic pseudo-lines**.
`manual_lines` is empty. Section 8 quantifies this: essentially *all* of the
apparent signal at a season-median line is line staleness. Swap in a form-aware
line and the same signals collapse to AUC 0.51–0.56. None of these numbers are
evidence of edge against a sportsbook.

---

## 2. What was measured

`scripts/diagnose_dump.py` replays the walk-forward exactly as
`scripts/backtest_unbiased.py` does — same `build_serve`, same
`get_prediction_features`, same `predict` / `get_confidence` /
`ProbabilityCalculator.calculate`, same per-player lookahead probe — but writes
one row per (player, stat, held-out game) instead of aggregating.

Reproduction check: **2424 rows / 44 players / 606 held-out games**, identical to
the Phase-2 report's counts, and pooled MAE reproduces
`PTS 6.517 / REB 2.546 / AST 1.885 / PRA 7.637` to three decimals.

| Artifact | Contents |
|---|---|
| `cache/diagnostics_t60/rows.parquet` | 2424 rows: pred, actual, served std, raw quantiles, median line, served `prob_over`, and eight causal baselines per row |
| `cache/diagnostics_t60/served.parquet` | the exact 81-feature vector served for each of the 606 games |
| `cache/diagnostics_t60/train/*.parquet` | the exact 60-row training frame each player's model was fitted on |
| `cache/diagnostics_t60/importance.json` | per (player, stat) feature importances |
| `cache/diagnostics_multi/*` | the same, with multi-season training (§7) |
| `cache/league_logs.parquet`, `cache/league_panel.parquet` | 79,811 game logs / 33,414 scored rows, 2023-24 + 2024-25, from Supabase |

**Regime being tested, stated plainly:** 60 training rows per player, 81 declared
features (**p/n = 1.35**), holdout = the last ~14 games of the season
(2025-02-28 → 2025-04-13, a 44-day window, mean 13.8 games per player).

---

## 3. H1 — the model has no edge over trivial baselines. **SUPPORTED.**

Pooled MAE on the same 606 held-out games:

| Stat | N | **model** | median | mean | L3 | L5 | L10 | L20 | last | EWMA5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PTS | 606 | **6.517** | 6.121 | 6.088 | 6.688 | 6.412 | 6.159 | 6.114 | 8.031 | **6.065** |
| REB | 606 | **2.546** | 2.439 | **2.427** | 2.696 | 2.595 | 2.483 | 2.460 | 3.411 | 2.459 |
| AST | 606 | **1.885** | 1.812 | 1.806 | 2.079 | 1.894 | 1.813 | **1.775** | 2.510 | 1.801 |
| PRA | 606 | **7.637** | 7.422 | 7.394 | 7.968 | 7.523 | 7.335 | 7.444 | 9.823 | **7.267** |

The model loses to every baseline except L3 and last-game. RMSE tells the same
story (model 8.305 PTS vs 7.720 for EWMA5).

Paired bootstrap on absolute errors, `mean(|model|) − mean(|baseline|)`, 95% CI:

| | vs median | vs mean | vs L10 | vs L20 | vs EWMA5 |
|---|---|---|---|---|---|
| PTS | **+0.395** [+0.18,+0.62] | **+0.429** [+0.21,+0.63] | **+0.357** [+0.09,+0.63] | **+0.403** [+0.19,+0.63] | **+0.451** [+0.21,+0.70] |
| REB | **+0.107** [+0.03,+0.19] | **+0.119** [+0.04,+0.20] | +0.064 (tie) | +0.086 (tie) | +0.087 (tie) |
| AST | **+0.073** [+0.02,+0.13] | **+0.079** [+0.03,+0.13] | **+0.073** [+0.00,+0.15] | **+0.110** [+0.05,+0.18] | **+0.084** [+0.02,+0.15] |
| PRA | +0.215 (tie) | **+0.244** [+0.01,+0.48] | +0.302 (tie) | +0.193 (tie) | **+0.370** [+0.09,+0.65] |

Positive = model worse. Fifteen of twenty comparisons are a statistically
distinguishable loss; the remaining five are ties. **Not one is a win.**

Per-player, against the *best* trivial baseline for that player:

| Stat | players where model wins | mean MAE penalty | worst case |
|---|---|---:|---|
| PTS | **4 / 44** | +0.762 | +3.77 (Deni Avdija) |
| REB | **7 / 44** | +0.274 | +1.65 (Kyle Kuzma) |
| AST | **6 / 44** | +0.215 | +1.22 (Giannis Antetokounmpo) |
| PRA | **10 / 44** | +0.860 | +5.81 (Deni Avdija) |

The deficit does not concentrate in any regime: it is the same in the early and
late half of the holdout window, and the same across quartiles of minutes
surprise (the model is marginally *better* than L20 only in the largest-minutes-
surprise quartile, and worse in the other three).

### H1b — is it level bias or resolution? **Both.**

| Stat | pooled bias (model) | per-player \|bias\| model | per-player \|bias\| L10 |
|---|---:|---:|---:|
| PTS | −0.080 | **2.637** | 1.461 |
| REB | +0.065 | **1.148** | 0.734 |
| AST | −0.434 | **0.847** | 0.407 |
| PRA | −0.411 | **3.233** | 2.235 |

Pooled bias is near zero, but per-player level error is roughly **2× the rolling
mean's**. The pooled figure hides large offsetting per-player offsets.

An oracle de-bias (subtract each player's own held-out mean error — not
achievable in production, diagnostic only) moves the model to
PTS 5.974 / REB 2.303 / AST 1.720 / PRA 6.986, which would finally edge past L10.
So *part* of the deficit is a recoverable per-player level offset. The rest is
resolution, and resolution is worse than absent:

Within-player correlation of prediction with outcome (each player's holdout means
removed), against a 2000-draw permutation null:

| Stat | observed | null mean ± sd | one-sided p (signal > 0) |
|---|---:|---|---:|
| PTS | **−0.1277** | +0.0005 ± 0.0447 | 0.999 |
| REB | −0.0053 | −0.0028 ± 0.0426 | 0.521 |
| AST | −0.0726 | +0.0002 ± 0.0468 | 0.940 |
| PRA | −0.0524 | +0.0018 ± 0.0434 | 0.895 |

For PTS the model's game-to-game variation is *significantly anti-correlated*
with the outcome. For the rest it is indistinguishable from zero. **There is no
within-player resolution to recover.**

---

## 4. H2 — the predictions are directionally uninformative at the median line. **SUPPORTED.**

AUC for the event `actual > season-to-date median`, 2187 non-push samples:

| Stat | N | **model prob** | pred−median | L5−median | L10−median | L20−median | mean−median |
|---|---:|---:|---:|---:|---:|---:|---:|
| PTS | 572 | 0.5318 | 0.5115 | 0.5676 | **0.5774** | 0.5685 | 0.5504 |
| REB | 536 | 0.5097 | 0.5372 | 0.5650 | 0.5759 | **0.5784** | 0.5949 |
| AST | 491 | 0.5549 | 0.5628 | 0.5824 | 0.6210 | **0.6483** | 0.5992 |
| PRA | 588 | 0.5508 | 0.5505 | 0.5715 | **0.5770** | 0.5586 | 0.5350 |
| **ALL** | **2187** | **0.5362** | 0.5319 | 0.5689 | **0.5830** | 0.5778 | 0.5624 |

The model is beaten by every trivial signal on every stat. Pooled AUC difference
(model − L10) = **−0.0468, 95% CI [−0.0854, −0.0096]** (600-draw bootstrap
clustered by player). Per-stat CIs straddle zero — the study is underpowered at
44 players — but the pooled result is a significant loss.

Sign test:

| Stat | N | base rate (always-over) | **model** | L5 | L10 |
|---|---:|---:|---:|---:|---:|
| PTS | 572 | 0.5594 | 0.5052 | 0.5507 | **0.5752** |
| REB | 536 | 0.5000 | 0.5317 | 0.5299 | **0.5392** |
| AST | 491 | 0.5764 | 0.5560 | 0.5927 | **0.6212** |
| PRA | 588 | 0.5697 | 0.5425 | 0.5510 | **0.5663** |
| **ALL** | **2187** | **0.5514** | **0.5332** | 0.5551 | **0.5743** |

**The model's directional call is worse than always betting the over.**

Median-line reliability with exact binomial 95% CIs on the realized rate:

| Bucket | N | predicted | realized | 95% CI realized | gap |
|---|---:|---:|---:|---|---:|
| 10–20% | 50 | 16.3% | 50.0% | [35.5%, 64.5%] | **−33.7** |
| 20–30% | 121 | 25.8% | 51.2% | [42.0%, 60.4%] | **−25.5** |
| 30–40% | 207 | 35.6% | 57.5% | [50.4%, 64.3%] | **−21.9** |
| 40–50% | 364 | 45.5% | 51.1% | [45.8%, 56.3%] | −5.6 |
| 50–60% | 473 | 54.9% | 53.5% | [48.9%, 58.1%] | +1.4 |
| 60–70% | 422 | 65.0% | 52.4% | [47.5%, 57.2%] | **+12.6** |
| 70–80% | 358 | 74.7% | 58.4% | [53.1%, 63.5%] | **+16.3** |
| 80–90% | 192 | 83.3% | 68.2% | [61.1%, 74.7%] | **+15.1** |

The 10–20% bucket is small (N=50), but even its *lower* CI bound (35.5%) is more
than double the 16.3% claim, and the 20–40% buckets (N=328 combined) are just as
inverted with much tighter intervals. The inversion is real.

**Mechanism, stated precisely.** The served std is *already conservative* — mean
served std ÷ realized RMSE is 1.17 (PTS), 1.21 (REB), 1.20 (AST), 1.34 (PRA).
The intervals are, if anything, too wide. Yet the probabilities are 10–16pp
overconfident in the 60–90% band. That combination is only possible one way: the
Platt calibrator is **sharpening a point prediction that carries no
generalizable directional signal**. Phase 2 was right that this is not a
dispersion problem. It is the calibrator manufacturing confidence out of noise.

---

## 5. H3 — is the pseudo-line benchmark adversarial? **REJECTED, decisively.**

This was the plausible benign explanation. It is wrong. Measured league-wide on
33,414 scored rows (2023-24 + 2024-25, all players with ≥25 games, ≥20 games of
history), `form_gap = (L5 mean − season-to-date median) / σ`:

| form_gap | PTS over-rate | REB | AST | PRA |
|---|---:|---:|---:|---:|
| < −1.0 | 29.1% | 26.6% | 23.8% | 25.2% |
| −1.0 … −0.5 | 37.0% | 35.6% | 33.3% | 36.3% |
| −0.5 … −0.2 | 43.4% | 43.7% | 39.8% | 43.1% |
| −0.2 … +0.2 | 48.9% | 48.8% | 49.0% | 48.5% |
| +0.2 … +0.5 | 53.9% | 54.3% | 58.6% | 55.5% |
| +0.5 … +1.0 | 60.5% | 61.7% | 63.8% | 61.5% |
| > +1.0 | **71.8%** | **71.1%** | **77.3%** | **74.1%** |

Monotone and steep, in every stat, on ~30k rows. A season-median line **rewards**
form-tracking. The same pattern holds on the 606 held-out rows themselves
(46.0% → 64.5% across form-gap bins).

The unconditional base rate is 51.3–53.4% over (pushes excluded) — right skew,
not 50%. That accounts for perhaps 1–3pp of the low-decile gap. It does not
account for 25–34pp.

Where do the model's low-probability median picks actually sit? Of the 171 rows
where the model says <30%:

- realized over-rate **50.9%**
- mean form gap **+0.058σ** — recent form is *above* the median, so the correct
  lean was mildly over
- mean model gap **−0.625σ** — the model leans hard under
- the model and the L5 signal **disagree on direction 52.0% of the time**

The model is not being punished by an adversarial line. It is taking a large
short position against a signal that points the other way.

---

## 6. H4 — feature signal is thin, and the extra features actively hurt. **SUPPORTED.**

Trained on the **exact same 60 training rows**, scored on the **exact same 606
served vectors**, changing only which columns the estimator may read:

MAE:

| Feature set | est | PTS | REB | AST | PRA |
|---|---|---:|---:|---:|---:|
| **PRODUCTION (81, ensemble + meta)** | | 6.517 | 2.546 | 1.885 | 7.637 |
| **T1 — `ROLL_10_<stat>` only (1 feature)** | ridge | **6.100** | **2.429** | **1.803** | **7.397** |
| T3 — + L5, L10 minutes | ridge | 6.176 | 2.476 | 1.823 | 7.512 |
| T5 — + opp def rating, is_home | ridge | 6.247 | 2.490 | 1.842 | 7.594 |
| T8 — + std, rest | ridge | 6.441 | 2.622 | 1.920 | 7.872 |
| FULL_81 | gbm | 6.901 | 2.773 | 2.034 | 8.345 |
| FULL_81 | ridge | 10.502 | 4.048 | 3.149 | 12.951 |

AUC at the median line:

| Feature set | PTS | REB | AST | PRA |
|---|---:|---:|---:|---:|
| PRODUCTION | 0.5115 | 0.5372 | 0.5628 | 0.5505 |
| **T1 (1 feature, ridge)** | **0.5520** | **0.5975** | **0.6117** | 0.5450 |
| FULL_81 (gbm) | 0.5174 | 0.5203 | 0.5639 | 0.5051 |

**A ridge regression on a single feature — the 10-game rolling mean — beats the
81-feature production ensemble on MAE for every stat and on AUC for three of
four.** Accuracy degrades monotonically as features are added. The 81-feature
ridge (p/n = 1.35) is catastrophic, which is the direct signature of the problem.

Importance is diffuse and points at noise. Across 132 (player, stat) pairs the
top feature carries a mean of **17.2%** of importance, the top 5 carry 51.3%, and
it takes a median of **14 features to reach 80%**, with ~22 features above 1%.
The highest mean-normalised importances:

- **PTS:** `GAMES_THIS_SEASON` (0.041), `FG3_RATE`, `FT_RATE`, `TRAVEL_MILES_NORM`, `PF_PER_MIN`, `ROLL_10_USG`
- **REB:** `FG3_TREND`, `GAMES_THIS_SEASON`, `ROLL_5_FG3_RATE`, `STD_10_REB`, `TRAVEL_MILES_NORM`
- **AST:** `FT_RATE`, `PF_PER_MIN`, `OPP_PACE_NORM`, `GAMES_THIS_SEASON`, `STD_10_AST`

For PTS, **no rolling mean of points appears in the top twelve.** A game counter
and a travel-distance normalisation outrank the player's own scoring level. With
60 rows and 81 columns the GBM is fitting the training noise, and the one column
that actually matters is diluted to nothing.

---

## 7. H6 (added) — is it just too little training data? **Partly, and it doesn't rescue the model.**

The harness trains on 60 single-season rows. Production pools up to three
seasons via `db.get_game_logs_multi_season` (`scripts/daily_best_picks.py:504`),
so the harness has been understating production's training volume. I built a
paired run: 2023-24 logs pulled from Supabase and prepended, split boundary
pinned to the same date, so the **held-out games are bit-identical** (verified:
2424 paired rows, actuals identical). Training rows go **60 → median 139**
(min 60, max 157).

| Stat | single-season | **multi-season** | L20 | best trivial |
|---|---:|---:|---:|---:|
| PTS | 6.517 | **6.335** | 6.114 | 6.065 |
| REB | 2.546 | **2.446** | 2.460 | 2.427 |
| AST | 1.885 | **1.818** | 1.775 | 1.775 |
| PRA | 7.637 | **7.531** | 7.444 | 7.267 |

Point accuracy improves 2.3–3.9%. **It still loses to the trivial baselines on
every stat.** And the probability ranking gets *worse*, not better:

| Stat | single AUC | **multi AUC** | L10 signal |
|---|---:|---:|---:|
| PTS | 0.5318 | **0.4927** | 0.5774 |
| REB | 0.5097 | 0.5191 | 0.5759 |
| AST | 0.5549 | **0.4486** | 0.6210 |
| PRA | 0.5508 | 0.5151 | 0.5770 |
| **ALL** | **0.5362** | **0.4932** | **0.5830** |

Pooled AUC of 0.493 is below a coin flip. The multi-season median-line deciles
are inverted just as badly (10–20% → 45.8% realized, gap −29.7). More data makes
the level estimate better and does nothing for direction, because there is no
direction to find. **Training volume is a real but second-order problem.**

---

## 8. H5 — the noise ceiling, and how much of the pseudo-line signal is fake

### 8a. The model is worse than a constant

| Stat | player σ | model RMSE | **RMSE / σ** | R² vs player's running mean |
|---|---:|---:|---:|---:|
| PTS | 7.128 | 8.305 | **1.165** | **−0.156** |
| REB | 2.871 | 3.235 | **1.127** | **−0.098** |
| AST | 2.208 | 2.541 | **1.151** | **−0.090** |
| PRA | 8.898 | 9.748 | **1.096** | **−0.079** |

### 8b. There is genuinely little to extract

League-wide, matched to the harness regime (≥60 prior games, ≥28 min/game, 200
player-seasons, 3669 rows/stat):

| Stat | median | mean | L10 | L20 | **oracle fwd mean** | **oracle minutes** |
|---|---:|---:|---:|---:|---:|---:|
| PTS | 5.879 | 5.852 | 5.956 | 5.884 | **4.946** | 5.379 |
| REB | 2.183 | 2.177 | 2.214 | 2.189 | **1.860** | 2.037 |
| AST | 1.760 | 1.772 | 1.784 | 1.760 | **1.480** | 1.723 |
| PRA | 7.364 | 7.309 | 7.269 | 7.265 | **6.138** | 6.188 |

`oracle fwd mean` knows the player's *actual* mean over all remaining games — an
upper bound on any level-only forecast. It buys **13–16%** over a rolling mean.
That is the entire headroom available to a better level estimate.

Serial signal beyond the level is near zero. Correlation of `actual − season
mean` with the mean of the previous k deviations, across 33,414 rows:

| Stat | lag 1 | prev 3 | prev 5 | prev 10 |
|---|---:|---:|---:|---:|
| PTS | 0.099 | 0.111 | 0.108 | 0.089 |
| REB | 0.094 | 0.117 | 0.112 | 0.092 |
| AST | 0.088 | 0.111 | 0.114 | 0.100 |
| PRA | 0.141 | 0.163 | 0.159 | 0.137 |

r ≈ 0.09–0.16 — real, small, and already captured by any rolling mean.

### 8c. Minutes: the one large lever, and it is not free

Knowing a player's actual minutes and applying their L10 per-minute rate cuts
MAE by **13.6% (PTS) / 10.0% (REB) / 5.8% (AST) / 20.2% (PRA)**. But minutes
themselves are only weakly predictable from the box score: L10 minutes predict
actual minutes with MAE 4.70 against a minutes sd of 7.90, and substituting the
L10-minutes forecast for the oracle recovers **exactly zero** of the gain
(`rate × L10min` MAE 5.439 vs plain L10 5.432 for PTS). **The minutes lever
requires information you do not currently ingest** — injury reports, rotation
news, blowout/rest risk.

### 8d. Almost all the pseudo-line "signal" is line staleness

Same rows, three synthetic line definitions:

| Stat | line | over% | AUC(L5) | AUC(L10) | AUC(season mean) |
|---|---|---:|---:|---:|---:|
| PTS | season median | 52.6% | 0.592 | 0.592 | 0.568 |
| PTS | **L10 mean, x.5** | 47.2% | **0.527** | **0.519** | 0.583 |
| REB | season median | 52.1% | 0.595 | 0.602 | 0.594 |
| REB | **L10 mean, x.5** | 46.1% | **0.539** | **0.561** | 0.600 |
| AST | season median | 53.5% | 0.617 | 0.623 | 0.606 |
| AST | **L10 mean, x.5** | 44.7% | **0.549** | **0.565** | 0.598 |
| PRA | season median | 53.2% | 0.614 | 0.611 | 0.568 |
| PRA | **L10 mean, x.5** | 48.1% | **0.533** | **0.510** | 0.572 |

Move the line from a season median to a merely *L10-aware* line and the
recent-form signal drops from AUC ~0.60 to ~0.51–0.56. A sportsbook line is far
more informed than an L10 mean.

Correspondingly, the staking simulation is an artifact of the line's
construction, in both directions — against a season-median line, form-tracking
wins; against an L10 line, mean-reversion wins (`season mean − line` returns
+5.3% to +11.2% ROI). Neither result means anything about a market.

Staking at −110 (breakeven 52.38%) on the 2187 median-line samples:

| Strategy | N | win rate | "ROI" |
|---|---:|---:|---:|
| **production model** | 2187 | **53.32%** | +1.78% |
| multi-season model | 2187 | 54.09% | +3.27% |
| **always take the over** | 2187 | **55.14%** | +5.27% |
| **L10 rolling mean** | 2187 | **57.43%** | **+9.64%** |
| pooled cross-player ridge | 2187 | 56.56% | +7.98% |

Every one of these numbers is measured against a strawman. The only meaningful
comparison in the table is the *ordering*: the production model finishes last.

---

## 9. What would have to be true to stake money — and how far this is

To bet props profitably at −110 you need a sustained **>52.4%** win rate against
**closing sportsbook lines**, net of vig. Concretely:

1. **A real line dataset.** `manual_lines` is empty. Without historical closing
   lines there is no measurement that distinguishes edge from line staleness.
   Section 8d shows the two are almost entirely confounded in the current
   evidence base. *Status: absent. This is a hard precondition, not an
   improvement.*
2. **Point predictions that beat a rolling mean.** *Status: they lose to it on
   all four stats, on 34–40 of 44 players.*
3. **Directional resolution — AUC meaningfully >0.50 against a line the model
   did not construct.** *Status: 0.536 against a generous strawman line, below
   both a 1-feature rolling mean (0.583) and the always-over base rate.*
4. **Probabilities that mean what they say.** *Status: 60–80% buckets are
   10–16pp overconfident; 10–40% buckets are 22–34pp inverted.*
5. **Enough edge to survive vig.** Even the *oracle* that knows each player's
   true forward level only improves MAE 13–16% over a rolling mean, and per-game
   residuals beyond the level have r ≈ 0.09–0.16. The achievable headroom from
   box-score data alone is small.

The gap is not incremental. On criterion 2 the model is *behind a one-line
baseline*, and criterion 1 means we cannot currently tell whether closing that
gap would be worth anything.

---

## 10. Recommended next steps, ranked by expected value

**1. Acquire real closing lines. (Precondition — highest value, nothing else is
measurable without it.)**
Start logging book lines daily into `manual_lines` now, even before any modelling
change; a season of closing lines is the asset that makes every later evaluation
real. *EV: not an accuracy improvement, but every other number in this report and
in Phases 0–2 is uninterpretable without it. Cost: low (a daily scrape). Do this
first.*

**2. Replace per-player fitting with one pooled cross-player model.**
Measured: a ridge on 9 causal recency features, trained on **2023-24 league data
only** (no per-player fitting, no 2024-25 data), scored on the same 606 held-out
games — PTS 6.004 / REB 2.430 / AST 1.792 / PRA 7.252, versus the production
model's 6.517 / 2.546 / 1.885 / 7.637. **7.9% better on PTS**, better on all four,
and AUC 0.574 / 0.579 / 0.628 / 0.563 versus 0.532 / 0.510 / 0.555 / 0.551.
It turns n=60 into n≈33,000. *EV: high and already demonstrated. Cost: moderate —
it is an architectural change to the serving path, but the model itself is
trivial.*

**3. Cut the feature set from 81 to under 10.**
Measured: a 1-feature ridge beats the 81-feature ensemble on every stat. Every
feature added past the rolling mean made accuracy worse. p/n = 1.35 is
indefensible on 60 rows and still bad on 139. *EV: high, near-zero cost, and it
composes with (2). This is the single cheapest improvement available.*

**4. Stop the calibrator from manufacturing confidence; shrink toward the base
rate.**
The served std is already 1.17–1.34× the realized RMSE, so the intervals are
fine. The overconfidence comes from Platt sharpening a point prediction with
AUC ≈ 0.50. Until (2)/(3) produce real resolution, probabilities should be
shrunk hard toward the 51–53% base rate. *EV: medium — it makes the product
honest and mechanically fixes Brier and the reliability gaps, but it creates no
profitability. It is a truthfulness fix, not an edge fix.*

**5. Build a real minutes projection from off-box-score data.**
This is the only large lever the data identifies: perfect minutes knowledge is
worth 13.6% (PTS) to 20.2% (PRA) of MAE. But rolling-mean minutes capture none of
it, so the gain requires ingesting injury reports, rotation news, and
blowout/rest signals. *EV: highest ceiling of any modelling change, but high cost
and genuinely uncertain — and it should come after (1)–(3), because without real
lines you cannot tell whether the 20% is worth anything.*

**6. Stop investing in the uncertainty and calibration path.**
Phases 0, 1 and 2 each fixed a real, well-diagnosed bug — a mismeasured harness,
a stale serve path, a σ-cancelling calibrator — and none moved the reliability
gaps, exactly as this diagnosis predicts, because all three are downstream of a
point prediction with no resolution. `CONSUME_LEARNED_INTERVAL_DIVISOR`, CQR
tuning and further Platt work should be considered closed until (2)/(3) land.
*EV: negative — further work here consumes effort and produces reports that
cannot improve.*

**7. Retire the pseudo-line calibration section from routine reporting, or
relabel it.**
Section 8d shows the pseudo-line ROI is a pure function of how the pseudo-line is
constructed. Reporting Brier and reliability against it invites exactly the
misreading these three phases have been chasing. *EV: low effort, prevents future
wasted phases.*

---

## 11. Honest summary of limitations

- 44 players, 606 held-out games, a 44-day late-season window. Per-stat CIs are
  wide; only the pooled comparisons are decisive. The direction of every
  comparison is consistent, which is what carries the verdict, not any single
  interval.
- The 10–20% median-line bucket has N=50. The 20–40% buckets (N=328) carry the
  inversion finding.
- The multi-season run pulls 2023-24 logs from Supabase, which include playoff
  games (median 89 games per player); production's pooled path has the same
  property, so this is faithful rather than a defect.
- The multi-season training frame applies one point-in-time 2024-25 team-context
  snapshot to the 2023-24 rows, which is exactly what production's
  `create_features(pooled_log, team_stats=...)` call does. Faithful, but it means
  the 2023-24 training rows carry approximate opponent context.
- All probability numbers are against synthetic pseudo-lines. See §8d.
