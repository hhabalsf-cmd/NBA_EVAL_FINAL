import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { supabase } from '../../lib/supabase'

interface LoginFormProps {
  onSuccess?: () => void
}

export default function LoginForm({ onSuccess }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [resetSent, setResetSent] = useState(false)
  const [resetLoading, setResetLoading] = useState(false)
  const { login, isLoading, error } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await login(email, password)
    onSuccess?.()
  }

  const handleForgotPassword = async () => {
    if (!email) return
    setResetLoading(true)
    try {
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/settings`,
      })
      if (resetError) throw resetError
      setResetSent(true)
    } catch {
      // Silently handle — don't reveal whether email exists
      setResetSent(true)
    } finally {
      setResetLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Email</label>
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
          className="w-full"
        />
      </div>
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-xs font-medium text-text-muted uppercase tracking-wider">Password</label>
          <button
            type="button"
            onClick={handleForgotPassword}
            disabled={!email || resetLoading}
            className="text-xs text-accent hover:text-accent-hover transition-colors disabled:opacity-40"
          >
            {resetLoading ? 'Sending...' : 'Forgot password?'}
          </button>
        </div>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="Enter password"
          required
          autoComplete="current-password"
          className="w-full"
        />
      </div>
      {resetSent && (
        <p className="text-xs text-accent-success">If an account exists for that email, a reset link has been sent.</p>
      )}
      {error && <p className="text-xs text-accent-danger">{error}</p>}
      <button type="submit" disabled={isLoading} className="btn btn-primary w-full">
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Signing in...
          </>
        ) : 'Sign In'}
      </button>
    </form>
  )
}
