# Change Password Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let authenticated users change their password from the Profile tab in Settings.

**Architecture:** 4-layer change — db helper → FastAPI endpoint → API client function → Zustand store action — then wire up an inline form in SettingsPage's Profile tab. Backend is tested with pytest against a temp SQLite DB (matches the existing test_auth.py pattern). No new files needed on the frontend.

**Tech Stack:** Python/FastAPI, SQLite (via `db.py`), pytest, React 18, TypeScript, Zustand 4, Tailwind CSS (CSS vars via `var(--x)`)

---

### Task 1: DB helper — `db.update_user_password`

**Files:**
- Modify: `db.py`

**Step 1: Write the failing test**

Add to `tests/test_auth.py` (after the last test):

```python
def test_update_user_password_changes_hash():
    import db as _db
    from api.auth_utils import hash_password, verify_password
    # create a user directly
    user = _db.create_user("uid-pw", "pw@test.com", hash_password("old"), "pwuser")
    _db.update_user_password("uid-pw", hash_password("new"))
    refreshed = _db.get_user_by_id("uid-pw")
    assert verify_password("new", refreshed["hashed_password"])
    assert not verify_password("old", refreshed["hashed_password"])
```

**Step 2: Run to verify it fails**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
pytest tests/test_auth.py::test_update_user_password_changes_hash -v
```

Expected: `AttributeError: module 'db' has no attribute 'update_user_password'`

**Step 3: Implement in `db.py`**

Find the `update_user_avatar` function (around line 165) and add the new function directly after it:

```python
def update_user_password(user_id: str, hashed_password: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE users SET hashed_password = ? WHERE id = ?",
        (hashed_password, user_id),
    )
    conn.commit()
    conn.close()
```

**Step 4: Run to verify it passes**

```bash
pytest tests/test_auth.py::test_update_user_password_changes_hash -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add db.py tests/test_auth.py
git commit -m "feat: add db.update_user_password helper"
```

---

### Task 2: API endpoint — `POST /api/auth/change-password`

**Files:**
- Modify: `api/routers/auth.py`

**Step 1: Write the failing tests**

Add to `tests/test_auth.py`:

```python
def _register_and_token(email="cp@test.com", pw="oldpass"):
    r = client.post("/api/auth/register", json={
        "email": email, "username": "cpuser", "password": pw
    })
    return r.json()["token"]


def test_change_password_success():
    token = _register_and_token()
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204
    # Old token still valid (we don't invalidate), but new password works for login
    r2 = client.post("/api/auth/login", json={"email": "cp@test.com", "password": "newpass123"})
    assert r2.status_code == 200


def test_change_password_wrong_current_returns_401():
    token = _register_and_token("cp2@test.com", "correct")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "anything"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


def test_change_password_unauthenticated_returns_403():
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "y"},
    )
    assert r.status_code in (401, 403)
