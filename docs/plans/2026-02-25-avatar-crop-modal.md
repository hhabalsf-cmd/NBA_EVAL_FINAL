# Avatar Crop Modal, No Size Limit, Remove Photo Spacing — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a circular crop modal after file selection, remove the 2MB upload limit, and add a small left indent to the "Remove photo" button.

**Architecture:** `react-easy-crop` renders a drag/zoom crop UI in a full-screen modal. On Apply, a canvas helper extracts the cropped region as a JPEG Blob and passes it as a `File` to the existing `updateAvatar` action. The file size check is removed from both frontend validation and the FastAPI upload endpoint.

**Tech Stack:** React 18, TypeScript, `react-easy-crop`, HTML Canvas API, FastAPI, Tailwind CSS (CSS variables only).

---

### Task 1: Install react-easy-crop

**Files:**
- Modify: `frontend/package.json` (via npm)

**Step 1: Install the package**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npm install react-easy-crop
```

Expected: package added to `node_modules` and `package.json` dependencies.

**Step 2: Verify the types are available**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npx tsc --noEmit 2>&1 | grep -i "easy-crop" | head -5
```

Expected: no output (the package ships its own types).

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: install react-easy-crop"
```

---

### Task 2: Create AvatarCropModal component

**Files:**
- Create: `frontend/src/components/AvatarCropModal.tsx`

**Step 1: Create the file with this exact content**

```tsx
import { useState, useCallback } from 'react'
import Cropper, { Area } from 'react-easy-crop'

interface AvatarCropModalProps {
  imageSrc: string
  onApply: (file: File) => void
  onCancel: () => void
  isUploading: boolean
}

async function getCroppedBlob(imageSrc: string, croppedAreaPixels: Area): Promise<File> {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image()
    img.addEventListener('load', () => resolve(img))
    img.addEventListener('error', reject)
    img.src = imageSrc
  })

  const canvas = document.createElement('canvas')
  canvas.width = croppedAreaPixels.width
  canvas.height = croppedAreaPixels.height
  const ctx = canvas.getContext('2d')!

  ctx.drawImage(
    image,
    croppedAreaPixels.x,
    croppedAreaPixels.y,
    croppedAreaPixels.width,
    croppedAreaPixels.height,
    0,
    0,
    croppedAreaPixels.width,
    croppedAreaPixels.height,
  )

  return new Promise<File>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) { reject(new Error('Canvas toBlob failed')); return }
        resolve(new File([blob], 'avatar.jpg', { type: 'image/jpeg' }))
      },
      'image/jpeg',
      0.9,
    )
  })
}

export default function AvatarCropModal({ imageSrc, onApply, onCancel, isUploading }: AvatarCropModalProps) {
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null)

  const onCropComplete = useCallback((_: Area, pixels: Area) => {
    setCroppedAreaPixels(pixels)
  }, [])

  async function handleApply() {
    if (!croppedAreaPixels) return
    const file = await getCroppedBlob(imageSrc, croppedAreaPixels)
    onApply(file)
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80">
      <div className="relative w-72 h-72 sm:w-80 sm:h-80">
        <Cropper
          image={imageSrc}
          crop={crop}
          zoom={zoom}
          aspect={1}
          cropShape="round"
          showGrid={false}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onCropComplete={onCropComplete}
        />
      </div>
      <p className="mt-4 text-xs text-text-muted">Scroll or pinch to zoom · Drag to reposition</p>
      <div className="flex gap-3 mt-4">
        <button
          onClick={onCancel}
          disabled={isUploading}
          className="px-5 py-2 text-sm font-medium rounded-lg text-text-muted hover:text-text-secondary bg-bg-tertiary transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleApply}
          disabled={isUploading || !croppedAreaPixels}
          className="px-5 py-2 text-sm font-medium rounded-lg text-white bg-accent hover:bg-accent/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {isUploading ? 'Uploading…' : 'Apply'}
        </button>
      </div>
    </div>
  )
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npx tsc --noEmit 2>&1 | tail -5
```

Expected: no errors.

**Step 3: Commit**

```bash
git add frontend/src/components/AvatarCropModal.tsx
git commit -m "feat: add AvatarCropModal with react-easy-crop circle crop"
```

---

### Task 3: Wire crop modal into SettingsPage + remove size limit

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

This task does four things in one file: adds crop state, rewires handleFileChange, adds crop handlers, and removes size limit + updates hint text.

**Step 1: Read the file** to confirm current line numbers before editing.

**Step 2: Add `AvatarCropModal` import** — add after the existing imports (after line 4):

```typescript
import AvatarCropModal from '../components/AvatarCropModal'
```

**Step 3: Remove `MAX_BYTES` constant** — delete line 8:
```typescript
const MAX_BYTES = 2 * 1024 * 1024
```

**Step 4: Add `cropImageSrc` state** inside the component, after the existing state declarations (after `const fileInputRef = ...`):

```typescript
const [cropImageSrc, setCropImageSrc] = useState<string | null>(null)
```

**Step 5: Replace `handleFileChange`** — the current function (lines 27-47) directly uploads. Replace the entire function with:

```typescript
async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
  const file = e.target.files?.[0]
  if (!file) return
  setUploadError(null)

  if (!ALLOWED_TYPES.includes(file.type)) {
    setUploadError('Only JPEG, PNG, and WebP images are allowed.')
    return
  }

  const src = URL.createObjectURL(file)
  setCropImageSrc(src)
}

