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
