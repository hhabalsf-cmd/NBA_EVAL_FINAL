# Rebuilt NBA player-prop engine

The new `forecasting/` engine improves held-out PTS, REB, AST and PRA forecasts over strong validation-selected baselines. It is implemented, fitted, tested, and connected to the app's **Forecasts** page at `/forecasts` and the authenticated `POST /api/forecasts/player` endpoint. Changes and model files are local; nothing has been deployed.

The improvement is measurable but modest: roughly **1.2–1.5% lower mean absolute error**. This establishes a better statistical forecast on the evaluated data, not a demonstrated profitable betting strategy. Historical offered prices and pregame injury/lineup snapshots were not available, so realized betting ROI was not measured.

## What changed in the prediction engine

The old per-player model fits many features to comparatively few games. The replacement pools observations across players and learns a regularized correction to a player's recent level. The 50 inputs summarize completed-game production, minutes, per-minute rates, rest, season opening and team changes. One shared feature function builds historical training rows and live forecast inputs. Target-game minutes, points, starter status and other results never enter those inputs.

Candidates included simple averages, exponential averages, a six-feature pooled ridge baseline, a richer regularized model, histogram gradient boosting, and predicted minutes multiplied by predicted production rates. **The richer regularized model won validation for all four stats.** The separately modeled minutes/rate approach and boosting did not win and were not promoted merely for being more complex.

The uncertainty layer uses standardized residuals from a strictly later calibration period. It produces nonnegative integer outcome distributions, central 80% ranges, and distinct over/under/push probabilities. Exact-price offer evaluation computes `P(win) × (decimal odds − 1) − P(loss)` per unit risked. It validates event/player/stat identity, quote freshness, timezone-aware timestamps and pregame status. A high point-estimate gap alone never becomes a betting recommendation.

Forecasts are conditional on participation. An out player is rejected; questionable or unknown availability is identified explicitly. The engine does not invent injury effects or apply the legacy pipeline's unvalidated percentage adjustments. Fewer than ten historical appearances results in abstention, so rookies are not covered until enough history exists.

## Research and experimental design

The [protocol](PREDICTOR_REBUILD_PROTOCOL.md) was recorded before selection and final testing. Research informed hypotheses and validation methods:

