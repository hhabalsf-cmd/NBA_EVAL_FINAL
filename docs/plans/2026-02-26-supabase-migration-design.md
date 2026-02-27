# Supabase Migration Design (Option A — psycopg2)

**Date:** 2026-02-26
**Scope:** Replace SQLite (`picks_history.db`) with Supabase Postgres. Auth, frontend, and ML core are unaffected.

---

## Approach

Direct Postgres connection via `psycopg2`. All function signatures in `db.py` remain identical — callers in `api/routers/` require no changes.

---

## Files Changed

| File | Change |
|---|---|
| `db.py` | Swap `sqlite3` → `psycopg2`, fix SQL dialect |
| `api/requirements.txt` | Add `psycopg2-binary` |
| `scripts/migrate_to_supabase.py` | New one-time data migration script |
| `start_api.sh` | Document `DATABASE_URL` env var |

---

## Schema (run once in Supabase SQL Editor)

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    username TEXT,
    created_at TEXT,
    role TEXT DEFAULT 'user',
    avatar_url TEXT
);

CREATE TABLE picks (
    id BIGSERIAL PRIMARY KEY,
    timestamp TEXT,
    player TEXT,
    player_id TEXT,
    team_abbrev TEXT,
    stat TEXT,
    line REAL,
    prediction REAL,
    direction TEXT,
    edge REAL,
    confidence REAL,
    opponent TEXT,
    is_home INTEGER DEFAULT 0,
    actual_result REAL,
    won INTEGER,
    model_type TEXT,
    game_date TEXT,
    graded_at TEXT,
    voided INTEGER DEFAULT 0,
    void_reason TEXT,
    prob_over REAL,
    user_id TEXT REFERENCES users(id)
);

CREATE TABLE game_predictions (
    id BIGSERIAL PRIMARY KEY,
    timestamp TEXT,
    game_date TEXT,
    home_team TEXT,
    away_team TEXT,
    home_team_id TEXT,
    away_team_id TEXT,
    predicted_winner TEXT,
    home_win_prob REAL,
    away_win_prob REAL,
    confidence REAL,
    actual_winner TEXT,
    correct INTEGER,
    key_factors TEXT,
    model_version TEXT,
    graded_at TEXT,
    extended_data TEXT
);
```

No RLS policies — existing `user_id` scoping in Python handles access control.

---

## Connection Management

Replace per-function SQLite connect with:

```python
import psycopg2
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)
```

Every `sqlite3.connect(DB_PATH)` call becomes `get_connection()`.

### SQL Dialect Fixes

| SQLite | Postgres |
|---|---|
| `?` placeholders | `%s` |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` |
| `PRAGMA table_info(t)` | `SELECT column_name FROM information_schema.columns WHERE table_name = 't'` |
| `datetime('now')` | `NOW()` |
| `cursor.lastrowid` | `RETURNING id` + `cursor.fetchone()[0]` |

---

## Data Migration Script (`scripts/migrate_to_supabase.py`)

One-time script to move existing data from SQLite to Supabase Postgres.

**Behaviour:**
- Opens `picks_history.db` locally via `sqlite3`
- Migrates in FK order: `users` → `picks` → `game_predictions`
- Uses `INSERT ... ON CONFLICT DO NOTHING` — safe to re-run
- Preserves existing `id` values; resets Postgres sequences for `picks` and `game_predictions` after insert
- Prints per-table summary (rows migrated, failures)
- Skips Excel sync (live operations only)

**Usage:**
```bash
DATABASE_URL="postgresql://postgres:[password]@[host]:5432/postgres" python scripts/migrate_to_supabase.py
```

Get `DATABASE_URL` from: Supabase dashboard → Project Settings → Database → Connection String (URI).

---

## Environment Config

Add to shell profile or `.env`:
```bash
export DATABASE_URL="postgresql://postgres:[password]@[host]:5432/postgres"
```

Document in `start_api.sh` as a required env var.
