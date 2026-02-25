# User Accounts & Auth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the mock Zustand auth with a real JWT-based account system — users can register, log in, and have their picks/stats scoped to their own account.

**Architecture:** Custom JWT auth (HS256, 7-day tokens) with bcrypt passwords stored in `picks_history.db`. A new `api/routers/auth.py` handles register/login/me. All picks endpoints gain a `get_current_user` FastAPI dependency that scopes DB queries to the authenticated user. The frontend `authStore.ts` is rewired to call the real API and persists tokens in `localStorage`.

**Tech Stack:** FastAPI, `passlib[bcrypt]`, `python-jose[cryptography]`, SQLite (`db.py`), React/Zustand, TypeScript, localStorage

---

### Task 1: Add backend auth dependencies

**Files:**
- Modify: `api/requirements.txt`

**Step 1: Add the two packages**

Edit `api/requirements.txt` to read:
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
sse-starlette>=1.8.0
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0
```

**Step 2: Install them**

```bash
pip install passlib[bcrypt] python-jose[cryptography]
```

Expected: both install without error.

**Step 3: Commit**

```bash
git add api/requirements.txt
git commit -m "chore: add passlib and python-jose for JWT auth"
```

---

### Task 2: DB migrations — users table + user_id on picks

**Files:**
- Modify: `db.py` — extend `init_db()` only

**Step 1: Add users table creation and user_id migration inside `init_db()`**

In `db.py`, find the end of `init_db()` — right before the final `conn.commit()` and `conn.close()`. Read lines 26–130 of `db.py` to find the exact closing lines, then add this block:

```python
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            username   TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Add user_id to picks if not present
    cursor.execute("PRAGMA table_info(picks)")
    picks_columns = {row[1] for row in cursor.fetchall()}
    if "user_id" not in picks_columns:
        cursor.execute("ALTER TABLE picks ADD COLUMN user_id TEXT")
```

This goes at the end of the `init_db()` function, before any existing `conn.commit()` / `conn.close()` calls.

**Step 2: Verify migration runs cleanly**

```bash
python -c "import db; db.init_db(); print('OK')"
```

Expected output: `OK` (no errors).

**Step 3: Verify schema in SQLite**

```bash
sqlite3 picks_history.db ".schema users"
sqlite3 picks_history.db "PRAGMA table_info(picks)" | grep user_id
```

Expected: users table printed, and `user_id` column appears in picks.

**Step 4: Commit**

```bash
git add db.py
git commit -m "feat: add users table and user_id column migration to db"
```

---

### Task 3: DB user CRUD functions

**Files:**
- Modify: `db.py` — add three functions after `init_db()`

**Step 1: Add user functions to `db.py`**

After the `init_db()` function (before any other function), add:

```python
# ── User functions ────────────────────────────────────────────

