"""Sync endpoints — triggered by Supabase pg_cron to run nightly data sync."""
import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..routers.auth import verify_service_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Resolve the project root (two levels up from this file: api/routers/sync.py → root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@router.post("/nightly")
async def run_nightly_sync(request: Request):
    """
    Trigger nightly player game-log sync from BallDontLie into Supabase.
    Protected by X-Service-Key header — called by Supabase pg_cron via pg_net.
    """
    verify_service_key(request)

    script = _PROJECT_ROOT / "scripts" / "nightly_sync.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="nightly_sync.py not found")

    logger.info("Starting nightly sync via %s", script)
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Nightly sync timed out after 600s")
    except Exception as exc:
        logger.exception("Nightly sync subprocess error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if result.returncode != 0:
        logger.error("Nightly sync failed (exit %d): %s", result.returncode, result.stderr[-1000:])
        raise HTTPException(
            status_code=500,
            detail=f"Sync exited {result.returncode}: {result.stderr[-500:]}",
        )

    logger.info("Nightly sync completed successfully")
    return {"status": "ok", "output": result.stdout[-500:]}
