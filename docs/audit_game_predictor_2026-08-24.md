# ELO Game Predictor Audit — 2026-08-24

**Scope:** `game_predictor.py`, the `game_predictions` table, and the write/grade
path around them. Never covered by the 2026-08-19 → 08-23 prop-model
investigation. Read-only audit; no production code, database row, or cron job
was modified.

**Re-runnable script:** `scripts/audit_game_predictor.py`
(`NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py`).
Every number below is its output.

---

## Verdict

**Gate the UI behind `VITE_ENABLE_PREDICTIONS` — recommendation (b) — but not
for the reason the audit was commissioned to find.**

The accuracy question is *unresolvable at this sample size*: the model went
**24/38 (63.2%, 95% Wilson [47.3%, 76.6%])** against always-picking-the-home-team
at **21/38 (55.3%, [39.7%, 69.9%])**. That is a three-game difference, exact
McNemar **p = 0.629**. This sample cannot distinguish the model from a one-line
baseline, and no amount of re-analysis will change that.

What *is* settled, and settled without needing a large sample, is the number
the UI actually displays:

> **The model's Brier score is 0.2542. Predicting a constant 55.3% for every
> game scores 0.2472. Predicting a flat coin-flip 50% scores 0.2500.**
> The displayed win probability is worse than a constant.

The confidence figure rendered on `GamesPage.tsx` is therefore not merely
uninformative — it is worse than showing no number at all. That, plus four
independently verified serve-path defects (below), is sufficient to gate the
surface without waiting for the sample to grow.

**It also cannot grow.** `db.py:save_game_prediction` hard-deletes every row
beyond the newest 40 on every insert. See "The sample is capped by design".

---

## 1. What the model is

| Property | Value |
|---|---|
| Predicted quantity | P(home team wins), a single binary outcome per game |
| Features built | **112** (`_build_historical_features`) |
| Features kept | **71** (RF importance, 95% cumulative, floor of 30) |
| Architecture | Stacking: RandomForest + HistGradientBoosting → LogisticRegression meta-learner |
| Calibration | `IsotonicRegression(y_min=0.15, y_max=0.85)` on TimeSeriesSplit OOF |
| Training data | 3 seasons of BDL games, `retrain_model` → `get_recent_seasons(3)` |
| Artifact | `models/games/game_predictor.pkl`, `trained_at` **2026-03-19** |
| Elo | Dual-track (K=20 fast, K=10 slow), 100-point home advantage |

XGBoost and LightGBM were **not available** in the environment that produced the
saved artifact — `base_models_` contains only `['rf', 'histgb']`. The module
docstring advertises "XGBoost + LightGBM + RF + HistGB".

### p/n is not the problem here

The prop model's root cause was **p/n = 1.35** (81 features, 60 rows). That
pathology is **absent** from the game predictor.

Training pools three seasons of games. A full season is 1,322 final games
(measured: 1,237 regular + 85 postseason for 2025-26), and the only rows dropped
are those where a team has fewer than 10 prior games — which bites once, at the
very start of the pooled window. Training n is therefore on the order of
**3,300–3,900 matchups** against 71 retained features:

**p/n ≈ 0.02** — roughly seventy times healthier than the prop model.

Caveat, stated plainly: this is derived from the season structure, not measured.
**The pkl does not record its own training row count.** It stores `trained_at`
and `graded_count_at_train` but not `n_train`, so the actual figure cannot be
recovered after the fact. The conclusion is insensitive to the estimate — even
if only one season had loaded, p/n ≈ 0.06 — but recording `n_train` at save time
would close the gap for a shell of a line of code.

**Whatever is wrong with this model, it is not the prop model's disease.**

---

## 2. The 40 rows

All 40 rows are **postseason games**, 2026-04-20 → 2026-05-04, verified against
BDL's `postseason` flag (40/40). 38 graded, 2 ungraded.

`correct` is **INTEGER 0/1**, the same convention as `picks.won` — checked, not
assumed.

**Grading integrity: clean.** Recomputing every outcome independently from BDL
final scores and comparing against the stored `correct` column gives
**0 mismatches in 38**. The grading path in `db.py:auto_grade_game_predictions`
reads only the final score of the game being graded and does not touch the
prediction, so it introduces no leakage.

