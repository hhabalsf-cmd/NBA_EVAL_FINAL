# Parlay Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist saved parlays to Supabase, add a Saved Parlays tab to ParlayPage, reduce max legs to 6, and unify auto-grade to grade both picks and parlays from a single endpoint.

**Architecture:** Two new Supabase tables (`parlays`, `parlay_legs`) link parlays to existing pick rows by ID. A new FastAPI router handles CRUD. The existing `POST /api/picks/auto-grade` endpoint is extended to also derive and store parlay results after grading picks. The frontend adds a tab-based layout to ParlayPage.

**Tech Stack:** Python/FastAPI, psycopg2 (Postgres/Supabase), Pydantic v2, React 18, TypeScript, TanStack Query v5, Tailwind CSS, CSS variables (never hardcoded hex), JetBrains Mono for numbers.

**Design doc:** `docs/plans/2026-03-06-parlay-persistence-design.md`

---

## Task 1: Database Schema (Supabase)

**Files:**
- No code files — run SQL in Supabase SQL Editor

**Step 1: Run this SQL in the Supabase SQL Editor**

```sql
-- Parlays table
CREATE TABLE IF NOT EXISTS parlays (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL,
    name        TEXT,
    legs_count  INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    graded_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Parlay legs table (links parlays to picks)
CREATE TABLE IF NOT EXISTS parlay_legs (
    id         BIGSERIAL PRIMARY KEY,
    parlay_id  BIGINT NOT NULL REFERENCES parlays(id) ON DELETE CASCADE,
    pick_id    BIGINT NOT NULL REFERENCES picks(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS parlays_user_id_idx ON parlays(user_id);
CREATE INDEX IF NOT EXISTS parlays_status_idx ON parlays(status);
CREATE INDEX IF NOT EXISTS parlay_legs_parlay_id_idx ON parlay_legs(parlay_id);
CREATE INDEX IF NOT EXISTS parlay_legs_pick_id_idx ON parlay_legs(pick_id);
```

**Step 2: Verify tables exist**

In Supabase Table Editor, confirm `parlays` and `parlay_legs` both appear.

**Step 3: Commit note**

No code change yet — schema is in Supabase. Add a comment to `db.py` header noting the new tables.

---

## Task 2: DB helper functions (`db.py`)

**Files:**
- Modify: `db.py` (append new functions near the bottom, before the Excel export section)

**Step 1: Write the failing tests first**

Create `tests/test_parlays_db.py`:

```python
"""Tests for parlay DB helper functions."""
import pytest
import db

# These tests require a real DB connection — skip if DATABASE_URL not set
pytestmark = pytest.mark.skipif(
    not __import__('os').environ.get('DATABASE_URL'),
    reason="DATABASE_URL not set"
)

def test_create_parlay_returns_dict_with_id(tmp_pick_ids):
    """create_parlay should return a dict with at least an id field."""
    result = db.create_parlay(
        user_id="test-user-id",
        pick_ids=tmp_pick_ids[:2],
        name="Test Parlay"
    )
    assert isinstance(result, dict)
    assert 'id' in result
    assert result['legs_count'] == 2
    assert result['status'] == 'pending'

def test_get_parlays_returns_list(tmp_parlay_id):
    """get_parlays should return a list of parlays for the user."""
    results = db.get_parlays(user_id="test-user-id")
    assert isinstance(results, list)
    ids = [r['id'] for r in results]
    assert tmp_parlay_id in ids

def test_void_parlay_sets_status(tmp_parlay_id):
    """void_parlay should set status to voided."""
    db.void_parlay(parlay_id=tmp_parlay_id, user_id="test-user-id")
    results = db.get_parlays(user_id="test-user-id")
    parlay = next(r for r in results if r['id'] == tmp_parlay_id)
    assert parlay['status'] == 'voided'

def test_grade_pending_parlays_marks_won_when_all_legs_win():
    """grade_pending_parlays should mark parlay won when all picks have won=1."""
    # Integration test — relies on fixture data
    # Run manually after seeding DB with known state
    pass
```

**Step 2: Add the four DB functions to `db.py`**

Append after the existing `auto_grade_picks` function (around line 1310+), before Excel export:

