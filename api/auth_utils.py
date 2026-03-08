"""JWT verification using Supabase JWT secret."""
import os
from jose import jwt

ALGORITHM = "HS256"


def _get_supabase_jwt_secret() -> str:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "SUPABASE_JWT_SECRET env var is not set or too short (min 32 chars)."
        )
    return secret


def decode_access_token(token: str) -> dict:
    """Verify and decode a Supabase-issued JWT. Raises JWTError on failure."""
    return jwt.decode(
        token,
        _get_supabase_jwt_secret(),
        algorithms=[ALGORITHM],
        audience="authenticated",
    )
