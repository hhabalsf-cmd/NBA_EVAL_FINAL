# Season readiness audit — October 1, 2026

The local ESPN evaluator is provisioned for personal research use. No paid credentials, hosted database, or live model fitting are required. This is a tested readiness assessment, not a guarantee that future source data will be error-free or that forecasts will be profitable.

The NBA's [official 2026–27 schedule announcement](https://pr.nba.com/2026-27-nba-regular-season-schedule) places opening day on October 20. ESPN's first supported tipoff in this audit was October 20 at 19:00 UTC (noon Pacific), consistent with the official opening game. Neutral-site games and the other documented unsupported competitions remain excluded.

## Verified live

- 30 distinct NBA teams, 605 rostered players, all 30 team schedules.
- 1,197 distinct supported upcoming events. Repeated events across team schedules agreed on their date, home team, and away team. This is not a claim that every scheduled event is supported: neutral-site games are excluded and NBA Cup assignments are not all known yet.
- Verified history plus real model inference for Scottie Barnes (56 appearances), Luka Doncic (58), Stephen Curry (57), and Nikola Jokic (59). Exclusions are recorded, not filled with invented stats. This is a four-player history sample, not an exhaustive verification of all 605 players' historical box scores.
- A live local API request generated and saved Scottie's next-game forecast with availability correctly left unconfirmed.
- SQLite integrity check passed. A consistent backup of the local history was created under `cache/personal/backups/`.
- Installed dependency checks passed; `personal/requirements.lock.txt` records the 28-package Python 3.12 runtime used on this computer.

Machine-readable evidence is in `season_readiness_checks_2026-10-01.json`. Running **Check NBA Readiness.cmd** refreshes the live checks and writes `cache/personal/check-report.json`.

## Automated verification

- Entire Python suite: **851 passed, 4 skipped**, no failures, in 96.33 seconds. The skips are three unimplemented live PostgreSQL fixture tests and one optional absent cached player log. This does not verify a real hosted deployment. Existing legacy warnings remain.
- Personal adapter, maintenance and forecast tests: **100 passed** in the focused run.
- Grading-function JavaScript tests: **5 passed**. Frontend lint passed; no frontend source was changed in this audit.
- `pip check`: no broken requirements. Git whitespace checks passed.
- The model-retention regression still fits and updates real models and checks all four stats and quantile artifacts; its unrelated 40-trial optimizer search was disabled within that test. Separate optimizer-reset coverage remains.
- The final suite used an isolated temporary directory under `cache/` after Windows permissions prevented elevated pytest from using a temporary directory created by another execution context. No application security settings were changed to get a passing run.

## Corrections and safeguards

- All-Star exhibitions are excluded even when ESPN labels them as regular season, using competing franchise identities as well as season type. Play-in and postseason filtering remains active.
- Histories reject conflicting records across season feeds, mismatched stat-label arrays, invalid home/away assignments, and genuinely conflicting player/date rows.
- Explicit final-box-score DNPs are excluded from active-player history. Missing player identity is still an error, not an assumed DNP. A DNP does not hide an inconsistent most-recent appearance.
- Roster duplicates are rejected. Search no longer silently selects a team when a matching player appears on two rosters.
- Repeated identical schedule entries are collapsed; conflicting versions of an event are rejected. Completed or in-progress games cannot qualify merely by carrying a scheduled status name.
- Future-dated cache entries are not trusted after a clock change.
- Artifacts must contain the four correctly identified stat models, finite one-dimensional sorted residuals, matching calibration counts, coherent cutoff dates, and matching manifest metadata. Digest and scikit-learn compatibility checks remain enforced. [Scikit-learn documents the need for compatible dependencies when loading persisted models](https://scikit-learn.org/stable/model_persistence.html).
- Forecasts also reject artifacts calibrated on or after the prediction's as-of date, even if the target game is later. This closes a historical-replay leakage path.
- The hosted test suite's old mocks were updated to the current dependency injection, pooled database, BDL adapter and Supabase verification contracts. Production authentication was not weakened. Tests use a dummy database address and mocked provider authentication.

## Model status

The deployed artifact remains the reproducible `forecast-1` model: fitted through December 31, 2025, calibrated through April 12, 2026. Its SHA-256 is `c4f4251aaf0d49daba6c1d65a612a0c8de6879c32d7fd91bd3f8a9dacbab1ed1`. The audit did not overwrite it or claim that refitting on the same available data improves it. Completed new games update player inputs; model coefficients stay versioned.

The previously frozen evaluation used 41,023 player-games. Its first-ten-season-appearance subset contained 4,932 rows:

| Stat | Model MAE | Validation-selected baseline MAE | Actual coverage of nominal 80% range |
|---|---:|---:|---:|
| PTS | 4.337 | 4.523 | 85.3% |
| REB | 1.827 | 1.899 | 89.5% |
| AST | 1.260 | 1.313 | 90.8% |
| PRA | 5.825 | 6.094 | 85.0% |

These are historical results, not a guarantee for the new season. The intervals are conservative on this subset. Roster changes, injuries and minutes changes remain important uncertainty; no injury listing is not proof of participation. Rookies and players with fewer than ten usable appearances are intentionally unsupported.

## Season operations

1. **Start NBA Eval.cmd** opens the local app as before.
2. **Check NBA Readiness.cmd** checks the artifact, storage, front-end build, all team rosters/schedules, and the four sampled histories. Run before opening night or when the feed behaves unexpectedly. First-time requests can take several minutes because calls are rate limited.
3. **Score Saved Forecasts.cmd** checks final results for saved predictions. It selects the latest pre-tipoff snapshot per player/event, excludes DNPs, and reports MAE, bias and interval coverage separately by model artifact. New snapshots also preserve a last-20-game baseline so it can report a paired comparison. Old snapshots without a baseline are not invented or backfilled. Repeated scoring is idempotent; actual-stat corrections retain separate evaluation revisions. The original forecasts are immutable.
4. **Backup NBA Eval.cmd** creates a consistent SQLite backup without overwriting existing backups. Model files and their manifests should also be preserved before manually rebuilding them.

The first forward-scoring run had four distinct upcoming player/event forecasts, all pending. It correctly reported no measured accuracy or betting ROI. These launchers run on demand; no hidden scheduled job was installed.

## Remaining boundaries

No priced historical betting validation has been completed. Positive modeled expected value is not proven profitability, and the app does not place wagers. Source availability and corrections can change after this audit. The original hosted/social deployment was not provisioned or tested against real Supabase/paid-provider credentials; the supported setup here is the local personal app.

Retraining is an offline, versioned action. Do not use forward evaluation results to repeatedly tune on the same holdout, and do not replace the current artifact until a new candidate has separate temporal calibration and evaluation evidence. See `PREDICTOR_REBUILD_PROTOCOL.md` and `PERSONAL_LOCAL.md` for reproduction and setup.
