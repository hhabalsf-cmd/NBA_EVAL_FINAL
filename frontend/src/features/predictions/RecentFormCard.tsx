import { motion } from 'framer-motion'
import { BarChart2, TrendingDown, TrendingUp } from 'lucide-react'
import { L10_WINDOW, type RecentForm } from './recentForm'
import { useTilt } from '../../shared/hooks/useTilt'

const STAT_LABELS: Record<string, string> = {
  PTS: 'Points',
  REB: 'Rebounds',
  AST: 'Assists',
  PRA: 'PTS+REB+AST',
}

interface RecentFormCardProps {
  stat: string
  form: RecentForm
  onChartClick?: () => void
}

/** Research-framed replacement for `PredictionCard` when predictions are gated off. */
export default function RecentFormCard({ stat, form, onChartClick }: RecentFormCardProps) {
  const tilt = useTilt({ maxTilt: 8, scale: 1.03 })

  if (form.l10 === null || form.logged === null) return null

  const delta = form.l10 - form.logged
  const trendUp = delta > 0

  return (
    <motion.div
      ref={tilt.ref}
      onClick={onChartClick}
      onMouseMove={tilt.onMouseMove}
      onMouseEnter={tilt.onMouseEnter}
      onMouseLeave={tilt.onMouseLeave}
      style={tilt.style}
      className={`card card-3d p-5 h-full ${onChartClick ? 'cursor-pointer group' : ''}`}
      whileTap={onChartClick ? { scale: 0.97 } : {}}
    >
      <div className="tilt-glare" />
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          {STAT_LABELS[stat] ?? stat}
        </span>
        <span className="font-mono font-semibold text-sm text-text-secondary">{stat}</span>
      </div>

      <div className="mb-4">
        <div className="font-mono text-3xl font-bold text-text-primary tracking-tight">
          {form.l10.toFixed(1)}
        </div>
        <div className="text-xs text-text-muted mt-1.5">Last {L10_WINDOW} games</div>
      </div>

      <div className="flex items-center gap-2 text-sm flex-wrap">
        <span className="text-text-muted text-xs">L{form.loggedGames}:</span>
        <span className="text-text-secondary font-medium text-xs">{form.logged.toFixed(1)}</span>
        {Math.abs(delta) >= 0.05 && (
          <span className={`flex items-center gap-0.5 text-xs font-mono ${trendUp ? 'text-accent-success' : 'text-accent-danger'}`}>
            {trendUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {trendUp ? '+' : ''}{delta.toFixed(1)}
          </span>
        )}
      </div>

      {onChartClick && (
        <div className="mt-3 flex items-center gap-1 text-[10px] text-text-muted opacity-0 group-hover:opacity-100 transition-opacity">
          <BarChart2 className="w-3 h-3" />
          View chart
        </div>
      )}
    </motion.div>
  )
}
