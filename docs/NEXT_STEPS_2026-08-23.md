# Next Steps — NBA Prop Platform (written 2026-08-23)

Companion to `SUMMARY_model_investigation_2026-08-23.md`. That document says what is
broken. This one says what to do about it, in what order, and what to stop doing.

---

## New evidence: the model has already been tested against real lines

The investigation reported that real-market validation was blocked because
`manual_lines` is empty. That is true of the *line-source* table, but it missed the
`picks` table — which records the real line each pick was placed against.

**106 graded picks, real lines, 2026-03-18 → 2026-04-29: 40 W – 66 L = 37.7%.**
Breakeven at −110 is 52.4%.

I spot-checked the grading against `line` / `direction` / `actual_result` — **zero
mismatches in 12**, so this is not a grading bug.

| Cut | n | Won | Rate |
|---|---:|---:|---:|
| All graded | 106 | 40 | **37.7%** |
| OVER | 63 | 25 | 39.7% |
| UNDER | 43 | 15 | 34.9% |
| Model edge ≥ 3 | 39 | 15 | 38.5% |
| Model edge < 3 | 67 | 25 | 37.3% |

Two things fall out of this, and they matter more than anything in the backtests:

1. **Mean claimed edge is 2.73. Mean absolute error is 4.83.** The model bets on a
   signal roughly half the size of its own noise. That is the whole story in one line.
2. **Edge magnitude does not sort outcomes** (38.5% vs 37.3%). The number the entire
   pick-selection rule keys off carries no information.

This is *worse* than the 53.3% the pseudo-line backtest produced, which is expected
and instructive: real book lines are sharp, season medians are stale, and picks were
selected on the model's highest-confidence signals — exactly the region the diagnosis
found to be anti-predictive.

**A 37.7% rate on a two-sided market is not neutral — it is systematically wrong.**
Do not read that as "just fade it": n=106, vig applies both ways, and selection
effects cut both directions. Read it as confirmation that the selection rule is
keying off noise.

---

## Do this first: the work is not saved anywhere

**~1,472 insertions and 363 deletions across 7 tracked files, plus 25 untracked
files, exist only in the working tree.** Last commit is `b8f9ac7`, 2026-08-06 —
seventeen days ago. A stray `git checkout`, a failed disk, or a cleanup script loses
five phases of work including every diagnostic script and all six reports.

It was left uncommitted for a good reason — `main` auto-deploys to Vercel — but that
argues for a **branch**, not for leaving it unsaved:

```bash
git checkout -b investigation/model-audit-2026-08
git add -A && git commit -m "Model investigation: harness, serve path, calibrator, diagnosis"
git push -u origin investigation/model-audit-2026-08   # does not deploy; Vercel builds main
```

Nothing else on this list matters if the work evaporates. This is fifteen minutes.

---

## The plan

### Phase A — Stop the bleeding (immediate, low effort)

1. **Branch and commit** (above).
2. **Turn off automated pick generation** until a model beats breakeven. `daily_picks`
   is empty and pg_cron job 16 (`daily-best-picks`) is already disabled — keep it
   that way, and make sure nothing in the UI presents model output as a betting
   recommendation. Shipping 37.7% picks to users is the one actively harmful thing
   the system can do.
3. **Relabel the confidence surface.** `CONFIDENCE_CAPS` (PTS 88%) and the displayed
   `prob_over` describe a model with AUC ≈ 0.50. Until that changes, the numbers are
   not just useless but misleading.

### Phase B — Rebuild the model (the demonstrated path)

The diagnosis measured a replacement, it did not merely propose one. On the same
holdout:

| Stat | Production (81 feat, per-player) | Pooled ridge (9 feat, league) |
|---|---:|---:|
| PTS | 6.517 | **6.004** |
| REB | 2.546 | **2.430** |
| AST | 1.885 | **1.792** |
| PRA | 7.637 | **7.252** |
| AUC | 0.532–0.555 | **0.574–0.628** |

That beats production *and* every trivial baseline — the only thing measured in this
entire investigation that does. Root cause it addresses: **p/n = 1.35** (81 features,
60 rows). Pooling turns n=60 into n≈33,000.

4. **Build the pooled cross-player model.** One model per stat, trained league-wide,
   under 10 recency features. Keep `MLPredictor`'s interface so the API and frontend
   are unchanged; swap what is behind it.
5. **Validate against the trivial baselines, not against the old model.** The bar is
   EWMA5 / L10 / season median. Anything that does not clear those is not a model.
6. **Shrink probabilities to the realized base rate** (51–53%). Mechanical fix for
   Brier and reliability. Truthfulness, not edge.

### Phase C — Instrument reality (parallel with B, continuous)

7. **Log closing lines daily** into `manual_lines` via `POST /api/bets/lines`. The
   `closing_line` column on `picks` is NULL on all 106, so CLV — the only fast,
   low-variance measure of whether a model beats a book — is permanently dead for
   the existing sample. Fix it going forward.
8. **Track paper picks, not real ones.** Accumulate a forward sample against real
   lines with no money at stake until the rate clears 52.4% with a sample large
   enough to mean something (n ≥ 500 for a ±4% band).

### What to stop doing

