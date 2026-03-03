# Supabase Game Log Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Store frozen historical seasons (2023-24, 2024-25) in Supabase so `get_player_game_log()` only makes one NBA API call (current season) instead of three.

**Architecture:** A new `player_game_logs` table in Supabase holds complete historical game logs. `get_player_game_log()` checks Supabase first for historical seasons and falls back to the NBA API only on a miss, writing the result to Supabase permanently. The current season (2025-26) keeps its existing local file cache behavior unchanged.

**Tech Stack:** Python, psycopg2 (already in use), Supabase Postgres, nba_api `PlayerGameLog`, pandas

---

### Task 1: Create Supabase Schema

**Files:**
- No code files — run SQL directly in Supabase SQL Editor

**Step 1: Run this SQL in the Supabase SQL Editor**

```sql
CREATE TABLE IF NOT EXISTS player_game_logs (
    player_id       TEXT    NOT NULL,
    season          TEXT    NOT NULL,
    season_id       TEXT,
    game_id         TEXT    NOT NULL,
    game_date       DATE    NOT NULL,
    matchup         TEXT,
    wl              TEXT,
    min             REAL,
    fgm             REAL,
    fga             REAL,
    fg_pct          REAL,
    fg3m            REAL,
    fg3a            REAL,
    fg3_pct         REAL,
    ftm             REAL,
    fta             REAL,
    ft_pct          REAL,
    oreb            REAL,
    dreb            REAL,
    reb             REAL,
    ast             REAL,
    stl             REAL,
    blk             REAL,
    tov             REAL,
    pf              REAL,
    pts             REAL,
    plus_minus      REAL,
    video_available INTEGER,
    PRIMARY KEY (player_id, game_id)
);

CREATE INDEX IF NOT EXISTS idx_player_game_logs_lookup
    ON player_game_logs (player_id, season);
```

**Step 2: Verify in Supabase Table Editor**

Confirm the table `player_game_logs` appears with the correct columns.

**Step 3: Commit**

```bash
git add docs/plans/2026-03-02-supabase-game-log-cache.md
git commit -m "docs: add supabase game log cache implementation plan"
```

---

### Task 2: Add `db.py` helpers — TDD

**Files:**
- Modify: `db.py`
- Create: `tests/test_game_log_cache.py`

**Step 1: Write the failing tests**

Create `tests/test_game_log_cache.py`:

