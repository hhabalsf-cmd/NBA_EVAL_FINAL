# Supabase Full Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the NBA Eval app from custom JWT/cookie auth + psycopg2 reads to Supabase Auth, RLS, direct client reads via PostgREST, realtime pick updates, and Edge Function auto-grading.

**Architecture:** Frontend uses `@supabase/supabase-js` for auth/reads/realtime; FastAPI keeps all write and ML endpoints, verifying Supabase JWTs via `SUPABASE_JWT_SECRET`. RLS enforces row ownership via `auth.uid()`. pg_cron + Edge Function trigger auto-grading nightly and on pick insert.

**Tech Stack:** Supabase (Auth, PostgREST, Realtime, Storage, Edge Functions, pg_cron), `@supabase/supabase-js` v2, FastAPI + python-jose, Deno (Edge Functions), Vite + React + Zustand + TanStack Query

**Design doc:** `docs/plans/2026-03-07-supabase-full-integration-design.md`

---

## Pre-flight checklist

Before starting, gather these from the Supabase dashboard:
- `SUPABASE_URL` → Project Settings → API → Project URL
- `SUPABASE_ANON_KEY` → Project Settings → API → `anon public` key
- `SUPABASE_SERVICE_KEY` → Project Settings → API → `service_role secret` key
- `SUPABASE_JWT_SECRET` → Project Settings → API → JWT Secret

---

## Task 1: Supabase SQL — profiles table + trigger

**Where:** Supabase Dashboard → SQL Editor (not local files)

**Step 1: Drop users table and create profiles**

Run this SQL in Supabase SQL Editor:

```sql
-- Drop existing users table (clean slate — all users deleted)
DROP TABLE IF EXISTS users CASCADE;

-- Profiles table linked to Supabase Auth
CREATE TABLE profiles (
  id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username    TEXT UNIQUE NOT NULL,
  avatar_url  TEXT,
  role        TEXT NOT NULL DEFAULT 'user',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-create profile when user signs up
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, username)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1)));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
```

**Step 2: Verify**

In SQL Editor, run:
```sql
SELECT id, username, created_at FROM profiles;
```
Expected: empty table, no error.

---

## Task 2: Supabase SQL — Row Level Security

**Where:** Supabase Dashboard → SQL Editor

**Step 1: Add `user_id` UUID column to picks if it's currently TEXT**

Check the column type first:
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'picks' AND column_name = 'user_id';
```

If `data_type` is `text` (not `uuid`), run:
```sql
ALTER TABLE picks ALTER COLUMN user_id TYPE UUID USING user_id::UUID;
ALTER TABLE parlays ALTER COLUMN user_id TYPE UUID USING user_id::UUID;
```

**Step 2: Enable RLS on all user-scoped tables**

```sql
-- picks
ALTER TABLE picks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "picks_own_rows" ON picks
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- parlays
ALTER TABLE parlays ENABLE ROW LEVEL SECURITY;
CREATE POLICY "parlays_own_rows" ON parlays
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- parlay_legs (scoped via parlay ownership)
ALTER TABLE parlay_legs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "parlay_legs_own_rows" ON parlay_legs
  USING (parlay_id IN (SELECT id FROM parlays WHERE user_id = auth.uid()));

-- game_predictions (readable by all authenticated users)
ALTER TABLE game_predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "game_predictions_authenticated_read" ON game_predictions
  FOR SELECT USING (auth.role() = 'authenticated');

-- profiles (own row only)
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "profiles_own_row" ON profiles
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());
```

**Step 3: Verify RLS is active**

```sql
SELECT tablename, rowsecurity FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('picks', 'parlays', 'parlay_legs', 'game_predictions', 'profiles');
```
Expected: `rowsecurity = true` for all 5 tables.

---

## Task 3: Supabase SQL — Postgres Views for stats

**Where:** Supabase Dashboard → SQL Editor

**Step 1: Create pick_performance_stats view**

```sql
-- Note: won and voided are INTEGER columns (0/1), not boolean
CREATE OR REPLACE VIEW pick_performance_stats AS
SELECT
  user_id,
  COUNT(*) AS total_picks,
  COUNT(*) FILTER (WHERE won IS NOT NULL AND COALESCE(voided, 0) = 0) AS graded_picks,
  COUNT(*) FILTER (WHERE won = 1) AS wins,
  COUNT(*) FILTER (WHERE won = 0 AND COALESCE(voided, 0) = 0) AS losses,
  COUNT(*) FILTER (WHERE COALESCE(voided, 0) = 1) AS pushes,
  ROUND(
    COUNT(*) FILTER (WHERE won = 1)::numeric /
    NULLIF(COUNT(*) FILTER (WHERE won IS NOT NULL AND COALESCE(voided, 0) = 0), 0) * 100, 1
  ) AS win_rate,
  ROUND(
    (COUNT(*) FILTER (WHERE won = 1) - COUNT(*) FILTER (WHERE won = 0 AND COALESCE(voided, 0) = 0))::numeric /
    NULLIF(COUNT(*) FILTER (WHERE won IS NOT NULL AND COALESCE(voided, 0) = 0), 0) * 100, 1
  ) AS roi,
  AVG(edge) FILTER (WHERE won = 1) AS avg_edge_winners
