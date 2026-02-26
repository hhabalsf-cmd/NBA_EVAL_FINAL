# Change Password — Design

**Date:** 2026-02-26
**Status:** Approved

## Context

Users currently have no way to change their password after registering. The Settings page (Profile tab) already shows read-only account fields; password change belongs there as a natural extension.

## Layers

### 1. Database — `db.py`
Add `update_user_password(user_id: str, hashed_password: str) -> None`.
Simple `UPDATE users SET hashed_password = ? WHERE id = ?`.

### 2. API — `api/routers/auth.py`
Add `POST /api/auth/change-password`.
- Requires Bearer token (`get_current_user` dependency)
- Request body: `{ current_password: str, new_password: str }`
- Verifies current password with `verify_password` against stored hash — raises `401` if wrong
- Hashes new password with `hash_password`, calls `db.update_user_password`
- Returns `204 No Content`

### 3. API Client — `frontend/src/api/client.ts`
Add `changePassword(currentPassword: string, newPassword: string): Promise<void>`.
`POST /api/auth/change-password` with Bearer token.

### 4. Auth Store — `frontend/src/store/authStore.ts`
Add `changePassword(currentPassword: string, newPassword: string): Promise<void>` action.
Calls `changePassword` from api client; throws on error so the UI can catch it.

### 5. UI — `frontend/src/pages/SettingsPage.tsx`
Add a "Change Password" section at the bottom of the Profile tab card, separated by a divider.
Local state: `currentPassword`, `newPassword`, `confirmPassword`, `pwError`, `pwSuccess`, `isChangingPw`.

**Fields:** Current password / New password / Confirm new password (all `type="password"`)
**Button:** "Update Password" — disabled while submitting
**Validation (client-side):**
- New password must not be empty
- New password must match confirm
- Min 8 characters

**On success:** clear all three fields, show green "Password updated." message (auto-clears after 3 s)
**On error:**
- API 401 → "Current password is incorrect."
- Confirm mismatch → "Passwords don't match." (before API call)
- Other → "Something went wrong. Please try again."
