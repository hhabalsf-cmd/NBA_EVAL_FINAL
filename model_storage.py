"""Three-tier model storage: L1 memory -> L2 local disk -> L3 Supabase Storage.

Provides upload/download helpers for ML model pickle files. All public
functions return ``bool`` so callers can fall back to retraining when
Supabase is unreachable.
"""

import logging
import os
import threading
from pathlib import Path

_logger = logging.getLogger(__name__)

BUCKET_NAME = "ml-models"
_PLAYER_PREFIX = "players/"
_GAME_PREFIX = "games/"

# ── Lazy singleton (same pattern as api/routers/auth.py) ──────────────────────
_supa_client = None
_supa_lock = threading.Lock()


def _get_storage_client():
    """Return a thread-safe lazy Supabase client singleton (service key)."""
    global _supa_client
    if _supa_client is None:
        with _supa_lock:
            if _supa_client is None:
                from supabase import create_client
                _supa_client = create_client(
                    os.environ["SUPABASE_URL"],
                    os.environ["SUPABASE_SERVICE_KEY"],
                )
    return _supa_client


# ── Player models ─────────────────────────────────────────────────────────────

def upload_player_model(player_name: str, local_path: Path) -> bool:
    """Upload a player model pkl from local disk to Supabase Storage."""
    storage_key = f"{_PLAYER_PREFIX}{local_path.name}"
    return _upload_file(local_path, storage_key, player_name)


def download_player_model(player_name: str, local_path: Path) -> bool:
    """Download a player model from Supabase Storage to *local_path*."""
    storage_key = f"{_PLAYER_PREFIX}{local_path.name}"
    return _download_file(storage_key, local_path, player_name)


# ── Game model ────────────────────────────────────────────────────────────────

def upload_game_model(local_path: Path) -> bool:
    """Upload ``game_predictor.pkl`` to Supabase Storage."""
    storage_key = f"{_GAME_PREFIX}{local_path.name}"
    return _upload_file(local_path, storage_key, "game_predictor")


def download_game_model(local_path: Path) -> bool:
    """Download ``game_predictor.pkl`` from Supabase Storage."""
    storage_key = f"{_GAME_PREFIX}{local_path.name}"
    return _download_file(storage_key, local_path, "game_predictor")


# ── Line-anchored models ─────────────────────────────────────────────────────

_LINE_PREFIX = "line_anchored/"


def upload_line_model(player_name: str, local_path: Path) -> bool:
    """Upload a line-anchored model pkl to Supabase Storage."""
    storage_key = f"{_LINE_PREFIX}{local_path.name}"
    return _upload_file(local_path, storage_key, f"line:{player_name}")


def download_line_model(player_name: str, local_path: Path) -> bool:
    """Download a line-anchored model from Supabase Storage."""
    storage_key = f"{_LINE_PREFIX}{local_path.name}"
    return _download_file(storage_key, local_path, f"line:{player_name}")


# ── Listing (migration / diagnostics) ────────────────────────────────────────

def list_player_models() -> list[str]:
    """Return filenames of all player models stored in the bucket."""
    try:
        supa = _get_storage_client()
        files = supa.storage.from_(BUCKET_NAME).list(_PLAYER_PREFIX)
        return [f["name"] for f in files if f.get("name", "").endswith(".pkl")]
    except Exception as exc:
        _logger.error("Failed to list player models in Supabase: %s", exc)
        return []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _upload_file(local_path: Path, storage_key: str, label: str) -> bool:
    """Upload a local file to Supabase Storage with upsert."""
    try:
        supa = _get_storage_client()
        with open(local_path, "rb") as f:
            data = f.read()
        supa.storage.from_(BUCKET_NAME).upload(
            path=storage_key,
            file=data,
            file_options={"content-type": "application/octet-stream", "upsert": "true"},
        )
        _logger.info("Uploaded %s to Supabase (%d bytes)", label, len(data))
        return True
    except Exception as exc:
        _logger.error("Failed to upload %s to Supabase: %s", label, exc)
        return False


def _download_file(storage_key: str, local_path: Path, label: str) -> bool:
    """Download a file from Supabase Storage to a local path."""
    try:
        supa = _get_storage_client()
        data = supa.storage.from_(BUCKET_NAME).download(storage_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        _logger.info("Downloaded %s from Supabase (%d bytes)", label, len(data))
        return True
    except Exception as exc:
        # 404 = model doesn't exist yet (expected after fresh deploy or bucket clear)
        exc_str = str(exc)
        if 'not_found' in exc_str or '404' in exc_str:
            _logger.debug("Model %s not found in Supabase (will train on demand)", label)
        else:
            _logger.warning("Failed to download %s from Supabase: %s", label, exc)
        return False
