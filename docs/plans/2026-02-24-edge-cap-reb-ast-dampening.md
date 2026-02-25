# Edge Cap + REB/AST Dampening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** (1) Filter picks with |edge| > 50% from best bets and show a warning badge on PlayerPage; (2) Increase REB/AST post-prediction dampening to correct ~+1 unit systematic over-prediction bias.

**Architecture:** All changes are post-prediction — no model retraining. Fix 1 adds a `high_edge_warning` flag in `LineEvaluator` (backend) and a filter in `get_todays_best_bets()` (API service), then renders an amber badge (frontend). Fix 2 bumps two class-level dicts in `MLPredictor` that are applied at inference time.

**Tech Stack:** Python 3.x (nba_evaluator.py, FastAPI service, Pydantic schema), TypeScript/React (frontend client interface + PlayerPage component)

---

### Task 1: Increase REB/AST dampening constants

**Files:**
- Modify: `nba_evaluator.py:1971-1985`

**Step 1: Locate the two dicts**

Open `nba_evaluator.py`. Search for `BIAS_CORRECTION_BY_STAT` — it's at line ~1971. The two dicts look like:

```python
BIAS_CORRECTION_BY_STAT = {
    'PTS': 0.15,
    'REB': 0.15,
    'AST': 0.20,
    'PRA': 0.12,
}

OVER_DAMPENING_BY_STAT = {
    'PTS': 0.08,
    'REB': 0.10,
    'AST': 0.10,
    'PRA': 0.08,
}
```

**Step 2: Update both dicts**

Change to:

```python
BIAS_CORRECTION_BY_STAT = {
    'PTS': 0.15,
    'REB': 0.20,   # increased from 0.15 — corrects +0.99 systematic over-prediction
    'AST': 0.25,   # increased from 0.20 — corrects +0.96 systematic over-prediction
    'PRA': 0.12,
}

OVER_DAMPENING_BY_STAT = {
    'PTS': 0.08,
    'REB': 0.18,   # increased from 0.10
    'AST': 0.16,   # increased from 0.10
    'PRA': 0.08,
}
```

**Step 3: Quick sanity check — run a prediction and confirm REB/AST moved down, PTS unchanged**

```bash
python nba_evaluator.py --player "Jarrett Allen" --stat REB --line 10.5
```

Expected: prediction should be slightly lower than before. PTS predictions for another player should be identical.

**Step 4: Commit**

```bash
git add nba_evaluator.py
git commit -m "fix: increase REB/AST dampening to correct +0.99/+0.96 systematic over-prediction bias"
```

---

### Task 2: Add `high_edge_warning` to `LineEvaluator.evaluate()`

**Files:**
- Modify: `nba_evaluator.py:2457-2465` (the `result = {...}` block in `LineEvaluator.evaluate()`)

**Step 1: Locate the result dict assembly**

In `LineEvaluator.evaluate()` (~line 2457), the result dict is built as:

```python
result = {
    'stat': stat,
    'line': line,
    'prediction': prediction,
    'difference': diff,
    'diff_pct': diff_pct,
    'recommendation': recommendation,
    'strength': strength,
}
```

**Step 2: Add `high_edge_warning` field**

```python
result = {
    'stat': stat,
    'line': line,
    'prediction': prediction,
    'difference': diff,
    'diff_pct': diff_pct,
    'recommendation': recommendation,
    'strength': strength,
    'high_edge_warning': abs(diff_pct) > 50,  # picks >50% edge hit <27% historically
}
```

**Step 3: Manual smoke test**

```bash
python nba_evaluator.py --player "LeBron James" --pts-line 15.0
```

A line set very far below the prediction (e.g. 15.0 for a player predicted at 28) should now log `high_edge_warning: True` if you add a quick print. Alternatively confirm by running with a normal line — `high_edge_warning` should be False.

**Step 4: Commit**

```bash
git add nba_evaluator.py
git commit -m "fix: add high_edge_warning flag to LineEvaluator when |edge| > 50%"
```

---

### Task 3: Add `max_edge=50` filter to `get_todays_best_bets()` in API service

**Files:**
- Modify: `api/services/prediction_service.py:469`

**Step 1: Locate the edge filter**

In `prediction_service.py` around line 469:

```python
# Only include if edge is significant
if abs(edge_pct) >= min_edge:
```

**Step 2: Add max_edge guard**

```python
# Only include if edge is within the reliable range (>50% edge picks hit <27% historically)
if abs(edge_pct) >= min_edge and abs(edge_pct) <= 50.0:
```

**Step 3: Start the API and verify best bets no longer return high-edge picks**

```bash
./start_api.sh
# In another terminal:
curl "http://localhost:8000/api/bets/today?min_edge=5&limit=20" | python -m json.tool | grep edge_pct
```

