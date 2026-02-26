# Design: Avatar Crop Modal, No Size Limit, Remove Photo Spacing

**Date:** 2026-02-25
**Status:** Approved

---

## Overview

Three improvements to the avatar upload flow in Settings > Profile:
1. Indent "Remove photo" slightly to the right of "Change photo"
2. Remove the 2MB file size restriction (keep type validation)
3. Add a circular crop modal (via `react-easy-crop`) between file selection and upload

---

## Feature 1 — "Remove photo" Spacing

Add `ml-2` to the "Remove photo" button className in `frontend/src/pages/SettingsPage.tsx`. This indents it visually beneath "Change photo", signalling it's a secondary/destructive action rather than a peer action.

---

## Feature 2 — Remove File Size Limit

**Frontend — `frontend/src/pages/SettingsPage.tsx`:**
- Remove the `MAX_BYTES` constant
- Remove the `if (file.size > MAX_BYTES)` guard and its error
- Update the hint text from `"JPEG, PNG, or WebP · max 2MB"` to `"JPEG, PNG, or WebP"`

**Backend — `api/routers/auth.py`:**
- Remove the `_MAX_BYTES` constant
- Remove the `len(contents) > _MAX_BYTES` / HTTP 413 check
- Keep `_ALLOWED_TYPES` and content-type validation

---

## Feature 3 — Circular Crop Modal

### Library
`react-easy-crop` — install via `npm install react-easy-crop` in `frontend/`.

### New component — `frontend/src/components/AvatarCropModal.tsx`

**Props:**
```typescript
interface AvatarCropModalProps {
  imageSrc: string          // object URL of the selected file
  onApply: (file: File) => void
  onCancel: () => void
  isUploading: boolean
}
```

**Internals:**
- `Cropper` from `react-easy-crop` with:
  - `cropShape="round"`, `aspect={1}`, `showGrid={false}`
  - `zoom` state (1–3), `crop` state `{x:0, y:0}`
  - `onCropChange` / `onZoomChange` / `onCropComplete` handlers
- `croppedAreaPixels` stored in state via `onCropComplete`
- Canvas helper `getCroppedBlob(imageSrc, croppedAreaPixels)`:
  - Creates an `<img>` from `imageSrc`
  - Draws the cropped region onto a `canvas` using `drawImage`
  - Returns `canvas.toBlob(...)` as `image/jpeg` at quality 0.9
  - Returns a `File` named `avatar.jpg`

**Layout:**
- Fixed full-screen overlay: `fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-center`
- Crop area container: `relative w-80 h-80` (or `w-72 h-72` on mobile)
- Bottom action bar: `flex gap-3 mt-6` with **Cancel** (muted) and **Apply** (accent, disabled + "Uploading…" while `isUploading`)

### SettingsPage changes — `frontend/src/pages/SettingsPage.tsx`

**New state:**
```typescript
const [cropImageSrc, setCropImageSrc] = useState<string | null>(null)
```

**Modified `handleFileChange`:**
- Remove size check (Feature 2)
- On valid file: `URL.createObjectURL(file)` → `setCropImageSrc(src)` (opens modal)
- Do NOT call `updateAvatar` here — that moves to the modal's `onApply`

**New `handleCropApply(file: File)`:**
```typescript
async function handleCropApply(file: File) {
  setUploadError(null)
  try {
    await updateAvatar(file)
  } catch (err) {
    setUploadError((err as Error).message)
  } finally {
    setCropImageSrc(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }
}
```

**New `handleCropCancel()`:**
```typescript
function handleCropCancel() {
  setCropImageSrc(null)
  if (fileInputRef.current) fileInputRef.current.value = ''
}
```

**Render:**
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

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/package.json` | Add `react-easy-crop` dependency |
| `frontend/src/components/AvatarCropModal.tsx` | New component |
| `frontend/src/pages/SettingsPage.tsx` | Spacing, remove size limit, crop modal wiring |
| `api/routers/auth.py` | Remove `_MAX_BYTES` and size check |

---

## Out of Scope
- Zoom slider UI (scroll/pinch is sufficient)
- Crop for other images (only avatar)
- Server-side image resizing
