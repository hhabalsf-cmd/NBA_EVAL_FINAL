# Profile Picture Upload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let authenticated users upload a profile picture that replaces the initials avatar in the nav and Settings page.

**Architecture:** Images are stored on disk at `uploads/avatars/{user_id}.{ext}`, served via FastAPI `StaticFiles`. An `avatar_url` column is added to the `users` SQLite table using the existing `PRAGMA table_info` auto-migration pattern. The frontend uploads via multipart POST, stores the returned URL in the Zustand auth store, and renders it wherever the user avatar appears.

**Tech Stack:** FastAPI (python-multipart for file upload), SQLite, React 18, TypeScript, Zustand, Tailwind CSS

---

### Task 1: DB — add `avatar_url` column and `update_user_avatar()` helper

**Files:**
- Modify: `db.py`

**Step 1: Write the failing test**

Add to `tests/test_auth.py`, before the existing fixtures:

```python
def test_update_user_avatar_stores_url():
    from db import create_user, update_user_avatar, get_user_by_id
    import uuid
    uid = str(uuid.uuid4())
    create_user(uid, "av@test.com", "hashed", "avuser")
    updated = update_user_avatar(uid, "/uploads/avatars/test.jpg")
    assert updated["avatar_url"] == "/uploads/avatars/test.jpg"
    fetched = get_user_by_id(uid)
    assert fetched["avatar_url"] == "/uploads/avatars/test.jpg"
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
pytest tests/test_auth.py::test_update_user_avatar_stores_url -v
```

Expected: FAIL with `AttributeError: module 'db' has no attribute 'update_user_avatar'`

**Step 3: Add migration + helper in `db.py`**

Inside `init_db()`, after the existing `if "role" not in users_columns:` block, add:

```python
    if "avatar_url" not in users_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
```

After `get_user_by_id()`, add:

```python
def update_user_avatar(user_id: str, avatar_url: str) -> dict:
    """Set avatar_url for user. Returns updated user dict."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET avatar_url = ? WHERE id = ?",
        (avatar_url, user_id)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_auth.py::test_update_user_avatar_stores_url -v
```

Expected: PASS

**Step 5: Run full test suite to confirm no regressions**

```bash
pytest tests/test_auth.py -v
```

Expected: All 9 existing tests + 1 new = 10 PASSED

**Step 6: Commit**

```bash
git add db.py tests/test_auth.py
git commit -m "feat: add avatar_url column to users + update_user_avatar() helper"
```

---

### Task 2: Backend — static file serving + upload endpoint

**Files:**
- Modify: `api/main.py`
- Modify: `api/routers/auth.py`
- Create: `uploads/avatars/.gitkeep`

**Step 1: Write failing tests**

Add to `tests/test_auth.py`:

```python
import io

def _get_token(email="av2@test.com", username="avuser2", password="pw"):
    r = client.post("/api/auth/register", json={
        "email": email, "username": username, "password": password
    })
    return r.json()["token"]


def test_avatar_upload_returns_avatar_url():
    token = _get_token()
    img_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
        b"\xff\xd9"  # minimal valid JPEG bytes
    )
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "avatar_url" in data
    assert data["avatar_url"].startswith("/uploads/avatars/")


def test_avatar_upload_rejects_non_image():
    token = _get_token("av3@test.com", "avuser3")
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("hack.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
    )
    assert r.status_code == 400


def test_avatar_upload_rejects_oversized_file():
    token = _get_token("av4@test.com", "avuser4")
    big = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024 + 1))
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("big.jpg", big, "image/jpeg")},
    )
    assert r.status_code == 413


def test_avatar_upload_requires_auth():
    r = client.post(
        "/api/auth/avatar",
        files={"file": ("x.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
    )
    assert r.status_code in (401, 403)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_auth.py -k "avatar" -v
```

Expected: FAIL — endpoint does not exist yet (404 or import error)

**Step 3: Create uploads directory**

```bash
mkdir -p uploads/avatars
touch uploads/avatars/.gitkeep
```

Add to `.gitignore` (append if not already present):
```
uploads/avatars/*.jpg
uploads/avatars/*.jpeg
uploads/avatars/*.png
uploads/avatars/*.webp
```

**Step 4: Install python-multipart (required for FastAPI file uploads)**

```bash
pip install python-multipart
```

Add `python-multipart>=0.0.9` to `api/requirements.txt`.

**Step 5: Mount static files in `api/main.py`**

Add imports at the top:
```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
```

After the CORS middleware block, before `app.include_router(...)` lines, add:

```python
# Serve uploaded avatars
_UPLOADS_DIR = Path(__file__).parent.parent / "uploads" / "avatars"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/avatars", StaticFiles(directory=str(_UPLOADS_DIR)), name="avatars")
```

**Step 6: Add upload endpoint in `api/routers/auth.py`**

Add imports (merge with existing imports):
```python
import os
from pathlib import Path
from fastapi import File, UploadFile
```

Add the endpoint after the `/me` endpoint:

```python
_AVATAR_DIR = Path(__file__).parent.parent.parent / "uploads" / "avatars"
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


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
    # Remove any old avatar files for this user (different extension)
    for old in _AVATAR_DIR.glob(f"{current_user['id']}.*"):
        old.unlink(missing_ok=True)

    dest = _AVATAR_DIR / filename
    dest.write_bytes(contents)

    avatar_url = f"/uploads/avatars/{filename}"
    updated = db.update_user_avatar(current_user["id"], avatar_url)

    return {
        "id": updated["id"],
        "email": updated["email"],
        "username": updated["username"],
        "created_at": updated["created_at"],
        "role": updated.get("role", "user"),
        "avatar_url": updated.get("avatar_url"),
    }
```

**Step 7: Include `avatar_url` in existing auth responses**

In `api/routers/auth.py`, update the user dict returned by `/register`, `/login`, and `/me` to include `"avatar_url": user.get("avatar_url")`. Each currently returns:
```python
{"id": ..., "email": ..., "username": ..., "created_at": ..., "role": ...}
```
Add `"avatar_url": user.get("avatar_url")` to each of these three dicts.

**Step 8: Run avatar tests**

```bash
pytest tests/test_auth.py -k "avatar" -v
```

Expected: 4 PASSED

**Step 9: Run full suite**

```bash
pytest tests/test_auth.py -v
```

Expected: All 14 PASSED

**Step 10: Commit**

```bash
git add api/main.py api/routers/auth.py api/requirements.txt uploads/avatars/.gitkeep tests/test_auth.py .gitignore
git commit -m "feat: add avatar upload endpoint + static file serving"
```

---

### Task 3: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/auth.ts`
- Modify: `frontend/src/api/client.ts`

**Step 1: Add `avatar_url` to the `User` interface**

In `frontend/src/types/auth.ts`, change:
```typescript
export interface User {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
}
```
to:
```typescript
export interface User {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
  avatar_url?: string
}
```

**Step 2: Add `avatar_url` to `AuthUser` in `client.ts`**

In `frontend/src/api/client.ts`, the `AuthUser` interface at line ~184:
```typescript
export interface AuthUser {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
}
```
Add `avatar_url?: string` as the last field.

**Step 3: Add `uploadAvatar` function to `client.ts`**

After `authGetMe()`, add:

```typescript
export async function uploadAvatar(file: File): Promise<AuthUser> {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${API_BASE}/auth/avatar`, {
    method: 'POST',
    headers: { ...authHeaders() },
    body: form,
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Upload failed')
  }
  return r.json()
}
```

Note: do **not** set `Content-Type` manually — the browser sets it automatically with the correct multipart boundary when using `FormData`.

**Step 4: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors

**Step 5: Commit**

```bash
git add frontend/src/types/auth.ts frontend/src/api/client.ts
git commit -m "feat: add avatar_url to User type and uploadAvatar() client function"
```

---

### Task 4: Auth store — `updateAvatar` action

**Files:**
- Modify: `frontend/src/store/authStore.ts`

**Step 1: Add `isUploadingAvatar` state and `updateAvatar` action**

In `frontend/src/store/authStore.ts`, update the `AuthStore` interface:

```typescript
interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isUploadingAvatar: boolean   // add this
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
  updateAvatar: (file: File) => Promise<void>   // add this
}
```

Add `uploadAvatar` to the imports from `'../api/client'`:
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

In the store initial state, add:
```typescript
  isUploadingAvatar: false,
```

After `clearError`, add:
```typescript
  updateAvatar: async (file) => {
    set({ isUploadingAvatar: true, error: null })
    try {
      const updated = await uploadAvatar(file)
      set((state) => ({
        user: state.user ? { ...state.user, avatar_url: updated.avatar_url } : null,
        isUploadingAvatar: false,
      }))
    } catch (err) {
      set({ error: (err as Error).message, isUploadingAvatar: false })
    }
  },
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -20
```

Expected: no errors

**Step 3: Commit**

```bash
git add frontend/src/store/authStore.ts
git commit -m "feat: add updateAvatar action to authStore"
```

---

### Task 5: SettingsPage — avatar upload UI

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Step 1: Replace the Profile tab stub with upload UI**

Replace the entire `SettingsPage.tsx` content with:

```typescript
import { useRef, useState } from 'react'
import { User, SlidersHorizontal, Camera } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

type Tab = 'profile' | 'preferences'

