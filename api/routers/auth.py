"""Authentication endpoints — register, login, me."""
import os
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field

from ..limiter import limiter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db
from ..auth_utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Cookie config ───────────────────────────────────────────────
_COOKIE_NAME = "access_token"
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

# ── Avatar upload constants ─────────────────────────────────────
_AVATAR_DIR = Path(__file__).parent.parent.parent / "uploads" / "avatars"
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Magic byte signatures for image validation (guards against spoofed Content-Type)
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),  # RIFF....WEBP — checked further below
]


def _validate_image_magic(data: bytes, declared_type: str) -> bool:
    """Return True if file magic bytes match the declared content type."""
    for magic, mime in _MAGIC_BYTES:
        if data[:len(magic)] == magic:
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime == declared_type
    return False


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set the httpOnly auth cookie on a response."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="strict",
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


# ── Schemas ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class AuthResponse(BaseModel):
    user: dict


# ── Dependency ─────────────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    """FastAPI dependency — validates httpOnly cookie, returns user dict."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
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
@limiter.limit("3/minute")
async def register(request: Request, response: Response, req: RegisterRequest):
    if db.get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Registration failed")

    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)
    user = db.create_user(user_id, req.email, hashed, req.username)

    access_token_str = create_access_token(user["id"], user["email"]) # nosec
    _set_auth_cookie(response, access_token_str)
    return AuthResponse(
        user={"id": user["id"], "email": user["email"], "username": user["username"],
              "created_at": user["created_at"], "role": user.get("role", "user"),
              "avatar_url": user.get("avatar_url")},
    )


@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, req: LoginRequest):
    invalid = HTTPException(status_code=401, detail="Invalid credentials")
    user = db.get_user_by_email(req.email)
    # Always run bcrypt to prevent timing-based account enumeration
    dummy_hash = "$2b$12$dummy.hash.to.prevent.timing.attacks.on.missing.accounts"
    candidate_hash = user["hashed_password"] if user else dummy_hash
    password_valid = verify_password(req.password, candidate_hash)
    if not user or not password_valid:
        raise invalid

    access_token_str = create_access_token(user["id"], user["email"]) # nosec
    _set_auth_cookie(response, access_token_str)
    return AuthResponse(
        user={"id": user["id"], "email": user["email"], "username": user["username"],
              "created_at": user["created_at"], "role": user.get("role", "user"),
              "avatar_url": user.get("avatar_url")},
    )


@router.post("/logout", status_code=204)
async def logout(response: Response):
    """Clear the auth cookie — no auth required."""
    response.delete_cookie(key=_COOKIE_NAME, path="/")


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
        raise HTTPException(status_code=413, detail="File too large — maximum 5MB")

    if not _validate_image_magic(contents, file.content_type):
        raise HTTPException(status_code=400, detail="File content does not match the declared image type")

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


@router.post("/change-password", status_code=204)
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    if not verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    db.update_user_password(current_user["id"], hash_password(req.new_password))


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(response: Response, current_user: dict = Depends(get_current_user)):
    """Issue a fresh JWT token for an already-authenticated user."""
    access_token_str = create_access_token(current_user["id"], current_user["email"]) # nosec
    _set_auth_cookie(response, access_token_str)
    return AuthResponse(
        user={
            "id": current_user["id"],
            "email": current_user["email"],
            "username": current_user["username"],
            "created_at": current_user.get("created_at"),
            "role": current_user.get("role", "user"),
            "avatar_url": current_user.get("avatar_url"),
        },
    )


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