- [UBC's NBA minutes prediction work](https://github.com/UBC-MDS-2019-20/NBA-Minutes-Predictor) motivated the minutes/rate candidate. Its reported performance was not treated as evidence for our implementation.
- [Scikit-learn's calibration documentation](https://scikit-learn.org/1.6/modules/calibration.html) informed the separation of model fitting and calibration.
- [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222) motivated evaluating later-period residual uncertainty. This implementation uses empirical standardized residuals, not the paper's full CQR algorithm, and makes no exchangeability guarantee for drifting NBA data.
- [Histogram gradient boosting documentation](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) informed the bounded nonlinear candidate.
- [The Odds API's historical-data specification](https://the-odds-api.com/historical-odds-data/) informed the distinction between game outcomes and timestamped executable offers.

The public dataset comes from [llimllib/nba_data](https://github.com/llimllib/nba_data), pinned to revision `3e809e9a04c4015de49dbdb86ac00e5a2fd2d7c9`. ESPN Analytics player box scores were joined to NBA game-log dates and checked against team point totals. The initial older per-season player files were incomplete and were not used as the training source. The final dataset contains **130,421 appearances by 1,029 players**, from October 19, 2021 through April 12, 2026. It excludes non-regular-season events, nonparticipants and 27 games with incomplete/inconsistent team totals. Zero rows remained unmatched to a schedule date. After requiring ten prior appearances, 121,055 rows were eligible.

An additional source check against the archived NBA player box scores matched 52,777 appearances in the latest two seasons. PTS/REB/AST agreement was at least 99.94% in each season/stat combination. Remaining discrepancies are a limitation of archived source/correction timing, not silently altered test outcomes. Public snapshots are not an as-of archive of every later statistical correction.

The chronological sequence was:

| Stage | Dates / rows | Purpose |
|---|---|---|
| Initial fitting | 2021–22 and 2022–23; 45,186 rows | Fit candidate models |
| Model selection | 2023–24; 25,063 rows | Choose a model and comparison baseline per stat |
| Frozen evaluation model fitting | Through April 14, 2024; 70,249 rows | Refit the selected specifications |
| Frozen evaluation calibration | October–December 2024; 9,783 rows | Fit residual distributions for the exact frozen models |
| Final held-out evaluation | January 2025 onward; 41,023 rows across 261 dates | Score without retuning against these outcomes |

Player histories update causally with completed games during evaluation; model coefficients and residual distributions remain fixed. EWMA10 was included in the final candidate comparison before scoring the holdout. Baselines were selected on validation, not chosen after inspecting which baseline looked easiest to beat on the test set.

The six-feature pooled ridge comparison uses the same bounded-history contract as the new engine. It is a recreated baseline specification, not a claim to have rerun the previous deployment artifact. The old published 40–66 betting record and previous 44-player scorecard use different samples and are not directly compared to these MAEs.

## Held-out results

Lower MAE is better. All comparisons below use identical rows.

| Stat | New model MAE | Validation-selected baseline MAE | Reduction | 95% CI for MAE difference, new minus baseline |
|---|---:|---:|---:|---|
| PTS | 4.6065 | 4.6764 — EWMA10 | 1.49% | −0.0835 to −0.0564 |
| REB | 1.9067 | 1.9298 — pooled ridge | 1.20% | −0.0268 to −0.0197 |
| AST | 1.3510 | 1.3667 — pooled ridge | 1.15% | −0.0180 to −0.0136 |
| PRA | 6.0653 | 6.1561 — EWMA10 | 1.48% | −0.1093 to −0.0727 |

Intervals use 2,000 date-cluster bootstrap draws. They account for same-date clustering, but do not capture every form of serial/player dependence or future distribution shift. The model also improves each stat separately in the 2024–25 and 2025–26 holdout periods.

For the **13,123 high-minute observations** whose pregame L10 minutes were at least 28, the new versus baseline MAEs are PTS **5.6507 vs 5.7673**, REB **2.1046 vs 2.1118**, AST **1.7231 vs 1.7288**, and PRA **6.9578 vs 7.0744**. The rebound/assist gains in this group are particularly small.

For **4,932 season-opening observations** with fewer than ten current-season appearances but sufficient prior-career history, all four stats improve. PTS MAE is **4.3372 vs 4.5234** and PRA is **5.8248 vs 6.0938**. This is evidence for returning players at season opening; it does not validate a rookie model.

| Stat | Central 80% interval observed coverage | Mean interval width | New / baseline CRPS |
|---|---:|---:|---:|
| PTS | 82.46% | 14.28 | 3.2558 / 3.3052 |
| REB | 86.90% | 6.07 | 1.3356 / 1.3496 |
| AST | 88.53% | 3.96 | 0.9302 / 0.9398 |
| PRA | 81.17% | 18.90 | 4.3084 / 4.3735 |

CRPS is approximated with 501 fixed empirical quantiles. The intervals are conservative, particularly for low integer counts. These are not claims of exact 80% coverage or proven sportsbook-line probability calibration. The full machine-readable metrics, sample counts, selections and source hashes are in [forecast_rebuild_results.json](forecast_rebuild_results.json).

## Current-use artifact and speed

The model used to calculate the reported results is preserved at `models/forecast/evaluation.pkl` with its adjacent JSON manifest. It must remain separate from future refits.

The app's current-use artifact is `models/forecast/league.pkl`, using the same selected specifications, fitted on **105,697 rows through December 31, 2025** and calibrated on **15,358 rows through April 12, 2026**. It is approximately **504 KB**. This refitted artifact itself has no subsequent held-out or forward-paper result yet; the retrospective evidence concerns the frozen older artifact and recipe.

A local benchmark of 30 warm four-stat forecasts, including feature preparation and uncertainty summaries, measured **14.0 ms median / 14.7 ms p95**. It excludes provider requests, authentication and production contention. Requests never train models. Models are cached by artifact/manifest modification time, and artifact version, feature schema, digest and scikit-learn version are checked on load.

Pickle artifacts must come from trusted storage. The checksum detects corruption, not a malicious publisher. Runtime model binaries and their manifests are ignored by Git; deployment must provision both files or reproduce the fit. `NBA_EVAL_FORECAST_MODEL_PATH` can select a trusted artifact location.

## Running it

Install the project dependencies, including the newly declared parquet engine:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Reproduce the research from the pinned public snapshot:

```powershell
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py prepare --download
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py select
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py evaluate
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py fit-current --calibration-start 2026-01-01 --through 2026-04-13
```

`--through` is exclusive. The explicit historical dates reproduce this experiment; later refits must choose a later calibration window and use updated, verified source files. Repeatedly tuning on the published test period would invalidate its status as a holdout.

With the existing API/auth environment configured, start FastAPI and the frontend, then open **Forecasts** in the navigation. Enter the player, current team, opponent, future tipoff and availability. Optionally enter a current sportsbook quote. The page displays point forecasts, ranges, and exact-price estimated return. Manual event/availability/quote data is caller supplied; it is not represented as a verified sportsbook feed. Out players and invalid/stale/in-play quotes fail explicitly. All offer outputs currently have `recommend: false` because priced betting validation is incomplete.

The new route is separate from the legacy per-player prediction and game-win models. Legacy model defects described in the earlier audit are not claimed to be repaired by adding this engine. The new Forecasts page uses the new route exclusively.

For offline use without Supabase or a provider subscription:

```powershell
.\.venv\Scripts\python.exe scripts/forecast_player.py --logs cache/research/forecast_logs.parquet --request request.json --out forecast.json
```

Request JSON contains `player_id`, `event_id`, timezone-aware `starts_at`, `team`, and `home`, plus optional `availability` and `offers`. Choose a real future event for practical use; example IDs and times would be scenarios. CLI `as_of` may be supplied for a reproducible replay. HTTP callers cannot override the server's current time.

## Verification and remaining work

- **40 new forecast tests pass**, covering temporal causality, identical train/serve features, offseason/trade inputs, artifact integrity, discrete pushes, offer math, authentication, API serialization, invalid offers and out-player abstention.
- **145 focused tests pass**, including prior readiness fixes and backtest context cases. Adding parquet support resolved the four missing-engine failures from the earlier audit.
- The full suite run recorded **765 passed / 23 failed / 4 skipped** before the final extra endpoint regression was added; that added case subsequently passed in the focused run. Remaining failures are the existing authentication/cache/scenario contract issues documented in the earlier audit. The full suite is not green.
- Frontend TypeScript/Vite build and lint pass. The new form, player selection, forecast result cards and quote fields were checked in a local browser fixture. The fixture used actual offline forecast output with mocked HTTP transport; this was not a production-provider/login test.

The remaining high-value inputs are timestamped historical prop prices and pregame availability/expected-minutes information. Those enable a separate frozen priced-offer replay and forward paper evaluation. Reliable current provider data, artifact provisioning and the unavailable production backend also need resolution before release. No amount of model complexity substitutes for that evidence.
