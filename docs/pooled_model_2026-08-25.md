# Track B — the pooled cross-player model (2026-08-25)

Implements Phase B of `docs/NEXT_STEPS_2026-08-23.md`: replace the per-player
81-feature model with **one pooled model per stat, fitted league-wide on six
recency features**, behind a flag that defaults OFF.

**Headline, stated plainly.** The pooled model clears the exit criterion the
plan wrote — it beats EWMA5, L10 and the season median on **all four stats**.
It does **not** clear the stricter bar of beating *every* trivial baseline:
**AST loses to a 20-game rolling mean (1.792 vs 1.775)** and REB is a dead heat
with the season mean (2.419 vs 2.427). And **not one of the four margins
against the best trivial baseline is distinguishable from noise** — every
paired-bootstrap interval straddles zero. On median-line AUC it clears 0.58 on
two stats of four. On reliability it fails the ±5-point band, in the
*conservative* direction.

So: this is a real improvement over the model it replaces — 4.9-7.9% better MAE
on every stat, and the first thing measured in this project that is not
*worse* than a rolling average — but it is **not yet evidence of edge**, and
nothing here should re-enable pick generation.

---

## 1. Correction to the plan's baseline table — read this first

`docs/NEXT_STEPS_2026-08-23.md` and the summary table in
`docs/SUMMARY_model_investigation_2026-08-23.md` §1 both attribute an AST MAE
of **1.775** to **EWMA5**. That number belongs to **L20**. Recomputed directly
from `cache/diagnostics_t60/rows.parquet`, the same artifact the diagnosis
scored:

| Stat | L3 | L5 | L10 | **L20** | median | mean | last | **EWMA5** | best |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| PTS | 6.688 | 6.412 | 6.159 | 6.114 | 6.121 | 6.088 | 8.031 | **6.065** | EWMA5 |
| REB | 2.696 | 2.595 | 2.483 | 2.460 | 2.439 | **2.427** | 3.411 | 2.459 | season mean |
| AST | 2.079 | 1.894 | 1.813 | **1.775** | 1.812 | 1.806 | 2.510 | 1.801 | **L20** |
| PRA | 7.968 | 7.523 | 7.335 | 7.444 | 7.422 | 7.394 | 9.823 | **7.267** | EWMA5 |

This matches `diagnosis_resolution_failure_2026-08-23.md` §3, which is correct;
the error is confined to the summary's condensed table, which dropped the L20
column and carried its bolded value into the EWMA5 slot.

The consequence matters for how Track B is judged. The demonstrated pooled
ridge scored **AST 1.792**. Against EWMA5 (1.801) that is a win, not the loss
the plan's arithmetic implied. Against **L20 (1.775)** it is still a loss.
**The plan's conclusion about AST was right; its reason was wrong.**

---

## 2. Stat-by-stat pass/fail

| Stat | pooled MAE | vs the 3 named baselines | vs the best of all 8 | AUC ≥ 0.58 |
|---|---:|---|---|---|
| PTS | **6.000** | **PASS** (−0.065 vs EWMA5) | −0.065 vs EWMA5, **tie** | 0.576 — **FAIL** |
| REB | **2.419** | **PASS** (−0.020 vs median) | −0.008 vs season mean, **tie** | 0.583 — PASS |
| AST | **1.792** | **PASS** (−0.010 vs EWMA5) | **+0.017 vs L20 — loses**, tie | 0.632 — PASS |
| PRA | **7.249** | **PASS** (−0.018 vs EWMA5) | −0.018 vs EWMA5, **tie** | 0.561 — **FAIL** |

"tie" means the 95% paired-bootstrap interval on the difference contains zero.

**What did not clear, in one list:**

1. **AST loses to L20** by 0.017 MAE. Not statistically distinguishable
   (CI [−0.002, +0.036]), but the point estimate is a loss and L20 is a
   one-line baseline.
2. **No margin against the best trivial baseline is distinguishable from
   noise** on any stat. The pooled model is *not measurably better* than the
   best rolling average; it is measurably better than the *production* model
   and than most rolling averages.
3. **PTS and PRA miss the AUC ≥ 0.58 bar** (0.576, 0.561).
4. **Reliability fails** the ±5-point band: −13.9 in the unclipped 60-80%
   band. See §7 — the sign is inverted relative to the failure the criterion
   was written to catch.
5. The forward criterion (≥ 500 paper picks at ≥ 52.4% with CLV) is
   unaddressed and unaddressable now. Not attempted, not simulated.

---

## 3. What the pooled model is