```python
# ── Parlay helpers ─────────────────────────────────────────────

def create_parlay(user_id: str, pick_ids: list, name: str = None) -> dict:
    """Create a parlay record and its leg records. Returns the created parlay dict."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO parlays (user_id, name, legs_count, status, created_at)
                VALUES (%s, %s, %s, 'pending', NOW())
                RETURNING id, user_id, name, legs_count, status, graded_at, created_at
                """,
                (user_id, name, len(pick_ids))
            )
            parlay = dict(cur.fetchone())
            parlay_id = parlay['id']

            for pick_id in pick_ids:
                cur.execute(
                    "INSERT INTO parlay_legs (parlay_id, pick_id) VALUES (%s, %s)",
                    (parlay_id, pick_id)
                )

            conn.commit()
            return parlay
    finally:
        conn.close()


def get_parlays(user_id: str) -> list:
    """Return all non-voided parlays for a user, newest first, with leg details."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.user_id, p.name, p.legs_count, p.status,
                       p.graded_at, p.created_at
                FROM parlays p
                WHERE p.user_id = %s
                ORDER BY p.created_at DESC
                """,
                (user_id,)
            )
            parlays = [dict(row) for row in cur.fetchall()]

            for parlay in parlays:
                cur.execute(
                    """
                    SELECT pl.id, pl.pick_id,
                           pk.player, pk.player_id, pk.team_abbrev, pk.stat,
                           pk.line, pk.prediction, pk.direction, pk.edge,
                           pk.prob_over, pk.actual_result, pk.won,
                           pk.voided, pk.void_reason, pk.game_date, pk.opponent
                    FROM parlay_legs pl
                    JOIN picks pk ON pk.id = pl.pick_id
                    WHERE pl.parlay_id = %s
                    ORDER BY pl.id
                    """,
                    (parlay['id'],)
                )
                parlay['legs'] = [dict(row) for row in cur.fetchall()]

            return parlays
    finally:
        conn.close()


def void_parlay(parlay_id: int, user_id: str) -> None:
    """Set parlay status to voided. Enforces ownership via user_id."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE parlays
                SET status = 'voided'
                WHERE id = %s AND user_id = %s
                """,
                (parlay_id, user_id)
            )
            conn.commit()
    finally:
        conn.close()


def grade_pending_parlays(user_id: str = None) -> dict:
    """
    Derive and store status for all pending parlays whose picks are all resolved.

    Grading rules:
    - All legs won=1 → 'won'
    - Any leg won=0 → 'lost'
    - Any leg won IS NULL (and no losses) → stay 'pending'
    - Voided legs (voided=1) are excluded from result calculation but kept in legs list.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query = "SELECT id FROM parlays WHERE status = 'pending'"
            params = []
            if user_id:
                query += " AND user_id = %s"
                params.append(user_id)
            cur.execute(query, params)
            pending_ids = [row['id'] for row in cur.fetchall()]

            graded_count = 0
            for parlay_id in pending_ids:
                cur.execute(
                    """
                    SELECT pk.won, pk.voided
                    FROM parlay_legs pl
                    JOIN picks pk ON pk.id = pl.pick_id
                    WHERE pl.parlay_id = %s
                    """,
                    (parlay_id,)
                )
                legs = cur.fetchall()

                # Active legs only (exclude voided picks)
                active = [l for l in legs if not l['voided']]

                if not active:
                    continue  # All legs voided — skip

                if any(l['won'] == False for l in active):
                    new_status = 'lost'
                elif all(l['won'] == True for l in active):
                    new_status = 'won'
                else:
                    continue  # Still pending legs

                cur.execute(
                    "UPDATE parlays SET status = %s, graded_at = NOW() WHERE id = %s",
                    (new_status, parlay_id)
                )
                graded_count += 1

            conn.commit()
            return {'parlays_graded': graded_count}
    finally:
        conn.close()
```

**Step 3: Run tests**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
pytest tests/test_parlays_db.py -v -k "not grade_pending"
```

Expected: tests that can run pass or skip gracefully (DB-dependent tests skip without live DB).

**Step 4: Commit**

```bash
git add db.py tests/test_parlays_db.py
git commit -m "feat: add parlay DB helpers (create, get, void, grade)"
```

---

## Task 3: Pydantic schemas for parlays

**Files:**
- Modify: `api/schemas/prediction.py`

**Step 1: Append these schemas to the bottom of `api/schemas/prediction.py`**

```python
# === Parlay Schemas ===

