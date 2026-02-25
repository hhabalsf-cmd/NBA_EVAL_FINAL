import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Settings, LogOut } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

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
        className="w-8 h-8 rounded-full overflow-hidden hover:ring-2 hover:ring-accent/40 transition-all"
        aria-label="User menu"
      >
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={user.username}
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="w-full h-full bg-accent/15 text-accent text-sm font-semibold flex items-center justify-center">
            {initial}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-bg-tertiary border border-border-subtle rounded-xl shadow-xl shadow-black/30 overflow-hidden animate-slide-up z-50">
          <div className="p-4 border-b border-border-subtle flex items-center gap-3">
            <div className="w-9 h-9 rounded-full overflow-hidden flex-shrink-0">
              {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.username} className="w-full h-full object-cover" />
              ) : (
                <span className="w-full h-full bg-accent/15 text-accent text-sm font-semibold flex items-center justify-center">
                  {initial}
                </span>
              )}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-text-primary truncate">{user.username}</div>
              <div className="text-xs text-text-muted truncate">{user.email}</div>
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
