import { Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../../features/auth/authStore'
import TermsModal from '../../shared/components/TermsModal'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading, acceptTos } = useAuthStore()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="w-5 h-5 text-accent animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  // Force existing users to accept TOS before accessing the app
  if (user && !user.tos_accepted_at) {
    return (
      <TermsModal
        isOpen
        onAccept={acceptTos}
        onClose={() => {}}
        canDismiss={false}
      />
    )
  }

  return <>{children}</>
}
