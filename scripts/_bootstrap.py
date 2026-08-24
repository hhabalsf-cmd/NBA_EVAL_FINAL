"""Shared script bootstrap: project path and environment.

Import this first, before any project module:

    import _bootstrap  # noqa: F401

``override=True`` is not optional. Without it a stale ``DATABASE_URL`` already
present in the shell wins over the one in ``.env``, and every query fails with
"password authentication failed for user postgres" — an error that points at
the database when the real fault is the probe. That misdiagnosis cost a false
"the database is dead" finding on 2026-08-22.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=True)
