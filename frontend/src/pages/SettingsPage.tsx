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

    try {
      await updateAvatar(file)
    } catch (err) {
      setUploadError((err as Error).message)
    }
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