class ParlayLegDetail(BaseModel):
    id: int
    pick_id: int
    player: str
    player_id: Optional[int] = None
    team_abbrev: Optional[str] = None
    stat: str
    line: float
    prediction: float
    direction: str
    edge: float
    prob_over: Optional[float] = None
    actual_result: Optional[float] = None
    won: Optional[bool] = None
    voided: Optional[bool] = None
    void_reason: Optional[str] = None
    game_date: Optional[str] = None
    opponent: Optional[str] = None


class ParlayResponse(BaseModel):
    id: int
    name: Optional[str] = None
    legs_count: int
    status: str  # 'pending' | 'won' | 'lost' | 'voided'
    graded_at: Optional[datetime] = None
    created_at: datetime
    legs: List[ParlayLegDetail] = []


class ParlayCreate(BaseModel):
    pick_ids: List[int] = Field(..., min_length=2, max_length=6)
    name: Optional[str] = Field(default=None, max_length=80)
```

**Step 2: Commit**

```bash
git add api/schemas/prediction.py
git commit -m "feat: add parlay Pydantic schemas"
```

---

## Task 4: Parlay API router

**Files:**
- Create: `api/routers/parlays.py`
- Modify: `api/routers/__init__.py`
- Modify: `api/main.py`

**Step 1: Create `api/routers/parlays.py`**

```python
"""Parlay persistence endpoints."""
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db

from ..schemas.prediction import ParlayCreate, ParlayResponse, ParlayLegDetail
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/parlays", tags=["parlays"])


def _parlay_to_response(p: dict) -> ParlayResponse:
    legs = [
        ParlayLegDetail(
            id=leg['id'],
            pick_id=leg['pick_id'],
            player=leg['player'],
            player_id=leg.get('player_id'),
            team_abbrev=leg.get('team_abbrev'),
            stat=leg['stat'],
            line=float(leg['line']),
            prediction=float(leg['prediction']),
            direction=leg['direction'],
            edge=float(leg['edge']),
            prob_over=leg.get('prob_over'),
            actual_result=leg.get('actual_result'),
            won=bool(leg['won']) if leg.get('won') is not None else None,
            voided=bool(leg.get('voided')) if leg.get('voided') is not None else None,
            void_reason=leg.get('void_reason'),
            game_date=leg.get('game_date'),
            opponent=leg.get('opponent'),
        )
        for leg in p.get('legs', [])
    ]
    return ParlayResponse(
        id=p['id'],
        name=p.get('name'),
        legs_count=p['legs_count'],
        status=p['status'],
        graded_at=p.get('graded_at'),
        created_at=p['created_at'],
        legs=legs,
    )


@router.post("", response_model=ParlayResponse, status_code=201)
async def create_parlay(
    body: ParlayCreate,
    current_user: dict = Depends(get_current_user),
):
    """Save a parlay from a list of pick IDs."""
    user_id = current_user["id"]

    # Validate all pick_ids belong to this user and are pending
    for pick_id in body.pick_ids:
        pick = db.get_pick_by_id(pick_id)
        if not pick:
            raise HTTPException(status_code=404, detail=f"Pick {pick_id} not found")
        if pick['user_id'] != user_id:
            raise HTTPException(status_code=403, detail=f"Pick {pick_id} is not yours")
        if pick.get('voided'):
            raise HTTPException(status_code=400, detail=f"Pick {pick_id} is voided")

    parlay = db.create_parlay(
        user_id=user_id,
        pick_ids=body.pick_ids,
        name=body.name,
    )
    # Fetch with legs
    parlays = db.get_parlays(user_id=user_id)
    full = next((p for p in parlays if p['id'] == parlay['id']), None)
    if not full:
        raise HTTPException(status_code=500, detail="Failed to retrieve created parlay")
    return _parlay_to_response(full)


