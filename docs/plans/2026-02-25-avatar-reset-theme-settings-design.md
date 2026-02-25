# Design: Avatar Reset & Theme Toggle in Settings

**Date:** 2026-02-25
**Status:** Approved

---

## Overview

Two small UX improvements:
1. Allow users to remove their profile photo and revert to the initials avatar.
2. Move the dark/light theme toggle out of the top nav and into Settings > Preferences.

---

## Feature 1 — Reset Avatar to Initials

### Backend

**New DB helper — `db.py`**
- `clear_user_avatar(user_id: str) -> Optional[dict]`: sets `avatar_url = NULL` for the user and returns the updated user row.

**New endpoint — `api/routers/auth.py`**
- `DELETE /api/auth/avatar`
- Requires Bearer token (`get_current_user` dependency).
- Deletes all files matching `uploads/avatars/{user_id}.*` from disk.
- Calls `db.clear_user_avatar(user_id)`.
- Returns updated user object (same shape as `/api/auth/me`).

### Frontend

**`api/client.ts`**
- Add `deleteAvatar(): Promise<User>` — calls `DELETE /api/auth/avatar` with Bearer token.

**`authStore.ts`**
- Add `removeAvatar(): Promise<void>` action — calls `deleteAvatar()`, sets `user.avatar_url = null` in store state.
- Reuses `isUploadingAvatar` flag for loading state.

**`SettingsPage.tsx` — Profile tab**
- Add a **"Remove photo"** text link below "Change photo".
- Only renders when `user.avatar_url` is truthy.
- Disabled and shows "Removing…" while `isUploadingAvatar` is true.
- On click: calls `removeAvatar()`, catches and surfaces errors via `setUploadError`.

---

## Feature 2 — Theme Toggle in Settings

### `App.tsx`
- Remove the Sun/Moon icon button and all `theme`/`toggleTheme` references from the top nav.

### `SettingsPage.tsx` — Preferences tab
- Replace "coming soon" placeholder with an **Appearance** row:
  - Label: "Appearance" (small uppercase muted label, consistent with Profile tab field labels)
  - Description: "Choose your preferred color theme"
  - Two-button pill toggle: **Dark** | **Light**
    - Active button: `bg-bg-tertiary text-text-primary`
    - Inactive button: `text-text-muted hover:text-text-secondary`
  - Uses `useThemeStore` — clicking a button calls `toggleTheme()` only if switching.

---

## Files Changed

| File | Change |
|------|--------|
| `db.py` | Add `clear_user_avatar()` |
| `api/routers/auth.py` | Add `DELETE /api/auth/avatar` endpoint |
| `frontend/src/api/client.ts` | Add `deleteAvatar()` |
| `frontend/src/store/authStore.ts` | Add `removeAvatar()` action |
| `frontend/src/pages/SettingsPage.tsx` | Add remove-photo link; add Appearance toggle in Preferences |
| `frontend/src/App.tsx` | Remove Sun/Moon theme toggle button |

---

## Out of Scope
- Password change
- Email change
- Notification preferences
- Three-way Dark/Light/System theme