```

**Step 2: Run to verify they fail**

```bash
pytest tests/test_auth.py::test_change_password_success tests/test_auth.py::test_change_password_wrong_current_returns_401 tests/test_auth.py::test_change_password_unauthenticated_returns_403 -v
```

Expected: all three `FAILED` — `404 Not Found`

**Step 3: Add schema + endpoint to `api/routers/auth.py`**

After the `LoginRequest` schema (around line 38), add:

```python
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
```

After the `delete_avatar` endpoint (end of file), add:

```python
@router.post("/change-password", status_code=204)
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    if not verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    db.update_user_password(current_user["id"], hash_password(req.new_password))
```

**Step 4: Run to verify they pass**

```bash
pytest tests/test_auth.py::test_change_password_success tests/test_auth.py::test_change_password_wrong_current_returns_401 tests/test_auth.py::test_change_password_unauthenticated_returns_403 -v
```

Expected: all three `PASSED`

**Step 5: Run the full test suite to check no regressions**

```bash
pytest tests/test_auth.py -v
```

Expected: all tests pass

**Step 6: Commit**

```bash
git add api/routers/auth.py tests/test_auth.py
git commit -m "feat: add POST /api/auth/change-password endpoint"
```

---

### Task 3: Frontend API client function

**Files:**
- Modify: `frontend/src/api/client.ts`

**Step 1: Add the function**

After the `deleteAvatar` function (around line 259), add:

```typescript
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const r = await fetch(`${API_BASE}/auth/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail || 'Failed to change password')
  }
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -5
```

Expected: build succeeds (or only pre-existing warnings)

**Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add changePassword API client function"
```

---

### Task 4: Zustand store action

**Files:**
- Modify: `frontend/src/store/authStore.ts`

**Step 1: Add the action to the interface**

In the `AuthStore` interface (around line 14), add after `removeAvatar`:

```typescript
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
```

**Step 2: Add the import**

At the top of the file, add `changePassword` to the import from `'../api/client'`:

```typescript
import {
  authLogin,
  authRegister,
  authGetMe,
  uploadAvatar,
  deleteAvatar,
  changePassword,    // add this
  setAuthToken,
  clearAuthToken,
  getAuthToken,
} from '../api/client'
```

**Step 3: Add the implementation**

After the `removeAvatar` action (around line 103), add:

```typescript
  changePassword: async (currentPassword, newPassword) => {
    await changePassword(currentPassword, newPassword)
  },
```

**Step 4: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -5
```

Expected: clean build

**Step 5: Commit**

```bash
git add frontend/src/store/authStore.ts
git commit -m "feat: add changePassword action to authStore"
```

---

### Task 5: SettingsPage — password change form

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Step 1: Add local state**

At the top of the `SettingsPage` component, after the existing `useState` declarations (around line 13), add:

```typescript
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwError, setPwError] = useState<string | null>(null)
  const [pwSuccess, setPwSuccess] = useState(false)
  const [isChangingPw, setIsChangingPw] = useState(false)
```

**Step 2: Add the `changePassword` action to the destructure**

Change the `useAuthStore` destructure (line 16) to include it:

```typescript
  const { user, updateAvatar, removeAvatar, isUploadingAvatar, changePassword } = useAuthStore()
```

**Step 3: Add the submit handler**

After the `handleCropCancel` function (around line 59), add:

```typescript
  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault()
    setPwError(null)
    setPwSuccess(false)

    if (!newPassword) { setPwError("New password can't be empty."); return }
    if (newPassword !== confirmPassword) { setPwError("Passwords don't match."); return }
    if (newPassword.length < 8) { setPwError('Password must be at least 8 characters.'); return }

    setIsChangingPw(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPwSuccess(true)
      setTimeout(() => setPwSuccess(false), 3000)
    } catch (err) {
      setPwError((err as Error).message)
    } finally {
      setIsChangingPw(false)
    }
  }
```

**Step 4: Add the form to the Profile tab card**

Inside the Profile tab's `<div className="card p-6 space-y-6">`, after the closing `</div>` of the "Member since" field (around line 169), add:

```tsx
          <hr className="border-border-subtle" />

          <div>
            <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-4">Change Password</p>
            <form onSubmit={handleChangePassword} className="space-y-3">
              <div>
                <label className="block text-xs text-text-muted mb-1">Current password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-xs text-text-muted mb-1">New password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-xs text-text-muted mb-1">Confirm new password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full"
                />
              </div>

              {pwError && <p className="text-xs text-accent-danger">{pwError}</p>}
              {pwSuccess && <p className="text-xs text-accent-success">Password updated.</p>}

              <button
                type="submit"
                disabled={isChangingPw}
                className="btn-primary text-sm px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isChangingPw ? 'Updating…' : 'Update Password'}
              </button>
            </form>
          </div>
```

**Step 5: Verify TypeScript compiles and dev server runs**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm run build 2>&1 | tail -10
```

Expected: clean build

**Step 6: Manual smoke test**

1. Start both servers: `./start_api.sh` + `cd frontend && npm run dev`
2. Log in at `http://localhost:5173`
3. Go to Settings → Profile tab — "Change Password" section should be visible below "Member since"
4. Try submitting with wrong current password → should show "Current password is incorrect"
5. Try submitting with mismatched new/confirm → should show "Passwords don't match."
6. Submit with correct current + matching new → should show green "Password updated." for 3 s, fields clear
7. Log out and log back in with the new password → should work

**Step 7: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add change password form to Settings Profile tab"
```
