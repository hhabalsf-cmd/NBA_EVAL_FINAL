import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import SubscriptionBadge from './SubscriptionBadge'

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
        className="w-8 h-8 rounded-full bg-accent/20 text-accent text-sm font-bold flex items-center justify-center hover:bg-accent/30 transition-colors"
      >
        {initial}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-bg-tertiary border border-border-subtle rounded-lg shadow-lg shadow-black/30 overflow-hidden animate-slide-up z-50">
          <div className="p-3 border-b border-border-subtle">
            <div className="text-sm font-medium text-text-primary">{user.username}</div>
            <div className="text-xs text-text-muted">{user.email}</div>
            <div className="mt-1.5">
              <SubscriptionBadge tier={user.subscription_tier} />
            </div>
          </div>
          <div className="py-1">
            <button
              onClick={() => { navigate('/settings'); setIsOpen(false) }}
              className="w-full px-3 py-2 text-left text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
            >
              Settings
            </button>
            <button
              onClick={() => { logout(); setIsOpen(false); navigate('/') }}
              className="w-full px-3 py-2 text-left text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
