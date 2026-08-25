# Next Steps — NBA Prop Platform (written 2026-08-25)

Supersedes `NEXT_STEPS_2026-08-23.md`, which is now history. That document planned
Tracks A, B and C. **All three are built.** This one says what they produced, what it
means, and what the single open decision is.

Evidence base: `SUMMARY_model_investigation_2026-08-23.md` (verdict, with one
correction noted below), `pooled_model_2026-08-25.md` + `_scorecard_` (Track B),
`audit_game_predictor_2026-08-24.md` (ELO).

---

## The one-paragraph version

The prop model was rebuilt the way the diagnosis prescribed — pooled across players,
six features instead of eighty-one, p/n from 1.35 to ~0.0003. **It works: it beats
the production model on all four stats and clears the exit criterion as written.** It
is also, on the same holdout, **statistically indistinguishable from a rolling
average on every single stat** — four ties against the best trivial baseline, zero
wins. Every distinguishable win it has is against a *short* window (L3, L5,
last-game). It fails the AUC bar on two stats and the reliability bar on all of them.
Pooling fixed the defect it was supposed to fix and did not produce an edge, which is
the same answer the previous five phases got by other means. The research
repositioning is built and tested but **has not shipped** — that is the open decision.

---

## State of the tree

Branch `investigation/model-audit-2026-08`, pushed to origin. **`main` is untouched
at `b8f9ac7` — Vercel has never rebuilt.**

| Commit | What |
|---|---|
| `23313fe` | The five phases of investigation work, unsaved since 2026-08-06 |
| `f1d8769` | Flag gating — every model surface behind a flag, default off |
| `2372f8f` | ELO game-predictor audit |
| `c640961` | CLV + paper-pick instrumentation; removed the 40-row hard delete |

**Uncommitted in the working tree:** the admin closing-line capture UI and all of
Track B (`pooled_features.py`, `pooled_model.py`, `pooled_predictor.py`, two scripts,
three test files, two reports).

Test suite: **698 passed / 20 failed / 3 skipped.** The 20 are the same pre-existing
failures as always — `test_auth` (2), `test_game_log_cache` (8), `test_scenarios`
(8), `test_supabase_auth` (2). Do not chase them.

**Applied to production:** migration `paper_picks_and_line_snapshots`. Verified: 114
picks all `is_paper=0`, 106 still graded, `line_snapshots` empty, RLS enabled with
zero policies. Nothing else in the database was touched.

---

## Track B — what the pooled model actually did

Six features per stat (`L5, L10, L20, MEDIAN, MEAN, EWMA5`), ridge α=3, PRA fitted
directly. 25,327 pooled training rows from 439 players. Spec chosen on a mirror
holdout under a rule fixed in advance; the real holdout was scored **once**.

### Exit criterion 1 — beat EWMA5 / L10 / season median: **PASS on all four**

| Stat | pooled | production | worst of the 3 named | best of **all 8** | margin | bootstrap |
|---|---:|---:|---:|---|---:|---|
| PTS | 6.000 | 6.517 | −0.065 | 6.065 (EWMA5) | −0.065 | **tie** [−0.131, +0.004] |
| REB | 2.419 | 2.546 | −0.020 | 2.427 (mean) | −0.008 | **tie** [−0.063, +0.039] |
| AST | 1.792 | 1.885 | −0.010 | 1.775 (**L20**) | **+0.017** | **tie** [−0.002, +0.036] |
| PRA | 7.249 | 7.637 | −0.018 | 7.267 (EWMA5) | −0.018 | **tie** [−0.096, +0.056] |

It passes the criterion the plan wrote. It does not beat the field. **Four ties, zero
wins, and AST is a point-estimate loss to a twenty-game rolling mean.** Of 32
model-vs-baseline comparisons, 17 are distinguishable wins — every one of them
against L3, L5 or last-game. Against every long window and season summary: tie.

### Exit criterion 2 — median-line AUC ≥ 0.58: **FAIL on 2 of 4**

| Stat | pooled | 95% CI | production | L10 signal | |
|---|---:|---|---:|---:|---|
| PTS | 0.5760 | [0.523, 0.627] | 0.5115 | 0.5774 | **FAIL** |
| REB | 0.5829 | [0.520, 0.639] | 0.5372 | 0.5759 | PASS |
| AST | 0.6318 | [0.570, 0.682] | 0.5628 | 0.6210 | PASS |
| PRA | 0.5610 | [0.497, 0.619] | 0.5505 | 0.5770 | **FAIL** |

Note the `L10 signal` column: on PTS and PRA the pooled model's AUC is *below* what a
plain ten-game rolling mean achieves on the same lines.

### Exit criterion 3 — reliability gap within ±5 points: **FAIL**

