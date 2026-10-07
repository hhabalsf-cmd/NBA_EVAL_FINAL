# NBA evaluator: season readiness audit

**Verdict: not ready for real-money betting.** The public frontend loads, but its configured backend is unavailable. The repository's own historical evaluations do not establish a profitable betting edge. Local reliability fixes in this audit improve record integrity and operation; they do not validate the predictions or restore production.

Audit completed September 24, 2026. Reviewed repository: `hhabalsf-cmd/NBA_EVAL_FINAL`, main at `fc82e9a`, plus the local changes described below. Nothing was deployed, pushed, or written to the production database.

## Scope and evidence

The audit covered the prop and game prediction paths, feature construction and calibration, model persistence, odds ingestion, daily generation, game-log synchronization, pick/parlay settlement, profit reporting, FastAPI authentication and scheduling, Supabase SQL and grading webhook, React frontend, dependencies, deployment configuration, tests, and existing evaluation reports. A broad static sweep covered 207 tracked code/configuration files; all 103 tracked Python files parsed successfully. Critical prediction and settlement paths received deeper inspection. Video/marketing code was inspected statically, without rendering its videos.

Evidence below distinguishes current source inspection and local tests from **historical results already checked into the repository**. No authenticated production database, deployed model artifact, provider subscription, or scheduler configuration was available. Historical backtests were not rerun against live data. The audit therefore cannot certify live RLS policies, data freshness, model contents, real wagers, or operating latency.

## 1. Immediate deployment blocker — P0

The frontend at <https://nba-eval-final.vercel.app> returns HTTP 200. Its downloaded JavaScript points to `https://nbaevalfinal-production.up.railway.app`.

During the audit, `/api/health`, `/api/bets/today`, and `/api/games/today` on that backend returned HTTP 404 with Railway's `Application not found` response. The final September 24 recheck additionally failed normal Python TLS validation with `certificate has expired`. A diagnostic request to the public health endpoint with certificate validation bypassed still returned Railway's 404. No application TLS settings were changed and no credentials were sent in that diagnostic request. The certificate result is an observation from this environment; the 404 independently establishes that this configured URL is not serving the application.

**Required:** restore the correct Railway service/domain, valid TLS, and frontend API URL. Then verify authenticated prediction, database reads, and service-key jobs end to end. A successful frontend load alone is insufficient. Keep betting generation disabled during that verification.

## 2. Prediction quality does not demonstrate profitable bets — P1

### Existing evidence

The repository reports **40 wins / 66 losses, 37.7%**, on 106 graded real-line prop picks. At a uniform -110 price, the mathematical break-even win rate excluding pushes is **52.38%**. The old deletion and voiding behavior described below can compromise historical samples, so this record must be reconciled against an immutable ledger before treating it as a complete performance history. These figures were read from repository reports/UI, not newly measured from production.

The [pooled scorecard](pooled_model_scorecard_2026-08-25.md) evaluates 44 held-out players, 606 games and 2,424 player-stat rows after training on 25,327 rows from 439 players:

| Stat | Pooled MAE | Existing production MAE | Best simple baseline MAE | Evidence versus best baseline |
|---|---:|---:|---:|---|
| PTS | 6.000 | 6.517 | 6.065 | Bootstrap interval includes a tie |
| REB | 2.419 | 2.546 | 2.427 | Bootstrap interval includes a tie |
| AST | 1.792 | 1.885 | 1.775 | Baseline point estimate is better; interval includes a tie |
| PRA | 7.249 | 7.637 | 7.267 | Bootstrap interval includes a tie |

The pooled model improves on the existing production model but has not convincingly beaten the strongest simple baselines. Its pseudo-line AUC is 0.576 for PTS and 0.561 for PRA. Its reported 60–80% probability band misses observed frequency by 13.9 percentage points; the production comparison is overconfident by 14.3 points. Pseudo-lines and stat MAE do not establish returns at available sportsbook prices.

