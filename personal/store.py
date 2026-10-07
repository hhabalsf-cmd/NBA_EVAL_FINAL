"""Local cache and an append-only record of observed statistical corrections."""
import json
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, fetched REAL, body TEXT);
                CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, body TEXT, checked REAL);
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY, key TEXT, observed REAL, before TEXT, after TEXT,
                    UNIQUE(key, before, after));
                CREATE TABLE IF NOT EXISTS forecasts (
                    id INTEGER PRIMARY KEY, created REAL, body TEXT);
            ''')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def cached(self, key, ttl):
        with self.connect() as db:
            row = db.execute('SELECT fetched,body FROM cache WHERE key=?', (key,)).fetchone()
        if row and 0 <= time.time() - row[0] < ttl:
            return json.loads(row[1]), row[0]
        return None

    def cache(self, key, body):
        fetched = time.time()
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (key, fetched, json.dumps(body)))
        return fetched

    def reconcile(self, key, row, reference=None):
        """Preserve original observations; never rewrite already saved forecasts."""
        body = json.dumps(row, sort_keys=True)
        with self.connect() as db:
            old = db.execute('SELECT body FROM stats WHERE key=?', (key,)).fetchone()
            before = old[0] if old else (json.dumps(reference, sort_keys=True) if reference else body)
            changed = json.loads(before) != row
            if changed:
                db.execute('INSERT OR IGNORE INTO corrections(key,observed,before,after) VALUES (?,?,?,?)',
                           (key, time.time(), before, body))
            db.execute('INSERT OR REPLACE INTO stats VALUES (?,?,?)', (key, body, time.time()))
        return changed

    def save_forecast(self, body):
        with self.connect() as db:
            cursor = db.execute('INSERT INTO forecasts(created,body) VALUES (?,?)',
                                (time.time(), json.dumps(body)))
            return cursor.lastrowid

    def forecasts(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,created,body FROM forecasts ORDER BY id DESC LIMIT 30').fetchall()
        return [dict(id=row[0], created=row[1], forecast=json.loads(row[2])) for row in rows]

    def corrections(self):
        with self.connect() as db:
            rows = db.execute('SELECT key,observed,before,after FROM corrections ORDER BY id DESC LIMIT 100').fetchall()
        return [dict(key=r[0], observed=r[1], before=json.loads(r[2]), after=json.loads(r[3])) for r in rows]

    def backup(self, destination):
        """Use SQLite's consistent online backup, including committed WAL data."""
        destination = Path(destination).resolve()
        if destination == self.path.resolve() or destination.exists():
            raise ValueError('Choose a new backup path outside the live database.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return str(destination)
