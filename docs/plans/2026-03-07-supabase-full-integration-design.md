# Supabase Full Integration Design

**Date:** 2026-03-07
**Status:** Approved
**Scope:** Auth migration, RLS, direct client reads, realtime, edge function grading

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND (React)                   │
│                                                      │
│  supabase-js client                                  │
│  ├── Auth: signIn/signUp/signOut/onAuthStateChange   │
│  ├── Direct reads: picks, parlays, game_predictions  │
│  │   (PostgREST, JWT auto-attached, RLS enforced)   │
│  └── Realtime: subscribe to picks/parlays UPDATE     │
│                                                      │
│  apiFetch() — Bearer token instead of cookie        │
│  └── Write/ML endpoints only → FastAPI               │
└───────────┬──────────────────────┬───────────────────┘
            │                      │
            ▼                      ▼
┌─────────────────┐    ┌────────────────────────────┐
│   FastAPI API   │    │     Supabase Platform       │
│                 │    │                             │
│ Verifies JWT    │    │  Auth (auth.users)          │
│ via JWT_SECRET  │    │  PostgREST (auto-REST)      │
│                 │    │  Realtime (WebSocket)       │
│ Keeps:          │    │  Storage (avatars bucket)   │
│ - /predict      │    │  Edge Functions (grading)   │
│ - /bets/today   │    │  pg_cron (nightly fallback) │
│ - /players/*    │    │                             │
│ - /games/predict│    │  Postgres DB                │
│ - POST/PUT/DEL  │    │  ├── auth.users (managed)   │
│   picks/parlays │    │  ├── profiles               │
│ - /auto-grade   │    │  ├── picks (RLS)            │
└────────┬────────┘    │  ├── parlays (RLS)          │
         │             │  ├── parlay_legs (RLS)      │
         └─────────────►  ├── game_predictions (RLS) │
           psycopg2    │  └── bets, games            │
           (service    └────────────────────────────┘
            role key)
```

**Key rule:** FastAPI uses the service role key (bypasses RLS). Frontend uses anon key + user JWT (RLS enforced). Service role key never touches the browser.

---

## 2. Auth Migration

### What's deleted
- `users` table (dropped — all existing users deleted, clean slate)
- `api/auth_utils.py` — JWT creation/bcrypt (replaced by Supabase Auth)
- `api/routers/auth.py` — `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, `/api/auth/refresh`
- Avatar disk storage at `uploads/avatars/`

### What's added — Supabase side

```sql
CREATE TABLE profiles (
  id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username    TEXT UNIQUE NOT NULL,
  avatar_url  TEXT,
  role        TEXT NOT NULL DEFAULT 'user',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, username)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'username');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
```

### What's added — Frontend side
- `src/lib/supabase.ts` — singleton `createClient(SUPABASE_URL, SUPABASE_ANON_KEY)`
- `authStore` uses `supabase.auth.onAuthStateChange()` instead of polling `/api/auth/me`
- Auth functions in `client.ts` replaced with `supabase.auth.signUp()`, `signInWithPassword()`, `signOut()`, `getUser()`
- `apiFetch` sends `Authorization: Bearer <access_token>` from `supabase.auth.getSession()`

### What changes — FastAPI side
- `decode_access_token` verifies against `SUPABASE_JWT_SECRET` (env var) instead of `AUTH_SECRET_KEY`
- `get_current_user` reads `Authorization: Bearer` header instead of httpOnly cookie
- Avatar upload (`POST /api/auth/avatar`) writes to Supabase Storage `avatars` bucket via `supabase-py`
- `change-password` proxies to Supabase Admin API
- `AUTH_SECRET_KEY` env var replaced with `SUPABASE_JWT_SECRET` + `SUPABASE_SERVICE_KEY`

### Avatar storage
Supabase Storage bucket: `avatars` (public)
URL format: `https://<project>.supabase.co/storage/v1/object/public/avatars/<user_id>.<ext>`
`profiles.avatar_url` stores this full URL.

---

## 3. Row Level Security

```sql
-- picks: user sees only their own
ALTER TABLE picks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "picks: own rows only" ON picks
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- parlays: user sees only their own
ALTER TABLE parlays ENABLE ROW LEVEL SECURITY;
CREATE POLICY "parlays: own rows only" ON parlays
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- parlay_legs: scoped via parlay ownership
ALTER TABLE parlay_legs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "parlay_legs: own rows only" ON parlay_legs
  USING (parlay_id IN (SELECT id FROM parlays WHERE user_id = auth.uid()));

-- game_predictions: all authenticated users can read
ALTER TABLE game_predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "game_predictions: authenticated read" ON game_predictions
  FOR SELECT USING (auth.role() = 'authenticated');

-- profiles: own row only
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "profiles: own row only" ON profiles
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());
```

FastAPI uses service role key → bypasses RLS for all writes. No Python query changes needed.

---

## 4. Direct Client Reads

### FastAPI endpoints deleted
| Endpoint | Replaced by |
|---|---|
| `GET /api/picks` | `supabase.from('picks').select('*').order('timestamp', { ascending: false })` |
| `GET /api/parlays` | `supabase.from('parlays').select('*, parlay_legs(*)')` |
| `GET /api/games/history` | `supabase.from('game_predictions').select('*').order('timestamp', { ascending: false })` |
| `GET /api/picks/stats/performance` | Postgres view `pick_performance_stats` |
| `GET /api/picks/stats/profit` | Postgres view `pick_cumulative_profit` |
| `GET /api/games/stats/accuracy` | Postgres view `game_accuracy_stats` |

### Postgres views (SQL Editor)

```sql
-- pick_performance_stats
CREATE VIEW pick_performance_stats AS
SELECT
  user_id,
  COUNT(*) AS total_picks,
  COUNT(*) FILTER (WHERE won IS NOT NULL AND NOT voided) AS graded_picks,
  COUNT(*) FILTER (WHERE won = true) AS wins,
  COUNT(*) FILTER (WHERE won = false AND NOT voided) AS losses,
  COUNT(*) FILTER (WHERE voided = true) AS pushes,
  ROUND(
    COUNT(*) FILTER (WHERE won = true)::numeric /
    NULLIF(COUNT(*) FILTER (WHERE won IS NOT NULL AND NOT voided), 0) * 100, 1
  ) AS win_rate,
  ROUND(
    (COUNT(*) FILTER (WHERE won = true) - COUNT(*) FILTER (WHERE won = false AND NOT voided))::numeric /
    NULLIF(COUNT(*) FILTER (WHERE won IS NOT NULL AND NOT voided), 0) * 100, 1
  ) AS roi
FROM picks
WHERE user_id = auth.uid()
GROUP BY user_id;

-- pick_cumulative_profit
CREATE VIEW pick_cumulative_profit AS
SELECT
  game_date,
  ROUND(SUM(CASE WHEN won = true THEN 1 WHEN won = false AND NOT voided THEN -1 ELSE 0 END)
    OVER (ORDER BY game_date ROWS UNBOUNDED PRECEDING), 2) AS cumulative_profit
FROM picks
WHERE user_id = auth.uid() AND game_date IS NOT NULL AND won IS NOT NULL
ORDER BY game_date;

-- game_accuracy_stats
CREATE VIEW game_accuracy_stats AS
SELECT
  COUNT(*) AS total_predictions,
  COUNT(*) FILTER (WHERE actual_winner IS NOT NULL) AS graded_predictions,
  COUNT(*) FILTER (WHERE correct = true) AS correct,
  COUNT(*) FILTER (WHERE correct = false) AS incorrect,
  ROUND(COUNT(*) FILTER (WHERE correct = true)::numeric /
    NULLIF(COUNT(*) FILTER (WHERE actual_winner IS NOT NULL), 0) * 100, 1) AS accuracy
FROM game_predictions;
```

Views inherit RLS from underlying tables — no extra policies needed.

### Frontend changes
- `src/lib/supabase.ts` singleton used for all direct reads
- React Query `queryFn` calls `supabase.from(...)` instead of `apiFetch`
- Types remain unchanged (same field names)
- `by_stat` and `by_edge_range` breakdowns in performance stats: computed client-side from raw picks data (simpler than a complex SQL view)

---

## 5. Realtime

```ts
// src/hooks/usePicksRealtime.ts
const channel = supabase
  .channel('picks-changes')
  .on(
    'postgres_changes',
    { event: 'UPDATE', schema: 'public', table: 'picks' },
    (payload) => {
      queryClient.setQueryData(['picks'], (old: Pick[]) =>
        old.map(p => p.id === payload.new.id ? { ...p, ...payload.new } : p)
      )
    }
  )
  .subscribe()

// src/hooks/useParlaysRealtime.ts
supabase
  .channel('parlays-changes')
  .on(
    'postgres_changes',
    { event: 'UPDATE', schema: 'public', table: 'parlays' },
    (payload) => {
      queryClient.setQueryData(['parlays'], (old: SavedParlay[]) =>
        old.map(p => p.id === payload.new.id ? { ...p, ...payload.new } : p)
      )
    }
  )
  .subscribe()
```

- RLS ensures users only receive their own row updates
- Hooks used on PicksPage and ParlaysPage
- Channel unsubscribed in `useEffect` cleanup

---

## 6. Edge Function + pg_cron Grading

### Edge Function — immediate trigger

**Trigger:** Database Webhook on `picks` INSERT
**File:** `supabase/functions/grade-picks/index.ts`

```ts
Deno.serve(async (req) => {
  const { record } = await req.json()
  const gameDate = record.game_date  // "2026-03-07"
  const now = new Date()
  const etHour = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' })).getHours()

  // Only trigger grading if game is today and it's past 11pm ET
  const isToday = gameDate === now.toISOString().slice(0, 10)
  if (!isToday || etHour < 23) {
    return new Response('skipped', { status: 200 })
  }

  await fetch(`${Deno.env.get('FASTAPI_URL')}/api/picks/auto-grade`, {
    method: 'POST',
    headers: { 'X-Service-Key': Deno.env.get('FASTAPI_SERVICE_KEY')! }
  })

  return new Response('graded', { status: 200 })
})
```

### pg_cron — nightly fallback

```sql
SELECT cron.schedule(
  'nightly-auto-grade-picks',
  '30 4 * * *',  -- 4:30am UTC = 11:30pm ET
  $$
  SELECT net.http_post(
    url := current_setting('app.fastapi_url') || '/api/picks/auto-grade',
    headers := jsonb_build_object('X-Service-Key', current_setting('app.fastapi_service_key'))
  );
  $$
);

SELECT cron.schedule(
  'nightly-auto-grade-games',
  '35 4 * * *',  -- 4:35am UTC
  $$
  SELECT net.http_post(
    url := current_setting('app.fastapi_url') || '/api/games/auto-grade',
    headers := jsonb_build_object('X-Service-Key', current_setting('app.fastapi_service_key'))
  );
  $$
);
```

### FastAPI security change

```python
# New dependency for auto-grade endpoints
SERVICE_KEY = os.getenv("FASTAPI_SERVICE_KEY")

def verify_service_key(request: Request):
    key = request.headers.get("X-Service-Key")
    if not key or key != SERVICE_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
```

`/api/picks/auto-grade` and `/api/games/auto-grade` use this dependency instead of `get_current_user`.

---

## Environment Variables

### FastAPI (new/changed)
| Variable | Purpose |
|---|---|
| `SUPABASE_JWT_SECRET` | Verify Supabase-issued JWTs (replaces `AUTH_SECRET_KEY`) |
| `SUPABASE_SERVICE_KEY` | Service role key for DB writes + Storage |
| `SUPABASE_URL` | Project URL for supabase-py |
| `FASTAPI_SERVICE_KEY` | Secret key for cron/edge function to call auto-grade |

### Frontend (new)
| Variable | Purpose |
|---|---|
| `VITE_SUPABASE_URL` | Project URL |
| `VITE_SUPABASE_ANON_KEY` | Anon key (safe to expose — RLS enforces security) |

---

## Files Deleted After Migration
- `api/auth_utils.py`
- `api/routers/auth.py`
- `uploads/avatars/` directory
- `users` table (via SQL Editor)

## Files Added
- `src/lib/supabase.ts`
- `src/hooks/usePicksRealtime.ts`
- `src/hooks/useParlaysRealtime.ts`
- `supabase/functions/grade-picks/index.ts`
- SQL: `profiles` table, trigger, RLS policies, 3 views, 2 cron jobs