The [historical game-model audit](audit_game_predictor_2026-08-24.md) reports 24/38 correct predictions (63.2%) versus 21/38 for always picking the home team. The paired comparison has p=0.629. Its Brier score of 0.2542 is worse than the constant-home-rate baseline's 0.2472. This small postseason sample cannot establish regular-season betting value. That report's claim that game history is deleted after 40 rows is stale: the current source removed that deletion, although the history API still limits retrieval.

### Open model defects

| Finding | Source evidence | Consequence and required correction |
|---|---|---|
| Game-model training/serving features differ | `game_predictor.py:1206` passes `all_games_df=None`; season-window and head-to-head calculations differ between historical training and serving | Rebuild both paths around the same as-of feature function. Replay historical fixtures and assert identical values at the same cutoff. |
| Elo and model freshness are not maintained by the API service | Elo replay occurs in `train_model()` around line 1735; `api/services/game_service.py` loads/trains once without using `should_retrain()` | Incrementally incorporate completed games, define offseason regression, and persist the data cutoff and artifact version. Test restart and stale-artifact behavior. |
| Game-model calibration is fitted to a different estimator | `_calibrate_probabilities()` around line 1499 fits first-base-estimator OOF scores, while prediction applies it to stacking scores | Fit calibration to strictly out-of-time predictions from the exact served stack. Put selection and preprocessing inside each fold; current feature selection/scaling use the full training set before CV. |
| Team-stat provider fallback can silently replace current context | `game_predictor.py:get_team_stats()` uses obsolete provider methods and falls back to defaults | Repair the supported data path and explicitly mark unavailable context. Do not present default ratings as observed data. |
| Pooled training and serving span different season windows | `pooled_features.py:203` groups training by player and season; `serve_features()` at 171 and `dispersion()` at 190 use the entire supplied history; `pooled_predictor.py:_absorb()` accepts the multi-season API frame | Define and enforce one history policy. Test October, trades, players with few current-season games, and multi-season input. Simply enabling the pooled flag does not fix this mismatch. |
| Line evaluation discards the model's uncertainty | `api/routers/players.py:836–870` replaces uncertainty with fixed per-stat CV and confidence 75 | Use the same model distribution/calibration as the full prediction path. Clearly distinguish a user-supplied point estimate from a model probability. |
| Artifact provenance is incomplete | Game predictions omit the artifact version that the saved model advertises; pooled artifact is local and ignored by Git | Record artifact digest/version, training cutoff, feature schema, calibration version and data cutoff with every prediction. Verify pooled artifact provisioning before enabling it. |

These require model/data work and a new time-ordered evaluation. They were not patched speculatively during a reliability audit.

## 3. The app cannot yet measure actual betting value — P1

`line_sources.py:14–88` reduces bookmaker offers to player, stat, consensus line, and teams. Bookmaker price, book identity, event ID, and quote time are discarded. Manual lines likewise lack executable odds and stake. The profit ledger assumes all bets are -110. The game predictor calls distance from 50% an `edge` (`game_predictor.py` around 1992) and can label a pick `STRONG_BET` without comparing any market price.

A high win probability is not sufficient. For example, a 60% win probability at -200 has expected net return per unit risked of `0.60 × 0.50 − 0.40 = −0.10`. That calculation is impossible to do correctly without the offered price. A consensus line may also combine different books and may not be available to the user.

**Required data contract:** preserve event ID, player ID, market and settlement rules, side, exact line, book, decimal/American odds, quote timestamp, scheduled start time, prediction timestamp, model version, and actual stake if tracking wagers. Compute expected value from the exact offer and calibrated win/loss/push probabilities. Store real settlement profit separately from standardized paper returns. Handle correlations when comparing a portfolio of props, PRA/components, and game bets.

**Closing-line value is currently unreliable:** `line_snapshots.py:300–313` chooses the latest snapshot after the pick, without requiring it to precede tipoff. Matching does not preserve the full book/price/event identity. Some timestamps are naive server-local values whereas snapshots are normalized to UTC. The 05:00 UTC closing-line job can run after games have started or finished. Capture quotes before each event's start, distinguish pregame from live lines, and compare like-for-like markets. Until corrected, current CLV must not be used as proof of betting skill.

## 4. Season-start data and daily operations — P1