### These are 8 series, not 38 independent trials

| Series | Games | Model |
|---|---:|---:|
| ATL-NYK | 4 | 3/4 |
| BOS-PHI | 6 | 2/6 |
| CLE-TOR | 5 | 4/5 |
| DEN-MIN | 5 | 3/5 |
| DET-ORL | 6 | 4/6 |
| HOU-LAL | 5 | 2/5 |
| OKC-PHX | 3 | 3/3 |
| POR-SAS | 4 | 3/4 |

Games inside a playoff series share both rosters, both coaching staffs and one
matchup dynamic. The effective sample is far nearer **8** than 38. Every
confidence interval below that treats games as independent is therefore
*optimistically narrow*; the series-clustered bootstrap is the honest one.

This also means the audit measures the model **on playoff basketball only**.
Nothing here speaks to its regular-season behaviour, which is what it will
mostly be asked to do.

---

## 3. Model vs baselines — the heart of it

All 38 graded games. Every baseline uses only information available before
tip-off; see §4 for how that is enforced.

| Method | Record | Rate | 95% Wilson |
|---|---:|---:|---|
| **Model (71-feature ensemble)** | 24/38 | **63.2%** | [47.3%, 76.6%] |
| Plain Elo, rebuilt as-of, fast track only | 23/38 | 60.5% | [44.7%, 74.4%] |
| Always pick the home team | 21/38 | 55.3% | [39.7%, 69.9%] |
| Better regular-season win pct | 21/38 | 55.3% | [39.7%, 69.9%] |
| Better record as of game date | 21/38 | 55.3% | [39.7%, 69.9%] |
| Coinflip | — | 50.0% | [34.8%, 65.2%] |

The actual home-win rate **on these games** is **21/38 = 55.3%** — measured, not
the assumed 55–58%. Playoff home-court advantage was unremarkable in this sample.

### Paired comparisons

| Comparison | Model right / base wrong | Model wrong / base right | Exact McNemar p | Diff, series-clustered 95% CI |
|---|---:|---:|---:|---|
| vs always-home | 10 | 7 | **0.629** | +7.9 pts [−9.1, +29.0] |
| vs better regular-season record | 6 | 3 | 0.508 | +7.9 pts [−5.4, +22.9] |
| vs better as-of record | 6 | 3 | 0.508 | +7.9 pts [−5.4, +22.9] |
| vs plain as-of Elo | 5 | 4 | **1.000** | +2.6 pts [+0.0, +8.1] |

**What this sample can resolve: nothing.** Every interval spans zero or nearly
so. The model and always-home disagree on only 17 of 38 games and split them
10–7 — one game short of a coin.

**What is worth stating anyway:** the 71-feature stacking ensemble beats a
plain, single-track, ~15-line Elo by **one game in 38** (p = 1.000), and has a
*lower* AUC than it (0.5756 vs **0.5798**). The entire apparatus — 112
engineered features, RF importance selection, a two-model stack, a logistic
meta-learner, isotonic calibration — buys nothing measurable over the Elo
number it already contains as its own top-ranked feature. This is the same
shape as the prop model's finding that a ridge on one feature beat all 81,
though here it is nowhere near statistically established.

### Market comparison: not possible

There is **no market line for these games**, and I did not substitute one.
Verified: `manual_lines` has **0 rows**; `picks.closing_line` is NULL on
**every** row. OddsAPI quota is exhausted and BDL odds have been gone since the
April 2026 tier downgrade. Closing-line value — the only fast, low-variance
measure of whether a model beats a book — is unavailable for this sample and
permanently unrecoverable for it.

---

## 4. Lookahead: how it was ruled out

**In the audit's own baselines.** Every baseline input passes through exactly
one function, `_games_before(games, game_date)`, which returns games with
`completed_date < game_date` — strictly less-than, never `<=`. NBA teams play at
most once per day, so a strict date cutoff cannot admit the game being predicted
or any later game; this is `.shift(1)` semantics at day granularity. The cutoff
lives in one auditable place by design. `--verify-cutoff` asserts it directly
and passes on all 40 rows:

```
NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py --verify-cutoff
  OK: 40 predictions checked; every baseline input strictly precedes its game date.
```