Expected: no `edge_pct` value above 50.0 in the response.

**Step 4: Commit**

```bash
git add api/services/prediction_service.py
git commit -m "fix: cap best bets at max 50% edge — picks above this threshold hit <27% historically"
```

---

### Task 4: Add `high_edge_warning` to Pydantic schema

**Files:**
- Modify: `api/schemas/prediction.py:83-95`

**Step 1: Locate `LineEvaluation` schema**

Around line 83:

```python
class LineEvaluation(BaseModel):
    stat: str
    line: float
    prediction: float
    difference: float
    diff_pct: float
    recommendation: str  # e.g., "STRONG OVER", "LEAN UNDER"
    strength: str  # "HIGH", "MODERATE", "SLIGHT"
    prob_over: Optional[float] = None
    confidence: Optional[float] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
```

**Step 2: Add the new field**

```python
class LineEvaluation(BaseModel):
    stat: str
    line: float
    prediction: float
    difference: float
    diff_pct: float
    recommendation: str  # e.g., "STRONG OVER", "LEAN UNDER"
    strength: str  # "HIGH", "MODERATE", "SLIGHT"
    prob_over: Optional[float] = None
    confidence: Optional[float] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    high_edge_warning: bool = False  # True when |edge| > 50% — historically unreliable
```

**Step 3: Verify API serializes the field**

```bash
curl -X POST "http://localhost:8000/api/players/evaluate-line" \
  -H "Content-Type: application/json" \
  -d '{"player_name": "LeBron James", "stat": "PTS", "line": 10.0}' | python -m json.tool | grep high_edge
```

Expected: `"high_edge_warning": true` (since predicting ~25+ PTS vs line 10.0 is >50% edge).

**Step 4: Commit**

```bash
git add api/schemas/prediction.py
git commit -m "feat: add high_edge_warning field to LineEvaluation schema"
```

---

### Task 5: Add `high_edge_warning` to TypeScript `LineEvaluation` interface

**Files:**
- Modify: `frontend/src/api/client.ts:60-72`

**Step 1: Locate the interface**

Around line 60:

```typescript
export interface LineEvaluation {
  stat: string
  line: number
  prediction: number
  difference: number
  diff_pct: number
  recommendation: string
  strength: string
  prob_over?: number
  confidence?: number
  range_low?: number
  range_high?: number
}
```

**Step 2: Add the field**

```typescript
export interface LineEvaluation {
  stat: string
  line: number
  prediction: number
  difference: number
  diff_pct: number
  recommendation: string
  strength: string
  prob_over?: number
  confidence?: number
  range_low?: number
  range_high?: number
  high_edge_warning?: boolean
}
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | grep -i error
```

Expected: no TypeScript errors.

**Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add high_edge_warning to LineEvaluation TypeScript interface"
```

---

### Task 6: Render amber warning badge in `EvalResult` component on PlayerPage

**Files:**
- Modify: `frontend/src/pages/PlayerPage.tsx:402-443` (the `EvalResult` return block)

**Step 1: Locate the recommendation pill line**

Around line 406-408:

```tsx
<div className="flex items-center gap-2 mb-3 sm:mb-4">
  <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>{evaluation.recommendation}</div>
  <span className="text-xs text-text-muted font-mono">{evaluation.stat}</span>
</div>
```

**Step 2: Add the warning badge after the stat span**

```tsx
<div className="flex items-center gap-2 mb-3 sm:mb-4 flex-wrap">
  <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>{evaluation.recommendation}</div>
  <span className="text-xs text-text-muted font-mono">{evaluation.stat}</span>
  {evaluation.high_edge_warning && (
    <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
      High Edge — Verify
    </span>
  )}
</div>
```

**Step 3: Start the frontend dev server and test visually**

```bash
cd frontend && npm run dev
```

Look up a player and enter a line far below the prediction (e.g. LeBron James, PTS, line 10.0). The amber `High Edge — Verify` badge should appear next to the recommendation pill. For a normal line it should not appear.

**Step 4: Commit**

```bash
git add frontend/src/pages/PlayerPage.tsx
git commit -m "feat: show amber 'High Edge — Verify' warning badge when edge > 50%"
```

---

## Verification Checklist

- [ ] Run `python test_fixes.py` — REB/AST predictions shift down by 0.5–1.5 units on overestimates vs before
- [ ] `GET /api/bets/today` — no picks with `abs(edge_pct) > 50` in response
- [ ] `POST /api/players/evaluate-line` with a low line — `high_edge_warning: true` in JSON
- [ ] `POST /api/players/evaluate-line` with a normal line — `high_edge_warning: false`
- [ ] PlayerPage with extreme line — amber badge visible
- [ ] PlayerPage with normal line — no badge
- [ ] PTS predictions unchanged (verify same output before/after on a PTS line)