async function handleCropApply(file: File) {
  setUploadError(null)
  try {
    await updateAvatar(file)
  } catch (err) {
    setUploadError((err as Error).message)
  } finally {
    if (cropImageSrc) URL.revokeObjectURL(cropImageSrc)
    setCropImageSrc(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }
}

function handleCropCancel() {
  if (cropImageSrc) URL.revokeObjectURL(cropImageSrc)
  setCropImageSrc(null)
  if (fileInputRef.current) fileInputRef.current.value = ''
}
```

**Step 6: Update the hint text** — find:
```tsx
<p className="text-xs text-text-muted">JPEG, PNG, or WebP · max 2MB</p>
```
Replace with:
```tsx
<p className="text-xs text-text-muted">JPEG, PNG, or WebP</p>
```

**Step 7: Add `ml-2` to "Remove photo" button** — find:
```tsx
className="text-xs text-text-muted hover:text-accent-danger transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
```
Replace with:
```tsx
className="text-xs text-text-muted hover:text-accent-danger transition-colors disabled:opacity-50 disabled:cursor-not-allowed ml-2"
```

**Step 8: Add the modal render** — just before the closing `</div>` of the component (before `</div>` at the bottom), add:

```tsx
{cropImageSrc && (
  <AvatarCropModal
    imageSrc={cropImageSrc}
    onApply={handleCropApply}
    onCancel={handleCropCancel}
    isUploading={isUploadingAvatar}
  />
)}
```

**Step 9: Verify TypeScript compiles**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend
npx tsc --noEmit 2>&1 | tail -5
```

Expected: no errors.

**Step 10: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: wire avatar crop modal, remove size limit, indent Remove photo button"
```

---

### Task 4: Remove file size limit from backend

**Files:**
- Modify: `api/routers/auth.py:23-31`

**Step 1: Remove `_MAX_BYTES` constant** — find and delete:
```python
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
```

**Step 2: Remove the size check** inside `upload_avatar` — find and delete these two lines:
```python
    if len(contents) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large — maximum 2MB")
```

Note: `contents = await file.read()` on the line before must be kept — it's still needed to write the file.

**Step 3: Verify the module imports cleanly**

```bash
cd /Users/hhabal/Downloads/Projects/NBA/EVAL
python -c "from api.routers.auth import router; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add api/routers/auth.py
git commit -m "feat: remove 2MB avatar upload size limit"
```

---

### Task 5: Manual smoke test

Start both servers:

```bash
# Terminal 1
cd /Users/hhabal/Downloads/Projects/NBA/EVAL && ./start_api.sh

# Terminal 2
cd /Users/hhabal/Downloads/Projects/NBA/EVAL/frontend && npm run dev
```

Checklist:
- [ ] Settings > Profile → click "Change photo", select any image → crop modal opens
- [ ] Drag to reposition and scroll to zoom work in the modal
- [ ] Click Apply → modal closes, avatar updates to the cropped circle
- [ ] Upload an image larger than 2MB → works (no size error)
- [ ] Click Cancel → modal closes, avatar unchanged
- [ ] "Remove photo" is indented slightly to the right of "Change photo"
- [ ] Format hint reads "JPEG, PNG, or WebP" (no "max 2MB")