| Finding | Evidence | Required behavior |
|---|---|---|
| Offseason roster changes can assign a player to the wrong team | `scripts/daily_best_picks.py` derives team from the latest historical matchup | Use the current roster tied to the scheduled event; retain historical team attribution for training. |
| Injury data does not adequately gate daily picks | Daily generation fetches injuries but does not exclude every explicitly out player; questionable status primarily receives a confidence discount | Enforce eligibility and current expected minutes, refresh before tipoff, and abstain when status is unresolved. |
| A freshness stage is effectively disabled | `_fetch_player_props_lookup()` leaves `by_id` empty; `_sync_game_logs_for_prop_players()` returns early on that empty mapping | Populate stable IDs, verify completed-slate coverage and provider timestamps, and block stale predictions. |
| Rookies/new roles are poorly covered | Daily eligibility requires history/minutes; existing history may reflect another team's role | Define an explicit cold-start/abstention policy. Report exclusions rather than making unsupported forecasts. |
| Completed-game data is not fully reconciled | Game-log inserts use `ON CONFLICT DO NOTHING`; aggregation can accept incomplete player totals; stale fallback can conceal provider failures | Upsert corrections, require final and sufficiently complete box scores, and expose data age/source/completeness. |
| Picks are not consistently bounded to pregame offers | No uniform event-start cutoff across generation and line ingestion | Reject stale or in-play quotes for the pregame model; persist game identity and start time. |
| Scheduled work can fail without durable evidence | In-process `asyncio.create_task()` returns 202 before completion; cron HTTP results are not followed to a successful run; sync can exit successfully despite failed work | Persist job ID, status, input cutoff, counts, errors and completion time; use retries and idempotency/locks. Alert on missing successful runs. |
| Health and scheduling do not establish readiness | `/api/health` returns HTTP 200 even when degraded; cron keepalive POSTs to a GET-only endpoint; grading precedes nightly sync in the checked-in schedule | Separate liveness from readiness. Check data/model/odds freshness. Fix method/order and inspect deployed cron state before changing it. |

The nightly back-to-back skip bug and tomorrow-slate fallback were fixed locally, as detailed below. They do not resolve the other data gaps. Repository comments about OddsAPI quota exhaustion and BDL subscription limits are historical configuration notes; active account entitlements were not verified.

## 5. Record integrity and settlement

The original code deleted picks beyond the newest 100 per user, automatically voided old unresolved picks as DNP, and could settle against a game one day away from the requested date. Those behaviors can silently distort a reported betting record. Missing provider data is not evidence that a player did not participate.

The local patches preserve history, require the exact game date and supplied opponent, use the pick's season, and leave missing/ambiguous data pending. An explicit zero-minute, all-zero row is voided only with evidence that the team's game is final. Pushes are now settled rather than repeatedly returned as pending. A follow-up production reconciliation is necessary: these patches cannot restore previously deleted rows or automatically identify every historically incorrect void/grade.

Remaining requirements:

- Match and settle by provider event ID and final result, with a correction/regrade trail. The current positive-minute grading path still relies on game-log finality rather than universally requiring an independently verified final event.
- Distinguish system-generated pregame paper picks from user-entered/backdated/manual grades. User-modifiable records and soft deletion cannot establish independently verified model performance.
- Record actual odds/stakes and sportsbook-specific void/parlay rules. The generic parlay status fix does not implement book-specific payout adjustments.
- Surface statistics failures as unavailable. Returning zeros on a database error can make an outage look like an empty record.

## 6. Security, performance and maintainability

**Security:** API ownership/admin checks and parameterized SQL are present in the inspected critical paths. The grading webhook previously failed open when its service secret was missing; it now rejects that configuration. The request-size middleware still trusts `Content-Length`, so chunked/streamed bodies can bypass the intended byte limit, and invalid lengths can raise an error. A warning comment flags this remaining issue. Implement a receive-byte limit, validate lengths, and reconcile the global 2 MB cap with the 5 MB avatar allowance.