−13.9 in the unclipped 60–80% band (N=212): it claims 63.4% and delivers 77.4%. The
sign is **inverted** from production's +14.3 — this model is *under*confident, not
over. That is a better failure than the old one, but it is still a failure, and the
[70,80) bucket has N=7, so do not over-read it.

This was left open deliberately. Closing it means sharpening against a season-median
pseudo-line that §5 of the summary showed is mostly line staleness. The shrink slope
is clamped at 1.0 so it can only pull toward the base rate; on all four stats the
free fit wanted to sharpen and the clamp bound. **That clamp is correct. Do not
remove it to make this number go green.**

### Two corrections Track B produced

1. **`SUMMARY` §1 had a transcription error.** The AST/EWMA5 cell read **1.775**;
   that is **L20's** figure. AST EWMA5 is **1.801**. When the table was condensed
   from `diagnosis` §3 the L20 column was dropped and its bolded value carried into
   the EWMA5 slot. AST was the only affected cell. **Corrected in place 2026-08-25.**
2. **`NEXT_STEPS_2026-08-23.md` overstated the pooled result**, claiming it "beats
   production *and* every trivial baseline — the only thing measured in this entire
   investigation that does." It beats production on all four. It ties the best
   baseline on all four. Both halves of that sentence cannot be true at once.

**Reproduction check:** refitting the diagnosis's 9-feature 2023-24-only ridge from
committed code gives 6.003 / 2.429 / 1.794 / 7.258 against the reported 6.004 /
2.430 / 1.792 / 7.252 — max deviation 0.006. The original measurement was sound.

**Lookahead control:** every served feature was asserted equal to the harness's
independently computed baselines — **max |difference| = 0.0 across 36 features × 606
games**. The Phase-0 derived-PRA trap is not live; `normalize_game_log` overwrites
any `PRA` column with `PTS+REB+AST`, pinned by a test that poisons it with 999.

---

## What this means

Three independent lines of evidence now say the same thing:

1. The per-player model has no edge (5 phases, 2026-08-19 → 08-23).
2. The pooled rebuild has no edge either — it is a well-engineered rolling average.
3. The ELO game predictor cannot be shown to beat "always pick the home team" on the
   sample that exists (McNemar p = 0.629), and its Brier is worse than a constant.

The strategic read from 2026-08-23 stands and is now better supported: **per-game NBA
box-score outcomes are close to unpredictable at this feature resolution.** RMSE/σ is
1.10–1.17, R² against the player's own running mean is negative on all four stats,
and an oracle knowing each player's true forward level buys only 13–16% over a
rolling mean.

Pooling was the highest-EV idea available and it was executed properly. The result is
not a failure of execution. It is an answer.

---

## The open decision

**The research repositioning is built, tested and pushed — and has not shipped.**
`main` is still `b8f9ac7`. Everything users currently see is the pre-investigation
app, including the surfaces the plan called "the one actively harmful thing the
system can do."

That is the decision to make. Three ways to go:

- **Ship it.** Merge the branch to `main`, let Vercel deploy. Users get the research
  product; every probability claim disappears. The pooled model stays behind
  `NBA_EVAL_POOLED_MODEL`, off, as the strictly better default if predictions are
  ever re-enabled. **This is what I would do.**
- **Ship it and start the paper loop.** Same, plus enable pooled picks as paper picks
  and begin accumulating toward n ≥ 500 against real lines. Honest, but it requires
  manual line entry twice a day, every day, and the expected outcome given four ties
  is ~52%. Worth doing only if the daily discipline is real.
- **Keep building first.** Minutes projection is the one high-ceiling lever never
  tried: oracle minutes are worth 13.6% (PTS) to 20.2% (PRA) MAE. But L10-minutes
  recovers **exactly zero** of it, so it needs injury and rotation data that is not
  ingested and has no working source. High cost, unbounded scope, and it delays
  shipping a product that is already finished.

---

## Do not reopen

1. **Calibration and uncertainty.** Three phases, three genuine bugs, zero movement.
   Track B's reliability failure is not an invitation — the clamp is deliberate.
2. **Adding features.** Accuracy degraded monotonically with feature count on the old
   model; the new one uses six and ties the field. There is no version of this that
   is fixed by a seventh.
3. **Pseudo-line ROI.** Its value is a pure function of how the pseudo-line is built.
   Moving from a season median to an L10-aware line collapses AUC ~0.60 → 0.51–0.56.
4. **The 40-row cap on `game_predictions`.** Removed 2026-08-24. If row growth ever
   needs bounding, archive or soft-void — never hard-delete graded rows.

---

## Loose ends, ranked

- **CLV is still structurally impossible to accumulate.** The apparatus is complete
  and tested end to end, but three things block it: (a) the order must be capture →
  pick → capture, since a closing line requires `captured_at > pick.timestamp`;
  (b) `scripts/snapshot_closing_lines.py` defaults to dry-run and the
  `nightly-closing-lines` cron was deliberately left unscheduled; (c) there are no
  picks to attach CLV to until something runs `scripts/record_paper_picks.py`.
