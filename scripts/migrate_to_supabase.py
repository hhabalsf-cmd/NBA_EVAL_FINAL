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