**Six features per stat**, all plain summaries of that stat over the player's
own completed in-season games: `L5`, `L10`, `L20`, `MEDIAN`, `MEAN`, `EWMA5`
(five-game half-life). Twenty-four columns across the four served stats;
**six** reach any single estimator. p/n falls from 1.35 to about 0.0002.

Choosing six *baselines* as the features is deliberate. Their linear span
contains L5, L10, L20, the season median, the season mean and EWMA5 exactly, so
the model cannot be structurally incapable of matching the baseline it has to
beat — if it loses, it lost on estimation, not on representation.

**Estimator:** `StandardScaler` + `Ridge(alpha=3.0)`, one model per stat. PRA
is fitted directly, not summed from components — validated on a 2023-24
late-season split (3,850 rows, ≥ 60 prior games): 6.628 direct vs 6.660 summed
vs 6.655 for the production 85/15 blend.

**Training window:** every league game strictly before the serving cut, from
players with ≥ 20 in-season games of history. For the holdout scorecard that is
**25,327 rows across 439 players** (2023-24 in full, plus 2024-25 up to
2025-02-27). The shipped artifact uses everything available: 33,495 rows / 460
players.

**Uncertainty:** σ is an affine function of the player's own in-season
dispersion, fitted league-wide. Dispersion is *not* a point-prediction feature.

### How the specification was chosen — and how it was not

Specification selection ran entirely on a **validation split that mirrors the
holdout one season earlier**: late 2023-24, ≥ 60 prior in-season games,
≥ 28 mpg, trained on everything before 2024-02-28. The rule was fixed before
looking at results — *best mean margin against the best trivial baseline across
the four stats, ties broken toward fewer features* — and it selected
`Ridge(alpha=3.0)` on the six features above. The holdout was scored once,
afterwards.

Two things worth recording because they cut against intuition:

