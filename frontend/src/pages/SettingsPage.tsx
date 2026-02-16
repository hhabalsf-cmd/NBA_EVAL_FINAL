import { useState } from 'react'
import { useAuthStore } from '../store/authStore'
import SubscriptionBadge from '../components/SubscriptionBadge'
import { SUBSCRIPTION_TIERS } from '../types/auth'

type Tab = 'profile' | 'subscription' | 'preferences'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const { user } = useAuthStore()

  if (!user) return null

  const tabs: { id: Tab; label: string }[] = [
    { id: 'profile', label: 'Profile' },
    { id: 'subscription', label: 'Subscription' },
    { id: 'preferences', label: 'Preferences' },
  ]

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-text-primary">Settings</h1>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border-subtle">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-accent text-text-primary'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="card p-5 space-y-4">
          <div>
            <label className="block text-xs text-text-muted mb-1.5">Username</label>
            <input type="text" value={user.username} readOnly className="w-full opacity-60" />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1.5">Email</label>
            <input type="email" value={user.email} readOnly className="w-full opacity-60" />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1.5">Member since</label>
            <p className="text-sm text-text-secondary">
              {new Date(user.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>
          <p className="text-xs text-text-muted">Profile editing coming soon.</p>
        </div>
      )}

      {/* Subscription Tab */}
      {activeTab === 'subscription' && (
        <div className="space-y-4">
          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-text-primary">Current Plan</h3>
              <SubscriptionBadge tier={user.subscription_tier} />
            </div>
            <p className="text-sm text-text-secondary">
              {user.subscription_tier === 'free'
                ? 'Upgrade to unlock unlimited predictions and full history.'
                : `You're on the ${user.subscription_tier} plan.`}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {SUBSCRIPTION_TIERS.map(tier => (
              <div
                key={tier.id}
                className={`card p-4 ${tier.id === user.subscription_tier ? 'border-accent' : ''}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold text-text-primary text-sm">{tier.name}</h4>
                  <span className="font-mono text-sm font-bold text-text-primary">
                    {tier.price === 0 ? 'Free' : `$${tier.price}/mo`}
                  </span>
                </div>
                <ul className="space-y-1">
                  {tier.features.map(f => (
                    <li key={f} className="text-xs text-text-secondary flex items-center gap-1.5">
                      <span className="text-accent-success">&#x2713;</span> {f}
                    </li>
                  ))}
                </ul>
                {tier.id !== user.subscription_tier && tier.id !== 'free' && (
                  <button className="btn btn-primary w-full mt-3 text-xs" disabled>
                    Coming Soon
                  </button>
                )}
                {tier.id === user.subscription_tier && (
                  <div className="mt-3 text-center text-xs text-text-muted">Current plan</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="card p-5">
          <p className="text-sm text-text-secondary">Preferences and notifications settings coming soon.</p>
        </div>
      )}
    </div>
  )
}
