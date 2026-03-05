import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

interface LoginFormProps {
  onSuccess?: () => void
}

export default function LoginForm({ onSuccess }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await login(email, password)
    onSuccess?.()
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
        <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Password</label>
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
