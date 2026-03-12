import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import TermsModal from '../TermsModal'

interface SignupFormProps {
  onSuccess?: () => void
}

export default function SignupForm({ onSuccess }: SignupFormProps) {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [tosAccepted, setTosAccepted] = useState(false)
  const [showTerms, setShowTerms] = useState(false)
  const { signup, acceptTos, isLoading, error } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!tosAccepted) return
    await signup(email, username, password)
    await acceptTos()
    onSuccess?.()
  }

  return (
    <>
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
          <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Username</label>
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
          <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Password</label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Create a password"
            required
            autoComplete="new-password"
            className="w-full"
          />
        </div>

        {/* TOS Checkbox */}
        <label className="flex items-start gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={tosAccepted}
            onChange={e => setTosAccepted(e.target.checked)}
            className="mt-0.5 w-4 h-4 rounded border-border accent-accent"
          />
          <span className="text-xs text-text-secondary">
            I agree to the{' '}
            <button
              type="button"
              onClick={() => setShowTerms(true)}
              className="text-accent hover:underline"
            >
              Terms of Service
            </button>
          </span>
        </label>

        {error && <p className="text-xs text-accent-danger">{error}</p>}
        <button type="submit" disabled={isLoading || !tosAccepted} className="btn btn-primary w-full">
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Creating account...
            </>
          ) : 'Create Account'}
        </button>
      </form>

      <TermsModal
        isOpen={showTerms}
        onAccept={() => {
          setTosAccepted(true)
          setShowTerms(false)
        }}
        onClose={() => setShowTerms(false)}
        canDismiss
      />
    </>
  )
}