**In the production serve path.** I went looking for the analog of the prop
model's `prediction_row()` bug, where a *derived* column (PRA) survived the
strip and leaked the outcome. **I did not find one.**

- Predictions are written at 13:00–13:01 UTC (09:00 ET) on the game date;
  the games tip that evening.
- `get_team_game_log` and `_get_historical_games` both skip any game whose
  `status` is not `'final'`, so the game being predicted cannot enter its own
  feature vector.
- `_build_training_data` slices with `GAME_DATE < game_date` and updates Elo
  *after* building each row.
- The `CacheManager` layer can only serve **stale** data, never future data —
  the error direction is safe.

**One real leak, but only into a printed diagnostic.** `train_model` calls
`_select_features(X.values, y, ...)` — fitting a RandomForest on the full label
vector — and `self.scaler.fit_transform` on all rows, *before* running
`TimeSeriesSplit` cross-validation on the already-selected, already-scaled
matrix. The "Cross-validation accuracy" it prints is therefore contaminated by
selection-on-all-data and is optimistically biased. It does not affect any
served prediction. **Do not trust that printed number.**

---

## 5. Serve-path defects — verified, and independent of sample size

These are code-path facts. They do not need n=40 to establish.

### 5a. Four features are hard-coded constants at serve time

`build_game_features` calls `_build_historical_features(..., all_games_df=None)`.
With `all_games_df=None`, `_compute_sos` is skipped and its defaults are used.
`feature_names` is stored in **descending RF importance order**
(`_select_features` sorts by `argsort(importances)[::-1]`), so the index is the
importance rank:

| Rank of 71 | Feature | Value on every served prediction |
|---:|---|---|
| **8** | `sos_diff` | 0.0 |
| 14 | `elo_x_sos` | 0.0 |
| 17 | `home_sos` | 0.5 |
| 34 | `away_sos` | 0.5 |

These features **vary in training and are constant at serve**. The 8th most
important feature of 71 is a hard zero in production. This is precisely the
failure mode Phase 0 of the prop investigation found at `nba_evaluator.py:3266`
— silent defaulting of a declared feature — reproduced here in a different file.

`predict_game` completes the pattern: `[features.get(f, 0) for f in
self.feature_names]` silently substitutes 0 for anything missing.

### 5b. The Elo snapshot is 32–46 days stale

`self.elo_tracker` is restored from the pkl. `compute_from_games` — the only
thing that advances it — is called **exclusively inside `train_model`**. Nothing
in the daily serve path updates it. The artifact was trained 2026-03-19:

| Prediction date | Days stale | League games the served Elo cannot see | Per team |
|---|---:|---:|---:|
| 2026-04-20 | 32 | 208 | ~13.9 |
| 2026-04-27 | 39 | 230 | ~15.3 |
| 2026-05-04 | 46 | 248 | ~16.5 |

`elo_diff` is the **#1 ranked feature of 71**; `elo_expected` is #3, `elo_x_form`
#4, `home_elo` #6, `away_elo` #18, `elo_x_sos` #14. Six of the top eighteen
features derive from a snapshot that missed the last month of the regular season
and every playoff game played to date. The audit's own as-of Elo baseline, which
*is* current, scores 60.5% — within one game of the full model.

`predict_all_sync` never calls `should_retrain`, so the artifact is frozen
indefinitely under cron operation.

### 5c. `get_team_stats()` returns nothing — and the UI shows the result

Every one of the 40 stored `extended_data` payloads contains:

```json
"record": "0-0", "off_rating": 110, "def_rating": 110,
"net_rating": 0, "pace": 100
```

Those are `predict_game`'s literal fallbacks. `get_team_stats` calls BDL
`get_team_season_averages`, which the April 2026 tier downgrade removed, so
`team_stats` is empty and `home_stats = team_stats.get(home_team, {})` is `{}`.

Two consequences:

1. **Benign for the model.** `build_game_features` guards the rating override
   with `if home_stats and away_stats:` — `{}` is falsy, so the block is skipped
   and the ratings stay at their game-log-derived values. The 14 `*_api_*` /
   standings features it injects unguarded do collapse to defaults, but they do
   not exist in training and are discarded by the `feature_names` alignment.
