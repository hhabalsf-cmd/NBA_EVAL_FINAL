import { useState } from 'react'
import { useAuthStore } from '../../store/authStore'

interface SignupFormProps {
  onSuccess?: () => void
}

export default function SignupForm({ onSuccess }: SignupFormProps) {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const { signup, isLoading, error } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await signup(email, username, password)
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
        <label className="block text-xs text-text-muted mb-1.5">Username</label>
        <input
          type="text"
          value={username}
          onChange={e => setUsername(e.target.value)}
          placeholder="Pick a username"
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
          placeholder="Create a password"
          required
          className="w-full"
        />
      </div>
      {error && <p className="text-xs text-accent-danger">{error}</p>}
      <button type="submit" disabled={isLoading} className="btn btn-primary w-full">
        {isLoading ? <><div className="spinner w-4 h-4" /> Creating account...</> : 'Create Account'}
      </button>
    </form>
  )
}