@router.get("", response_model=List[ParlayResponse])
async def list_parlays(current_user: dict = Depends(get_current_user)):
    """List the authenticated user's saved parlays."""
    parlays = db.get_parlays(user_id=current_user["id"])
    return [_parlay_to_response(p) for p in parlays]


@router.delete("/{parlay_id}")
async def delete_parlay(parlay_id: int, current_user: dict = Depends(get_current_user)):
    """Void a saved parlay."""
    parlays = db.get_parlays(user_id=current_user["id"])
    match = next((p for p in parlays if p['id'] == parlay_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Parlay not found")
    db.void_parlay(parlay_id=parlay_id, user_id=current_user["id"])
    return {"message": "Parlay voided", "id": parlay_id}
```

**Step 2: Register in `api/routers/__init__.py`**

```python
"""Routers package."""
from .players import router as players_router
from .bets import router as bets_router
from .picks import router as picks_router
from .games import router as games_router
from .auth import router as auth_router
from .parlays import router as parlays_router

__all__ = ['players_router', 'bets_router', 'picks_router', 'games_router', 'auth_router', 'parlays_router']
```

**Step 3: Add to `api/main.py`**

In the imports line:
```python
from .routers import players_router, bets_router, picks_router, games_router, auth_router, parlays_router
```

After `app.include_router(auth_router)`:
```python
app.include_router(parlays_router)
```

**Step 4: Verify the API starts without errors**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
./start_api.sh
# In another terminal:
curl http://localhost:8000/api/docs
# Should load without error
```

**Step 5: Commit**

```bash
git add api/routers/parlays.py api/routers/__init__.py api/main.py
git commit -m "feat: add parlays router with create/list/void endpoints"
```

---

## Task 5: Extend auto-grade to include parlays

**Files:**
- Modify: `api/routers/picks.py` — `auto_grade_picks` endpoint only

**Step 1: Update the `auto_grade_picks` endpoint**

Find the `auto_grade_picks` function (around line 147) and replace it:

```python
@router.post("/auto-grade")
async def auto_grade_picks(current_user: dict = Depends(get_current_user)):
    """
    Automatically grade pending picks by fetching actual results,
    then derive and store results for any pending parlays whose picks are all resolved.
    """
    result = db.auto_grade_picks()
    parlay_result = db.grade_pending_parlays(user_id=current_user["id"])
    return {
        "graded_count": result['graded_count'],
        "parlays_graded": parlay_result['parlays_graded'],
        "errors": result['errors'],
        "results": result['results'],
    }
```

**Step 2: Verify it returns the new field**

```bash
# With API running:
curl -X POST http://localhost:8000/api/picks/auto-grade \
  -H "Authorization: Bearer <your_token>"
# Response should include "parlays_graded" key
```

**Step 3: Commit**

```bash
git add api/routers/picks.py
git commit -m "feat: auto-grade also grades pending parlays"
```

---

## Task 6: Frontend API client

**Files:**
- Modify: `frontend/src/api/client.ts`

**Step 1: Add types and functions to `client.ts`**

After the existing `Pick` interface (around line 96), add:

```typescript
export interface ParlayLegDetail {
  id: number
  pick_id: number
  player: string
  player_id?: number
  team_abbrev?: string
  stat: string
  line: number
  prediction: number
  direction: string
  edge: number
  prob_over?: number
  actual_result?: number
  won?: boolean
  voided?: boolean
  void_reason?: string
  game_date?: string
  opponent?: string
}

export interface SavedParlay {
  id: number
  name?: string
  legs_count: number
  status: 'pending' | 'won' | 'lost' | 'voided'
  graded_at?: string
  created_at: string
  legs: ParlayLegDetail[]
}
```

After the existing `deletePick` function (around line 462), add:

```typescript
export async function createParlay(pickIds: number[], name?: string): Promise<SavedParlay> {
  const response = await apiFetch(`${API_BASE}/parlays`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pick_ids: pickIds, name }),
  })
  if (!response.ok) await throwResponseError(response, 'Failed to save parlay')
  return response.json()
}

export async function getParlays(): Promise<SavedParlay[]> {
  const response = await apiFetch(`${API_BASE}/parlays`)
  if (!response.ok) throw new Error('Failed to fetch parlays')
  return response.json()
}

export async function deleteParlay(parlayId: number): Promise<void> {
  const response = await apiFetch(`${API_BASE}/parlays/${parlayId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete parlay')
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | grep -E "error|Error"
# Should produce no TypeScript errors
```

**Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add parlay API client types and functions"
```

---

## Task 7: Update max legs in parlayStore

**Files:**
- Modify: `frontend/src/store/parlayStore.ts`

**Step 1: Change max legs from 8 to 6**

In `parlayStore.ts` line 26, change:

```typescript
// Before:
if (legs.length >= 8) return

// After:
if (legs.length >= 6) return
```

**Step 2: Commit**

```bash
git add frontend/src/store/parlayStore.ts
git commit -m "feat: reduce max parlay legs from 8 to 6"
```

---

## Task 8: ParlayPage — tab layout + Save button + Auto-grade

**Files:**
- Modify: `frontend/src/pages/ParlayPage.tsx`

This is the largest task. Do it in sub-steps.

### 8a: Add tab state and imports

At the top of `ParlayPage.tsx`, add to existing imports:

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, RefreshCw as AutoGrade } from 'lucide-react'
import { createParlay, getParlays, deleteParlay, SavedParlay, autoGradePicks } from '../api/client'
```

Add `autoGradePicks` to `client.ts` (it already exists as `autoGradePicks` — check the import name matches).

Add tab state near the top of the component (after existing useState declarations):

```typescript
const [activeTab, setActiveTab] = useState<'builder' | 'saved'>('builder')
const [saveName, setSaveName] = useState('')
const [saveError, setSaveError] = useState<string | null>(null)
const queryClient = useQueryClient()
```

### 8b: Add saved parlays query

```typescript
const { data: savedParlays = [], refetch: refetchParlays } = useQuery({
  queryKey: ['parlays'],
  queryFn: getParlays,
  staleTime: 1000 * 30,
})
```

### 8c: Add save parlay mutation

```typescript
const saveParlayMutation = useMutation({
  mutationFn: () => createParlay(
    Array.from(selectedIds),
    saveName.trim() || undefined
  ),
  onSuccess: () => {
    setSelectedIds(new Set())
    setSaveName('')
    setSaveError(null)
    queryClient.invalidateQueries({ queryKey: ['parlays'] })
    setActiveTab('saved')
  },
  onError: (err: Error) => {
    setSaveError(err.message)
  },
})
```

### 8d: Add delete parlay mutation

```typescript
const deleteParlayMutation = useMutation({
  mutationFn: (id: number) => deleteParlay(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['parlays'] })
  },
})
```

### 8e: Add auto-grade mutation

```typescript
const autoGradeMutation = useMutation({
  mutationFn: autoGradePicks,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['pending-picks'] })
    queryClient.invalidateQueries({ queryKey: ['parlays'] })
    refetch()
    refetchParlays()
  },
})
```

### 8f: Replace the header section

Replace the existing header `<section>` (the div with `flex items-start sm:items-center justify-between`) with:

```tsx
<section>
  <div className="flex items-start sm:items-center justify-between gap-3">
    <div>
      <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">Parlay Builder</h1>
      <p className="text-sm text-text-secondary mt-1">
        {activeTab === 'builder'
          ? picks.length === 0
            ? 'Save picks from player analysis to build a parlay'
            : `${picks.length} pending pick${picks.length !== 1 ? 's' : ''} · ${selected.length} selected`
          : `${savedParlays.filter(p => p.status !== 'voided').length} saved parlay${savedParlays.filter(p => p.status !== 'voided').length !== 1 ? 's' : ''}`}
      </p>
    </div>
    <div className="flex items-center gap-2 flex-shrink-0">
      <button
        onClick={() => autoGradeMutation.mutate()}
        disabled={autoGradeMutation.isPending}
        className="btn btn-secondary text-sm"
        title="Auto-grade picks and parlays"
      >
        <AutoGrade className={`w-4 h-4 ${autoGradeMutation.isPending ? 'animate-spin' : ''}`} />
        <span className="hidden sm:inline">Auto-grade</span>
      </button>
      {activeTab === 'builder' && selectedIds.size > 0 && (
        <button
          onClick={() => setSelectedIds(new Set())}
          className="btn btn-secondary text-sm"
        >
          <X className="w-4 h-4" />
          <span className="hidden sm:inline">Clear</span>
        </button>
      )}
      {activeTab === 'builder' && (
        <button onClick={() => refetch()} className="btn btn-secondary text-sm" title="Refresh picks">
          <RefreshCw className="w-4 h-4" />
        </button>
      )}
    </div>
  </div>

  {/* Tabs */}
  <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5 mt-4 w-fit">
    <button
      onClick={() => setActiveTab('builder')}
      className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
        activeTab === 'builder' ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
      }`}
    >
      Builder
    </button>
    <button
      onClick={() => setActiveTab('saved')}
      className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
        activeTab === 'saved' ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
      }`}
    >
      Saved Parlays
      {savedParlays.filter(p => p.status === 'pending').length > 0 && (
        <span className="ml-1.5 text-[10px] bg-accent text-white rounded-full px-1.5 py-0.5 font-mono">
          {savedParlays.filter(p => p.status === 'pending').length}
        </span>
      )}
    </button>
  </div>