```python
"""Tests for Supabase game log cache helpers in db.py."""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Provide a fake DATABASE_URL so importing db doesn't crash
os.environ.setdefault("DATABASE_URL", "postgresql://fake/test")

import db


SAMPLE_ROWS = [
    {
        "player_id": "203999", "season": "2024-25", "season_id": "22024",
        "game_id": "0022401001", "game_date": "2025-01-15",
        "matchup": "DEN vs. OKC", "wl": "W",
        "min": 35.0, "fgm": 10.0, "fga": 18.0, "fg_pct": 0.556,
        "fg3m": 3.0, "fg3a": 7.0, "fg3_pct": 0.429,
        "ftm": 4.0, "fta": 5.0, "ft_pct": 0.800,
        "oreb": 1.0, "dreb": 7.0, "reb": 8.0, "ast": 9.0,
        "stl": 2.0, "blk": 1.0, "tov": 3.0, "pf": 2.0,
        "pts": 27.0, "plus_minus": 12.0, "video_available": 1,
    }
]


def make_mock_conn(rows):
    """Build a mock psycopg2 connection that returns `rows` from fetchall."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn, mock_cursor


# ── get_game_logs_from_supabase ───────────────────────────────

class TestGetGameLogsFromSupabase:
    def test_returns_dataframe_when_rows_exist(self):
        mock_conn, mock_cursor = make_mock_conn(SAMPLE_ROWS)
        with patch("db.get_connection", return_value=mock_conn):
            result = db.get_game_logs_from_supabase("203999", "2024-25")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_returns_none_when_no_rows(self):
        mock_conn, mock_cursor = make_mock_conn([])
        with patch("db.get_connection", return_value=mock_conn):
            result = db.get_game_logs_from_supabase("203999", "2024-25")
        assert result is None

    def test_column_names_match_nba_api_format(self):
        """Returned DataFrame must use uppercase column names matching NBA API."""
        mock_conn, mock_cursor = make_mock_conn(SAMPLE_ROWS)
        with patch("db.get_connection", return_value=mock_conn):
            result = db.get_game_logs_from_supabase("203999", "2024-25")
        assert "GAME_DATE" in result.columns
        assert "PTS" in result.columns
        assert "MATCHUP" in result.columns
        assert "Game_ID" in result.columns
        assert "Player_ID" in result.columns
        assert "SEASON" in result.columns

    def test_queries_correct_player_and_season(self):
        mock_conn, mock_cursor = make_mock_conn(SAMPLE_ROWS)
        with patch("db.get_connection", return_value=mock_conn):
            db.get_game_logs_from_supabase("203999", "2024-25")
        call_args = mock_cursor.execute.call_args
        sql, params = call_args[0]
        assert "player_id" in sql.lower()
        assert "season" in sql.lower()
        assert ("203999", "2024-25") == params


# ── insert_game_logs_to_supabase ─────────────────────────────

class TestInsertGameLogsToSupabase:
    def _make_sample_df(self):
        return pd.DataFrame([{
            "SEASON_ID": "22024", "Player_ID": "203999", "Game_ID": "0022401001",
            "GAME_DATE": "JAN 15, 2025", "MATCHUP": "DEN vs. OKC", "WL": "W",
            "MIN": "35:00", "FGM": 10, "FGA": 18, "FG_PCT": 0.556,
            "FG3M": 3, "FG3A": 7, "FG3_PCT": 0.429,
            "FTM": 4, "FTA": 5, "FT_PCT": 0.8,
            "OREB": 1, "DREB": 7, "REB": 8, "AST": 9,
            "STL": 2, "BLK": 1, "TOV": 3, "PF": 2,
            "PTS": 27, "PLUS_MINUS": 12, "VIDEO_AVAILABLE": 1,
            "SEASON": "2024-25",
        }])

    def test_executes_insert(self):
        mock_conn, mock_cursor = make_mock_conn([])
        df = self._make_sample_df()
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(df, "203999", "2024-25")
        assert mock_cursor.execute.called

    def test_uses_on_conflict_do_nothing(self):
        mock_conn, mock_cursor = make_mock_conn([])
        df = self._make_sample_df()
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(df, "203999", "2024-25")
        call_sql = mock_cursor.execute.call_args[0][0]
        assert "ON CONFLICT" in call_sql.upper()
        assert "DO NOTHING" in call_sql.upper()

    def test_commits(self):
        mock_conn, _ = make_mock_conn([])
        df = self._make_sample_df()
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(df, "203999", "2024-25")
        mock_conn.commit.assert_called_once()

    def test_empty_df_is_noop(self):
        mock_conn, mock_cursor = make_mock_conn([])
        with patch("db.get_connection", return_value=mock_conn):
            db.insert_game_logs_to_supabase(pd.DataFrame(), "203999", "2024-25")
        mock_cursor.execute.assert_not_called()
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -m pytest tests/test_game_log_cache.py -v
```

Expected: `AttributeError: module 'db' has no attribute 'get_game_logs_from_supabase'`

**Step 3: Implement the helpers in `db.py`**

Add after the existing `get_connection()` function (around line 25), before the User functions block:

