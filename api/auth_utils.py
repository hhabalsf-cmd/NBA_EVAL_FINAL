"""JWT token creation/verification and password hashing utilities."""
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def _get_secret_key() -> str:
    """Read secret key from AUTH_SECRET_KEY env var only."""
    secret = os.environ.get("AUTH_SECRET_KEY")
    if secret:
        return secret
    raise RuntimeError(
        "AUTH_SECRET_KEY environment variable is not set. "
        "Set it before starting the server: export AUTH_SECRET_KEY=<your-secret>"
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
