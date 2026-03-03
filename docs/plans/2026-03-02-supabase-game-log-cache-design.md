# Supabase Game Log Cache Design

**Date:** 2026-03-02
**Scope:** Store frozen historical seasons (2023-24, 2024-25) in Supabase. Keep 2025-26 hitting the live NBA API. Reduces per-player NBA API calls from 3 → 1 on every prediction/research load.

---

## Problem

`get_player_game_log()` calls the NBA API 3× per player (one per season) with a 0.6s rate-limit sleep each call. Seasons 2023-24 and 2024-25 are complete and never change — there is no reason to re-fetch them.

At 100-200 players this compounds: cold-start research for an uncached player makes ~1.8s of forced sleeps alone, plus network latency × 3.

---

## Solution

```
Historical seasons (2023-24, 2024-25):
  Supabase hit? → return instantly (0 API calls)
  Miss?         → NBA API → write to Supabase permanently → return
                  (only happens once per player, ever)

Current season (2025-26):
  Local file cache hit (< 1h)? → return (unchanged)
  Miss?                        → NBA API → save to local cache → return
```

All 3 seasons are still combined and fed to FeatureEngineer exactly as today — the ML pipeline is unchanged.

---

## Supabase Schema

Run once in the Supabase SQL Editor:

```sql
CREATE TABLE player_game_logs (
    player_id   TEXT    NOT NULL,
    season      TEXT    NOT NULL,
    game_id     TEXT    NOT NULL,
    game_date   DATE    NOT NULL,
    matchup     TEXT,
    wl          TEXT,
    min         REAL,
    pts         REAL,
    reb         REAL,
    ast         REAL,
    stl         REAL,
    blk         REAL,
    tov         REAL,
    fgm         REAL,
    fga         REAL,
    fg_pct      REAL,
    fg3m        REAL,
    fg3a        REAL,
    fg3_pct     REAL,
    ftm         REAL,
    fta         REAL,
    ft_pct      REAL,
    oreb        REAL,
    dreb        REAL,
    pf          REAL,
    plus_minus  REAL,
    video_available INTEGER,
    PRIMARY KEY (player_id, game_id)
);

CREATE INDEX idx_player_game_logs_lookup
    ON player_game_logs (player_id, season);
```

Primary key `(player_id, game_id)` prevents duplicates on re-runs. Index on `(player_id, season)` makes per-season lookups fast.

---

## Files Changed

| File | Change |
|------|--------|
| `nba_evaluator.py` | Modify `get_player_game_log()` — check Supabase for historical seasons, write on miss |
| `db.py` | Add `get_game_logs_from_supabase()` and `insert_game_logs_to_supabase()` helpers |
| `scripts/backfill_game_logs.py` | New — one-time seed for existing ~50 players × 2 historical seasons |
| `api/requirements.txt` | `psycopg2-binary` already present (from Supabase migration) |

---

## Data Flow Detail

### `get_player_game_log(player_id, seasons=None)`

```
For each season in ['2025-26', '2024-25', '2023-24']:
  if season == CURRENT_SEASON ('2025-26'):
    → existing local file cache logic (unchanged)
  else:
    rows = get_game_logs_from_supabase(player_id, season)
    if rows is not None and len(rows) > 0:
      → use rows (DataFrame)
    else:
      → fetch from NBA API
      → insert_game_logs_to_supabase(df, player_id, season)
      → use df

Combine all seasons → sort ascending by game_date → return
```

### `db.py` helpers

```python
def get_game_logs_from_supabase(player_id: str, season: str) -> pd.DataFrame | None:
    """Returns DataFrame of game logs or None if not stored."""

def insert_game_logs_to_supabase(df: pd.DataFrame, player_id: str, season: str) -> None:
    """Bulk inserts game log rows. Uses INSERT ... ON CONFLICT DO NOTHING."""
```

Both use the existing `get_connection()` / `DATABASE_URL` pattern from the Supabase migration.

---

## Backfill Script (`scripts/backfill_game_logs.py`)

One-time script to seed all currently active players.

**Behaviour:**
- Reads player list from `models/*.pkl` filenames (already trained players)
- For each player × each historical season: checks if rows already exist → skips if yes
- Fetches from NBA API with 0.6s sleep (same rate limiting as today)
- Inserts to Supabase via `ON CONFLICT DO NOTHING`
- Prints progress: `player | season | rows inserted | skipped`
- Safe to re-run — idempotent

**Usage:**
```bash
DATABASE_URL="..." python scripts/backfill_game_logs.py
```

Estimated runtime for 50 players × 2 seasons = ~100 API calls × ~1s each ≈ 2 minutes.

---

## Research for Any Player

No frontend changes required. `ResearchPage.tsx` already accepts any player name.

The benefit: the first time you research a player (e.g. Shai Gilgeous-Alexander who has no trained model), the historical seasons are fetched from NBA API and stored to Supabase. Every subsequent research load for that player costs 0 NBA API calls for those seasons.

---

## Season Archival

At the end of the 2025-26 season (April):
1. Run `backfill_game_logs.py` with `--season 2025-26` flag to archive current season
2. Update `CURRENT_SEASON = '2026-27'` constant in `nba_evaluator.py`
3. Historical seasons list becomes `['2024-25', '2025-26']`

---

## Environment Config

Existing `DATABASE_URL` env var is sufficient — no new credentials needed.