FROM picks
WHERE user_id = auth.uid()
GROUP BY user_id;
```

**Step 2: Create pick_cumulative_profit view**

```sql
CREATE OR REPLACE VIEW pick_cumulative_profit AS
SELECT
  game_date,
  profit,
  SUM(profit) OVER (ORDER BY game_date ROWS UNBOUNDED PRECEDING)::numeric AS cumulative_profit
FROM (
  SELECT
    game_date,
    SUM(CASE WHEN won = 1 THEN 1 WHEN won = 0 AND COALESCE(voided, 0) = 0 THEN -1 ELSE 0 END) AS profit
  FROM picks
  WHERE user_id = auth.uid()
    AND game_date IS NOT NULL
    AND won IS NOT NULL
  GROUP BY game_date
) daily
ORDER BY game_date;
```

**Step 3: Create game_accuracy_stats view**

```sql
CREATE OR REPLACE VIEW game_accuracy_stats AS
SELECT
  COUNT(*) AS total_predictions,
  COUNT(*) FILTER (WHERE actual_winner IS NOT NULL) AS graded_predictions,
  COUNT(*) FILTER (WHERE correct = 1) AS correct,
  COUNT(*) FILTER (WHERE correct = 0) AS incorrect,
  ROUND(
    COUNT(*) FILTER (WHERE correct = 1)::numeric /
    NULLIF(COUNT(*) FILTER (WHERE actual_winner IS NOT NULL), 0) * 100, 1
  ) AS accuracy
FROM game_predictions;
```

**Step 4: Verify views exist**

```sql
SELECT table_name FROM information_schema.views WHERE table_schema = 'public';
```
Expected: `pick_performance_stats`, `pick_cumulative_profit`, `game_accuracy_stats` in results.

---

## Task 4: Supabase Storage — avatars bucket

**Where:** Supabase Dashboard → Storage

**Step 1: Create bucket**

1. Go to Storage → New bucket
2. Name: `avatars`
3. Public bucket: ✅ (checked)
4. Click Create

**Step 2: Set storage policy**

In SQL Editor:
```sql
-- Allow authenticated users to upload their own avatar
CREATE POLICY "avatar_upload" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'avatars' AND name = auth.uid()::text || '.' || (storage.extension(name)));

-- Allow authenticated users to update/delete their own avatar
CREATE POLICY "avatar_update" ON storage.objects
  FOR UPDATE TO authenticated
  USING (bucket_id = 'avatars' AND owner = auth.uid());

CREATE POLICY "avatar_delete" ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'avatars' AND owner = auth.uid());

-- Public read (bucket is public so CDN URLs work)
CREATE POLICY "avatar_public_read" ON storage.objects
  FOR SELECT USING (bucket_id = 'avatars');
```

**Step 3: Note your storage URL**

Format: `https://<project-ref>.supabase.co/storage/v1/object/public/avatars/`

---

## Task 5: FastAPI — install supabase-py + update JWT verification

**Files:**
- Modify: `api/auth_utils.py`
- Modify: `api/routers/auth.py`
- Modify: `requirements.txt`

**Step 1: Install supabase-py**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
pip install supabase
pip freeze | grep supabase >> requirements.txt
```

**Step 2: Write failing test for new JWT verification**

Create `tests/test_supabase_auth.py`:
```python
"""Tests for Supabase JWT verification."""
import pytest
from unittest.mock import patch
import time
from jose import jwt

SUPABASE_JWT_SECRET = "test-supabase-jwt-secret-that-is-long-enough-32chars"

def make_supabase_token(user_id: str, email: str, secret: str = SUPABASE_JWT_SECRET) -> str:
    """Create a mock Supabase-format JWT."""
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_decode_supabase_token_returns_user_id():
    from api.auth_utils import decode_access_token
    token = make_supabase_token("user-uuid-123", "test@example.com")
    with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": SUPABASE_JWT_SECRET}):
        payload = decode_access_token(token)
    assert payload["sub"] == "user-uuid-123"
    assert payload["email"] == "test@example.com"