The repository lacks a complete reproducible migration set for core tables and RLS policies. Verify cross-user read/write isolation, protection of profile roles, storage ACLs, service-role usage, and schema from a fresh database plus two ordinary accounts. This is an unverified boundary, not a demonstrated production breach. Pickle/joblib artifacts must come only from trusted, access-controlled storage with verified provenance; loading them executes Python deserialization.

**Dependency checks:** compatible frontend lockfile updates reduced the production npm audit result from six affected packages to two moderate findings in the React Router family. Remediation requires a major-version migration; it was not forced into this audit. Python `pip-audit` reported advisories for two audit-environment packages: bundled pip and `ecdsa` pulled in by the audit-only `python-jose` installation. No additional installed application-runtime dependency was flagged in that scan. This is a point-in-time scanner result, not a guarantee against vulnerabilities. `pip check` passed. Python requirements mostly allow broad version ranges and are not a reproducible lock.

**Efficiency:** some asynchronous routes invoke synchronous database/provider work, and game-model loading/training can block the event loop. The sync endpoint was moved to FastAPI's threadpool, but game prediction still needs bounded workers and precomputed artifacts. Daily generation can train/update/save models before establishing that an actionable offer exists. Fetch eligible priced offers first, batch data retrieval, and update models once per new data cutoff. Measure cold/warm p50/p95 latency, provider calls, CPU/memory, and behavior during concurrent prediction and grading before setting performance claims.

The frontend build passes but emits an approximately 1.23 MB main JavaScript bundle (344 KB gzip) and a chunk-size warning. Route/chart splitting is a secondary optimization after correctness. Live prop status is not functional through the current BDL box-score path: `bdl_client.py:get_box_scores()` deliberately raises `NotImplementedError`, and the service catches that failure.

**Maintenance:** no automated CI workflow was found. README architecture/setup descriptions, missing frontend environment-template instructions, old branch-status notes, and marketing/demo accuracy claims need reconciliation with measured behavior. Historical documentation must not be mistaken for current deployed state.

## 7. Local fixes included in this audit

| Area | Change |
|---|---|
| Prediction availability | Defined the missing `PRED_CACHE_DIR`, preventing a prediction-path `NameError`. Replaced Unix-only `fcntl` with a cross-platform file lock and declared `filelock` in production dependencies. |
| Prediction consistency | Cache keys include model/ensemble/pooled configuration, use a path-safe hash, and expire after 15 minutes. Responses report the actual model type. Model/data-version-aware invalidation is still needed. |
| Shared model selection | Added `predictor_factory.py`; interactive and scheduled prediction select the same enabled model and do not silently fall back when the pooled artifact is missing. |
| Slate and freshness | Removed tomorrow fallback from today's generation. Nightly sync compares the latest log with the completed ET slate, so back-to-back games are not skipped based on elapsed whole days. |
| Generation control | Disabled generation returns 503 before queuing a background task. Backend defaults remain disabled. Other game/legacy entry points still need equivalent enforcement. |
| History and settlement | Removed the 100-pick deletion cap and age-only voiding; require exact date/opponent; fetch the pick's season; handle missing minutes conservatively; recognize explicit final-game zero-minute DNPs. |
| Pushes and transactions | Write result and `graded_at` atomically. Exclude pushes from pending queries; return/display push status and handle pushes/voids when grading parlays. |
| Performance reporting | Centralized the cumulative frontend profit source in the backend, excluded paper/voided picks, aligned the existing -110 unit convention, and fixed optimistic UNDER grading. These remain standardized returns, not actual wager P&L. |
| Webhook | Missing secret returns 503, bad authorization returns 401, downstream grading failure returns 502, and ET date selection no longer depends on reparsing locale strings. |
| Runtime/dependencies | Moved blocking sync subprocess work off the event loop; applied compatible frontend dependency fixes. |
| Regression coverage | Added 32 Python regression cases and five JavaScript webhook tests. |

All changes are local and reviewable. No deployed environment variables or gates were enabled. No trained coefficients or model artifacts were replaced.

## 8. Verification results

