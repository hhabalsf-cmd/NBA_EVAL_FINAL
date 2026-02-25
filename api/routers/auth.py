"""Authentication endpoints — register, login, me."""
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, EmailStr

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db
from ..auth_utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer()


# ── Schemas ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


# ── Dependency ─────────────────────────────────────────────────

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """FastAPI dependency — validates Bearer token, returns user dict."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get_user_by_id(user_id)
    if not user:
        raise credentials_exception
    return user


# ── Endpoints ──────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(req: RegisterRequest):
    if db.get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already in use")

    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)
    user = db.create_user(user_id, req.email, hashed, req.username)

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "email": user["email"], "username": user["username"],
              "created_at": user["created_at"]},
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    invalid = HTTPException(status_code=401, detail="Invalid credentials")
    user = db.get_user_by_email(req.email)
    if not user:
        raise invalid
    if not verify_password(req.password, user["hashed_password"]):
        raise invalid

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "email": user["email"], "username": user["username"],
              "created_at": user["created_at"]},
    )


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
    }