def test_decode_invalid_token_raises():
    from api.auth_utils import decode_access_token
    from jose import JWTError
    with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": SUPABASE_JWT_SECRET}):
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")
```

**Step 3: Run test to verify it fails**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -m pytest tests/test_supabase_auth.py -v
```
Expected: FAIL — `decode_access_token` still uses `AUTH_SECRET_KEY`.

**Step 4: Update `api/auth_utils.py`**

Replace the entire file:
```python
"""JWT verification using Supabase JWT secret."""
import os
from jose import jwt

ALGORITHM = "HS256"


def _get_supabase_jwt_secret() -> str:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "SUPABASE_JWT_SECRET env var is not set or too short (min 32 chars)."
        )
    return secret


def decode_access_token(token: str) -> dict:
    """Verify and decode a Supabase-issued JWT. Raises JWTError on failure."""
    return jwt.decode(
        token,
        _get_supabase_jwt_secret(),
        algorithms=[ALGORITHM],
        audience="authenticated",
    )
```

**Step 5: Run test to verify it passes**

```bash
python -m pytest tests/test_supabase_auth.py -v
```
Expected: PASS for both tests.

**Step 6: Update `get_current_user` in `api/routers/auth.py` to read Bearer header**

Replace the `get_current_user` function (lines 90–115):
```python
def get_current_user(request: Request) -> dict:
    """FastAPI dependency — validates Supabase Bearer JWT, returns profile dict."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    # Fetch profile from Supabase (service role — bypasses RLS)
    from supabase import create_client
    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    result = supa.table("profiles").select("*").eq("id", user_id).single().execute()
    if not result.data:
        raise credentials_exception

    profile = result.data
    return {
        "id": profile["id"],
        "email": payload.get("email", ""),
        "username": profile["username"],
        "created_at": profile["created_at"],
        "role": profile.get("role", "user"),
        "avatar_url": profile.get("avatar_url"),
    }
```

Remove unused imports from `auth.py`: `uuid`, `hash_password`, `verify_password`, `create_access_token`, `File`, `UploadFile`.

**Step 7: Add service-key protection dependency for auto-grade endpoints**

Add to `api/routers/auth.py` (at end of file):
```python
FASTAPI_SERVICE_KEY = os.getenv("FASTAPI_SERVICE_KEY")

def verify_service_key(request: Request) -> None:
    """Dependency for internal endpoints called by Edge Functions / pg_cron."""
    key = request.headers.get("X-Service-Key")
    if not key or key != FASTAPI_SERVICE_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
```

**Step 8: Apply service key dependency to auto-grade endpoints**

In `api/routers/picks.py`, find the `auto_grade_picks` endpoint and change its dependency:
```python
# Before:
@router.post("/auto-grade")
async def auto_grade_picks(current_user: dict = Depends(get_current_user)):

# After:
from ..routers.auth import verify_service_key
@router.post("/auto-grade")
async def auto_grade_picks(_: None = Depends(verify_service_key)):
```

Do the same for `auto_grade_game_predictions` in `api/routers/games.py`.

**Step 9: Update environment variables**

Add to your `.env` / server config:
```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
SUPABASE_JWT_SECRET=<jwt_secret>
FASTAPI_SERVICE_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
```

Remove `AUTH_SECRET_KEY` from env config.

**Step 10: Update `api/main.py` — remove uploads static mount + auth_router**

```python
# Remove these lines:
_UPLOADS_DIR = Path(__file__).parent.parent / "uploads" / "avatars"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/avatars", StaticFiles(directory=str(_UPLOADS_DIR)), name="avatars")

# Remove from imports:
from .routers import players_router, bets_router, picks_router, games_router, auth_router, parlays_router
# Change to:
from .routers import players_router, bets_router, picks_router, games_router, parlays_router

# Remove:
app.include_router(auth_router)
```

Also update `api/routers/__init__.py` to remove `auth_router` export.

**Step 11: Update CSP in SecurityHeadersMiddleware to allow Supabase**

In `api/main.py`, update the CSP `connect-src`:
```python
"connect-src 'self' https://*.supabase.co wss://*.supabase.co;"
```

**Step 12: Restart FastAPI and verify health check**

```bash
uvicorn api.main:app --reload --port 8000
curl http://localhost:8000/api/health
```
Expected: `{"status": "healthy", ...}`

**Step 13: Commit**

```bash
git add api/auth_utils.py api/routers/auth.py api/routers/picks.py api/routers/games.py api/main.py api/routers/__init__.py requirements.txt tests/test_supabase_auth.py
git commit -m "feat: migrate FastAPI JWT verification to Supabase JWT secret"
```

---

## Task 6: FastAPI — avatar upload to Supabase Storage

**Files:**
- Modify: `api/routers/auth.py` — `upload_avatar` and `delete_avatar` endpoints

**Step 1: Update `upload_avatar` to write to Supabase Storage**

