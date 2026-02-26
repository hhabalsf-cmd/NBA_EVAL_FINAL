"""Tests for auth endpoints."""
import sys
import os
from pathlib import Path

# Point at a temp DB for tests
os.environ["AUTH_SECRET_KEY"] = "test-secret-key-for-tests"
_TEST_DB = Path(__file__).parent / "test_picks.db"
os.environ["TEST_DB_PATH"] = str(_TEST_DB)

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import pytest
from fastapi.testclient import TestClient

# Patch DB_PATH before importing anything that uses it
import db
db.DB_PATH = _TEST_DB

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Re-init DB and wipe users before each test."""
    db.init_db()
    conn = db.get_connection()
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM picks")
    conn.commit()
    conn.close()
    yield
    # teardown: remove test DB
    if _TEST_DB.exists():
        _TEST_DB.unlink()


def test_register_creates_user_and_returns_token():
    r = client.post("/api/auth/register", json={
        "email": "user@test.com", "username": "tester", "password": "pass123"
    })
    assert r.status_code == 201
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == "user@test.com"
    assert data["user"]["username"] == "tester"


def test_register_duplicate_email_returns_409():
    payload = {"email": "dup@test.com", "username": "a", "password": "pass"}
    client.post("/api/auth/register", json=payload)
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 409


def test_login_valid_credentials():
    client.post("/api/auth/register", json={
        "email": "log@test.com", "username": "logger", "password": "mypass"
    })
    r = client.post("/api/auth/login", json={"email": "log@test.com", "password": "mypass"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_wrong_password_returns_401():
    client.post("/api/auth/register", json={
        "email": "x@test.com", "username": "x", "password": "right"
    })
    r = client.post("/api/auth/login", json={"email": "x@test.com", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_email_returns_401():
    r = client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "x"})
    assert r.status_code == 401


def test_me_with_valid_token():
    reg = client.post("/api/auth/register", json={
        "email": "me@test.com", "username": "meuser", "password": "pw"
    })
    token = reg.json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "me@test.com"


def test_me_without_token_returns_403():
    r = client.get("/api/auth/me")
    assert r.status_code in (401, 403)


def test_create_pick_requires_auth():
    r = client.post("/api/picks", json={
        "player": "LeBron James", "stat": "PTS", "line": 25.5,
        "prediction": 27.0, "direction": "OVER", "edge": 5.8,
    })
    assert r.status_code in (401, 403)


def test_create_and_retrieve_pick_scoped_to_user():
    # Register two users
    r1 = client.post("/api/auth/register", json={
        "email": "u1@test.com", "username": "u1", "password": "pw"
    })
    token1 = r1.json()["token"]
    r2 = client.post("/api/auth/register", json={
        "email": "u2@test.com", "username": "u2", "password": "pw"
    })
    token2 = r2.json()["token"]

    # User 1 saves a pick
    client.post("/api/picks", json={
        "player": "LeBron James", "stat": "PTS", "line": 25.5,
        "prediction": 27.0, "direction": "OVER", "edge": 5.8,
    }, headers={"Authorization": f"Bearer {token1}"})

    # User 1 sees 1 pick, user 2 sees 0
    picks1 = client.get("/api/picks", headers={"Authorization": f"Bearer {token1}"}).json()
    picks2 = client.get("/api/picks", headers={"Authorization": f"Bearer {token2}"}).json()
    assert len(picks1) == 1
    assert len(picks2) == 0


def test_update_user_avatar_stores_url():
    from db import create_user, update_user_avatar, get_user_by_id
    import uuid
    uid = str(uuid.uuid4())
    create_user(uid, "av@test.com", "hashed", "avuser")
    updated = update_user_avatar(uid, "/uploads/avatars/test.jpg")
    assert updated["avatar_url"] == "/uploads/avatars/test.jpg"
    fetched = get_user_by_id(uid)
    assert fetched["avatar_url"] == "/uploads/avatars/test.jpg"


def test_update_user_avatar_unknown_user_returns_none():
    from db import update_user_avatar
    result = update_user_avatar("nonexistent-id", "/uploads/avatars/x.jpg")
    assert result is None

import io

def _get_token(email="av2@test.com", username="avuser2", password="pw"):
    r = client.post("/api/auth/register", json={
        "email": email, "username": username, "password": password
    })
    return r.json()["token"]


def test_avatar_upload_returns_avatar_url():
    token = _get_token()
    img_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
        b"\xff\xd9"
    )
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "avatar_url" in data
    assert data["avatar_url"].startswith("/uploads/avatars/")


def test_avatar_upload_rejects_non_image():
    token = _get_token("av3@test.com", "avuser3")
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("hack.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
    )
    assert r.status_code == 400


def test_avatar_upload_rejects_oversized_file():
    token = _get_token("av4@test.com", "avuser4")
    big = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024 + 1))
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("big.jpg", big, "image/jpeg")},
    )
    assert r.status_code == 413


def test_avatar_upload_requires_auth():
    r = client.post(
        "/api/auth/avatar",
        files={"file": ("x.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )
    assert r.status_code in (401, 403)


def test_me_returns_avatar_url_after_upload():
    """End-to-end: avatar_url is persisted and returned by /me after upload."""
    import io
    token = _get_token("av5@test.com", "avuser5")
    img_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert "avatar_url" in me
    assert me["avatar_url"] is not None
    assert me["avatar_url"].startswith("/uploads/avatars/")


def test_update_user_password_changes_hash():
    import db as _db
    from api.auth_utils import hash_password, verify_password
    # create a user directly
    user = _db.create_user("uid-pw", "pw@test.com", hash_password("old"), "pwuser")
    _db.update_user_password("uid-pw", hash_password("new"))
    refreshed = _db.get_user_by_id("uid-pw")
    assert verify_password("new", refreshed["hashed_password"])
    assert not verify_password("old", refreshed["hashed_password"])
