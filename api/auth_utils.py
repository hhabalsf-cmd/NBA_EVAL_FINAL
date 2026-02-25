"""JWT token creation/verification and password hashing utilities."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import JWTError, jwt
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _get_secret_key() -> str:
    """Read secret key from AUTH_SECRET_KEY env var, then config.json, then raise."""
    secret = os.environ.get("AUTH_SECRET_KEY")
    if secret:
        return secret
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text())
            if cfg.get("auth_secret_key"):
                return cfg["auth_secret_key"]
        except Exception:
            pass
    raise RuntimeError(
        "AUTH_SECRET_KEY not set. Add it as an env var or set 'auth_secret_key' in config.json"
    )


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Return decoded payload dict, or raise JWTError on failure."""
    return jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