Replace the `upload_avatar` endpoint body:
```python
@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")

    contents = await file.read()
    if len(contents) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large — maximum 5MB")

    if not _validate_image_magic(contents, file.content_type):
        raise HTTPException(status_code=400, detail="File content does not match declared type")

    from supabase import create_client
    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    ext = _EXT_MAP[file.content_type]
    storage_path = f"{current_user['id']}.{ext}"

    # Upload to Supabase Storage (upsert overwrites existing)
    supa.storage.from_("avatars").upload(
        storage_path,
        contents,
        {"content-type": file.content_type, "upsert": "true"},
    )

    avatar_url = f"{os.environ['SUPABASE_URL']}/storage/v1/object/public/avatars/{storage_path}"

    # Update profiles table
    supa.table("profiles").update({"avatar_url": avatar_url}).eq("id", current_user["id"]).execute()

    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
        "role": current_user.get("role", "user"),
        "avatar_url": avatar_url,
    }
```

**Step 2: Update `delete_avatar` to remove from Supabase Storage**

```python
@router.delete("/avatar", status_code=200)
async def delete_avatar(current_user: dict = Depends(get_current_user)):
    from supabase import create_client
    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    user_id = current_user["id"]

    # Remove all avatar variants from storage
    for ext in ["jpg", "png", "webp"]:
        try:
            supa.storage.from_("avatars").remove([f"{user_id}.{ext}"])
        except Exception:
            pass  # File may not exist for that extension

    supa.table("profiles").update({"avatar_url": None}).eq("id", user_id).execute()

    return {
        "id": user_id,
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
        "role": current_user.get("role", "user"),
        "avatar_url": None,
    }
```

**Step 3: Update `change_password` to use Supabase Admin API**

```python
@router.post("/change-password", status_code=204)
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    from supabase import create_client
    supa = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    try:
        supa.auth.admin.update_user_by_id(
            current_user["id"],
            {"password": req.new_password}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

Note: Remove `current_password` verification — Supabase handles this client-side. The `ChangePasswordRequest` schema can drop `current_password`.

**Step 4: Commit**

```bash
git add api/routers/auth.py
git commit -m "feat: avatar upload/delete via Supabase Storage"
```

---

## Task 7: Frontend — install supabase-js + create singleton

**Files:**
- Create: `frontend/src/lib/supabase.ts`
- Modify: `frontend/.env.local` (or `.env`)
- Modify: `frontend/src/vite-env.d.ts`

**Step 1: Install @supabase/supabase-js**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm install @supabase/supabase-js
```

**Step 2: Add env vars to `frontend/.env.local`**

```
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon_public_key>
```

**Step 3: Update `frontend/src/vite-env.d.ts` to declare env vars**

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string
  readonly VITE_SUPABASE_ANON_KEY: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

**Step 4: Create `frontend/src/lib/supabase.ts`**

```ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY env vars')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

**Step 5: Verify the app still builds**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build
```
Expected: build succeeds (supabase client not yet wired to anything).

**Step 6: Commit**

```bash
git add frontend/src/lib/supabase.ts frontend/src/vite-env.d.ts frontend/.env.local frontend/package.json frontend/package-lock.json
git commit -m "feat: add supabase-js client singleton"
```

---

## Task 8: Frontend — migrate authStore to Supabase Auth

**Files:**
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/api/client.ts` — auth functions + apiFetch
- Modify: `frontend/src/types/auth.ts`
- Modify: `frontend/src/App.tsx` — initialize auth listener

**Step 1: Update `frontend/src/types/auth.ts`**

No change needed — `User` interface is unchanged (same fields).

**Step 2: Replace `frontend/src/store/authStore.ts`**

```ts
import { create } from 'zustand'
import { User } from '../types/auth'
import { supabase } from '../lib/supabase'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isUploadingAvatar: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
  clearError: () => void
  updateAvatar: (file: File) => Promise<void>
  removeAvatar: () => Promise<void>
  changePassword: (curPass: string, newPass: string) => Promise<void>
}