- **No automated line source exists, and there is no path to one without paying.**
  BDL odds raise `NotImplementedError` unconditionally (`bdl_client.py:328`).
  OddsAPI has no key at all — `config.json` does not exist and `ODDS_API_KEY` is
  unset, so it is not merely quota-exhausted. Manual admin entry is the only source.
- **The ELO serve path has two live defects.** `sos_diff` and `elo_x_sos` are
  hard-coded 0.0 on every prediction (rank-8 feature, `all_games_df=None` — the same
  class of bug as `nba_evaluator.py:3266`), and `elo_tracker` only advances inside
  `train_model`, leaving feature #1 32–46 days stale. Fix these before reviving the
  crons, or the growing sample is drawn from a known-broken path.
- **Both game-prediction crons have had zero effect since 2026-05-04.** `pg_net`
  never inspects the response, so `active: true` was never a health signal. They are
  currently dormant by choice.
- **The pooled artifact lives only in gitignored `models/`.** If the pooled path is
  ever enabled in production it needs a Supabase Storage copy like the per-player
  fleet has. Build it with `scripts/train_pooled_model.py`.
- **`CLAUDE.md` has no section on the pooled module.** Add one when it stops being
  experimental.
- `autoGradePicks` / `autoGradeGamePredictions` in `client.ts` call endpoints that
  require `X-Service-Key`, so the frontend 403s. Pre-existing, unrelated.

---

## Constraints that will bite you

- `NBA_EVAL_DISABLE_TF=1` on **every** python invocation.
- The interpreter is **`python3`**. Plain `python` is not on PATH.
- Anything reading through `db.py` needs `load_dotenv(override=True)` — and
  **`override=True` alone is not enough from a script outside the repo**, because
  `find_dotenv()` walks up from the calling file, not the cwd. Pass the `.env` path
  explicitly or you get a misleading `password authentication failed for user
  "postgres"` while looking like you already handled it.
- Test baseline **698 / 20 / 3**. The 20 are pre-existing. Do not chase them, do not
  add to them.
- `won` and `voided` in `picks` are INTEGER (0/1), not boolean.
- Read the `nba-model-gotchas` memory before editing `nba_evaluator.py`. All ten
  traps fail silently.
- Flags are OFF unless the value is exactly `'1'` or `'true'`:
  `VITE_ENABLE_PREDICTIONS`, `NBA_EVAL_ENABLE_PICKS`, `NBA_EVAL_POOLED_MODEL`.

---

## Kickoff prompt for the next session

Start in `/Users/hhabal/Downloads/Projects/NBA/EVAL`. Edit the bracketed line.

> Read `docs/NEXT_STEPS_2026-08-25.md` — it is the plan of record and supersedes the
> 08-23 version. Its evidence base is `docs/pooled_model_2026-08-25.md`,
> `docs/audit_game_predictor_2026-08-24.md` and
> `docs/SUMMARY_model_investigation_2026-08-23.md`. Read them; don't re-derive them.
>
> Context up front: three independent efforts now agree that this platform cannot
> predict per-game NBA box-score outcomes at a useful resolution. The per-player
> model has no edge (5 phases). The pooled rebuild fixed p/n from 1.35 to ~0.0003,
> beat production on all four stats, and still **ties the best trivial baseline on
> all four** — zero wins, and it loses to a 20-game rolling mean on AST. The ELO
> game predictor's Brier is worse than predicting a constant. **Do not reopen
> calibration, do not add features, do not re-litigate any of this.**
>
> Everything is on branch `investigation/model-audit-2026-08`, pushed. `main` is
> still `b8f9ac7` and has never rebuilt. The research repositioning is built and
> tested but **not shipped** — that is the open decision.
>
> [I want to: **merge the branch to `main` and ship the research product**, keeping
> the pooled model behind its flag / *swap in "ship it and start the paper-pick
> loop" or "build minutes projection first" if you prefer*]
>
> Standing constraints: `NBA_EVAL_DISABLE_TF=1` on every python invocation; the
> interpreter is `python3`, not `python`; test baseline is **698 passed / 20 failed
> / 3 skipped** and those 20 are pre-existing (`test_auth`, `test_game_log_cache`,
> `test_scenarios`, `test_supabase_auth`) — don't chase them. Anything reading
> through `db.py` needs `load_dotenv(override=True)`, and from a script outside the
> repo you must pass the `.env` path explicitly — `find_dotenv()` walks up from the
> calling file, not the cwd. Read the `nba-model-gotchas` memory before editing
> `nba_evaluator.py`. Flags are off unless exactly `'1'` or `'true'`.
>
> Use Opus subagents for implementation, and don't commit or push without asking.