2. **Not benign for users.** `GamesPage.tsx` renders the `matchup` block. Every
   game has shown both teams at **0-0** with identical 110/110/0/100 ratings.

### 5d. Train/serve definition skew on five more features

Training builds `home_games` from the pooled 3-season frame
(`games_df[TEAM == x][GAME_DATE < game_date]`), so `win_pct(home_games)` is a
**multi-season cumulative** rate over hundreds of games. At serve,
`get_team_game_log(team_id)` fetches `season or get_current_season()` — a
**single season**. The same feature name carries a different quantity in the two
regimes:

| Rank of 71 | Feature |
|---:|---|
| 7 | `win_pct_diff` |
| 12 | `home_win_pct` |
| 22 | `away_win_pct` |
| 44 | `h2h_avg_margin` |
| 70 | `h2h_home_wins` |

A 3-season cumulative win pct regresses hard toward 0.500; a season-to-date one
does not. The model learned coefficients on the former and is served the latter.

### 5e. What is correct

Worth recording, because these were live hypotheses that the evidence rejected:

- **Feature ordering is right.** `X_selected = X.values[:, selected_idx]` and
  `selected_names[j] = feature_names[selected_idx[j]]`, so column *j* of the
  scaler matches `self.feature_names[j]`, which is what `predict_game` indexes.
  No misalignment.
- **Injury features are inert, not skewed.** They are constant 0 in training, so
  `_select_features` dropped all seven. The live injury values computed at serve
  are discarded. Wasteful, not wrong.
- **Grading is correct** — 0/38 mismatches, no leakage.

---

## 6. Calibration: the probabilities are worse than a constant

| Forecast | Brier |
|---|---:|
| Constant 0.553 (the base rate) | **0.2472** |
| Constant 0.500 | 0.2500 |
| Plain as-of Elo | 0.2534 |
| **Model** | **0.2542** |

The model is last. AUC is **0.5756** (plain Elo: 0.5798).

### The probabilities live on a 12-value lattice

Across 38 games the model emitted **12 distinct** values:

```
0.201  0.303  0.364  0.471  0.521  0.591
0.603  0.606  0.662  0.689  0.756  0.778
```

`IsotonicRegression` is a step function; the fitted calibrator has only 20
distinct output levels, clipped to [0.15, 0.85]. Distinct matchups collapse onto
identical probabilities — 0.606 was emitted for SAS-POR, DET-ORL, HOU-LAL and
CLE-TOR alike. This is the same shape as the prop model's "fixed 9-point
lattice" finding, arrived at by a different mechanism.

### Reliability is non-monotone

| Bucket | n | Mean predicted | Realised | Gap | 95% Wilson |
|---|---:|---:|---:|---:|---|
| [0.00, 0.35) | 8 | 27.7% | 25.0% | −2.7 | [7.1%, 59.1%] |
| [0.35, 0.45) | 4 | 36.4% | 75.0% | **+38.6** | [30.1%, 95.4%] |
| [0.45, 0.55) | 10 | 49.6% | 60.0% | +10.4 | [31.3%, 83.2%] |
| [0.55, 0.65) | 10 | 60.4% | 80.0% | +19.6 | [49.0%, 94.3%] |
| [0.65, 1.01) | 6 | 71.0% | **33.3%** | **−37.7** | [9.7%, 70.0%] |

The most confident bucket is the least accurate.

### Confidence sorts outcomes backwards

| Split | Record | Rate | 95% Wilson |
|---|---:|---:|---|
| Confidence < 62% | 15/20 | 75.0% | [53.1%, 88.8%] |
| Confidence ≥ 62% | 9/18 | 50.0% | [29.0%, 71.0%] |

Fisher exact two-sided **p = 0.179** — **not significant**, and I am not
claiming the inversion is real. At n=38 it cannot be. The honest statement is
narrower and still damaging: *the model's confidence shows no evidence of
sorting outcomes in the correct direction*, which is the same conclusion the
prop investigation reached about claimed edge (38.5% vs 37.3%).

By the model's own `bet_quality` tiers: `STRONG_BET` (edge ≥ 0.20) covers **27
of 38 games** and goes 16/27 = 59.3% [40.7%, 75.5%]; `NO_BET` goes 4/5 = 80.0%.
A model that labels 71% of playoff games "STRONG_BET" is not discriminating.

