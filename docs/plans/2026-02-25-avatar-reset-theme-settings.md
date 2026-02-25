# Avatar Reset & Theme Toggle in Settings — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users remove their profile photo (reverting to the initials avatar) and move the dark/light theme toggle from the top nav into Settings > Preferences.

**Architecture:** Backend gets a new `DELETE /api/auth/avatar` endpoint that deletes the file from disk and NULLs the DB column. Frontend adds `deleteAvatar()` to the client, a `removeAvatar()` action to authStore, a "Remove photo" link in the Profile tab, and a two-button Appearance toggle in the Preferences tab. The Sun/Moon nav button is removed.

**Tech Stack:** FastAPI, SQLite (via `db.py`), React 18, TypeScript, Zustand, Tailwind CSS, CSS variables.

---

### Task 1: Add `clear_user_avatar` DB helper

**Files:**
- Modify: `db.py:165-177`

**Step 1: Add the helper directly after `update_user_avatar`**

In `db.py`, after the closing of `update_user_avatar` (around line 177), add:

```python
def clear_user_avatar(user_id: str) -> Optional[dict]:
    """Set avatar_url to NULL for user. Returns updated user dict."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET avatar_url = NULL WHERE id = ?",
        (user_id,)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
```

**Step 2: Verify the function is importable**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -c "import db; print(hasattr(db, 'clear_user_avatar'))"
```
Expected: `True`

**Step 3: Commit**

```bash
git add db.py
git commit -m "feat: add clear_user_avatar db helper"
```

---

### Task 2: Add `DELETE /api/auth/avatar` endpoint

**Files:**
- Modify: `api/routers/auth.py`

**Step 1: Import `clear_user_avatar` in auth.py**

At the top of `api/routers/auth.py`, the existing import reads:
```python
from ..auth_utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
```
No change needed there — `clear_user_avatar` is imported from `db` which is already imported as `import db`.

**Step 2: Add the endpoint after `upload_avatar` (after line 161)**

```python
@router.delete("/avatar", status_code=200)
async def delete_avatar(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # Delete all avatar files for this user from disk
    for old in _AVATAR_DIR.glob(f"{user_id}.*"):
        old.unlink(missing_ok=True)

    updated = db.clear_user_avatar(user_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update user")

    return {
        "id": updated["id"],
        "email": updated["email"],
        "username": updated["username"],
        "created_at": updated["created_at"],
        "role": updated.get("role", "user"),
        "avatar_url": updated.get("avatar_url"),
    }
```

**Step 3: Verify the server starts without errors**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -c "from api.routers.auth import router; print('OK')"
```
Expected: `OK`

**Step 4: Commit**

```bash
git add api/routers/auth.py
git commit -m "feat: add DELETE /api/auth/avatar endpoint to reset avatar"
```

---

### Task 3: Add `deleteAvatar` to API client

**Files:**
- Modify: `frontend/src/api/client.ts:235-248`

**Step 1: Add `deleteAvatar` after `uploadAvatar` (after line 248)**

```typescript
export async function deleteAvatar(): Promise<AuthUser> {
  const r = await fetch(`${API_BASE}/auth/avatar`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Failed to remove avatar')
  }
  return r.json()
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add deleteAvatar api client function"
```

---

### Task 4: Add `removeAvatar` action to authStore

**Files:**
- Modify: `frontend/src/store/authStore.ts`

**Step 1: Add `removeAvatar` to the interface**

In `authStore.ts`, the `AuthStore` interface currently ends with `updateAvatar`. Add after it:

```typescript
removeAvatar: () => Promise<void>
```

**Step 2: Import `deleteAvatar` at the top**

The existing import block in `authStore.ts` reads:
```typescript
import {
  authLogin,
  authRegister,
  authGetMe,
  uploadAvatar,
  setAuthToken,
  clearAuthToken,
  getAuthToken,
} from '../api/client'
```

Add `deleteAvatar` to that import:
```typescript
import {
  authLogin,
  authRegister,
  authGetMe,
  uploadAvatar,
  deleteAvatar,
  setAuthToken,
  clearAuthToken,
  getAuthToken,
} from '../api/client'
```

**Step 3: Add `removeAvatar` action in the store body, after `updateAvatar`**

```typescript
removeAvatar: async () => {
  set({ isUploadingAvatar: true, error: null })
  try {
    const updated = await deleteAvatar()
    set((state) => ({
      user: state.user ? { ...state.user, avatar_url: updated.avatar_url } : null,
      isUploadingAvatar: false,
    }))
  } catch (err) {
    set({ isUploadingAvatar: false })
    throw err
  }
},
```

**Step 4: Commit**

```bash
git add frontend/src/store/authStore.ts
git commit -m "feat: add removeAvatar action to authStore"
```

---

### Task 5: Add "Remove photo" link in SettingsPage Profile tab

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Step 1: Pull `removeAvatar` from the store**

In `SettingsPage.tsx`, the destructure currently reads:
```typescript
const { user, updateAvatar, isUploadingAvatar } = useAuthStore()
```

Change to:
```typescript
const { user, updateAvatar, removeAvatar, isUploadingAvatar } = useAuthStore()
```

**Step 2: Add the "Remove photo" button below "Change photo"**

Currently the button section in the Profile tab avatar area reads:
```tsx
<button
  onClick={() => fileInputRef.current?.click()}
  disabled={isUploadingAvatar}
  className="text-xs text-accent hover:text-accent/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
>
  {isUploadingAvatar ? 'Uploading…' : 'Change photo'}
</button>
<p className="text-xs text-text-muted">JPEG, PNG, or WebP · max 2MB</p>
```

Replace with:
```tsx
<button
  onClick={() => fileInputRef.current?.click()}
  disabled={isUploadingAvatar}
  className="text-xs text-accent hover:text-accent/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
>
  {isUploadingAvatar ? 'Uploading…' : 'Change photo'}
</button>
{user.avatar_url && (
  <button
    onClick={async () => {
      setUploadError(null)
      try {
        await removeAvatar()
      } catch (err) {
        setUploadError((err as Error).message)
      }
    }}
    disabled={isUploadingAvatar}
    className="text-xs text-text-muted hover:text-accent-danger transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
  >
    {isUploadingAvatar ? 'Removing…' : 'Remove photo'}
  </button>
)}
<p className="text-xs text-text-muted">JPEG, PNG, or WebP · max 2MB</p>
```

**Step 3: Verify the UI compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -5
```
Expected: build output with no TypeScript errors.

**Step 4: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add Remove photo button in Settings profile tab"
```

---

### Task 6: Replace Preferences placeholder with Appearance theme toggle

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Step 1: Import `useThemeStore` at the top of SettingsPage**

Add after the existing imports:
```typescript
import { useThemeStore } from '../store/themeStore'
```

**Step 2: Destructure theme state inside the component**

Inside `SettingsPage()`, after the existing `const { user, ... } = useAuthStore()` line, add:
```typescript
const { theme, toggleTheme } = useThemeStore()
```

**Step 3: Replace the Preferences tab placeholder**

The current Preferences tab body reads:
```tsx
{activeTab === 'preferences' && (
  <div className="card p-6">
    <p className="text-sm text-text-secondary">Preferences and notifications settings coming soon.</p>
  </div>
)}
```

Replace with:
```tsx
{activeTab === 'preferences' && (
  <div className="card p-6 space-y-6">
    <div>
      <label className="block text-xs font-medium text-text-muted mb-1 uppercase tracking-wider">Appearance</label>
      <p className="text-xs text-text-muted mb-3">Choose your preferred color theme</p>
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
        {(['dark', 'light'] as const).map((t) => (
          <button
            key={t}
            onClick={() => { if (theme !== t) toggleTheme() }}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all capitalize ${
              theme === t
                ? 'bg-bg-tertiary text-text-primary shadow-sm'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  </div>
)}
```

**Step 4: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add Appearance theme toggle in Settings Preferences tab"
```

---

### Task 7: Remove Sun/Moon toggle from top nav

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Remove the theme button from the nav**

In `App.tsx`, the auth/theme section of the nav reads:
```tsx
{/* Auth + Theme toggle */}
<div className="flex items-center gap-1">
  <button
    onClick={toggleTheme}
    aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    className="w-9 h-9 flex items-center justify-center rounded-lg transition-all duration-150 text-text-muted hover:text-text-secondary hover:bg-bg-tertiary"
  >
    {theme === 'dark' ? (
      <Sun className="w-4 h-4" />
    ) : (
      <Moon className="w-4 h-4" />
    )}
  </button>
  {isAuthenticated ? (
    <UserMenu />
  ) : (
    <NavLink
      to="/login"
      className="text-sm font-medium text-text-muted hover:text-text-primary transition-colors px-3 py-1.5"
    >
      Sign In
    </NavLink>
  )}
</div>
```

Replace with (button removed, wrapper kept):
```tsx
{/* Auth */}
<div className="flex items-center gap-1">
  {isAuthenticated ? (
    <UserMenu />
  ) : (
    <NavLink
      to="/login"
      className="text-sm font-medium text-text-muted hover:text-text-primary transition-colors px-3 py-1.5"
    >
      Sign In
    </NavLink>
  )}
</div>
```

**Step 2: Remove unused `useThemeStore` destructure and unused icon imports**

The top of `App.tsx` currently has:
```typescript
const { theme, toggleTheme } = useThemeStore()
```
Remove `theme` and `toggleTheme` from the destructure (or remove the whole line if `useThemeStore` is no longer used).

Also remove `Sun` and `Moon` from the lucide-react import line:
```typescript
import { Home, Gamepad2, History, Dice5, FlaskConical, Sun, Moon } from 'lucide-react'
```
becomes:
```typescript
import { Home, Gamepad2, History, Dice5, FlaskConical } from 'lucide-react'
```

If `useThemeStore` is no longer imported anywhere in `App.tsx`, remove its import line too.

**Step 3: Verify the build is clean**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -5
```
Expected: no TypeScript or lint errors.

**Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: remove theme toggle from nav, now lives in Settings"
```

---

### Task 8: Manual smoke test

Start both servers and verify end-to-end:

```bash
# Terminal 1
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
./start_api.sh

# Terminal 2
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run dev
```

Checklist:
- [ ] Log in → top nav has no Sun/Moon button
- [ ] Settings > Preferences → Dark/Light buttons appear; clicking Light switches theme; clicking Dark switches back
- [ ] Settings > Profile → "Change photo" and "Remove photo" both visible when avatar exists
- [ ] Click "Remove photo" → avatar disappears, initials letter shows immediately
- [ ] "Remove photo" link disappears after removal (no avatar_url)
- [ ] Upload a new photo → "Remove photo" reappears
- [ ] Logged-out visitors → no Sun/Moon button, theme stays at last saved value
