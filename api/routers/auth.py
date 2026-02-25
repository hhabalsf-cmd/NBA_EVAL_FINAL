"""Authentication endpoints — register, login, me."""
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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

# Avatar upload constants
_AVATAR_DIR = Path(__file__).parent.parent.parent / "uploads" / "avatars"
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


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
              "created_at": user["created_at"], "role": user.get("role", "user"),
              "avatar_url": user.get("avatar_url")},
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
              "created_at": user["created_at"], "role": user.get("role", "user"),
              "avatar_url": user.get("avatar_url")},
    )


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
        "role": current_user.get("role", "user"),
        "avatar_url": current_user.get("avatar_url"),
    }


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")

    contents = await file.read()
    if len(contents) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large — maximum 2MB")

    ext = _EXT_MAP[file.content_type]
    filename = f"{current_user['id']}.{ext}"
    dest = _AVATAR_DIR / filename

    # Write new file first — only clean up old files after successful write
    try:
        dest.write_bytes(contents)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Failed to save avatar") from exc

    # Remove old avatar files with a different extension (e.g. old .jpg when uploading .png)
    for old in _AVATAR_DIR.glob(f"{current_user['id']}.*"):
        if old != dest:
            old.unlink(missing_ok=True)

    avatar_url = f"/uploads/avatars/{filename}"
    updated = db.update_user_avatar(current_user["id"], avatar_url)

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated user")

    return {
        "id": updated["id"],
        "email": updated["email"],
        "username": updated["username"],
        "created_at": updated["created_at"],
        "role": updated.get("role", "user"),
        "avatar_url": updated.get("avatar_url"),
    }


@router.delete("/avatar", status_code=200)
async def delete_avatar(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    updated = db.clear_user_avatar(user_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update user")

    # Delete avatar files from disk only after DB write succeeds
    for old in _AVATAR_DIR.glob(f"{user_id}.*"):
        old.unlink(missing_ok=True)

    return {
        "id": updated["id"],
        "email": updated["email"],
        "username": updated["username"],
        "created_at": updated["created_at"],
        "role": updated.get("role", "user"),
        "avatar_url": updated.get("avatar_url"),
    }
