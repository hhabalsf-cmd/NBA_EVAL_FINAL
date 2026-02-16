import { useState } from 'react'
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs text-text-muted mb-1.5">Email</label>
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
        <label className="block text-xs text-text-muted mb-1.5">Password</label>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="Enter password"
          required
          className="w-full"
        />
      </div>
      {error && <p className="text-xs text-accent-danger">{error}</p>}
      <button type="submit" disabled={isLoading} className="btn btn-primary w-full">
        {isLoading ? <><div className="spinner w-4 h-4" /> Signing in...</> : 'Sign In'}
      </button>
    </form>
  )
}
