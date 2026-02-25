# Design: Edge Cap (50%) + REB/AST Dampening Increase

**Date:** 2026-02-24
**Status:** Approved

## Problem

Analysis of 2026-02-23 losses and historical pick data revealed two systematic model failures:

1. **High-edge picks underperform coin flip.** Picks with |edge| 50–75% win at only 22–27%, well below random. The model becomes most confident precisely when it is most wrong. The API's `get_todays_best_bets()` has no max_edge filter, surfacing these picks freely.

2. **REB and AST are systematically over-predicted.** REB avg bias = +0.99 (over-predicted 60.5% of games). AST avg bias = +0.96 (over-predicted 67.6% of games). The existing `OVER_DAMPENING_BY_STAT` and `BIAS_CORRECTION_BY_STAT` constants are insufficient to correct this drift.

## Design

### Fix 1 — Edge Cap at 50% with Warning Flag (Full Pipeline)

**`nba_evaluator.py` — `LineEvaluator.evaluate()`**
Add `high_edge_warning: True` to the result dict when `abs(diff_pct) > 50`. No change to recommendation strength or label — purely additive.

**`api/services/prediction_service.py` — `get_todays_best_bets()`**
Add hard `max_edge=50.0` filter alongside existing `min_edge` check. High-edge picks never surface in best bets discovery.

**`api/schemas/prediction.py`**
Add `high_edge_warning: bool = False` to `LineEvaluation` schema.

**`frontend/src/api/client.ts`**
Add `high_edge_warning?: boolean` to `LineEvaluation` TypeScript interface.

**`frontend/src/pages/PlayerPage.tsx`**
Render an amber `"HIGH EDGE — VERIFY"` badge on line evaluation cards when `high_edge_warning` is true. Non-blocking — user can still save the pick.

### Fix 2 — REB/AST Dampening Increase (Post-Prediction Parameters, No Retraining)

**`nba_evaluator.py` — `MLPredictor` class constants:**

```python
BIAS_CORRECTION_BY_STAT = {
    'PTS': 0.15,
    'REB': 0.20,   # was 0.15
    'AST': 0.25,   # was 0.20
    'PRA': 0.12,
}

OVER_DAMPENING_BY_STAT = {
    'PTS': 0.08,
    'REB': 0.18,   # was 0.10
    'AST': 0.16,   # was 0.10
    'PRA': 0.08,
}
```

**Expected impact** on a typical REB overestimate (prediction=7.6, recent_avg=4.5, diff=+3.1):
- Before: ~1.0 unit total reduction → prediction ~6.6
- After: ~1.46 unit total reduction → prediction ~6.1

Closes the systematic +0.99 bias gap without flipping predictions negative.

## Files Changed

| File | Change |
|------|--------|
| `nba_evaluator.py` | Update `BIAS_CORRECTION_BY_STAT`, `OVER_DAMPENING_BY_STAT`; add `high_edge_warning` to `LineEvaluator.evaluate()` |
| `api/services/prediction_service.py` | Add `max_edge=50.0` filter in `get_todays_best_bets()` |
| `api/schemas/prediction.py` | Add `high_edge_warning: bool = False` to `LineEvaluation` |
| `frontend/src/api/client.ts` | Add `high_edge_warning?: boolean` to `LineEvaluation` interface |
| `frontend/src/pages/PlayerPage.tsx` | Amber warning badge when `high_edge_warning` is true |

## Verification

1. Run `python test_fixes.py` — confirm REB/AST predictions shift down by ~0.5–1.5 units on overestimates
2. Call `GET /api/bets/today` — confirm no picks with `abs(edge_pct) > 50` appear
3. Manually evaluate a line that would produce >50% edge on PlayerPage — confirm amber badge renders
4. Confirm PTS and PRA predictions are unchanged (no collateral dampening)
