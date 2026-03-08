import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { User, SlidersHorizontal, Camera, History, ChevronRight, TrendingUp } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useThemeStore } from '../store/themeStore'
import AvatarCropModal from '../components/AvatarCropModal'

type Tab = 'profile' | 'preferences'

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [cropImageSrc, setCropImageSrc] = useState<string | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwError, setPwError] = useState<string | null>(null)
  const [pwSuccess, setPwSuccess] = useState(false)
  const [isChangingPw, setIsChangingPw] = useState(false)
  const { user, updateAvatar, removeAvatar, isUploadingAvatar, changePassword } = useAuthStore()
  const { theme, toggleTheme } = useThemeStore()

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
                Change photo
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
                  className="text-xs text-text-muted hover:text-accent-danger transition-colors disabled:opacity-50 disabled:cursor-not-allowed ml-2"
                >
                  {isUploadingAvatar ? 'Removing…' : 'Remove photo'}
                </button>
              )}
              <p className="text-xs text-text-muted">JPEG, PNG, or WebP</p>
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
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="space-y-4">
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

          {/* Pick History Card */}
          <Link
            to="/history"
            className="card p-5 flex items-center gap-4 group transition-all duration-150 hover:border-border-accent"
            style={{ display: 'flex', textDecoration: 'none' }}
          >
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors duration-150"
              style={{ background: 'var(--accent-muted)' }}
            >
              <History className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Pick History
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                View past picks, profits, and performance trends
              </p>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <TrendingUp className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--accent)' }} />
              <ChevronRight className="w-4 h-4 transition-transform duration-150 group-hover:translate-x-0.5" style={{ color: 'var(--text-muted)' }} />
            </div>
          </Link>
        </div>
      )}
      {cropImageSrc && (
        <AvatarCropModal
          imageSrc={cropImageSrc}
          onApply={handleCropApply}
          onCancel={handleCropCancel}
          isUploading={isUploadingAvatar}
        />
      )}
    </div>
  )
}