async function fetchProfile(userId: string): Promise<Partial<User>> {
  const { data } = await supabase
    .from('profiles')
    .select('username, avatar_url, role, created_at')
    .eq('id', userId)
    .single()
  return data ?? {}
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  isUploadingAvatar: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      const profile = await fetchProfile(data.user.id)
      set({
        user: {
          id: data.user.id,
          email: data.user.email!,
          username: profile.username ?? '',
          created_at: profile.created_at ?? data.user.created_at,
          role: (profile.role as 'user' | 'admin') ?? 'user',
          avatar_url: profile.avatar_url,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  signup: async (email, username, password) => {
    set({ isLoading: true, error: null })
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { username } },
      })
      if (error) throw error
      if (!data.user) throw new Error('Sign up failed')
      // Profile is created via DB trigger — fetch it
      const profile = await fetchProfile(data.user.id)
      set({
        user: {
          id: data.user.id,
          email: data.user.email!,
          username: profile.username ?? username,
          created_at: profile.created_at ?? new Date().toISOString(),
          role: 'user',
          avatar_url: undefined,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  logout: async () => {
    await supabase.auth.signOut()
    set({ user: null, isAuthenticated: false, error: null })
  },

  checkAuth: async () => {
    set({ isLoading: true })
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        set({ user: null, isAuthenticated: false, isLoading: false })
        return
      }
      const profile = await fetchProfile(session.user.id)
      set({
        user: {
          id: session.user.id,
          email: session.user.email!,
          username: profile.username ?? '',
          created_at: profile.created_at ?? session.user.created_at,
          role: (profile.role as 'user' | 'admin') ?? 'user',
          avatar_url: profile.avatar_url,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),

  updateAvatar: async (file) => {
    set({ isUploadingAvatar: true, error: null })
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) throw new Error('Not authenticated')

      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/auth/avatar', {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.access_token}` },
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? 'Upload failed')
      }
      const updated = await res.json()
      set((state) => ({
        user: state.user ? { ...state.user, avatar_url: updated.avatar_url } : null,
        isUploadingAvatar: false,
      }))
    } catch (err) {
      set({ isUploadingAvatar: false })
      throw err
    }
  },

  removeAvatar: async () => {
    set({ isUploadingAvatar: true, error: null })
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) throw new Error('Not authenticated')

      const res = await fetch('/api/auth/avatar', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      if (!res.ok) throw new Error('Failed to remove avatar')
      set((state) => ({
        user: state.user ? { ...state.user, avatar_url: undefined } : null,
        isUploadingAvatar: false,
      }))
    } catch (err) {
      set({ isUploadingAvatar: false })
      throw err
    }
  },

  changePassword: async (_curPass, newPass) => {
    const { error } = await supabase.auth.updateUser({ password: newPass })
    if (error) throw error
  },
}))
```

**Step 3: Update `apiFetch` in `frontend/src/api/client.ts` to send Bearer token**

Replace the `apiFetch` function:
```ts
async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  // Attach Supabase session token as Bearer
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(init.headers)
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }

  const res = await fetch(input, { ...init, headers })
  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:unauthorized'))
  }
  return res
}
```

Add `import { supabase } from '../lib/supabase'` at the top of `client.ts`.

Remove auth functions from `client.ts` that are now handled by Supabase directly:
- Delete: `authRegister`, `authLogin`, `authLogout`, `authGetMe`, `authRefresh`
- Keep: `uploadAvatar`, `deleteAvatar`, `changePassword` — but these are now called from the store directly (above), so delete them from `client.ts` too.

**Step 4: Update `frontend/src/App.tsx` — wire auth state listener**

Find where `checkAuth()` is called on mount (likely in a `useEffect` in App.tsx). Replace or supplement with an `onAuthStateChange` listener so the store stays in sync when the Supabase session changes (e.g., token refresh, tab refocus):

```ts
// In App.tsx, add inside the component or at module level:
useEffect(() => {
  checkAuth() // initial session check

  const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
    if (!session) {
      // User signed out (from another tab, token expired, etc.)
      useAuthStore.setState({ user: null, isAuthenticated: false })
    }
  })
  return () => subscription.unsubscribe()
}, [])
```

**Step 5: Test auth flow manually**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run dev
```

1. Navigate to `/signup` — create a new account
2. Check Supabase Dashboard → Auth → Users — new user should appear
3. Check Supabase Dashboard → Table Editor → profiles — row should be created by trigger
4. Log out, log back in
5. Verify user state is restored on page refresh (session persisted in localStorage by supabase-js)

**Step 6: Commit**

```bash
git add frontend/src/store/authStore.ts frontend/src/api/client.ts frontend/src/App.tsx
git commit -m "feat: migrate frontend auth to Supabase Auth"
```

---

## Task 9: Frontend — direct client reads

**Files:**
- Modify: `frontend/src/api/client.ts` — replace read functions
- Modify: `frontend/src/pages/HistoryPage.tsx`
- Modify: `frontend/src/pages/ParlayPage.tsx`
- Modify: `frontend/src/pages/GamesPage.tsx`

**Step 1: Replace read functions in `client.ts` with Supabase direct calls**

Add these functions (replacing the existing `getPicks`, `getParlays`, `getPerformanceStats`, `getCumulativeProfit`, `getGamePredictionHistory`, `getGameAccuracyStats`):