| Check | Result |
|---|---|
| Full Python suite | **722 passed, 27 failed, 4 skipped**, 268.35 seconds; 9,742 warnings |
| Focused readiness/flags/paper/ET-date/season tests | **153 passed** |
| Grading webhook tests | **5 passed** |
| Frontend TypeScript/Vite production build | **Passed**, with bundle-size warning |
| Frontend ESLint | **Passed** |
| Python dependency consistency | `pip check` passed |
| Static parse / whitespace | All 103 tracked Python files parsed; `git diff --check` passed |
| Production availability | Frontend 200; configured API unavailable as described above |

### Why the full suite is still red

| Existing test area | Failures | Diagnosis |
|---|---:|---|
| `tests/test_auth.py` avatar cases | 2 | Test mocks do not override FastAPI's captured authentication dependency, so requests stop at 401. |
| `tests/test_backtest_opponent_context.py` cache cases | 4 | A parquet engine is required but absent from declared development dependencies. |
| `tests/test_game_log_cache.py` | 11 | Tests mock obsolete database/provider interfaces and use assumptions inconsistent with current cache/season behavior. |
| `tests/test_scenarios.py` | 8 | Requests lack the authentication dependency override required by the current endpoint. |
| `tests/test_supabase_auth.py` | 2 | Tests assume local JWT decoding, while current code performs Supabase user verification; unmocked network access fails. |

These failures must be repaired without weakening endpoint authentication or changing tests merely to accept broken behavior. A raw Windows installation initially also failed collection on Unix-only locking and an undeclared test import of `python-jose`. Locking is fixed in this patch; `python-jose` was installed only in the audit virtual environment to inspect the remaining suite. Declare or remove obsolete test dependencies and provide a documented parquet dependency for training/backtesting.

Local evidence logs are `audit-tests.txt` and `audit-final-tests.txt` (ignored working files). Tests used dummy database/service-key values and mocked providers for the new cases; this was not a production integration test.

Re-run from the repository root after installing the declared requirements and resolving the test dependency issues:

```powershell
$env:NBA_EVAL_DISABLE_TF='1'
$env:PYTHONUTF8='1'
$env:DATABASE_URL='postgresql://audit:audit@127.0.0.1:1/audit'
$env:FASTAPI_SERVICE_KEY='audit-local-test-service-key'
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
node --test supabase/functions/grade-picks/index.test.mjs
npm --prefix frontend run build
npm --prefix frontend run lint
```

The webhook tests use TypeScript from the frontend's installed dependencies. Production acceptance additionally requires real credentials in a controlled integration environment, without substituting production writes for test fixtures.

## 9. Release gates, in order

1. **Operational recovery:** valid public API/TLS, authenticated smoke tests, verified database schema/RLS, supported provider access, and complete model artifacts. Record a successful sync → prediction → quote capture → grading cycle with durable job status.
2. **Trustworthy ledger:** retain all picks; reconcile old deletions/voids where recoverable; distinguish paper/manual/system records; store exact event/book/price/times; enforce pregame cutoffs and final-result settlement. Verify pushes, DNPs, postponements, corrections and repeated job execution.
3. **One validated serving contract:** resolve game and pooled feature mismatches, stale Elo, and calibration estimator mismatch. Make all recommendation entry points honor the same release gate. Repair the existing tests and add CI; require a clean test/build run.
4. **Out-of-time evaluation:** freeze model/selection rules before evaluating later dates. Use historical offers available at prediction time, include vig and pushes, and compare against simple statistical baselines and de-vigged market probabilities. Report Brier/log loss, calibration, coverage, realized priced return and uncertainty. Cluster uncertainty by date/game/player as appropriate; correlated props are not independent observations. Test season opening, trades, injuries, and changed minutes separately.
5. **Forward paper validation:** retain every eligible offer and every issued/abstained prediction. Use a prespecified evaluation window and decision rule, actual offered prices, reliable pregame CLV and no retrospective pick removal. A fixed number of bets alone does not prove an edge. Only consider enabling a betting recommendation surface after the resulting evidence and operating checks support it.

The current appropriate mode is **disabled recommendations while repairing infrastructure, then transparent paper/research use**. Accuracy, sophisticated model architecture, and passing software tests alone cannot establish future betting profitability.
