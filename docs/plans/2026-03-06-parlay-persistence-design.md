# Parlay Persistence & Overhaul Design

**Date:** 2026-03-06
**Status:** Approved

---

## Overview

Add persistent saved parlays to the NBA Eval platform. Users can select pending picks in the Parlay Builder, save them as a named parlay (up to 6 legs), view saved parlays in a dedicated tab, and auto-grade both picks and parlays from a single button on either the Parlay or History page.

---

## Goals

- Persist parlays to Supabase (currently ephemeral client-side only)
- Add "Saved Parlays" tab to ParlayPage alongside the Builder
- Reduce max parlay legs from 8 to 6
- Unify auto-grade: one button press grades both individual picks and all pending parlays
- Picks and parlays are always user-scoped (each user sees only their own data)

---

## Database Schema

### New table: `parlays`

```sql
CREATE TABLE parlays (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES auth.users(id),
  name        TEXT,                        -- optional user label
  legs_count  INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'won' | 'lost' | 'voided'
  graded_at   TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### New table: `parlay_legs`

```sql
CREATE TABLE parlay_legs (
  id         BIGSERIAL PRIMARY KEY,
  parlay_id  BIGINT NOT NULL REFERENCES parlays(id) ON DELETE CASCADE,
  pick_id    BIGINT NOT NULL REFERENCES picks(id)
);
```

**Design decisions:**
- Parlay legs reference existing picks — no data duplication
- `ON DELETE CASCADE` on parlay_legs means deleting a pick cleans up its legs automatically
- Both tables filtered by `user_id` on every query

---

## Grading Rules

Parlay status is derived from its constituent pick results:

| Condition | Parlay Status |
|-----------|--------------|
| All legs `won = 1` | `won` |
| Any leg `won = 0` | `lost` |
| Any leg `won IS NULL` (and none lost) | `pending` |
| Any leg `voided = 1` | Leg dropped; payout recalculated for N-1 legs |

---

## Backend

### New file: `api/routers/parlays.py`

```
POST   /api/parlays          Create a parlay
                             Body: { pick_ids: int[], name?: str }
                             Auth: required
                             Validates: 2–6 pick_ids, all picks belong to user and are pending

GET    /api/parlays          List user's parlays (newest first)
                             Returns: parlay metadata + leg details with full pick data
                             Auth: required

DELETE /api/parlays/{id}     Void a parlay (sets status='voided')
                             Auth: required, ownership enforced
```

### New functions in `db.py`

```python
create_parlay(user_id, pick_ids, name=None) -> dict
get_parlays(user_id) -> List[dict]           # includes legs with pick data joined
void_parlay(parlay_id, user_id)
grade_pending_parlays(user_id=None)          # derives status from pick results
```

### Modified: `api/routers/picks.py` — `POST /api/picks/auto-grade`

After grading individual picks, call `grade_pending_parlays()` and include parlay counts in response:

```json
{
  "graded_count": 3,
  "parlays_graded": 1,
  "errors": [],
  "results": [...]
}
```

### Register router in `api/main.py`

Add `parlays` router alongside existing routers.

---

## Frontend

### `api/client.ts` additions

```typescript
export interface ParlayLegDetail {
  id: number
  pick_id: number
  player: string
  player_id?: number
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
  team_abbrev?: string
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

export async function createParlay(pickIds: number[], name?: string): Promise<SavedParlay>
export async function getParlays(): Promise<SavedParlay[]>
export async function deleteParlay(parlayId: number): Promise<void>
```

### `ParlayPage.tsx` — Tab structure

```
[ Builder ]  [ Saved Parlays ]
```

**Builder tab (existing + changes):**
- Max legs: 6 (update `parlayStore.ts` and UI copy)
- "Save Parlay" button appears when ≥ 2 picks selected in parlay summary panel
- After successful save: clear selection, show success toast, switch to Saved tab
- Auto-grade button added next to Refresh button in header

**Saved Parlays tab (new):**
- List of parlay cards, newest first
- Each card shows:
  - Status badge: `Pending` (muted) / `Won` (green) / `Lost` (red) / `Voided` (muted)
  - Created date
  - Optional name
  - Leg breakdown: player · stat · direction · line, with ✓ / ✗ / ⏳ icon per leg
  - Effective legs count (voided legs shown struck-through)
  - Payout multiplier (recalculated for active legs)
  - Trash icon to void
- Empty state: "No saved parlays yet. Build one in the Builder tab."

### `HistoryPage.tsx` — No UI changes

Auto-grade button already exists. Endpoint response now includes `parlays_graded` count — can optionally surface in the success message ("Graded 3 picks + 1 parlay").

---

## Implementation Order

1. **DB schema** — Add `parlays` + `parlay_legs` tables in Supabase SQL Editor
2. **`db.py`** — Add `create_parlay`, `get_parlays`, `void_parlay`, `grade_pending_parlays`
3. **`api/routers/parlays.py`** — New router with 3 endpoints
4. **`api/main.py`** — Register parlays router
5. **`api/routers/picks.py`** — Extend auto-grade to call `grade_pending_parlays`
6. **`api/client.ts`** — Add types + 3 new API functions
7. **`ParlayPage.tsx`** — Tab UI, Save button, max legs 6, auto-grade button
8. **`parlayStore.ts`** — Update max legs constant from 8 → 6

---

## Out of Scope

- Parlay profit tracking in performance stats (parlays have different payout math vs single picks)
- Push notifications when parlay resolves
- Editing a saved parlay (void + re-create instead)
