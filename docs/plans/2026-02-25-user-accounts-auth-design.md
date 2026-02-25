# User Accounts & Auth Design

**Date:** 2026-02-25
**Status:** Approved
**Scope:** Custom JWT auth, per-user picks data, full feature access for all authenticated users

---

## Goal

Replace the mock Zustand auth with a real account system so that:
- Users can register, log in, and persist a session
- Picks, pick history, and performance stats are scoped per user
- All features (research, parlay builder, games, predictions) are accessible to any account holder
- No payment/Stripe layer — monetization deferred until more data and reach are established

---

## What Changes vs. What Stays the Same

**Unchanged:**
- ML core (`nba_evaluator.py`, all models)
- All frontend pages and their layouts
- SQLite database file (`picks_history.db`)
- Player/game prediction endpoints (stateless, remain public)
- Research, games, and parlay endpoints (public)
- Design system, CSS variables, theming

**Added:**
- `users` table in `picks_history.db`
- `user_id` column on `picks` table
- `api/routers/auth.py` with register/login/me endpoints
- JWT middleware (`get_current_user` dependency)
- Real `authStore.ts` replacing mock implementation
- Auth header injection in `api/client.ts`

---

## Database Changes

### New `users` table
```sql
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,   -- UUID v4
    email      TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL       -- ISO 8601
);
```

### Migration: add `user_id` to `picks`
```sql
ALTER TABLE picks ADD COLUMN user_id TEXT;
-- Nullable: existing rows keep NULL (no data loss)
-- New picks attach the authenticated user's id
```

No changes to `game_predictions` — game predictions are global/shared.

---

## Auth API Layer

**File:** `api/routers/auth.py`
**Mounted at:** `/api/auth`

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| POST | `/api/auth/register` | No | Create account, return JWT + user info |
| POST | `/api/auth/login` | No | Verify credentials, return JWT + user info |
| GET | `/api/auth/me` | Yes | Return current user from token |

### Token spec
- Algorithm: HS256
- Expiry: 7 days
- Payload: `{ sub: user_id, email, exp }`
- Secret: `AUTH_SECRET_KEY` env var, falls back to `secret_key` in `config.json`

### Password hashing
- bcrypt, 12 rounds (via `passlib[bcrypt]`)

### FastAPI dependencies
- `get_current_user(token)` — extracts Bearer token, verifies JWT, returns user dict or raises `401`
- `get_optional_user(token)` — same but returns `None` instead of raising (for future public/private hybrid endpoints)

### Error responses
| Scenario | Status | Detail |
|----------|--------|--------|
| Email already registered | 409 | "Email already in use" |
| Wrong password | 401 | "Invalid credentials" |
| User not found | 401 | "Invalid credentials" |
| Expired/invalid token | 401 | "Could not validate credentials" |

---

## Data Scoping — Picks Endpoints

Only `api/routers/picks.py` changes. All picks endpoints require authentication.

| Endpoint | Change |
|----------|--------|
| `POST /api/picks` | Attach `user_id` from JWT to new pick |
| `GET /api/picks` | Filter `WHERE user_id = ?` |
| `PUT /api/picks/{id}/grade` | Verify `user_id` ownership before update |
| `DELETE /api/picks/{id}` | Verify `user_id` ownership before delete |
| `POST /api/picks/auto-grade` | Scope to requesting user's picks |
| `GET /api/picks/stats/performance` | Scope to requesting user |
| `GET /api/picks/stats/profit` | Scope to requesting user |

Unauthenticated requests to any picks endpoint → `401 Unauthorized`.

---

## Frontend Changes

### `store/authStore.ts`

Replace mock implementation. Keep the same Zustand interface so no other components need updating:

```ts
// State (unchanged interface)
user: { id, email, displayName } | null
isAuthenticated: boolean
isLoading: boolean
error: string | null

// Actions (unchanged interface)
login(email, password): Promise<void>       // POST /api/auth/login → store JWT
signup(email, password, displayName): Promise<void>  // POST /api/auth/register → store JWT
logout(): void                              // clear localStorage + store
checkAuth(): Promise<void>                  // GET /api/auth/me → rehydrate on app load
clearError(): void
```

JWT stored in `localStorage` under key `nba_eval_token`.

On app load (`App.tsx`): call `checkAuth()` — if token exists but returns 401, clear and stay on public routes.

### `api/client.ts`

Add auth header injection to all picks-related calls:

```ts
// Helper — reads token from localStorage
function authHeaders(): HeadersInit {
  const token = localStorage.getItem('nba_eval_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}
```

Applied to: `createPick`, `getPicks`, `gradePick`, `deletePick`, `autoGrade`, `getPerformanceStats`, `getCumulativeProfit`.

Not applied to: `predictPlayer`, `predictTodaysGames`, `getPlayerResearch`, `getTodaysGames` (these stay public).

### `LoginForm.tsx` / `SignupForm.tsx`

Already exist in `frontend/src/pages/auth/`. Wire to real `authStore` actions instead of mock. No layout changes needed.

### `ProtectedRoute.tsx`

Already exists. No changes needed — it reads `isAuthenticated` from the store, which will now reflect real auth state.

---

## Security Notes

- Passwords never stored in plaintext — bcrypt only
- JWT secret must be set as env var in production (`AUTH_SECRET_KEY`)
- CORS is already configured for localhost:5173 and :3000
- No rate limiting for now (acceptable at current scale)
- Token expiry: 7 days — user stays logged in across sessions without re-entering credentials

---

## Dependencies to Add

**Backend (`api/requirements.txt`):**
```
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0
```

**Frontend:** No new packages — uses existing `fetch` via `api/client.ts`.

---

## Out of Scope (Deferred)

- Stripe / payment integration
- Feature gating / tier limits
- Email verification
- Password reset flow
- OAuth (Google/GitHub)
- Rate limiting per user
