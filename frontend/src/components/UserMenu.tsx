import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Settings, LogOut } from 'lucide-react'
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
        className="w-8 h-8 rounded-full bg-accent/15 text-accent text-sm font-semibold flex items-center justify-center hover:bg-accent/25 transition-colors"
      >
        {initial}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-bg-tertiary border border-border-subtle rounded-xl shadow-xl shadow-black/30 overflow-hidden animate-slide-up z-50">
          <div className="p-4 border-b border-border-subtle">
            <div className="text-sm font-medium text-text-primary">{user.username}</div>
            <div className="text-xs text-text-muted mt-0.5">{user.email}</div>
            <div className="mt-2">
              <SubscriptionBadge tier={user.subscription_tier} />
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
