"""Tests for auth endpoints (post-Supabase migration).

Legacy tests for /register, /login, /me, /refresh have been removed because
those endpoints were deleted in the Supabase migration (Task 5).  JWT decoding
tests live in test_supabase_auth.py.
"""
import io
import sys
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

# Provide required env vars before importing the app
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-supabase-jwt-secret-that-is-long-enough-32ch")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("FASTAPI_SERVICE_KEY", "test-fastapi-service-key")

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

# ── Shared fake user returned by mocked get_current_user ────────────────────

FAKE_USER = {
    "id": "test-user-id",
    "email": "test@example.com",
    "username": "testuser",
    "created_at": "2026-01-01T00:00:00",
    "role": "user",
    "avatar_url": None,
}


def _auth_headers() -> dict:
    """Return headers with a dummy bearer token (get_current_user is mocked)."""
    return {"Authorization": "Bearer fake-token"}


# ── Unauthenticated rejection tests ─────────────────────────────────────────

def test_avatar_upload_requires_auth():
    r = client.post(
        "/api/auth/avatar",
        files={"file": ("x.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )
    assert r.status_code in (401, 403)


def test_delete_avatar_requires_auth():
    r = client.delete("/api/auth/avatar")
    assert r.status_code in (401, 403)


def test_change_password_requires_auth():
    r = client.post(
        "/api/auth/change-password",
        json={"new_password": "newpass123"},
    )
    assert r.status_code in (401, 403)


# ── Avatar upload validation tests ──────────────────────────────────────────

def test_avatar_upload_rejects_non_image():
    with patch("api.routers.auth.get_current_user", return_value=FAKE_USER):
        r = client.post(
            "/api/auth/avatar",
            headers=_auth_headers(),
            files={"file": ("hack.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
        )
    assert r.status_code == 400


def test_avatar_upload_rejects_oversized_file():
    big = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * (6 * 1024 * 1024))
    with patch("api.routers.auth.get_current_user", return_value=FAKE_USER):
        r = client.post(
            "/api/auth/avatar",
            headers=_auth_headers(),
            files={"file": ("big.jpg", big, "image/jpeg")},
        )
    assert r.status_code == 413


def test_avatar_upload_rejects_spoofed_content_type():
    """File claims to be JPEG but magic bytes are PNG — should be rejected."""
    # PNG magic bytes with jpeg content-type header
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with patch("api.routers.auth.get_current_user", return_value=FAKE_USER):
        r = client.post(
            "/api/auth/avatar",
            headers=_auth_headers(),
            files={"file": ("spoofed.jpg", io.BytesIO(png_bytes), "image/jpeg")},
        )
    assert r.status_code == 400


def test_create_pick_requires_auth():
    r = client.post("/api/picks", json={
        "player": "LeBron James", "stat": "PTS", "line": 25.5,
        "prediction": 27.0, "direction": "OVER", "edge": 5.8,
    })
    assert r.status_code in (401, 403)