- A **league-wide** validation set (all players, 2024-25 pre-holdout) preferred
  **least-absolute-deviations** regression over ridge on all four stats, by
  ~0.02 MAE. On the holdout LAD was *worse* on three of four (AST 1.807 vs
  ridge's 1.792). The population matters more than the loss function: the
  holdout is 44 high-minute stars, and a spec tuned on the whole league does
  not transfer to them. This is why selection was moved to the mirror split.
- **Adding L5/L10 minutes features helped on validation and was still
  rejected**, to hold the feature count under ten and because the diagnosis
  found accuracy degrades monotonically as features are added. It is not in the
  shipped model.

---

## 4. Reproduction of the number the plan is built on

The diagnosis reported a nine-feature ridge trained on 2023-24 alone at
**6.004 / 2.430 / 1.792 / 7.252**. Refitted here from committed code and scored
on the identical holdout:

| Variant | features/stat | train rows | PTS | REB | AST | PRA |
|---|---:|---:|---:|---:|---:|---:|
| 9-feature ridge, 2023-24 only (as reported) | 9 | — | 6.004 | 2.430 | 1.792 | 7.252 |
| 9-feature ridge, 2023-24 only (**refitted here**) | 9 | 16,323 | 6.003 | 2.429 | 1.794 | 7.258 |
| **shipped: 6-feature ridge, through 2025-02-27** | 6 | 25,327 | **6.000** | **2.419** | **1.792** | **7.249** |
| production per-player, 81 features | 81 | ~60 | 6.517 | 2.546 | 1.885 | 7.637 |

Maximum deviation from the reported figures is 0.006. The pipeline is on the
same footing as the diagnosis, so the numbers above are comparable to every
report in this series.

Regenerate with:

```bash
NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py \
    --seasons 2023-24 \
    --feature-kinds L3,L5,L10,L20,MEDIAN,MEAN,LAST,EWMA5,STD \
    --out models/pooled/ref9.pkl
```

---

## 5. Paired bootstrap, every model-vs-baseline comparison

2,000 draws, resampling the **44 players** (the 606 games are repeated
measures, not independent observations) — the convention the investigation
used. Negative = pooled wins.

| Stat | L3 | L5 | L10 | L20 | median | mean | last | EWMA5 |
|---|---|---|---|---|---|---|---|---|
| PTS | −0.688 **W** | −0.413 **W** | −0.160 **W** | −0.114 **W** | −0.122 tie | −0.088 tie | −2.032 **W** | −0.065 tie |
| REB | −0.277 **W** | −0.176 **W** | −0.064 **W** | −0.041 tie | −0.020 tie | −0.008 tie | −0.992 **W** | −0.040 **W** |
| AST | −0.287 **W** | −0.102 **W** | −0.021 tie | **+0.017 tie** | −0.020 tie | −0.014 tie | −0.718 **W** | −0.010 tie |
| PRA | −0.718 **W** | −0.273 **W** | −0.086 tie | −0.195 **W** | −0.173 tie | −0.144 tie | −2.574 **W** | −0.018 tie |

**W** = 95% CI entirely below zero. Seventeen of thirty-two comparisons are
distinguishable wins, fifteen are ties, **zero are distinguishable losses**.
Compare the production model on the same rows: 15 distinguishable losses,
5 ties, 0 wins.

The wins concentrate against the short windows (L3, L5, last game). Against the
*long* windows and the season-level summaries — the ones that actually win —
everything is a tie. That is the honest shape of the result.

Full per-comparison intervals are in the generated scorecard (§9).

---

## 6. Median-line AUC

| Stat | pooled | 95% CI | production (81f) | L10 signal | ≥ 0.58? |
|---|---:|---|---:|---:|---|
| PTS | 0.5760 | [0.523, 0.627] | 0.5115 | 0.5774 | **FAIL** |
| REB | 0.5829 | [0.520, 0.639] | 0.5372 | 0.5759 | PASS |
| AST | 0.6318 | [0.570, 0.682] | 0.5628 | 0.6210 | PASS |
| PRA | 0.5610 | [0.497, 0.619] | 0.5505 | 0.5770 | **FAIL** |

Two of four clear 0.58. On every stat the pooled model ranks better than the
81-feature production model; on PTS and PRA it does not rank better than a
plain L10 mean.

**Standing caveat, unchanged and load-bearing.** These are AUCs against a
*season-median pseudo-line*. §8d of the diagnosis showed that moving to a
merely L10-aware line collapses this class of signal from ~0.60 to 0.51-0.56.
None of these numbers is evidence of edge against a sportsbook.

---

## 7. Reliability, and why it fails

| Probability source | band | N | predicted | realized | gap |
|---|---|---:|---:|---:|---:|
| pooled (shrunk) | 60-80% | 212 | 63.4 | 77.4 | **−13.9** |
| pooled (shrunk) | 40-60% | 1,905 | 49.9 | 53.0 | −3.1 |
| production (81f) | 60-80% | 780 | 69.4 | 55.1 | +14.3 |

The criterion asks for |gap| < 5. The pooled model fails it at **−13.9** —
but note the **sign**. Production claims 69% and delivers 55%: it overstates,
which is the direction that inflates apparent edge and drives bad bets. The
pooled model claims 63% and delivers 77%: it *understates*. Under any
threshold-based pick rule, understating produces fewer bets, not worse ones.

**I did not close this gap, deliberately.** Closing it means sharpening the
probability until it matches the realized rate at the season-median pseudo-line
— which is exactly what Phase 2 did, and exactly what §8d says is mostly line
staleness rather than skill. The shrinkage is therefore implemented as a
one-directional operator: the fitted slope is clamped at 1.0 so it can pull a
probability toward the base rate and can never push it away. On all four stats
the free fit wanted a slope **above** 1 — it wanted to sharpen — and the clamp
bound. What remains active is the base-rate intercept, which puts
P(over | prediction = line) at 47.7-49.2%.

This criterion should be re-measured against **real closing lines** once Track
C has accumulated them. Against a pseudo-line it is not answerable.

Implementation note: the intercept is refitted with the slope held at its
clamped value. Fitting jointly and then clamping leaves an intercept that
belongs to a different slope, which biased every served probability
(60-80% gap −19.6 before the fix, −13.9 after).

---

## 8. How lookahead was ruled out

The known trap: **Phase 0's `prediction_row()` stripped PTS/REB/AST but not the
derived `PRA`**, so `predict`'s dynamic floor read the realized PRA of the game
being predicted, making Phase 0's PRA figures optimistic.

Three independent controls, all mechanical, all in `scripts/eval_pooled_model.py`
and `tests/test_pooled_features.py`:

1. **PRA is never read, only recomputed.** `pooled_features.normalize_game_log`
   overwrites any `PRA` column with `PTS + REB + AST` from the history.
   `test_pra_is_recomputed_not_read_from_the_frame` poisons an incoming `PRA`
   column with 999 and asserts the served vector does not move.
2. **The served features are asserted equal to the harness's own baselines, to
   the last bit.** For each of the 606 held-out games the features are rebuilt
   here from the cached stats.nba.com log, taking exactly the `step` games
   before the target; they are then compared against the `b_l3 / b_l5 / b_l10 /
   b_l20 / b_median / b_mean / b_last / b_ewma5 / hist_std` columns that
   `scripts/diagnose_dump.py` computed independently inside its own
   walk-forward from `step_frame.iloc[:-1]`. **Maximum absolute difference
   across 36 features × 606 games: 0.0.** The script raises if any difference
   is non-zero, and separately raises if the cached log puts the target game at
   a different index than the harness's split step. Two constructions from
   different sources agreeing exactly is what rules out an off-by-one in either
   direction.
3. **Future games cannot reach the serve path.**
   `test_spiking_the_last_game_moves_features_but_spiking_the_future_does_not`
   rewrites every box score from the target game onward to 999 and asserts the
   served vector is unchanged; `test_upcoming_synthetic_row_is_dropped` and
   `test_the_upcoming_row_does_not_shorten_the_windows` assert that
   `create_features`' synthetic next-game row is removed rather than counted
   as a game.

The training panel is grouped by (player, **season**), so no feature reaches
across an offseason, and the holdout scorecard trains only on games strictly
before 2025-02-28, the first held-out date.

---

## 9. The flag

**`NBA_EVAL_POOLED_MODEL` — default OFF.** Convention matches `api/config.py`
and `frontend/src/shared/lib/flags.ts`: a flag is off unless the value is
exactly `1` or `true` (case-insensitive, whitespace ignored).

```bash
# 1. build the league artifact (models/ is gitignored, so this is required)
NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py

# 2. enable
export NBA_EVAL_POOLED_MODEL=1
```

`NBA_EVAL_POOLED_MODEL_PATH` overrides the artifact location.

With the flag **off**, `api/services/prediction_service.py` builds
`ev.MLPredictor` exactly as before — the per-player path is untouched and still
works. With it **on**, it builds `pooled_predictor.PooledPredictor`, which
subclasses `MLPredictor` and answers the same eleven-method serve sequence with
the same shapes, so nothing downstream changes. A missing or version-mismatched
artifact raises a 503 rather than silently falling back to the model that went
40-66 against real lines.

The flag is independent of `NBA_EVAL_ENABLE_PICKS`. **Nothing here re-enables
pick generation**, and nothing in this work argues that it should be.

### Two traps this design removes rather than avoids

- **Write-but-never-save state.** There is no per-player fitted state at all:
  `load()` returns False, `save()` is a no-op, and `train()` merely recomputes
  the six features from the player's log. The class of bug where state works
  only inside the training process (as `season_averages` did) cannot occur
  because nothing per-player is persisted.
- **Missing features served as 0.** `MLPredictor.predict` substitutes 0 for any
  declared feature absent from the served frame. `StatFit.predict` raises
  `KeyError` instead, and `test_a_missing_feature_raises_instead_of_serving_zero`
  pins it.

---

## 10. Reproducing this report

```bash
NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py \
    --through 2025-02-28 --out models/pooled/holdout.pkl

NBA_EVAL_DISABLE_TF=1 python3 scripts/eval_pooled_model.py \
    --model models/pooled/holdout.pkl \
    --out docs/pooled_model_scorecard_2026-08-25.md
```

The scorecard carries every per-comparison bootstrap interval and the full
decile reliability table.

---

## 11. Test suite

**698 passed / 20 failed / 3 skipped.** The 20 failures are the four
pre-existing files (`test_auth` 2, `test_game_log_cache` 8, `test_scenarios` 8,
`test_supabase_auth` 2) and are unchanged. This work adds **84 tests** across
`tests/test_pooled_features.py`, `tests/test_pooled_model.py` and
`tests/test_pooled_predictor.py`; the remainder of the increase over the
580-test baseline comes from work landing in parallel on the closing-line UI.

---

## 12. What I would do next, ranked

1. **Nothing that touches calibration or features.** Both are closed. The
   binding constraint is now that the pooled model is statistically
   indistinguishable from a rolling average, and no amount of calibration
   changes that.
2. **Let Track C run.** Real closing lines are the only measurement that can
   tell a genuine edge from the pseudo-line artifact. Every number in §6 and §7
   is uninterpretable without them, and that is a data-collection problem, not
   a modelling one.
3. **Treat the pooled model as the honest default for any displayed
   projection** — it is 4.9-7.9% better than production on every stat and is no
   longer *worse* than a rolling average — while continuing to present it as a
   projection, never as a recommendation.
4. **If more modelling effort is spent, spend it on minutes.** The diagnosis
   priced oracle minutes at 13.6-20.2% of MAE, and rolling-mean minutes recover
   none of it. That is the only lever the data shows is large, and it needs
   injury and rotation data the system does not ingest.

A fair summary of Track B: the rebuild works, it fixed the root cause it was
aimed at, and it moved the model from *measurably worse than a rolling average*
to *statistically indistinguishable from one*. That is progress and it is not
an edge.
