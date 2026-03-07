"""Authentication endpoints — avatar management and password change."""
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import db
from ..auth_utils import (
    decode_access_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

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


# ── Schemas ────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


# ── Dependency ─────────────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    """FastAPI dependency — validates Supabase Bearer JWT, returns profile dict."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    from supabase import create_client
    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    result = supa.table("profiles").select("*").eq("id", user_id).single().execute()
    if not result.data:
        raise credentials_exception

    profile = result.data
    return {
        "id": profile["id"],
        "email": payload.get("email", ""),
        "username": profile["username"],
        "created_at": profile["created_at"],
        "role": profile.get("role", "user"),
        "avatar_url": profile.get("avatar_url"),
    }


# ── Service key dependency ──────────────────────────────────────

FASTAPI_SERVICE_KEY = os.getenv("FASTAPI_SERVICE_KEY")


def verify_service_key(request: Request) -> None:
    """Dependency for internal endpoints called by Edge Functions / pg_cron."""
    key = request.headers.get("X-Service-Key")
    if not key or key != FASTAPI_SERVICE_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Endpoints ──────────────────────────────────────────────────

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
    from ..auth_utils import verify_password, hash_password
    if not verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    db.update_user_password(current_user["id"], hash_password(req.new_password))


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
