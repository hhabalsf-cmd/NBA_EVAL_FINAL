import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import LoginForm from '../../components/auth/LoginForm'
import { useEffect } from 'react'

export default function LoginPage() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()

  useEffect(() => {
    if (isAuthenticated) navigate('/', { replace: true })
  }, [isAuthenticated, navigate])

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <img src="/logo-full.png" alt="Bettin' Jrys" className="h-[360px] mx-auto mb-5" />
          <h1 className="text-xl font-semibold text-text-primary mb-1.5 tracking-tight">Sign in to EVAL</h1>
          <p className="text-sm text-text-secondary">Enter your credentials to continue</p>
        </div>
        <div className="card p-6">
          <LoginForm onSuccess={() => navigate('/')} />
        </div>
        <p className="text-center text-sm text-text-muted mt-5">
          Don't have an account?{' '}
          <Link to="/signup" className="text-accent hover:text-accent-hover transition-colors">Sign up</Link>
        </p>
      </div>
    </div>
  )
}
