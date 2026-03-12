"""One-time backfill: populate headshot_url for existing picks using Sleeper CDN."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from sleeper_client import get_headshot_url


def main():
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, player FROM picks WHERE headshot_url IS NULL"
            )
            rows = cur.fetchall()

            if not rows:
                print("No picks need backfilling.")
                return

            updated = 0
            for row in rows:
                url = get_headshot_url(row["player"])
                if url:
                    cur.execute(
                        "UPDATE picks SET headshot_url = %s WHERE id = %s",
                        (url, row["id"]),
                    )
                    updated += 1
                    print(f"  {row['player']}: {url}")
                else:
                    print(f"  {row['player']}: no Sleeper match")

            conn.commit()
            print(f"\nBackfilled {updated}/{len(rows)} picks.")
    finally:
        db.put_connection(conn)


if __name__ == "__main__":
    main()
