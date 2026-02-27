# Profile Picture Upload — Design

**Date:** 2026-02-25
**Status:** Approved

## Overview

Allow authenticated users to upload a custom profile picture. Images are stored on the server filesystem and served via FastAPI StaticFiles. The `UserMenu` avatar and `SettingsPage` profile tab both reflect the uploaded image.

## Backend

### DB migration (`db.py`)
- Add `avatar_url TEXT` column to `users` table using the existing `PRAGMA table_info` auto-migration pattern.
- Add `update_user_avatar(user_id: str, avatar_url: str) -> dict` helper that updates the column and returns the updated user row.
- All user-returning functions (`create_user`, `get_user_by_email`, `get_user_by_id`) already return `dict(row)`, so `avatar_url` is automatically included after migration.

### Static file serving (`api/main.py`)
- Mount `uploads/avatars/` directory at `/uploads/avatars` using FastAPI `StaticFiles`.
- Create the directory if it doesn't exist on startup.

### Upload endpoint (`api/routers/auth.py`)
- `POST /api/auth/avatar` — requires Bearer token (`get_current_user` dependency).
- Accepts `multipart/form-data` with a single `file` field.
- Server-side validation: allowed MIME types `image/jpeg`, `image/png`, `image/webp`; max 2MB.
- Saves file as `uploads/avatars/{user_id}.{ext}` (overwrites previous avatar automatically).
- Calls `db.update_user_avatar(user_id, "/uploads/avatars/{user_id}.{ext}")`.
- Returns updated user dict.
- All existing auth responses (`/register`, `/login`, `/me`) include `avatar_url` field.

## Frontend

### Type (`types/auth.ts`)
- Add `avatar_url?: string` to `User` interface.

### API client (`api/client.ts`)
- Add `uploadAvatar(file: File): Promise<User>` — sends `multipart/form-data` POST to `/api/auth/avatar` with Bearer token header, returns updated user.

### Auth store (`store/authStore.ts`)
- Add `updateAvatar(file: File): Promise<void>` action — calls `uploadAvatar`, updates `user` in store on success.
- Add `isUploadingAvatar: boolean` state flag for loading indicator.

### SettingsPage (`pages/SettingsPage.tsx`)
- Profile tab: show circular avatar (80×80px) — `<img>` if `user.avatar_url` is set, else initials fallback circle.
- "Change photo" button opens a hidden `<input type="file" accept="image/jpeg,image/png,image/webp">`.
- On file selection: client-side size validation (max 2MB), then call `updateAvatar`. Show spinner during upload.
- On success: avatar preview updates instantly from store.
- On error: show inline error message.

### UserMenu (`components/UserMenu.tsx`)
- Replace initials circle with `<img src={user.avatar_url}>` when `avatar_url` is set.
- Fall back to existing initials circle when `avatar_url` is null/undefined.
- Same 32×32px circle shape, `object-cover` for proper cropping.

## Constraints

- Allowed formats: JPEG, PNG, WebP
- Max file size: 2MB (enforced both client-side and server-side)
- One avatar per user — new upload overwrites previous file
- No CDN or cloud storage — local filesystem only
- `uploads/` directory is gitignored

## Files Changed

| File | Change |
|------|--------|
| `db.py` | Add `avatar_url` column migration + `update_user_avatar()` |
| `api/main.py` | Mount `/uploads/avatars` StaticFiles |
| `api/routers/auth.py` | Add `POST /api/auth/avatar` endpoint; include `avatar_url` in all user responses |
| `frontend/src/types/auth.ts` | Add `avatar_url?: string` |
| `frontend/src/api/client.ts` | Add `uploadAvatar()` |
| `frontend/src/store/authStore.ts` | Add `updateAvatar()` + `isUploadingAvatar` |
| `frontend/src/pages/SettingsPage.tsx` | Avatar preview + file picker in Profile tab |
| `frontend/src/components/UserMenu.tsx` | Show avatar image with initials fallback |