const MAX_BYTES = 2 * 1024 * 1024
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { user, updateAvatar, isUploadingAvatar } = useAuthStore()

  if (!user) return null

  const initial = user.username.charAt(0).toUpperCase()

  const tabs: { id: Tab; label: string; icon: typeof User }[] = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'preferences', label: 'Preferences', icon: SlidersHorizontal },
  ]

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)

    if (!ALLOWED_TYPES.includes(file.type)) {
      setUploadError('Only JPEG, PNG, and WebP images are allowed.')
      return
    }
    if (file.size > MAX_BYTES) {
      setUploadError('Image must be 2MB or smaller.')
      return
    }

    await updateAvatar(file)
    // Reset input so re-selecting the same file still triggers onChange
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold text-text-primary tracking-tight">Settings</h1>

      {/* Tabs */}
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-md transition-all flex-1 justify-center ${
                activeTab === tab.id
                  ? 'bg-bg-tertiary text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          )
        })}
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="card p-6 space-y-6">

          {/* Avatar */}
          <div className="flex items-center gap-5">
            <div className="relative group">
              {user.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={user.username}
                  className="w-20 h-20 rounded-full object-cover ring-2 ring-border-subtle"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-accent/15 text-accent text-2xl font-semibold flex items-center justify-center ring-2 ring-border-subtle">
                  {initial}
                </div>
              )}
              {/* Overlay on hover */}
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingAvatar}
                className="absolute inset-0 rounded-full bg-black/50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity disabled:cursor-not-allowed"
                aria-label="Change profile photo"
              >
                <Camera className="w-6 h-6 text-white" />
              </button>
            </div>

            <div className="space-y-1.5">
              <p className="text-sm font-medium text-text-primary">{user.username}</p>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingAvatar}
                className="text-xs text-accent hover:text-accent/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isUploadingAvatar ? 'Uploading…' : 'Change photo'}
              </button>
              <p className="text-xs text-text-muted">JPEG, PNG, or WebP · max 2MB</p>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          {uploadError && (
            <p className="text-xs text-accent-danger">{uploadError}</p>
          )}

          {/* Read-only fields */}
          <div>
            <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Username</label>
            <input type="text" value={user.username} readOnly className="w-full opacity-50 cursor-not-allowed" />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Email</label>
            <input type="email" value={user.email} readOnly className="w-full opacity-50 cursor-not-allowed" />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Member since</label>
            <p className="text-sm text-text-secondary">
              {new Date(user.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="card p-6">
          <p className="text-sm text-text-secondary">Preferences and notifications settings coming soon.</p>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -20
```

Expected: no errors

**Step 3: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add profile photo upload UI to SettingsPage"
```

---

### Task 6: UserMenu — show avatar image

**Files:**
- Modify: `frontend/src/components/UserMenu.tsx`

**Step 1: Replace initials button with avatar-aware button**

Replace the `UserMenu.tsx` content with:

```typescript
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Settings, LogOut } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

export default function UserMenu() {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  if (!user) return null

  const initial = user.username.charAt(0).toUpperCase()

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-8 h-8 rounded-full overflow-hidden hover:ring-2 hover:ring-accent/40 transition-all"
        aria-label="User menu"
      >
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={user.username}
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="w-full h-full bg-accent/15 text-accent text-sm font-semibold flex items-center justify-center">
            {initial}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-bg-tertiary border border-border-subtle rounded-xl shadow-xl shadow-black/30 overflow-hidden animate-slide-up z-50">
          <div className="p-4 border-b border-border-subtle flex items-center gap-3">
            <div className="w-9 h-9 rounded-full overflow-hidden flex-shrink-0">
              {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.username} className="w-full h-full object-cover" />
              ) : (
                <span className="w-full h-full bg-accent/15 text-accent text-sm font-semibold flex items-center justify-center">
                  {initial}
                </span>
              )}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-text-primary truncate">{user.username}</div>
              <div className="text-xs text-text-muted truncate">{user.email}</div>
            </div>
          </div>
          <div className="py-1">
            <button
              onClick={() => { navigate('/settings'); setIsOpen(false) }}
              className="w-full px-4 py-2.5 text-left text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors flex items-center gap-2.5"
            >
              <Settings className="w-3.5 h-3.5" />
              Settings
            </button>
            <button
              onClick={() => { logout(); setIsOpen(false); navigate('/') }}
              className="w-full px-4 py-2.5 text-left text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors flex items-center gap-2.5"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -20
```

Expected: no errors

**Step 3: Lint check**

```bash
npm run lint 2>&1 | tail -20
```

Expected: no errors

**Step 4: Commit**

```bash
git add frontend/src/components/UserMenu.tsx
git commit -m "feat: show avatar image in UserMenu with initials fallback"
```

---

### Task 7: Manual smoke test

**Step 1: Start both servers**

Terminal 1:
```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
./start_api.sh
```

Terminal 2:
```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run dev
```

**Step 2: Test the flow**

1. Open http://localhost:5173
2. Log in with an existing account (or register one)
3. Click the initials avatar in the nav → confirm menu opens
4. Click **Settings**
5. On the Profile tab, confirm the avatar circle shows with initials and a "Change photo" button
6. Click "Change photo" → pick a JPEG/PNG under 2MB
7. Confirm: spinner shows during upload, then avatar updates instantly in both the Settings page and the nav button
8. Refresh the page — avatar should persist (comes from `checkAuth` → `/me` → `avatar_url`)
9. Try uploading a `.exe` or PDF — confirm you see "Only JPEG, PNG, and WebP images are allowed."
10. Try uploading a file over 2MB — confirm "Image must be 2MB or smaller."
