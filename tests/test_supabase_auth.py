"""Tests for Supabase JWT verification."""
import pytest
from unittest.mock import patch
import time
from jose import jwt

SUPABASE_JWT_SECRET = "test-supabase-jwt-secret-that-is-long-enough-32ch"

def make_supabase_token(user_id: str, email: str, secret: str = SUPABASE_JWT_SECRET) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_decode_supabase_token_returns_user_id():
    from api.auth_utils import decode_access_token
    token = make_supabase_token("user-uuid-123", "test@example.com")
    with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": SUPABASE_JWT_SECRET}):
        payload = decode_access_token(token)
    assert payload["sub"] == "user-uuid-123"
    assert payload["email"] == "test@example.com"


def test_decode_invalid_token_raises():
    from api.auth_utils import decode_access_token
    from jose import JWTError
    with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": SUPABASE_JWT_SECRET}):
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")