---

## 7. The sample is capped by design — and the pipeline is dead

### 7a. History is deleted on every insert

`db.py:save_game_prediction` ends with:

```sql
DELETE FROM game_predictions
WHERE id NOT IN (SELECT id FROM game_predictions ORDER BY timestamp DESC LIMIT 40)
```

Every insert destroys everything past the newest 40 rows. This is not a
coincidence of the table being young — **40 is a ceiling**.

Direct evidence that rows have already been destroyed: 42 games were played
2026-04-20 → 05-04, but only 40 rows survive, and the two absent ones
(2026-04-20 ATL@NYK and TOR@CLE) are the **oldest** two. The surviving ids run
**406 → 445 with no gaps** (verified contiguous), which is exactly 40 rows.
Predictions for those two games were therefore written as ids **404 and 405**
and deleted when id 445 pushed the table over the cap. The table did not start
at 406; it was trimmed to start there.

At playoff volume (~3 games/day) the table holds ~13 days. At regular-season
volume (8–12 games/day) it holds **3–4 days**. The nightly grader has just
enough runway, but no historical sample can ever accumulate. `GET
/api/games/history` even caps `limit` at `le=40` to match.

**Any future re-run of this audit will still be an n≤40 audit** until the cap is
removed. That is the single highest-leverage fix on this list, and it is one
`DELETE` statement.

### 7b. Both cron jobs have produced nothing since 2026-05-04

- The 2025-26 playoffs ran to **2026-06-13**. **35 games were played after the
  last stored prediction and zero predictions exist for any of them.**
- The two 2026-05-04 rows are **still ungraded** (`correct IS NULL`) although
  both games are final in BDL and trivially gradeable (SAS 102–104 MIN;
  NYK 137–98 PHI).

Job 17 (`daily-game-predictions`) and job 19 (`nightly-auto-grade-games`) are
both marked ACTIVE, yet neither has had an effect in 16 weeks. **`pg_cron` +
`pg_net` fire an HTTP POST and never inspect the response** — an ACTIVE job is
evidence that a request was *sent*, not that anything succeeded. The most likely
cause is the Railway backend being unreachable from 2026-05-05, but the point
stands regardless: **the job status field is not a health check.**

### 7c. Smaller defects

- **`model_version` is wrong in every row.** `predict_game` does not return
  `model_version`, so `save_game_prediction` falls through to its `'v1.0'`
  default. The pkl says `v2.0`. All 40 rows read `v1.0`. You cannot tell from
  the table which model produced a prediction.
- **The dual-track Elo is dead code.** `get_blended_rating`, `get_blended_diff`
  and `get_rating_slow` are **never called** from any feature-building path —
  `_build_historical_features` uses `get_diff` / `get_rating` / `get_expected`,
  all fast-track only. The slow track is computed on every update, persisted in
  the pkl, and never read. The class docstring says the blend "shift[s] to 50/50
  in playoffs where long-term quality matters more"; all 40 predictions are
  playoff games and none of them used it.
- **`EloTracker.copy()` drops `ratings_slow`.** It rebuilds only `ratings`.
  Currently harmless — `_build_training_data` copies a freshly-initialised
  tracker — but it is a live trap for anyone who later copies a warm tracker.

---

## 8. What I could not determine

1. **Whether the model actually beats always-picking-home.** n=38 across 8
   series. p = 0.629. Settling a ~5-point edge at 95% confidence needs on the
   order of **n ≈ 1,000 independent games**; the current pipeline caps the table
   at 40 and has been producing zero.
2. **Regular-season behaviour.** 40/40 rows are playoff games. Playoff
   basketball is a different distribution — fixed matchups, compressed rotations,
   no rest-day variance of the regular-season kind. Nothing here generalises.
3. **Whether the model beats the market.** No line exists for these games.
   `manual_lines` is empty, every `picks.closing_line` is NULL. Unrecoverable
   for this sample.
