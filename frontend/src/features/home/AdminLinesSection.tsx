import { useState } from 'react'
import { ClipboardEdit } from 'lucide-react'
import ManualLinesPanel from './ManualLinesPanel'
import { useAuthStore } from '../auth/authStore'

/**
 * Admin-only closing-line entry.
 *
 * Deliberately hoisted out of `BestBetsSection`: manual line logging is
 * operational tooling (it feeds the closing-line record used to measure any
 * future model), not a betting recommendation, so it must survive
 * `VITE_ENABLE_PREDICTIONS` being off.
 *
 * Manual line entry mutates lines everyone sees — the API 403s non-admins.
 */
export default function AdminLinesSection() {
  const [showLinesPanel, setShowLinesPanel] = useState(false)
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin')

  if (!isAdmin) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ClipboardEdit className="w-4 h-4 text-text-muted" />
          <h2 className="heading-display text-lg font-semibold text-text-primary">Line Entry</h2>
        </div>
        <button
          onClick={() => setShowLinesPanel((v) => !v)}
          className="text-xs font-medium text-text-muted hover:text-accent transition-colors"
          aria-expanded={showLinesPanel}
        >
          {showLinesPanel ? 'Hide' : 'Show'}
        </button>
      </div>
      <p className="text-xs text-text-muted mb-4">
        Admin only. Log today's book lines so closing lines are on record.
      </p>
      {showLinesPanel && <ManualLinesPanel />}
    </div>
  )
}