def create_user(user_id: str, email: str, hashed_password: str, username: str) -> dict:
    """Insert a new user row. Returns the created user dict."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO users (id, email, hashed_password, username, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, email, hashed_password, username, now)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


def get_user_by_email(email: str) -> dict | None:
    """Return user dict for given email, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    """Return user dict for given id, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
```

**Step 2: Smoke-test the functions**

```bash
python -c "
import db, uuid
db.init_db()
uid = str(uuid.uuid4())
u = db.create_user(uid, 'test@test.com', 'hashed', 'testuser')
print('created:', u['email'])
found = db.get_user_by_email('test@test.com')
print('found by email:', found['username'])
by_id = db.get_user_by_id(uid)
print('found by id:', by_id['id'])
# Cleanup
import sqlite3
conn = sqlite3.connect('picks_history.db')
conn.execute('DELETE FROM users WHERE email=?', ('test@test.com',))
conn.commit()
conn.close()
print('OK')
"
```

Expected: prints created/found/found lines then `OK`.

**Step 3: Commit**

```bash
git add db.py
git commit -m "feat: add create_user, get_user_by_email, get_user_by_id to db"
```

---

### Task 4: Auth utilities — JWT + bcrypt

**Files:**
- Create: `api/auth_utils.py`

**Step 1: Create the file**

```python
"""JWT token creation/verification and password hashing utilities."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import JWTError, jwt
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _get_secret_key() -> str:
    """Read secret key from AUTH_SECRET_KEY env var, then config.json, then raise."""
    secret = os.environ.get("AUTH_SECRET_KEY")
    if secret:
        return secret
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text())
            if cfg.get("auth_secret_key"):
                return cfg["auth_secret_key"]
        except Exception:
            pass
    raise RuntimeError(
        "AUTH_SECRET_KEY not set. Add it as an env var or set 'auth_secret_key' in config.json"
    )


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Return decoded payload dict, or raise JWTError on failure."""
    return jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
```

**Step 2: Smoke-test**

```bash
python -c "
import sys; sys.path.insert(0, 'api')
# Set a test secret
import os; os.environ['AUTH_SECRET_KEY'] = 'testsecret123'
from auth_utils import hash_password, verify_password, create_access_token, decode_access_token
h = hash_password('mypassword')
assert verify_password('mypassword', h), 'verify failed'
assert not verify_password('wrong', h), 'should fail'
token = create_access_token('user-123', 'a@b.com')
payload = decode_access_token(token)
assert payload['sub'] == 'user-123'
assert payload['email'] == 'a@b.com'
print('OK')
"
```

Expected: `OK`.

**Step 3: Add `auth_secret_key` placeholder to config.json**

Read `config.json` (currently `{"odds_api_key": "..."}`). Add the auth key field:

```json
{
  "odds_api_key": "<existing_value>",
  "auth_secret_key": "CHANGE_ME_use_a_long_random_string_in_production"
}
```

**Step 4: Commit**

```bash
git add api/auth_utils.py config.json
git commit -m "feat: add JWT and bcrypt auth utilities"
```

---

### Task 5: Auth router — register / login / me

**Files:**
- Create: `api/routers/auth.py`

**Step 1: Create the file**

```python
"""Authentication endpoints — register, login, me."""
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, EmailStr

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db
from ..auth_utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer()


# ── Schemas ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


# ── Dependency ─────────────────────────────────────────────────

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """FastAPI dependency — validates Bearer token, returns user dict."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get_user_by_id(user_id)
    if not user:
        raise credentials_exception
    return user


# ── Endpoints ──────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(req: RegisterRequest):
    if db.get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already in use")

    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)
    user = db.create_user(user_id, req.email, hashed, req.username)

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "email": user["email"], "username": user["username"],
              "created_at": user["created_at"]},
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    invalid = HTTPException(status_code=401, detail="Invalid credentials")
    user = db.get_user_by_email(req.email)
    if not user:
        raise invalid
    if not verify_password(req.password, user["hashed_password"]):
        raise invalid

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "email": user["email"], "username": user["username"],
              "created_at": user["created_at"]},
    )


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
    }
```

**Step 2: Write the pytest tests**

Create `tests/test_auth.py`:

```python
"""Tests for auth endpoints."""
import sys
import os
from pathlib import Path

# Point at a temp DB for tests
os.environ["AUTH_SECRET_KEY"] = "test-secret-key-for-tests"
_TEST_DB = Path(__file__).parent / "test_picks.db"
os.environ["TEST_DB_PATH"] = str(_TEST_DB)

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import pytest
from fastapi.testclient import TestClient

