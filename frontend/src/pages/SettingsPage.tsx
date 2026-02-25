import { useState } from 'react'
import { User, SlidersHorizontal } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

type Tab = 'profile' | 'preferences'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const { user } = useAuthStore()

  if (!user) return null

  const tabs: { id: Tab; label: string; icon: typeof User }[] = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'preferences', label: 'Preferences', icon: SlidersHorizontal },
  ]

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
        <div className="card p-6 space-y-5">
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
          <p className="text-xs text-text-muted pt-2">Profile editing coming soon.</p>
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
