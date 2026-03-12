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
        <div className="text-center mb-8">
          <img src="/logo-full.png" alt="Bettin' Jrys" className="h-14 mx-auto mb-5" />
          <h1 className="text-xl font-semibold text-text-primary mb-1.5 tracking-tight">Create your account</h1>
          <p className="text-sm text-text-secondary">Get started with NBA prop analysis</p>
        </div>
        <div className="card p-6">
          <SignupForm onSuccess={() => navigate('/')} />
        </div>
        <p className="text-center text-sm text-text-muted mt-5">
          Already have an account?{' '}
          <Link to="/login" className="text-accent hover:text-accent-hover transition-colors">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