```ts
import { supabase } from '../lib/supabase'

export async function getPicks(pendingOnly = false): Promise<Pick[]> {
  let query = supabase
    .from('picks')
    .select('*')
    .order('timestamp', { ascending: false })

  if (pendingOnly) {
    query = query.is('won', null).eq('voided', false)
  }

  const { data, error } = await query
  if (error) throw new Error(error.message)
  return (data ?? []).map(p => ({ ...p, won: p.won ?? null }))
}

export async function getParlays(): Promise<SavedParlay[]> {
  const { data, error } = await supabase
    .from('parlays')
    .select('*, parlay_legs(*)')
    .order('created_at', { ascending: false })

  if (error) throw new Error(error.message)
  return data ?? []
}

export async function getGamePredictionHistory(): Promise<GamePredictionHistoryItem[]> {
  const { data, error } = await supabase
    .from('game_predictions')
    .select('*')
    .order('timestamp', { ascending: false })

  if (error) throw new Error(error.message)
  return (data ?? []).map(item => ({
    ...item,
    key_factors: typeof item.key_factors === 'string'
      ? JSON.parse(item.key_factors)
      : (item.key_factors ?? []),
  }))
}

export async function getPerformanceStats(): Promise<PerformanceStats> {
  // Fetch raw picks and compute stats client-side
  // (simpler than complex SQL view for by_stat/by_edge_range breakdowns)
  const { data: picks, error } = await supabase
    .from('picks')
    .select('stat, edge, won, voided')

  if (error) throw new Error(error.message)
  if (!picks) return emptyPerformanceStats()

  const graded = picks.filter(p => p.won !== null && !p.voided)
  const wins = graded.filter(p => p.won === true)
  const losses = graded.filter(p => p.won === false)
  const pushes = picks.filter(p => p.voided)

  const win_rate = graded.length > 0 ? wins.length / graded.length : 0
  const roi = graded.length > 0 ? (wins.length - losses.length) / graded.length : 0
  const avg_edge_winners = wins.length > 0
    ? wins.reduce((sum, p) => sum + (p.edge ?? 0), 0) / wins.length
    : 0

  // by_stat breakdown
  const by_stat: Record<string, { total: number; wins: number; win_rate: number }> = {}
  for (const p of graded) {
    if (!by_stat[p.stat]) by_stat[p.stat] = { total: 0, wins: 0, win_rate: 0 }
    by_stat[p.stat].total++
    if (p.won) by_stat[p.stat].wins++
  }
  for (const stat of Object.keys(by_stat)) {
    const s = by_stat[stat]
    s.win_rate = s.total > 0 ? s.wins / s.total : 0
  }

  // by_edge_range breakdown
  const edgeRanges = [
    { label: '0-5', min: 0, max: 5 },
    { label: '5-10', min: 5, max: 10 },
    { label: '10-15', min: 10, max: 15 },
    { label: '15+', min: 15, max: Infinity },
  ]
  const by_edge_range: Record<string, { total: number; wins: number; win_rate: number }> = {}
  for (const range of edgeRanges) {
    const inRange = graded.filter(p => (p.edge ?? 0) >= range.min && (p.edge ?? 0) < range.max)
    const rangeWins = inRange.filter(p => p.won)
    by_edge_range[range.label] = {
      total: inRange.length,
      wins: rangeWins.length,
      win_rate: inRange.length > 0 ? rangeWins.length / inRange.length : 0,
    }
  }

  return {
    total_picks: picks.length,
    graded_picks: graded.length,
    wins: wins.length,
    losses: losses.length,
    pushes: pushes.length,
    win_rate,
    roi,
    avg_edge_winners,
    by_stat,
    by_edge_range,
  }
}

function emptyPerformanceStats(): PerformanceStats {
  return {
    total_picks: 0, graded_picks: 0, wins: 0, losses: 0, pushes: 0,
    win_rate: 0, roi: 0, avg_edge_winners: 0, by_stat: {}, by_edge_range: {},
  }
}

export async function getCumulativeProfit(): Promise<CumulativeProfitPoint[]> {
  const { data, error } = await supabase
    .from('picks')
    .select('game_date, won, voided')
    .not('won', 'is', null)
    .not('game_date', 'is', null)
    .order('game_date', { ascending: true })

  if (error) throw new Error(error.message)

  let cumulative = 0
  return (data ?? []).map(p => {
    const profit = p.won === true ? 1 : (!p.voided ? -1 : 0)
    cumulative += profit
    return {
      date: p.game_date,
      profit,
      cumulative_profit: cumulative,
    }
  })
}

export async function getGameAccuracyStats(): Promise<GameAccuracyStats> {
  const { data, error } = await supabase
    .from('game_accuracy_stats')
    .select('*')
    .single()

  if (error) throw new Error(error.message)
  return {
    total_predictions: data.total_predictions ?? 0,
    graded_predictions: data.graded_predictions ?? 0,
    correct: data.correct ?? 0,
    incorrect: data.incorrect ?? 0,
    accuracy: data.accuracy ?? 0,
    by_confidence_range: {},  // computed client-side if needed
    recent_streak: '',        // computed client-side if needed
  }
}
```