```python
# ── Game log cache (Supabase) ─────────────────────────────────

# NBA API returns these mixed/upper-case column names; DB stores lowercase.
# On read we rename back so the rest of the codebase is unchanged.
_DB_TO_NBA_COLS = {
    "season_id": "SEASON_ID",
    "player_id": "Player_ID",
    "game_id": "Game_ID",
    "game_date": "GAME_DATE",
    "matchup": "MATCHUP",
    "wl": "WL",
    "min": "MIN",
    "fgm": "FGM", "fga": "FGA", "fg_pct": "FG_PCT",
    "fg3m": "FG3M", "fg3a": "FG3A", "fg3_pct": "FG3_PCT",
    "ftm": "FTM", "fta": "FTA", "ft_pct": "FT_PCT",
    "oreb": "OREB", "dreb": "DREB", "reb": "REB",
    "ast": "AST", "stl": "STL", "blk": "BLK",
    "tov": "TOV", "pf": "PF", "pts": "PTS",
    "plus_minus": "PLUS_MINUS", "video_available": "VIDEO_AVAILABLE",
    "season": "SEASON",
}


def get_game_logs_from_supabase(player_id: str, season: str):
    """
    Return a DataFrame of game logs for (player_id, season) from Supabase,
    or None if no rows exist. Column names match NBA API format.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM player_game_logs WHERE player_id = %s AND season = %s",
            (player_id, season),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return None

    df = pd.DataFrame([dict(r) for r in rows])
    df = df.rename(columns=_DB_TO_NBA_COLS)
    return df


def insert_game_logs_to_supabase(df: pd.DataFrame, player_id: str, season: str) -> None:
    """
    Bulk-insert game log rows into Supabase. Safe to re-run — uses ON CONFLICT DO NOTHING.
    df must be a raw NBA API PlayerGameLog DataFrame (uppercase column names).
    """
    if df.empty:
        return

    _NBA_TO_DB_COLS = {v: k for k, v in _DB_TO_NBA_COLS.items()}
    db_df = df.rename(columns=_NBA_TO_DB_COLS).copy()

    # Ensure player_id and season are set from function params (source of truth)
    db_df["player_id"] = player_id
    db_df["season"] = season

    # Parse MIN: NBA API returns "35:22" strings; store as float minutes
    if "min" in db_df.columns:
        def _parse_min(val):
            try:
                parts = str(val).split(":")
                return float(parts[0]) + float(parts[1]) / 60 if len(parts) == 2 else float(parts[0])
            except Exception:
                return None
        db_df["min"] = db_df["min"].apply(_parse_min)

    # Parse game_date to a plain date string for Postgres DATE column
    if "game_date" in db_df.columns:
        db_df["game_date"] = pd.to_datetime(db_df["game_date"], format="mixed").dt.strftime("%Y-%m-%d")

    cols = list(_DB_TO_NBA_COLS.keys())  # canonical DB column order
    cols_present = [c for c in cols if c in db_df.columns]

    insert_sql = (
        f"INSERT INTO player_game_logs ({', '.join(cols_present)}) "
        f"VALUES ({', '.join(['%s'] * len(cols_present))}) "
        f"ON CONFLICT (player_id, game_id) DO NOTHING"
    )

    rows = [tuple(row[c] for c in cols_present) for _, row in db_df.iterrows()]

    conn = get_connection()
    with conn.cursor() as cur:
        cur.executemany(insert_sql, rows)
    conn.commit()
    conn.close()
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_game_log_cache.py -v
```

Expected: all 8 tests PASS.

**Step 5: Commit**

```bash
git add db.py tests/test_game_log_cache.py
git commit -m "feat: add Supabase game log cache helpers to db.py"
```

---

### Task 3: Modify `get_player_game_log()` — TDD

**Files:**
- Modify: `nba_evaluator.py:324-350`
- Modify: `tests/test_game_log_cache.py` (append new test class)

**Step 1: Add `CURRENT_SEASON` constant to `nba_evaluator.py`**

Find the `CACHE_EXPIRY` block (~line 97) and add directly above it:

```python
CURRENT_SEASON = '2025-26'
HISTORICAL_SEASONS = ['2024-25', '2023-24']
```

**Step 2: Write failing integration tests**

Append to `tests/test_game_log_cache.py`:

```python
# ── get_player_game_log integration ──────────────────────────

import importlib
import nba_evaluator as nba_eval
from nba_evaluator import NBADataScraper


class TestGetPlayerGameLogWithCache:
    """Tests that get_player_game_log() uses Supabase for historical seasons."""

    def _make_fake_api_df(self, season):
        return pd.DataFrame([{
            "SEASON_ID": "22024", "Player_ID": "203999", "Game_ID": f"002240{season[-2:]}01",
            "GAME_DATE": "JAN 15, 2025", "MATCHUP": "DEN vs. OKC", "WL": "W",
            "MIN": "35:00", "FGM": 10, "FGA": 18, "FG_PCT": 0.556,
            "FG3M": 3, "FG3A": 7, "FG3_PCT": 0.429,
            "FTM": 4, "FTA": 5, "FT_PCT": 0.8,
            "OREB": 1, "DREB": 7, "REB": 8, "AST": 9,
            "STL": 2, "BLK": 1, "TOV": 3, "PF": 2,
            "PTS": 27, "PLUS_MINUS": 12, "VIDEO_AVAILABLE": 1,
            "SEASON": season,
        }])

    def test_historical_season_hits_supabase_not_api(self):
        """When Supabase has the data, NBA API must NOT be called for historical seasons."""
        fake_df = self._make_fake_api_df("2024-25")
        fake_df_renamed = fake_df.rename(columns={v: k for k, v in db._DB_TO_NBA_COLS.items()})

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase", return_value=fake_df) as mock_get, \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog") as mock_api:
            result = scraper.get_player_game_log("203999", seasons=["2024-25"])

        mock_get.assert_called_once_with("203999", "2024-25")
        mock_api.assert_not_called()
        assert len(result) == 1

    def test_historical_season_miss_calls_api_then_stores(self):
        """On Supabase miss, NBA API is called and result is written to Supabase."""
        fake_df = self._make_fake_api_df("2024-25")
        mock_log = MagicMock()
        mock_log.get_data_frames.return_value = [fake_df]

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase", return_value=None), \
             patch("db.insert_game_logs_to_supabase") as mock_insert, \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog", return_value=mock_log), \
             patch("time.sleep"):
            result = scraper.get_player_game_log("203999", seasons=["2024-25"])

        mock_insert.assert_called_once()
        assert len(result) == 1

    def test_current_season_skips_supabase(self):
        """Current season (2025-26) must always hit the NBA API, never Supabase."""
        fake_df = self._make_fake_api_df("2025-26")
        mock_log = MagicMock()
        mock_log.get_data_frames.return_value = [fake_df]

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase") as mock_get, \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog", return_value=mock_log), \
             patch("time.sleep"), \
             patch("nba_evaluator.CacheManager.get", return_value=None), \
             patch("nba_evaluator.CacheManager.set"):
            result = scraper.get_player_game_log("203999", seasons=["2025-26"])

        mock_get.assert_not_called()

    def test_three_seasons_returns_combined_df(self):
        """Full three-season call returns all games sorted ascending by date."""
        fake_historical_df = pd.concat([
            self._make_fake_api_df("2024-25"),
            self._make_fake_api_df("2023-24"),
        ])
        fake_current_df = self._make_fake_api_df("2025-26")
        mock_log = MagicMock()
        mock_log.get_data_frames.return_value = [fake_current_df]

        scraper = NBADataScraper()
        with patch("db.get_game_logs_from_supabase", return_value=fake_historical_df), \
             patch("nba_api.stats.endpoints.playergamelog.PlayerGameLog", return_value=mock_log), \
             patch("time.sleep"), \
             patch("nba_evaluator.CacheManager.get", return_value=None), \
             patch("nba_evaluator.CacheManager.set"):
            result = scraper.get_player_game_log("203999")

        # Should have all 3 seasons' games
        assert len(result) >= 3
```

**Step 3: Run new tests to confirm they fail**

```bash
python -m pytest tests/test_game_log_cache.py::TestGetPlayerGameLogWithCache -v
```

Expected: FAIL (existing code makes 3 API calls, no Supabase check)

**Step 4: Modify `get_player_game_log()` in `nba_evaluator.py`**

Replace lines 324–350:

```python
def get_player_game_log(self, player_id, seasons=None):
    """Get player's game log for specified seasons.
    Historical seasons are fetched from Supabase (permanent cache).
    Current season uses local file cache + live NBA API.
    """
    from nba_evaluator import CURRENT_SEASON
    import db as _db

    if seasons is None:
        seasons = [CURRENT_SEASON, '2024-25', '2023-24']

    all_games = []

    for season in seasons:
        if season != CURRENT_SEASON:
            # Historical: check Supabase first
            cached_df = _db.get_game_logs_from_supabase(str(player_id), season)
            if cached_df is not None and not cached_df.empty:
                print(f"📦 Loaded {season} from Supabase ({len(cached_df)} games)")
                all_games.append(cached_df)
                continue

            # Miss: fetch from NBA API and store permanently
            print(f"📊 Fetching {season} game log (first time)...")
            try:
                log = playergamelog.PlayerGameLog(
                    player_id=player_id,
                    season=season
                )
                time.sleep(0.6)
                df = log.get_data_frames()[0]
                df['SEASON'] = season
                _db.insert_game_logs_to_supabase(df, str(player_id), season)
                print(f"  ✅ Stored {len(df)} rows to Supabase")
                all_games.append(df)
            except Exception as e:
                print(f"⚠️ Could not fetch {season}: {e}")

        else:
            # Current season: existing local cache + live API (unchanged behaviour)
            cached = CacheManager.get('game_log', player_id, season, expiry_type='game_log')
            if cached is not None:
                print(f"📦 Loaded {season} from local cache")
                all_games.append(cached)
                continue

            print(f"📊 Fetching {season} game log...")
            try:
                log = playergamelog.PlayerGameLog(
                    player_id=player_id,
                    season=season
                )
                time.sleep(0.6)
                df = log.get_data_frames()[0]
                df['SEASON'] = season
                CacheManager.set('game_log', df, player_id, season)
                all_games.append(df)
            except Exception as e:
                print(f"⚠️ Could not fetch {season}: {e}")

    if all_games:
        combined = pd.concat(all_games, ignore_index=True)
        combined['_sort_date'] = pd.to_datetime(combined['GAME_DATE'], format='mixed')
        combined = combined.sort_values('_sort_date', ascending=True).drop(columns=['_sort_date']).reset_index(drop=True)
        return combined
    return pd.DataFrame()
```

**Step 5: Run all game log tests**

```bash
python -m pytest tests/test_game_log_cache.py -v
```

Expected: all tests PASS.

**Step 6: Smoke test against real Supabase (manual)**

```bash
DATABASE_URL="..." python -c "
from nba_evaluator import NBADataScraper
s = NBADataScraper()
# Nikola Jokic player_id = 203999
df = s.get_player_game_log('203999', seasons=['2024-25'])
print(df.shape, df.columns.tolist()[:5])
"
```

Expected: prints shape like `(82, 28)` and no errors.

**Step 7: Commit**

```bash
git add nba_evaluator.py tests/test_game_log_cache.py
git commit -m "feat: use Supabase cache for historical seasons in get_player_game_log"
```

---

### Task 4: Backfill Script

**Files:**
- Create: `scripts/backfill_game_logs.py`

**Step 1: Write the script**

Create `scripts/backfill_game_logs.py`:

