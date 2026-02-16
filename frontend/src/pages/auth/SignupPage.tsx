import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import SignupForm from '../../components/auth/SignupForm'
import { useEffect } from 'react'

export default function SignupPage() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()

  useEffect(() => {
    if (isAuthenticated) navigate('/', { replace: true })
  }, [isAuthenticated, navigate])

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <h1 className="text-xl font-bold text-text-primary mb-1">Create your account</h1>
          <p className="text-sm text-text-secondary">Get started with NBA prop analysis</p>
        </div>
        <div className="card p-6">
          <SignupForm onSuccess={() => navigate('/')} />
        </div>
        <p className="text-center text-sm text-text-muted mt-4">
          Already have an account?{' '}
          <Link to="/login" className="text-accent hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