9. **Stop all calibration and uncertainty work.** Three phases, three genuine
   verified bugs, zero movement. The invariant is now exactly 1.0, coverage is
   0.66–0.70, Brier improved — and the 60–80% reliability band did not budge.
   Negative expected value to continue.
10. **Stop adding features.** Accuracy degrades monotonically as features are added.
    A ridge on one feature beats all 81.
11. **Stop reporting pseudo-line ROI.** Its value is a pure function of how the
    pseudo-line is built — moving from a season median to an L10-aware line collapses
    the apparent signal from AUC ~0.60 to 0.51–0.56. That artifact invited three
    phases of chasing.

---

## The strategic question worth asking

Every measurement points the same way: per-game NBA box-score outcomes are close to
unpredictable at this feature resolution. RMSE/σ is 1.10–1.17, R² against the
player's own running mean is **negative on all four stats**, and an oracle knowing
each player's true forward level buys only 13–16% over a rolling mean.

That does not mean the platform is worthless — it means the **pick generator** may be
the wrong product. The app already contains the parts that work without predicting
anything: game logs, rolling averages, home/away and matchup splits, opponent
context, defensive ranks, the research page. Those are honest and genuinely useful.

So there are three real options, and this is a decision to make deliberately rather
than by drift:

- **Rebuild** (Phase B). Demonstrated upside, bounded scope, still unproven against a
  real book.
- **Reposition the product** as research and analytics — present the data, drop the
  probability claims. Lowest risk, immediately honest, keeps everything already built.
- **Both** — ship research now, develop the pooled model behind a flag until it clears
  breakeven on paper.

I would do the third. It removes the harmful surface immediately, keeps the useful
surface, and gives the model a real bar to clear before it is trusted again.

---

## Exit criteria — how you know it worked

Do not re-enable pick generation until **all** of these hold:

- Pooled model beats EWMA5 / L10 / season median MAE on all four stats, out of sample.
- Median-line AUC ≥ 0.58 on held-out data.
- Reliability gap in the unclipped 60–80% band under ±5 points (currently ~+10.6).
- **≥ 500 paper picks against real closing lines at ≥ 52.4%**, with CLV logged.

The last one is the only one that is actually evidence. The first three are
necessary, not sufficient.

---

## Loose ends worth closing

- `autoGradePicks` / `autoGradeGamePredictions` in `client.ts` are called from
  HistoryPage / ParlayPage / GamesPage but those endpoints require `X-Service-Key`,
  so the frontend calls 403. Pre-existing; unrelated to the model.
- **OddsAPI quota exhausted**, BDL props/odds permanently gone since the Apr 2026
  tier downgrade, and BDL now 401s on current-season stats *and* injuries. The
  stats.nba.com fallback added on 2026-08-23 covers game logs — **injuries are still
  unsourced**, which matters because minutes projection is the highest-ceiling
  improvement (oracle minutes worth 13.6–20.2% MAE) and L10-minutes recovers exactly
  none of it.
- The ELO **game predictor** (`game_predictor.py`, 40 rows in `game_predictions`) was
  never in scope here. Its accuracy is unaudited — it may be fine, it may have
  analogous problems. Worth its own look before trusting it.
- `models/Stephen_Curry_model.pkl` is a lone survivor of the abandoned retrain. The
  fleet is otherwise empty and cold-trains on demand.

---

## Kickoff prompt for the next session

Start it in `/Users/hhabal/Downloads/Projects/NBA/EVAL`. Edit the bracketed line to
pick a strategic direction before pasting.

> Read `docs/NEXT_STEPS_2026-08-23.md` — it is the plan of record. Its evidence base
> is `docs/SUMMARY_model_investigation_2026-08-23.md` and the five reports indexed
> there; read the summary too, but don't re-derive its findings, they were verified
> independently.
>
> Context you need up front: a 5-phase investigation (2026-08-19 → 08-23) established
> that the per-player prop model has **no usable edge** — it loses to a 10-game
> rolling average on all four stats, and went **40-66 (37.7%)** on 106 real-line
> graded picks against a 52.4% breakeven. Root cause is **p/n = 1.35** (81 features,
> 60 training rows), not calibration. Do not reopen the calibration or uncertainty
> work; three phases of it fixed three real bugs and moved nothing.
>
> **Do Track A step 1 first, before anything else:** ~1,472 insertions / 363 deletions
> across 7 files plus 25 untracked files exist only in the working tree, uncommitted
> since 2026-08-06. Branch and commit them (do NOT push to `main` — it auto-deploys
> to Vercel). Confirm with me before pushing anything anywhere.
>
> [I want to: **ship the research surface now and build the pooled model behind a
> flag** — i.e. Track A + Track C, then Track B. / *swap in Rebuild-only or
> Reposition-only if you prefer*]
>
> Standing constraints: `NBA_EVAL_DISABLE_TF=1` on every python invocation; the test
> suite baseline is **449 passed / 20 failed / 3 skipped** and those 20 are
> pre-existing (`test_auth`, `test_game_log_cache`, `test_scenarios`,
> `test_supabase_auth`) — don't chase them, don't add new ones. Anything reading
> through `db.py` needs `load_dotenv(override=True)` or you'll get a misleading
> auth error. Read the `nba-model-gotchas` memory before editing `nba_evaluator.py`.
>
> Use Opus subagents for implementation, gate each track on its exit criteria, and
> don't commit or push without asking.
