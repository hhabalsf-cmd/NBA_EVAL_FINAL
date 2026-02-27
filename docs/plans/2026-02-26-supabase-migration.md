# Supabase Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace SQLite (`picks_history.db`) with Supabase Postgres by swapping `sqlite3` for `psycopg2` in `db.py`, fixing SQL dialect differences, and migrating existing data.

**Architecture:** `db.py` keeps all function signatures identical — only the connection layer and SQL syntax changes. All callers in `api/routers/` are untouched. A one-time migration script moves existing rows from SQLite to Supabase.

**Tech Stack:** `psycopg2-binary`, Supabase Postgres (free tier), `DATABASE_URL` env var (Supabase connection string URI)

---

### Task 1: Add dependency and document env var

**Files:**
- Modify: `api/requirements.txt`
- Modify: `start_api.sh`

**Step 1: Add psycopg2-binary to requirements**

In `api/requirements.txt`, after the last line, add:
```
psycopg2-binary>=2.9.9
```

**Step 2: Install it**

```bash
pip install psycopg2-binary
```

Expected: installs without errors.

**Step 3: Document DATABASE_URL in start_api.sh**

In `start_api.sh`, after line 4 (`cd "$(dirname "$0")"`), add:
```bash
# Required env var: DATABASE_URL (Supabase connection string)
# Get from: Supabase dashboard → Project Settings → Database → URI
# export DATABASE_URL="postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres"
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set. See start_api.sh for instructions."
    exit 1
fi
```

**Step 4: Commit**

```bash
git add api/requirements.txt start_api.sh
git commit -m "feat: add psycopg2-binary dependency and DATABASE_URL guard"
```

---

### Task 2: Create schema in Supabase

**Files:** None (done in Supabase SQL Editor)

**Step 1: Open Supabase SQL Editor**

Go to: Supabase dashboard → your project → SQL Editor → New query

**Step 2: Run this SQL**

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    username TEXT,
    created_at TEXT,
    role TEXT DEFAULT 'user',
    avatar_url TEXT
);

