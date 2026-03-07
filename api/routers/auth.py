"""Authentication endpoints — avatar management and password change."""
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ..auth_utils import (
    decode_access_token,
)
from supabase import create_client as _create_supabase_client

_supa_client = None


def _get_supa_client():
    global _supa_client
    if _supa_client is None:
        _supa_client = _create_supabase_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    return _supa_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Avatar upload constants ─────────────────────────────────────
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

    supa = _get_supa_client()
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
if not FASTAPI_SERVICE_KEY:
    raise RuntimeError(
        "FASTAPI_SERVICE_KEY env var is not set. Auto-grade endpoints would be unprotected."
    )


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
        raise HTTPException(status_code=400, detail="File content does not match declared type")

    ext = _EXT_MAP[file.content_type]
    storage_path = f"{current_user['id']}.{ext}"

    supa = _get_supa_client()
    try:
        supa.storage.from_("avatars").upload(
            storage_path,
            contents,
            {"content-type": file.content_type, "upsert": "true"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to upload avatar") from exc

    avatar_url = f"{os.environ['SUPABASE_URL']}/storage/v1/object/public/avatars/{storage_path}"

    supa.table("profiles").update({"avatar_url": avatar_url}).eq("id", current_user["id"]).execute()

    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
        "role": current_user.get("role", "user"),
        "avatar_url": avatar_url,
    }


@router.post("/change-password", status_code=204)
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    supa = _get_supa_client()
    try:
        supa.auth.admin.update_user_by_id(
            current_user["id"],
            {"password": req.new_password}
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/avatar", status_code=200)
async def delete_avatar(current_user: dict = Depends(get_current_user)):
    supa = _get_supa_client()
    user_id = current_user["id"]

    # Remove all avatar variants from storage (user may have uploaded different extensions)
    for ext in ["jpg", "png", "webp"]:
        try:
            supa.storage.from_("avatars").remove([f"{user_id}.{ext}"])
        except Exception:
            pass  # File may not exist for that extension

    supa.table("profiles").update({"avatar_url": None}).eq("id", user_id).execute()

    return {
        "id": user_id,
        "email": current_user["email"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
        "role": current_user.get("role", "user"),
        "avatar_url": None,
    }