**Step 2: Verify the app loads picks/parlays correctly**

```bash
npm run dev
```

Navigate to `/history` — picks should load. Navigate to parlays page — parlays should load.

**Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: replace FastAPI read endpoints with direct Supabase client reads"
```

---

## Task 10: Frontend — realtime hooks

**Files:**
- Create: `frontend/src/hooks/usePicksRealtime.ts`
- Create: `frontend/src/hooks/useParlaysRealtime.ts`
- Modify: `frontend/src/pages/HistoryPage.tsx`
- Modify: `frontend/src/pages/ParlayPage.tsx`

**Step 1: Create `frontend/src/hooks/usePicksRealtime.ts`**

```ts
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import type { Pick } from '../api/client'

export function usePicksRealtime() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const channel = supabase
      .channel('picks-realtime')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'picks' },
        (payload) => {
          queryClient.setQueryData<Pick[]>(['picks'], (old) =>
            old
              ? old.map((p) =>
                  p.id === payload.new.id ? { ...p, ...payload.new } : p
                )
              : old
          )
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [queryClient])
}
```

**Step 2: Create `frontend/src/hooks/useParlaysRealtime.ts`**

```ts
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import type { SavedParlay } from '../api/client'

export function useParlaysRealtime() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const channel = supabase
      .channel('parlays-realtime')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'parlays' },
        (payload) => {
          queryClient.setQueryData<SavedParlay[]>(['parlays'], (old) =>
            old
              ? old.map((p) =>
                  p.id === payload.new.id ? { ...p, ...payload.new } : p
                )
              : old
          )
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [queryClient])
}
```

**Step 3: Wire hooks into pages**

In `frontend/src/pages/HistoryPage.tsx`, add at the top of the component:
```ts
import { usePicksRealtime } from '../hooks/usePicksRealtime'

// Inside component:
usePicksRealtime()
```

In `frontend/src/pages/ParlayPage.tsx`:
```ts
import { useParlaysRealtime } from '../hooks/useParlaysRealtime'

// Inside component:
useParlaysRealtime()
```

**Step 4: Test realtime manually**

1. Open the History page in the browser
2. In Supabase Dashboard → Table Editor → picks, manually update a `won` value
3. Verify the UI updates without page refresh

**Step 5: Commit**

```bash
git add frontend/src/hooks/usePicksRealtime.ts frontend/src/hooks/useParlaysRealtime.ts frontend/src/pages/HistoryPage.tsx frontend/src/pages/ParlayPage.tsx
git commit -m "feat: add realtime picks and parlays subscriptions"
```

---

## Task 11: Edge Function — grade-picks

**Files:**
- Create: `supabase/functions/grade-picks/index.ts`

**Step 1: Install Supabase CLI if not already installed**

```bash
brew install supabase/tap/supabase
supabase --version
```

**Step 2: Initialize Supabase local config**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
supabase init
```

**Step 3: Create Edge Function file**

```bash
mkdir -p supabase/functions/grade-picks
```

Create `supabase/functions/grade-picks/index.ts`:
```ts
const FASTAPI_URL = Deno.env.get('FASTAPI_URL')!
const FASTAPI_SERVICE_KEY = Deno.env.get('FASTAPI_SERVICE_KEY')!

function isAfterGradeWindow(): boolean {
  const now = new Date()
  const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  return etTime.getHours() >= 23
}

function getTodayET(): string {
  const now = new Date()
  return new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
    .toISOString()
    .slice(0, 10)
}

Deno.serve(async (req) => {
  try {
    const body = await req.json()
    const record = body.record

    if (!record?.game_date) {
      return new Response('no game_date', { status: 200 })
    }

    const todayET = getTodayET()
    const isToday = record.game_date === todayET

    if (!isToday || !isAfterGradeWindow()) {
      return new Response('skipped — not today or too early', { status: 200 })
    }

    // Call FastAPI auto-grade
    const res = await fetch(`${FASTAPI_URL}/api/picks/auto-grade`, {
      method: 'POST',
      headers: { 'X-Service-Key': FASTAPI_SERVICE_KEY },
    })

    const text = await res.text()
    console.log(`auto-grade picks response: ${res.status} ${text}`)

    // Also grade game predictions
    await fetch(`${FASTAPI_URL}/api/games/auto-grade`, {
      method: 'POST',
      headers: { 'X-Service-Key': FASTAPI_SERVICE_KEY },
    })

    return new Response('graded', { status: 200 })
  } catch (err) {
    console.error('grade-picks error:', err)
    return new Response(`error: ${err}`, { status: 500 })
  }
})
```