4. **The magnitude of the serve-path defects.** That `sos_diff` (rank 8) is a
   constant 0 at serve and the Elo is 46 days stale are *verified facts*; how
   many of the 14 losses they caused is **not measured**. Quantifying it needs a
   backtest harness that replays the true serve path — the same instrument Phase
   0 had to build for the prop model, and which does not exist for games.
5. **The exact training row count.** Not recorded in the pkl and not recoverable
   without re-running training. The p/n ≈ 0.02 conclusion is robust to the
   estimate; the precise number is not known.

---

## 9. Recommendation

**(b) Gate the UI behind `VITE_ENABLE_PREDICTIONS`.**

`frontend/src/shared/lib/flags.ts` already defines `PREDICTIONS_ENABLED`, and
`GamesPage.tsx` currently contains **no reference to it** — the game predictor
is the one model surface still ungated. Wiring it there is consistent with what
that flag was created to do.

Justification, ordered by how much it depends on the thin sample:

1. **Independent of sample size.** The served feature vector is provably
   degraded: 4 of 71 features are constants including rank #8, the #1 feature is
   a 46-day-old snapshot, and 5 more features carry a different definition than
   they did in training. A prediction built from that vector should not be
   presented as authoritative regardless of how it scored on 38 playoff games.
2. **Nearly independent of sample size.** The UI has been displaying **0-0
   records and identical 110/110/0/100 ratings for both teams on every game**.
   That is a visible data-quality failure on the same page.
3. **Sample-dependent but directionally clear.** Brier 0.2542 against 0.2472 for
   a constant. The specific number the UI emphasises — `confidence`, rendered
   with a green/amber traffic light at 65% and 55% thresholds — is the weakest
   thing the model produces, and its top-bucket reliability gap is −37.7 points.

**Deliberately not recommending (c) "disable pending a rebuild."** The accuracy
case for that does not exist: 63.2% vs 55.3% at p = 0.629 does not establish the
model is bad, only that this sample cannot tell. Gating the *presentation* while
leaving the pipeline intact is the proportionate response.

### Prerequisites before the accuracy question can be reopened — this is the (d) part

Ordered by leverage per unit effort:

1. **Remove the 40-row cap** in `db.py:save_game_prediction`. One `DELETE`
   statement. Until this is gone the sample cannot grow and this audit cannot be
   improved by waiting. *Everything else on this list is worthless without it.*
2. **Verify the two cron jobs actually execute.** 35 unpredicted games and 2
   ungraded rows say they have not since 2026-05-04. Have the endpoints log a
   heartbeat; `pg_cron`'s ACTIVE flag is not a health check.
3. **Fix the SOS default** — pass a real `all_games_df` into
   `build_game_features`, or drop the four SOS features from the model. Either
   is defensible; silently serving 0.5 is not.
4. **Refresh Elo at serve time**, or retrain on a schedule. Feature #1 should
   not be a month-and-a-half old.
5. **Set `model_version` from the pkl** on write, so a future audit can tell
   which model produced which row.
6. **Then re-run `scripts/audit_game_predictor.py`** once ≥ 400 regular-season
   games have accumulated. At n=400 the Wilson half-width on a 60% rate is about
   ±4.8 points — enough to separate the model from a 55% always-home baseline.
   At n=38 it is ±15.

### Explicitly do not

- **Do not tune the calibrator.** The prop investigation spent three phases on
  calibration, fixed three genuine bugs, and moved nothing. The isotonic
  step-function lattice here is a symptom, not the disease.
- **Do not add features.** 112 built, 71 kept, and the whole stack beats a
  ~15-line as-of Elo by one game in 38 with a *lower* AUC. If anything, the
  cheap experiment worth running is the opposite: serve the plain as-of Elo
  directly and see whether anything is lost.

---

## Appendix — reproduction

```bash
NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py                 # full report
NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py --verify-cutoff # lookahead assertions
NBA_EVAL_DISABLE_TF=1 python3 scripts/audit_game_predictor.py --refresh       # re-fetch BDL
```

The BDL season fetch takes ~2 minutes and is cached to
`cache/audit_game_predictor_games.json` (gitignored). The script reads through
`db.py` with `load_dotenv(override=True)` — without it psycopg2 reports a
misleading `password authentication failed for user postgres`.

Test suite untouched; baseline remains 449 passed / 20 failed / 3 skipped.