CREATE TABLE IF NOT EXISTS picks (
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

CREATE TABLE IF NOT EXISTS game_predictions (
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
    model_version TEXT DEFAULT 'v1.0',
    graded_at TEXT,
    extended_data TEXT
);
```

**Step 3: Verify**

In Supabase → Table Editor, confirm all three tables appear with correct columns.

---

### Task 3: Rewrite imports, get_connection(), and init_db()

**Files:**
- Modify: `db.py:1-124`

**Step 1: Replace the import block and constants (lines 1–16)**

Replace:
```python
"""
SQLite database helper for tracking picks history and performance metrics.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import time
import pandas as pd

DB_PATH = Path(__file__).parent / "picks_history.db"

# Cache for team schedule lookups (date_str -> set of team abbreviations that played)
_team_schedule_cache = {}
EXCEL_PATH = Path(__file__).parent / "nba_picks_tracker.xlsx"
```

With:
```python
"""
Postgres (Supabase) database helper for tracking picks history and performance metrics.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import time
import pandas as pd

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")

# Cache for team schedule lookups (date_str -> set of team abbreviations that played)
_team_schedule_cache = {}
EXCEL_PATH = Path(__file__).parent / "nba_picks_tracker.xlsx"
```

**Step 2: Replace get_connection() (lines 19–23)**

Replace:
```python
def get_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
```

With:
```python
def get_connection():
    """Get database connection with dict cursor factory."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn
```

**Step 3: Replace init_db() (lines 26–124)**

Replace the entire `init_db()` function body (everything from `def init_db():` through the final `conn.close()`) with:
```python
def init_db():
    """Schema is managed via Supabase SQL Editor. This is a no-op kept for compatibility."""
    pass
```

**Step 4: Verify import works**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
DATABASE_URL="<your-supabase-url>" python -c "import db; print('OK')"
```

Expected: prints `OK` with no errors.

**Step 5: Commit**

```bash
git add db.py
git commit -m "feat: replace sqlite3 with psycopg2 connection layer"
```

---

### Task 4: Fix user functions

**Files:**
- Modify: `db.py` — user functions section (~lines 127–202)

All changes: replace `?` with `%s`, and fix `conn.execute()` → cursor pattern in `update_user_password`.

**Step 1: Fix create_user (around line 134)**

Replace:
```python
    cursor.execute(
        "INSERT INTO users (id, email, hashed_password, username, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, email, hashed_password, username, now)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

With:
```python
    cursor.execute(
        "INSERT INTO users (id, email, hashed_password, username, created_at) VALUES (%s, %s, %s, %s, %s)",
        (user_id, email, hashed_password, username, now)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

**Step 2: Fix get_user_by_email (around line 149)**

Replace:
```python
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
```
With:
```python
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
```

**Step 3: Fix get_user_by_id (around line 158)**

Replace:
```python
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```
With:
```python
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

**Step 4: Fix update_user_avatar (around lines 169–176)**

Replace:
```python
    cursor.execute(
        "UPDATE users SET avatar_url = ? WHERE id = ?",
        (avatar_url, user_id)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```
With:
```python
    cursor.execute(
        "UPDATE users SET avatar_url = %s WHERE id = %s",
        (avatar_url, user_id)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

**Step 5: Fix update_user_password (around lines 181–187) — conn.execute() pattern**

Replace the entire function body:
```python
def update_user_password(user_id: str, hashed_password: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE users SET hashed_password = ? WHERE id = ?",
        (hashed_password, user_id),
    )
    conn.commit()
    conn.close()
```
With:
```python
def update_user_password(user_id: str, hashed_password: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET hashed_password = %s WHERE id = %s",
        (hashed_password, user_id),
    )
    conn.commit()
    conn.close()
```

**Step 6: Fix clear_user_avatar (around lines 194–201)**

Replace:
```python
    cursor.execute(
        "UPDATE users SET avatar_url = NULL WHERE id = ?",
        (user_id,)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```
With:
```python
    cursor.execute(
        "UPDATE users SET avatar_url = NULL WHERE id = %s",
        (user_id,)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

**Step 7: Run auth tests**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
DATABASE_URL="<your-supabase-url>" python -m pytest tests/test_auth.py -v
```

Expected: all 9 tests pass.

**Step 8: Commit**

```bash
git add db.py
git commit -m "feat: migrate user functions to psycopg2 (%s placeholders, cursor fix)"
```

---

### Task 5: Fix game prediction functions

**Files:**
- Modify: `db.py` — game prediction functions (~lines 205–560)

Changes: `?` → `%s`, `cursor.lastrowid` → `RETURNING id`, `fetchone()[0]` → `fetchone()['count']`

**Step 1: Fix save_game_prediction INSERT + lastrowid (lines ~219–246)**

Replace the INSERT statement and `pred_id` line:
```python
    cursor.execute("""
        INSERT INTO game_predictions (
            timestamp, game_date, home_team, away_team,
            home_team_id, away_team_id, predicted_winner,
            home_win_prob, away_win_prob, confidence,
            key_factors, model_version, extended_data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
```
With:
```python
    cursor.execute("""
        INSERT INTO game_predictions (
            timestamp, game_date, home_team, away_team,
            home_team_id, away_team_id, predicted_winner,
            home_win_prob, away_win_prob, confidence,
            key_factors, model_version, extended_data
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
```

Then replace:
```python
    pred_id = cursor.lastrowid
```
With:
```python
    pred_id = cursor.fetchone()['id']
```

**Step 2: Fix get_todays_stored_predictions WHERE clause (line ~260)**

Replace:
```python
    cursor.execute("""
        SELECT * FROM game_predictions
        WHERE game_date = ?
        ORDER BY timestamp DESC
    """, (today,))
```
With:
```python
    cursor.execute("""
        SELECT * FROM game_predictions
        WHERE game_date = %s
        ORDER BY timestamp DESC
    """, (today,))
```

**Step 3: Fix get_game_predictions cutoff (line ~337)**

Replace:
```python
    cursor.execute("""
        SELECT * FROM game_predictions
        WHERE timestamp >= ?
        ORDER BY timestamp DESC
    """, (cutoff,))
```
With:
```python
    cursor.execute("""
        SELECT * FROM game_predictions
        WHERE timestamp >= %s
        ORDER BY timestamp DESC
    """, (cutoff,))
```

**Step 4: Fix grade_game_prediction (lines ~393–407)**

Replace:
```python
    cursor.execute("SELECT predicted_winner FROM game_predictions WHERE id = ?", (prediction_id,))
```
With:
```python
    cursor.execute("SELECT predicted_winner FROM game_predictions WHERE id = %s", (prediction_id,))
```

Replace:
```python
    cursor.execute("""
        UPDATE game_predictions
        SET actual_winner = ?, correct = ?, graded_at = ?
        WHERE id = ?
    """, (actual_winner, correct, datetime.now().isoformat(), prediction_id))
```
With:
```python
    cursor.execute("""
        UPDATE game_predictions
        SET actual_winner = %s, correct = %s, graded_at = %s
        WHERE id = %s
    """, (actual_winner, correct, datetime.now().isoformat(), prediction_id))
```

**Step 5: Fix get_game_accuracy_stats COUNT (line ~512)**

Replace:
```python
    cursor.execute("SELECT COUNT(*) FROM game_predictions")
    total = cursor.fetchone()[0]
```
With:
```python
    cursor.execute("SELECT COUNT(*) FROM game_predictions")
    total = cursor.fetchone()['count']
```

**Step 6: Commit**

```bash
git add db.py
git commit -m "feat: migrate game prediction functions to psycopg2"
```

---

### Task 6: Fix picks CRUD functions

**Files:**
- Modify: `db.py` — picks functions (~lines 563–1097)

**Step 1: Fix save_pick INSERT + lastrowid (lines ~578–606)**

Replace the VALUES line:
```python
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
```
With:
```python
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
```

Replace:
```python
    pick_id = cursor.lastrowid
```
With:
```python
    pick_id = cursor.fetchone()['id']
```

**Step 2: Fix get_picks_history (lines ~626–636)**

Replace both `?` in queries:
```python
        cursor.execute("""
            SELECT * FROM picks
            WHERE timestamp >= ? AND (voided IS NULL OR voided = 0) AND user_id = ?
            ORDER BY timestamp DESC
        """, (cutoff, user_id))
```
With:
```python
        cursor.execute("""
            SELECT * FROM picks
            WHERE timestamp >= %s AND (voided IS NULL OR voided = 0) AND user_id = %s
            ORDER BY timestamp DESC
        """, (cutoff, user_id))
```

And:
```python
        cursor.execute("""
            SELECT * FROM picks
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (cutoff,))
```
With:
```python
        cursor.execute("""
            SELECT * FROM picks
            WHERE timestamp >= %s
            ORDER BY timestamp DESC
        """, (cutoff,))
```

**Step 3: Fix update_pick_result (lines ~680–686)**

Replace:
```python
    cursor.execute("""
        UPDATE picks
        SET actual_result = ?, won = ?
        WHERE id = ?
    """, (actual_result, won, pick_id))
```
With:
```python
    cursor.execute("""
        UPDATE picks
        SET actual_result = %s, won = %s
        WHERE id = %s
    """, (actual_result, won, pick_id))
```

**Step 4: Fix delete_pick (line ~695)**

Replace:
```python
    cursor.execute("DELETE FROM picks WHERE id = ?", (pick_id,))
```
With:
```python
    cursor.execute("DELETE FROM picks WHERE id = %s", (pick_id,))
```

**Step 5: Fix void_pick (lines ~712–716)**

Replace:
```python
    cursor.execute("""
        UPDATE picks
        SET voided = 1, void_reason = ?, won = NULL, actual_result = NULL
        WHERE id = ?
    """, (reason, pick_id))
```
With:
```python
    cursor.execute("""
        UPDATE picks
        SET voided = 1, void_reason = %s, won = NULL, actual_result = NULL
        WHERE id = %s
    """, (reason, pick_id))
```

**Step 6: Fix unvoid_pick (lines ~744–748)**

Replace:
```python
    cursor.execute("""
        UPDATE picks
        SET voided = 0, void_reason = NULL
        WHERE id = ?
    """, (pick_id,))
```
With:
```python
    cursor.execute("""
        UPDATE picks
        SET voided = 0, void_reason = NULL
        WHERE id = %s
    """, (pick_id,))
```

**Step 7: Fix reset_pick_to_pending (lines ~759–763)**

Replace:
```python
    cursor.execute("""
        UPDATE picks
        SET won = NULL, actual_result = NULL, graded_at = NULL
        WHERE id = ?
    """, (pick_id,))
```
With:
```python
    cursor.execute("""
        UPDATE picks
        SET won = NULL, actual_result = NULL, graded_at = NULL
        WHERE id = %s
    """, (pick_id,))
```

**Step 8: Fix reset_all_graded_for_date COUNT + queries (lines ~784–795)**

Replace the COUNT fetchone:
```python
    cursor.execute("""
        SELECT COUNT(*) FROM picks
        WHERE game_date LIKE ? AND won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """, (f"{game_date}%",))
    count = cursor.fetchone()[0]
```
With:
```python
    cursor.execute("""
        SELECT COUNT(*) FROM picks
        WHERE game_date LIKE %s AND won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """, (f"{game_date}%",))
    count = cursor.fetchone()['count']
```

Replace the UPDATE:
```python
    cursor.execute("""
        UPDATE picks
        SET won = NULL, actual_result = NULL, graded_at = NULL
        WHERE game_date LIKE ? AND won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """, (f"{game_date}%",))
```
With:
```python
    cursor.execute("""
        UPDATE picks
        SET won = NULL, actual_result = NULL, graded_at = NULL
        WHERE game_date LIKE %s AND won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """, (f"{game_date}%",))
```

**Step 9: Fix remaining picks query functions (get_pending_picks, get_picks_for_date, get_stale_pending_picks, auto_void_stale_picks)**

These follow the same `?` → `%s` pattern. For each function, replace all `?` with `%s`.

In `get_pending_picks` (~line 959, 967):
- `AND user_id = ?` → `AND user_id = %s`

In `get_picks_for_date` (~line 984):
- `WHERE game_date = ?` → `WHERE game_date = %s`

In `auto_void_stale_picks` (~line 1059):
- `AND game_date < ?` → `AND game_date < %s`

In `get_stale_pending_picks` (~line 1088):
- `AND game_date < ?` → `AND game_date < %s`

**Step 10: Fix graded_at UPDATE inside auto_grade_picks (lines ~1269–1271)**

Replace:
```python
            cursor.execute("UPDATE picks SET graded_at = ? WHERE id = ?",
                          (datetime.now().isoformat(), pick['id']))
```
With:
```python
            cursor.execute("UPDATE picks SET graded_at = %s WHERE id = %s",
                          (datetime.now().isoformat(), pick['id']))
```

**Step 11: Commit**

```bash
git add db.py
git commit -m "feat: migrate picks CRUD functions to psycopg2"
```

---

### Task 7: Fix performance stats functions

**Files:**
- Modify: `db.py` — stats functions (~lines 801–1416)

**Step 1: Fix get_performance_stats COUNT (lines ~813–828)**

The two COUNT queries and their fetchone calls:

Replace:
```python
        cursor.execute("""
            SELECT * FROM picks WHERE won IS NOT NULL AND (voided IS NULL OR voided = 0) AND user_id = ?
        """, (user_id,))
```
With:
```python
        cursor.execute("""
            SELECT * FROM picks WHERE won IS NOT NULL AND (voided IS NULL OR voided = 0) AND user_id = %s
        """, (user_id,))
```

Replace:
```python
        cursor.execute("SELECT COUNT(*) FROM picks WHERE (voided IS NULL OR voided = 0) AND user_id = ?", (user_id,))
```
With:
```python
        cursor.execute("SELECT COUNT(*) FROM picks WHERE (voided IS NULL OR voided = 0) AND user_id = %s", (user_id,))
```

Replace both `cursor.fetchone()[0]` after COUNT queries:
```python
    total_picks = cursor.fetchone()[0]
```
With:
```python
    total_picks = cursor.fetchone()['count']
```

**Step 2: Fix get_cumulative_profit (lines ~916–927)**

Replace:
```python
        cursor.execute("""
            SELECT timestamp, won FROM picks
            WHERE won IS NOT NULL AND user_id = ?
            ORDER BY timestamp ASC
        """, (user_id,))
```
With:
```python
        cursor.execute("""
            SELECT timestamp, won FROM picks
            WHERE won IS NOT NULL AND user_id = %s
            ORDER BY timestamp ASC
        """, (user_id,))
```

**Step 3: Commit**

```bash
git add db.py
git commit -m "feat: migrate performance stats functions to psycopg2"
```

---

### Task 8: Write migration script

**Files:**
- Create: `scripts/migrate_to_supabase.py`

**Step 1: Create the scripts directory**

```bash
mkdir -p /Users/hhabal/Downloads/Projects/NBA/EVAL/scripts
```

**Step 2: Create the migration script**

Create `scripts/migrate_to_supabase.py` with this content:

```python
"""
One-time migration script: SQLite → Supabase Postgres.

Usage:
    DATABASE_URL="postgresql://..." python scripts/migrate_to_supabase.py

Get DATABASE_URL from: Supabase dashboard → Project Settings → Database → URI
"""
import sqlite3
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

SQLITE_PATH = Path(__file__).parent.parent / "picks_history.db"
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def migrate_users(sqlite_conn, pg_conn):
    src = sqlite_conn.cursor()
    src.execute("SELECT * FROM users")
    rows = [dict(r) for r in src.fetchall()]
    if not rows:
        print("  users: 0 rows (skipping)")
        return 0

    dst = pg_conn.cursor()
    inserted = 0
    for row in rows:
        dst.execute("""
            INSERT INTO users (id, email, hashed_password, username, created_at, role, avatar_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
            row.get('id'),
            row.get('email'),
            row.get('hashed_password'),
            row.get('username'),
            row.get('created_at'),
            row.get('role', 'user'),
            row.get('avatar_url'),
        ))
        if dst.rowcount:
            inserted += 1

    pg_conn.commit()
    print(f"  users: {inserted}/{len(rows)} rows migrated")
    return inserted


def migrate_picks(sqlite_conn, pg_conn):
    src = sqlite_conn.cursor()
    src.execute("SELECT * FROM picks ORDER BY id ASC")
    rows = [dict(r) for r in src.fetchall()]
    if not rows:
        print("  picks: 0 rows (skipping)")
        return 0

    dst = pg_conn.cursor()
    inserted = 0
    for row in rows:
        dst.execute("""
            INSERT INTO picks (
                id, timestamp, player, player_id, team_abbrev, stat, line, prediction,
                direction, edge, confidence, opponent, is_home, actual_result, won,
                model_type, game_date, graded_at, voided, void_reason, prob_over, user_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            row.get('id'),
            row.get('timestamp'),
            row.get('player'),
            row.get('player_id'),
            row.get('team_abbrev'),
            row.get('stat'),
            row.get('line'),
            row.get('prediction'),
            row.get('direction'),
            row.get('edge'),
            row.get('confidence'),
            row.get('opponent'),
            row.get('is_home', 0),
            row.get('actual_result'),
            row.get('won'),
            row.get('model_type'),
            row.get('game_date'),
            row.get('graded_at'),
            row.get('voided', 0),
            row.get('void_reason'),
            row.get('prob_over'),
            row.get('user_id'),
        ))
        if dst.rowcount:
            inserted += 1

    # Reset sequence so new inserts don't collide with migrated IDs
    max_id = max(r['id'] for r in rows)
    dst.execute(f"SELECT setval('picks_id_seq', {max_id})")
    pg_conn.commit()
    print(f"  picks: {inserted}/{len(rows)} rows migrated (sequence reset to {max_id})")
    return inserted


def migrate_game_predictions(sqlite_conn, pg_conn):
    src = sqlite_conn.cursor()
    # Check if table exists in SQLite
    src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='game_predictions'")
    if not src.fetchone():
        print("  game_predictions: table not found in SQLite (skipping)")
        return 0

    src.execute("SELECT * FROM game_predictions ORDER BY id ASC")
    rows = [dict(r) for r in src.fetchall()]
    if not rows:
        print("  game_predictions: 0 rows (skipping)")
        return 0

    dst = pg_conn.cursor()
    inserted = 0
    for row in rows:
        dst.execute("""
            INSERT INTO game_predictions (
                id, timestamp, game_date, home_team, away_team,
                home_team_id, away_team_id, predicted_winner,
                home_win_prob, away_win_prob, confidence,
                actual_winner, correct, key_factors, model_version,
                graded_at, extended_data
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            row.get('id'),
            row.get('timestamp'),
            row.get('game_date'),
            row.get('home_team'),
            row.get('away_team'),
            row.get('home_team_id'),
            row.get('away_team_id'),
            row.get('predicted_winner'),
            row.get('home_win_prob'),
            row.get('away_win_prob'),
            row.get('confidence'),
            row.get('actual_winner'),
            row.get('correct'),
            row.get('key_factors'),
            row.get('model_version', 'v1.0'),
            row.get('graded_at'),
            row.get('extended_data'),
        ))
        if dst.rowcount:
            inserted += 1

    if rows:
        max_id = max(r['id'] for r in rows)
        dst.execute(f"SELECT setval('game_predictions_id_seq', {max_id})")

    pg_conn.commit()
    print(f"  game_predictions: {inserted}/{len(rows)} rows migrated")
    return inserted


def main():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL env var is not set.")
        print("  export DATABASE_URL='postgresql://postgres.[ref]:[password]@...:5432/postgres'")
        sys.exit(1)

    if not SQLITE_PATH.exists():
        print(f"ERROR: SQLite file not found at {SQLITE_PATH}")
        sys.exit(1)

    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {DATABASE_URL[:40]}...")
    print()

    sqlite_conn = get_sqlite()
    pg_conn = get_postgres()

    try:
        print("Migrating...")
        migrate_users(sqlite_conn, pg_conn)
        migrate_picks(sqlite_conn, pg_conn)
        migrate_game_predictions(sqlite_conn, pg_conn)
        print()
        print("Migration complete.")
    except Exception as e:
        pg_conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
```

**Step 3: Commit**

```bash
git add scripts/migrate_to_supabase.py
git commit -m "feat: add SQLite→Supabase migration script"
```

---

### Task 9: Run migration and verify

**Step 1: Get your DATABASE_URL**

Supabase dashboard → Project Settings → Database → scroll to "Connection string" → copy the URI (starts with `postgresql://`).

**Step 2: Export env var and run migration**

```bash
export DATABASE_URL="postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres"
python scripts/migrate_to_supabase.py
```

Expected output:
```
Source: /path/to/picks_history.db
Target: postgresql://postgres.[ref]:...

Migrating...
  users: N/N rows migrated
  picks: N/N rows migrated (sequence reset to N)
  game_predictions: N/N rows migrated

Migration complete.
```

**Step 3: Verify data in Supabase dashboard**

Go to Supabase → Table Editor → picks. Confirm rows match what you had locally.

**Step 4: Run auth tests against Supabase**

```bash
DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_auth.py -v
```

Expected: all 9 tests pass.

**Step 5: Start the API and smoke test**

```bash
DATABASE_URL="$DATABASE_URL" ./start_api.sh
```

Open http://localhost:8000/api/picks — should return picks from Supabase.
Open http://localhost:8000/api/picks/stats/performance — should return correct stats.

**Step 6: Commit**

```bash
git add .
git commit -m "feat: complete Supabase migration — psycopg2 replacing sqlite3 in db.py"
```

---

## Post-Migration Checklist

- [ ] All 9 auth tests pass
- [ ] `GET /api/picks` returns rows from Supabase (not empty)
- [ ] `GET /api/picks/stats/performance` returns correct win rate / ROI
- [ ] `POST /api/picks` creates a new row (check Supabase table editor)
- [ ] `PUT /api/picks/{id}/grade` updates a row (check Supabase table editor)
- [ ] `GET /api/games/today` works if you have game predictions
- [ ] `DATABASE_URL` is documented in `.env.example` or README