**Step 4: Set Edge Function secrets**

```bash
supabase secrets set FASTAPI_URL=https://<your-fastapi-host>
supabase secrets set FASTAPI_SERVICE_KEY=<same-value-as-FASTAPI_SERVICE_KEY-in-fastapi-env>
```

**Step 5: Deploy Edge Function**

```bash
supabase functions deploy grade-picks --project-ref <your-project-ref>
```
Expected: `Deployed edge function grade-picks`

**Step 6: Create Database Webhook**

In Supabase Dashboard → Database → Webhooks → Create new webhook:
- Name: `on-pick-insert-grade`
- Table: `picks`
- Events: `INSERT`
- URL: `https://<project-ref>.supabase.co/functions/v1/grade-picks`
- HTTP headers: `Authorization: Bearer <anon_key>`

**Step 7: Set up pg_cron jobs**

In Supabase SQL Editor (enable pg_cron extension first if not already):
```sql
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Nightly picks grading (11:30 PM ET = 4:30 AM UTC)
SELECT cron.schedule(
  'nightly-auto-grade-picks',
  '30 4 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/picks/auto-grade',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>')
  );
  $$
);

-- Nightly game grading (11:35 PM ET = 4:35 AM UTC)
SELECT cron.schedule(
  'nightly-auto-grade-games',
  '35 4 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/games/auto-grade',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>')
  );
  $$
);
```

**Step 8: Verify cron jobs are scheduled**

```sql
SELECT jobname, schedule, active FROM cron.job;
```
Expected: both jobs listed with `active = true`.

**Step 9: Commit**

```bash
git add supabase/functions/grade-picks/index.ts supabase/config.toml
git commit -m "feat: add Edge Function + pg_cron for automated pick grading"
```

---

## Task 12: Cleanup

**Step 1: Delete old FastAPI auth endpoints**

Remove from `api/routers/auth.py`:
- `register` endpoint
- `login` endpoint
- `logout` endpoint
- `me` endpoint
- `refresh_token` endpoint
- `hash_password`, `verify_password` imports
- `create_access_token` import
- `_COOKIE_NAME`, `_COOKIE_SECURE`, `_COOKIE_MAX_AGE`, `_set_auth_cookie`
- `RegisterRequest`, `LoginRequest`, `AuthResponse` schemas (not used by remaining endpoints)

Keep in `api/routers/auth.py`:
- `get_current_user` (used by all other routers)
- `verify_service_key` (used by auto-grade endpoints)
- `upload_avatar`
- `delete_avatar`
- `change_password`
- `ChangePasswordRequest` schema

**Step 2: Remove avatar disk storage**

```bash
rm -rf /Users/hhabal/Downloads/Projects/NBA/EVAL/uploads/
```

**Step 3: Remove old auth client functions from `client.ts`**

Verify these are already removed (done in Task 8):
- `authRegister`, `authLogin`, `authLogout`, `authGetMe`, `authRefresh`
- `uploadAvatar`, `deleteAvatar`, `changePassword` (moved to authStore)

**Step 4: Remove `AUTH_SECRET_KEY` from any env files or documentation**

```bash
grep -r "AUTH_SECRET_KEY" /Users/hhabal/Downloads/Projects/NBA/EVAL --include="*.py" --include="*.md" --include="*.env*"
```
Remove any references found.

**Step 5: Run full build to verify no broken imports**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build

cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -m pytest tests/ -v
```

**Step 6: Final commit**

```bash
git add -A
git commit -m "chore: remove legacy custom auth, cookie handling, and disk avatar storage"
```

---

## Verification checklist

After all tasks complete, verify end-to-end:

- [ ] Sign up with a new account → profile row created in Supabase
- [ ] Log in → session persisted in localStorage, survives page refresh
- [ ] Log out → session cleared, redirected to login
- [ ] Upload avatar → appears in Supabase Storage `avatars` bucket
- [ ] Create a pick → appears in picks table with `user_id = auth.uid()`
- [ ] Another user cannot see your picks (test with two accounts)
- [ ] Manually update a pick's `won` field in Supabase → History page updates without refresh (realtime)
- [ ] Manually update a parlay's `status` → Parlay page updates without refresh
- [ ] Hit `POST /api/picks/auto-grade` without `X-Service-Key` → 403 Forbidden
- [ ] Hit `POST /api/picks/auto-grade` with correct `X-Service-Key` → grades pending picks
- [ ] Invoke Edge Function manually → calls FastAPI grader successfully
- [ ] Verify cron jobs listed in `cron.job` table