```python
"""
One-time backfill: fetch historical game logs for all trained players and store in Supabase.

Usage:
    DATABASE_URL="postgresql://..." python scripts/backfill_game_logs.py [--dry-run]

Options:
    --dry-run   Print what would be fetched without writing to Supabase
    --season    Season to backfill (default: both historical seasons)

Safe to re-run: uses ON CONFLICT DO NOTHING, skips players already stored.
"""
import sys
import os
import time
import argparse
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from nba_evaluator import NBADataScraper, CURRENT_SEASON, HISTORICAL_SEASONS

MODEL_DIR = Path(__file__).parent.parent / "models"


def get_trained_player_names() -> list[str]:
    """Read player names from existing model .pkl filenames."""
    return [
        p.stem.replace("_model", "").replace("_", " ")
        for p in MODEL_DIR.glob("*_model.pkl")
        if p.parent == MODEL_DIR  # skip models/games/
    ]


def name_to_player_id(scraper: NBADataScraper, name: str) -> str | None:
    try:
        info = scraper.get_player_info(name)
        return str(info["id"]) if info else None
    except Exception:
        return None


def already_stored(player_id: str, season: str) -> bool:
    """Return True if Supabase already has rows for this player+season."""
    df = db.get_game_logs_from_supabase(player_id, season)
    return df is not None and not df.empty


def backfill(dry_run: bool = False, seasons: list[str] | None = None):
    if seasons is None:
        seasons = HISTORICAL_SEASONS

    scraper = NBADataScraper()
    player_names = get_trained_player_names()
    total = len(player_names) * len(seasons)

    print(f"Backfilling {len(player_names)} players × {len(seasons)} seasons = {total} checks")
    print(f"Seasons: {seasons}")
    if dry_run:
        print("DRY RUN — no writes\n")

    stored = skipped = failed = 0

    for name in sorted(player_names):
        player_id = name_to_player_id(scraper, name)
        if not player_id:
            print(f"  ⚠️  {name}: player not found")
            failed += 1
            continue

        for season in seasons:
            if already_stored(player_id, season):
                print(f"  ✓  {name} {season}: already in Supabase (skip)")
                skipped += 1
                continue

            print(f"  → {name} {season}: fetching...", end=" ", flush=True)
            if dry_run:
                print("(dry run)")
                continue

            try:
                from nba_api.stats.endpoints import playergamelog
                log = playergamelog.PlayerGameLog(player_id=player_id, season=season)
                time.sleep(0.6)
                import pandas as pd
                df = log.get_data_frames()[0]
                df['SEASON'] = season
                db.insert_game_logs_to_supabase(df, player_id, season)
                print(f"{len(df)} rows stored")
                stored += 1
            except Exception as e:
                print(f"ERROR: {e}")
                failed += 1

    print(f"\nDone. Stored: {stored} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--season", help="Single season to backfill (e.g. 2024-25)")
    args = parser.parse_args()

    seasons = [args.season] if args.season else None
    backfill(dry_run=args.dry_run, seasons=seasons)
```

**Step 2: Dry-run to verify player detection**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python scripts/backfill_game_logs.py --dry-run
```

Expected: prints list of all player names and which seasons would be fetched. No errors.

**Step 3: Run the real backfill (one-time)**

```bash
DATABASE_URL="..." python scripts/backfill_game_logs.py
```

Expected: ~2-5 minutes, all players stored to Supabase. Safe to interrupt and re-run.

**Step 4: Commit**

```bash
git add scripts/backfill_game_logs.py
git commit -m "feat: add backfill script for historical game logs to Supabase"
```

---

### Task 5: Verify End-to-End

**Step 1: Clear local cache to force Supabase reads**

```bash
rm -rf cache/
```

**Step 2: Run a prediction for an already-backfilled player**

```bash
DATABASE_URL="..." python nba_evaluator.py --player "LeBron James" --stat PTS --line 25.5
```

Expected: logs show `📦 Loaded 2024-25 from Supabase` and `📦 Loaded 2023-24 from Supabase` — only ONE NBA API call (for 2025-26).

**Step 3: Run a prediction for a new player (not yet in Supabase)**

Pick any player without a trained model (e.g. "Anthony Davis") via the research endpoint:

```bash
curl "http://localhost:8000/api/players/Anthony%20Davis/research"
```

Expected: first call fetches from NBA API and stores to Supabase. Second call is instant.

**Step 4: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete Supabase historical game log cache"
```

---

## Season Archival (future, end of 2025-26 season)

When the 2025-26 season ends:

1. Archive current season to Supabase:
   ```bash
   DATABASE_URL="..." python scripts/backfill_game_logs.py --season 2025-26
   ```

2. Update constants in `nba_evaluator.py`:
   ```python
   CURRENT_SEASON = '2026-27'
   HISTORICAL_SEASONS = ['2025-26', '2024-25']
   ```

3. Commit:
   ```bash
   git commit -m "chore: advance season to 2026-27, archive 2025-26 to Supabase"
   ```
