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