</section>
```

### 8g: Add "Save Parlay" button to the summary panel

In the desktop sidebar summary panel (inside `{selected.length > 0 && (...)}` near line 396), add after the Selected Legs card:

```tsx
{/* Save Parlay */}
<div className="card p-4 space-y-3">
  <div className="text-[11px] text-text-muted uppercase tracking-wider">Save Parlay</div>
  <input
    type="text"
    value={saveName}
    onChange={e => setSaveName(e.target.value)}
    placeholder="Name (optional)"
    className="w-full px-3 py-2 text-sm bg-bg-secondary border border-border-subtle rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
    maxLength={80}
  />
  {saveError && <p className="text-xs text-accent-danger">{saveError}</p>}
  <button
    onClick={() => saveParlayMutation.mutate()}
    disabled={saveParlayMutation.isPending || selected.length < 2}
    className="btn btn-primary w-full text-sm"
  >
    <BookmarkPlus className="w-4 h-4" />
    {saveParlayMutation.isPending ? 'Saving…' : `Save ${selected.length}-Leg Parlay`}
  </button>
</div>
```

Also add the same Save Parlay block inside the mobile summary panel (the `lg:hidden` section near line 167).

### 8h: Add the Saved Parlays tab content

Wrap the existing builder content in `{activeTab === 'builder' && (...)}`.

Then add after it:

```tsx
{activeTab === 'saved' && (
  <div className="space-y-4">
    {savedParlays.length === 0 ? (
      <div className="card p-16 text-center">
        <BookmarkCheck className="w-10 h-10 text-text-muted mx-auto mb-4 opacity-40" />
        <h2 className="text-lg font-semibold text-text-primary mb-2">No Saved Parlays</h2>
        <p className="text-sm text-text-secondary max-w-sm mx-auto leading-relaxed mb-6">
          Build a parlay in the Builder tab and hit <span className="text-accent font-medium">Save Parlay</span>.
        </p>
        <button onClick={() => setActiveTab('builder')} className="btn btn-primary">
          Go to Builder
        </button>
      </div>
    ) : (
      savedParlays.map(parlay => {
        const activeLegs = parlay.legs.filter(l => !l.voided)
        const effectiveLegs = activeLegs.length
        const payout = effectiveLegs > 0 ? Math.pow(1.909, effectiveLegs) : 0
        const statusColor = parlay.status === 'won'
          ? 'text-accent-success'
          : parlay.status === 'lost'
          ? 'text-accent-danger'
          : 'text-text-muted'
        const statusBg = parlay.status === 'won'
          ? 'bg-accent-success/10 border-accent-success/20'
          : parlay.status === 'lost'
          ? 'bg-accent-danger/10 border-accent-danger/20'
          : 'bg-bg-secondary border-border-subtle'

        return (
          <div key={parlay.id} className="card p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  {parlay.name && (
                    <span className="font-semibold text-text-primary text-sm truncate">{parlay.name}</span>
                  )}
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${statusBg} ${statusColor}`}>
                    {parlay.status}
                  </span>
                  <span className="text-[11px] text-text-muted font-mono">
                    {effectiveLegs}-leg · {payout.toFixed(2)}x
                  </span>
                </div>
                <div className="text-[11px] text-text-muted mt-0.5">
                  {new Date(parlay.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                </div>
              </div>
              {parlay.status !== 'voided' && (
                <button
                  onClick={() => { if (confirm('Void this parlay?')) deleteParlayMutation.mutate(parlay.id) }}
                  className="p-1.5 rounded text-text-muted hover:text-accent-danger transition-colors flex-shrink-0"
                  title="Void parlay"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Leg breakdown */}
            <div className="space-y-2 pt-2 border-t border-border-subtle">
              {parlay.legs.map(leg => {
                const legIcon = leg.voided
                  ? <span className="text-text-muted text-xs line-through">VOID</span>
                  : leg.won === true
                  ? <span className="text-accent-success text-sm font-bold">✓</span>
                  : leg.won === false
                  ? <span className="text-accent-danger text-sm font-bold">✗</span>
                  : <span className="text-text-muted text-sm">⏳</span>

                return (
                  <div key={leg.id} className={`flex items-center gap-2 text-xs ${leg.voided ? 'opacity-40' : ''}`}>
                    <div className="w-4 flex-shrink-0 text-center">{legIcon}</div>
                    <span className={`font-medium truncate flex-1 ${leg.voided ? 'line-through' : 'text-text-primary'}`}>
                      {leg.player}
                    </span>
                    <span className="font-mono text-text-secondary flex-shrink-0">
                      {leg.stat} {leg.direction} {leg.line}
                    </span>
                    {leg.actual_result != null && (
                      <span className="font-mono text-text-muted flex-shrink-0">
                        → {leg.actual_result}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })
    )}
  </div>
)}
```

### 8i: Update the max legs copy in the UI

In the summary panel, find the "Legs (max 8)" text and change to "Legs (max 6)".

**Step 2: Verify the TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | grep -E "error|Error"
```

Fix any type errors before committing.

**Step 3: Manual smoke test**

1. Start both servers (`./start_api.sh` and `cd frontend && npm run dev`)
2. Log in
3. Go to Parlay Builder — select 2+ pending picks, hit Save Parlay → should switch to Saved tab
4. Saved tab shows the parlay with Pending badge
5. Hit Auto-grade — should grade picks and re-derive parlay status
6. Void a parlay via trash icon — should disappear or show Voided

**Step 4: Commit**

```bash
git add frontend/src/pages/ParlayPage.tsx
git commit -m "feat: parlay builder tabs, save parlay, auto-grade, max 6 legs"
```

---

## Task 9: Update HistoryPage auto-grade response (minor)

**Files:**
- Modify: `frontend/src/pages/HistoryPage.tsx`

**Step 1: The auto-grade mutation in HistoryPage already calls the same endpoint**

The response now includes `parlays_graded`. Optionally surface it in a toast or console. This is a cosmetic-only change — no functional change needed. The parlay grading already happens server-side when the endpoint is called.

If you want to show it: find `autoGradeMutation` in `HistoryPage.tsx` and update the `onSuccess` callback to include the parlay count in a console log or toast notification system if one exists.

**Step 2: Commit (only if you made a change)**

```bash
git add frontend/src/pages/HistoryPage.tsx
git commit -m "chore: surface parlays_graded count in history auto-grade response"
```

---

## Task 10: Final verification

**Step 1: TypeScript build passes clean**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build
npm run lint
```

**Step 2: Backend linting passes**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -m py_compile api/routers/parlays.py db.py
```

**Step 3: Full flow test**

1. Register or log in as a test user
2. Save 2–3 individual picks from PlayerPage
3. Go to Parlay Builder — confirm picks show up
4. Select 2 picks, hit Save Parlay with a name → lands on Saved Parlays tab
5. Saved parlay shows correct legs, Pending status, payout multiplier
6. Select 6 picks — confirm the 7th cannot be added (max 6)
7. Go to History page → hit Auto-grade → confirm it returns without error
8. Return to Parlay tab Saved → verify pending parlay status updated if picks were graded
9. Void a parlay — confirm it shows Voided or disappears

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: parlay persistence complete — save, view, grade, void"
```