# Patch DB_PATH before importing anything that uses it
import db
db.DB_PATH = _TEST_DB

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Re-init DB and wipe users before each test."""
    db.init_db()
    conn = db.get_connection()
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM picks")
    conn.commit()
    conn.close()
    yield
    # teardown: remove test DB
    if _TEST_DB.exists():
        _TEST_DB.unlink()


def test_register_creates_user_and_returns_token():
    r = client.post("/api/auth/register", json={
        "email": "user@test.com", "username": "tester", "password": "pass123"
    })
    assert r.status_code == 201
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == "user@test.com"
    assert data["user"]["username"] == "tester"


def test_register_duplicate_email_returns_409():
    payload = {"email": "dup@test.com", "username": "a", "password": "pass"}
    client.post("/api/auth/register", json=payload)
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 409


def test_login_valid_credentials():
    client.post("/api/auth/register", json={
        "email": "log@test.com", "username": "logger", "password": "mypass"
    })
    r = client.post("/api/auth/login", json={"email": "log@test.com", "password": "mypass"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_wrong_password_returns_401():
    client.post("/api/auth/register", json={
        "email": "x@test.com", "username": "x", "password": "right"
    })
    r = client.post("/api/auth/login", json={"email": "x@test.com", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_email_returns_401():
    r = client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "x"})
    assert r.status_code == 401


def test_me_with_valid_token():
    reg = client.post("/api/auth/register", json={
        "email": "me@test.com", "username": "meuser", "password": "pw"
    })
    token = reg.json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "me@test.com"


def test_me_without_token_returns_403():
    r = client.get("/api/auth/me")
    assert r.status_code in (401, 403)
```

**Step 3: Run the tests — expect them to fail (router not registered yet)**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
pip install pytest httpx
pytest tests/test_auth.py -v 2>&1 | head -40
```

Expected: import errors or 404s — the router isn't wired in yet.

**Step 4: Commit the tests + router (pre-wiring)**

```bash
git add api/routers/auth.py tests/test_auth.py
git commit -m "feat: add auth router and test suite (pre-wire)"
```

---

### Task 6: Wire auth router into main.py

**Files:**
- Modify: `api/routers/__init__.py`
- Modify: `api/main.py`

**Step 1: Export auth_router from `__init__.py`**

Edit `api/routers/__init__.py`:

```python
"""Routers package."""
from .players import router as players_router
from .bets import router as bets_router
from .picks import router as picks_router
from .games import router as games_router
from .auth import router as auth_router

__all__ = ['players_router', 'bets_router', 'picks_router', 'games_router', 'auth_router']
```

**Step 2: Include router in `api/main.py`**

Change the import line and add the router:

```python
from .routers import players_router, bets_router, picks_router, games_router, auth_router
```

After the existing `app.include_router(games_router)` line, add:

```python
app.include_router(auth_router)
```

**Step 3: Run the tests — expect them to pass**

```bash
pytest tests/test_auth.py -v
```

Expected: all 6 tests PASS.

**Step 4: Commit**

```bash
git add api/routers/__init__.py api/main.py
git commit -m "feat: wire auth router into FastAPI app — auth tests passing"
```

---

### Task 7: Scope picks endpoints by authenticated user

**Files:**
- Modify: `db.py` — add `user_id` param to 5 functions
- Modify: `api/routers/picks.py` — add `get_current_user` dependency

**Step 1: Update `db.py` picks functions to accept `user_id`**

Find each of these functions in `db.py` and add the `user_id` parameter + `WHERE` clause. The changes are surgical — only the query changes, not the return type.

**`get_picks_history(days, user_id=None)`** — add `user_id` param, add `AND user_id = ?` when set:
```python
def get_picks_history(days: int = 30, user_id: str = None) -> List[dict]:
    # ... existing code to build cutoff date ...
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute(
            "SELECT * FROM picks WHERE timestamp >= ? AND (voided IS NULL OR voided = 0) AND user_id = ? ORDER BY timestamp DESC",
            (cutoff.isoformat(), user_id)
        )
    else:
        cursor.execute(
            "SELECT * FROM picks WHERE timestamp >= ? AND (voided IS NULL OR voided = 0) ORDER BY timestamp DESC",
            (cutoff.isoformat(),)
        )
    # ... rest unchanged ...
```

**`get_pending_picks(user_id=None)`** — add filter:
```python
def get_pending_picks(user_id: str = None) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute(
            "SELECT * FROM picks WHERE won IS NULL AND (voided IS NULL OR voided = 0) AND user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        )
    else:
        cursor.execute(
            "SELECT * FROM picks WHERE won IS NULL AND (voided IS NULL OR voided = 0) ORDER BY timestamp DESC"
        )
    # ... rest unchanged ...
```

**`get_performance_stats(user_id=None)`** — the inner SQL queries need `AND user_id = ?` appended where they filter picks. Find the SELECT statements inside this function and add the user filter when `user_id` is set. Look for the pattern `WHERE won IS NOT NULL AND voided` and add `AND user_id = ?` (with `user_id` bound in the params tuple).

**`get_cumulative_profit(user_id=None)`** — same pattern: add `AND user_id = ?` to the SQL and pass `user_id` as param when set.

**`save_pick(pick_data)`** — already accepts a dict; the caller will add `user_id` to the dict. Update the INSERT to include `user_id`:

Find the INSERT statement in `save_pick` and add `user_id` to both the column list and `?` placeholders. Add:
```python
    user_id = pick_data.get('user_id')
    # add to the INSERT VALUES
```

The exact edit: find `INSERT INTO picks (` and extend with `, user_id` and add the value at the end.

> **Note:** `db.py` is 1400+ lines. Read the relevant function bodies before editing. Use `grep` to find exact line numbers: `grep -n "def get_picks_history\|def get_pending_picks\|def get_performance_stats\|def get_cumulative_profit\|def save_pick" db.py`

**Step 2: Update `api/routers/picks.py` to require auth**

Add imports at the top of `picks.py`:
```python
from fastapi import APIRouter, HTTPException, Query, Depends
from ..routers.auth import get_current_user
```

Then update each endpoint to inject the user:

**`get_picks`:**
```python
@router.get("", response_model=List[PickResponse])
async def get_picks(
    days: int = Query(default=30, ge=1, le=365),
    pending_only: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    if pending_only:
        picks = db.get_pending_picks(user_id=user_id)
    else:
        picks = db.get_picks_history(days=days, user_id=user_id)
    return [_pick_to_response(p) for p in picks]
```

**`create_pick`:**
```python
@router.post("", response_model=PickResponse)
async def create_pick(pick: PickCreate, current_user: dict = Depends(get_current_user)):
    pick_data = {
        # ... existing fields ...
        'user_id': current_user["id"],
    }
    # ... rest unchanged ...
```

**`get_pick`**, **`grade_pick`**, **`delete_pick`** — add `current_user = Depends(get_current_user)` and verify ownership:
```python
    pick = next((p for p in all_picks if p['id'] == pick_id), None)
    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")
    if pick.get('user_id') and pick['user_id'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Not your pick")
```

**`auto_grade_picks`:**
```python
@router.post("/auto-grade")
async def auto_grade_picks(current_user: dict = Depends(get_current_user)):
    result = db.auto_grade_picks()  # auto-grade still runs globally (NBA scores); scoping is in the response
    return result
```

**`get_performance_stats`:**
```python
@router.get("/stats/performance", response_model=PerformanceStats)
async def get_performance_stats(current_user: dict = Depends(get_current_user)):
    stats = db.get_performance_stats(user_id=current_user["id"])
    # ... response unchanged ...
```

**`get_cumulative_profit`:**
```python
@router.get("/stats/profit", response_model=List[CumulativeProfitPoint])
async def get_cumulative_profit(current_user: dict = Depends(get_current_user)):
    profit_data = db.get_cumulative_profit(user_id=current_user["id"])
    # ... response unchanged ...
```

**Step 3: Write a picks-with-auth test**

Add to `tests/test_auth.py`:

```python
def test_create_pick_requires_auth():
    r = client.post("/api/picks", json={
        "player": "LeBron James", "stat": "PTS", "line": 25.5,
        "prediction": 27.0, "direction": "OVER", "edge": 5.8,
    })
    assert r.status_code in (401, 403)


def test_create_and_retrieve_pick_scoped_to_user():
    # Register two users
    r1 = client.post("/api/auth/register", json={
        "email": "u1@test.com", "username": "u1", "password": "pw"
    })
    token1 = r1.json()["token"]
    r2 = client.post("/api/auth/register", json={
        "email": "u2@test.com", "username": "u2", "password": "pw"
    })
    token2 = r2.json()["token"]

    # User 1 saves a pick
    client.post("/api/picks", json={
        "player": "LeBron James", "stat": "PTS", "line": 25.5,
        "prediction": 27.0, "direction": "OVER", "edge": 5.8,
    }, headers={"Authorization": f"Bearer {token1}"})

    # User 1 sees 1 pick, user 2 sees 0
    picks1 = client.get("/api/picks", headers={"Authorization": f"Bearer {token1}"}).json()
    picks2 = client.get("/api/picks", headers={"Authorization": f"Bearer {token2}"}).json()
    assert len(picks1) == 1
    assert len(picks2) == 0
```

**Step 4: Run full test suite**

```bash
pytest tests/test_auth.py -v
```

Expected: all tests PASS.

**Step 5: Commit**

```bash
git add db.py api/routers/picks.py tests/test_auth.py
git commit -m "feat: scope all picks endpoints to authenticated user"
```

---

### Task 8: Frontend — auth API functions and auth headers

**Files:**
- Modify: `frontend/src/api/client.ts`

**Step 1: Add auth helper and functions at the top of the API section**

After the existing type definitions (around line 161), add:

```typescript
// ── Auth helpers ────────────────────────────────────────────

const TOKEN_KEY = 'nba_eval_token'

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(): HeadersInit {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Auth API functions ─────────────────────────────────────

export interface AuthUser {
  id: string
  email: string
  username: string
  created_at: string
}

export interface AuthResponse {
  token: string
  user: AuthUser
}

export async function authRegister(
  email: string,
  username: string,
  password: string
): Promise<AuthResponse> {
  const r = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username, password }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || 'Registration failed')
  }
  return r.json()
}

export async function authLogin(email: string, password: string): Promise<AuthResponse> {
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || 'Invalid credentials')
  }
  return r.json()
}

export async function authGetMe(): Promise<AuthUser> {
  const r = await fetch(`${API_BASE}/auth/me`, {
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
  })
  if (!r.ok) throw new Error('Not authenticated')
  return r.json()
}
```

**Step 2: Update all picks functions to pass auth headers**

For each of these functions, add `...authHeaders()` to the `headers` object:

- `getPicks` — add `headers: { ...authHeaders() }` to the fetch call
- `createPick` — add `...authHeaders()` alongside `'Content-Type': 'application/json'`
- `gradePick` — same
- `deletePick` — add `headers: { ...authHeaders() }`
- `autoGradePicks` — add `headers: { ...authHeaders() }`
- `getPerformanceStats` — add `headers: { ...authHeaders() }`
- `getCumulativeProfit` — add `headers: { ...authHeaders() }`

Example for `getPicks`:
```typescript
export async function getPicks(days = 30, pendingOnly = false): Promise<Pick[]> {
  const params = new URLSearchParams({
    days: days.toString(),
    pending_only: pendingOnly.toString(),
  })
  const response = await fetch(`${API_BASE}/picks?${params}`, {
    headers: { ...authHeaders() },
  })
  if (!response.ok) throw new Error('Failed to fetch picks')
  return response.json()
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add auth API functions and inject auth headers on picks calls"
```

---

### Task 9: Replace mock authStore with real implementation

**Files:**
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/types/auth.ts` — simplify User type

**Step 1: Simplify the User type in `types/auth.ts`**

The `subscription_tier` field no longer makes sense (everyone gets full access). Replace the `User` interface:

```typescript
export interface User {
  id: string
  email: string
  username: string
  created_at: string
}
```

Keep `AuthState` as-is. Remove `SubscriptionTier` and `SUBSCRIPTION_TIERS` (unused).

**Step 2: Rewrite `authStore.ts`**

```typescript
import { create } from 'zustand'
import { User } from '../types/auth'
import {
  authLogin,
  authRegister,
  authGetMe,
  setAuthToken,
  clearAuthToken,
  getAuthToken,
} from '../api/client'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { token, user } = await authLogin(email, password)
      setAuthToken(token)
      set({ user, isAuthenticated: true, isLoading: false })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  signup: async (email, username, password) => {
    set({ isLoading: true, error: null })
    try {
      const { token, user } = await authRegister(email, username, password)
      setAuthToken(token)
      set({ user, isAuthenticated: true, isLoading: false })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  logout: () => {
    clearAuthToken()
    set({ user: null, isAuthenticated: false, error: null })
  },

  checkAuth: async () => {
    if (!getAuthToken()) return
    set({ isLoading: true })
    try {
      const user = await authGetMe()
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      clearAuthToken()
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),
}))
```

**Step 3: Check for TypeScript errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Fix any type errors (likely `subscription_tier` references in other files). Search for usages:

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL && grep -rn "subscription_tier" frontend/src/
```

Remove or replace any references found.

**Step 4: Commit**

```bash
git add frontend/src/store/authStore.ts frontend/src/types/auth.ts
git commit -m "feat: replace mock authStore with real JWT-backed implementation"
```

---

### Task 10: Wire checkAuth on app load + guard pending-picks query

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Call `checkAuth` on mount and guard the pending-picks query**

In `App.tsx`, the `useAuthStore` import already exists. Add `checkAuth` to the destructure and add a `useEffect`. Also gate the pending-picks query on `isAuthenticated` so it doesn't fire a 401 for logged-out users:

```tsx
import { useEffect } from 'react'
// ...existing imports...

function App() {
  const { isAuthenticated, checkAuth } = useAuthStore()
  const { theme, toggleTheme } = useThemeStore()

  // Rehydrate session on app load
  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  const { data: pendingPicks = [] } = useQuery({
    queryKey: ['pending-picks'],
    queryFn: () => getPicks(30, true),
    staleTime: 1000 * 30,
    enabled: isAuthenticated,   // ← add this line
  })

  // ... rest of component unchanged ...
}
```

**Step 2: Run the frontend dev server and manually verify the full flow**

```bash
cd frontend && npm run dev
```

Manual test checklist:
1. Open `http://localhost:5173` — loads without console errors
2. Click Sign In — login page loads
3. Register a new account at `/signup` — redirects to home, user menu appears in nav
4. Navigate to History — picks list loads (empty for new user)
5. Run a prediction on PlayerPage, save a pick — pick appears in History
6. Log out — nav reverts to "Sign In", History redirects to /login
7. Log back in — same pick appears in History (persisted)
8. Hard-refresh (`Cmd+R`) — still logged in (token from localStorage)

**Step 3: Run TypeScript build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors.

**Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: call checkAuth on app load, gate pending-picks query on auth"
```

---

### Task 11: Final integration check + push

**Step 1: Run full test suite**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
pytest tests/test_auth.py -v
```

Expected: all 8 tests PASS.

**Step 2: Start both servers and run the manual checklist from Task 10**

```bash
./start_api.sh &
cd frontend && npm run dev
```

Verify all 8 manual test steps pass.

**Step 3: Push**

```bash
git push origin main
```

---

## Summary of files changed

| File | Change |
|------|--------|
| `api/requirements.txt` | + passlib, python-jose |
| `db.py` | + users table, user_id migration, 3 user functions, user_id scoping on 5 pick functions |
| `api/auth_utils.py` | **New** — bcrypt + JWT helpers |
| `api/routers/auth.py` | **New** — register/login/me + `get_current_user` dependency |
| `api/routers/__init__.py` | + auth_router export |
| `api/main.py` | + include auth_router |
| `api/routers/picks.py` | + `Depends(get_current_user)` on all endpoints, ownership checks |
| `frontend/src/api/client.ts` | + auth functions, authHeaders on picks calls |
| `frontend/src/store/authStore.ts` | Full rewrite — real API calls |
| `frontend/src/types/auth.ts` | Simplify User type |
| `frontend/src/App.tsx` | + checkAuth on mount, guard pending-picks query |
| `tests/test_auth.py` | **New** — 8 pytest tests |
| `config.json` | + auth_secret_key placeholder |
