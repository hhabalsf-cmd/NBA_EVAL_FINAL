import { useQuery } from '@tanstack/react-query'
import { Zap, Loader2, TrendingUp, TrendingDown } from 'lucide-react'
import { evaluateLine } from '../predictions/api'
import { STAT_LABELS, type Stat } from './types'

interface ModelEdgeCardProps {
  playerName: string
  stat: Stat
  line: number
}

export default function ModelEdgeCard({ playerName, stat, line }: ModelEdgeCardProps) {
  const { data: evaluation, isLoading, error } = useQuery({
    queryKey: ['evaluate-line', playerName, stat, line],
    queryFn: () => evaluateLine(playerName, stat, line),
    enabled: !!playerName && !!stat && line > 0,
    staleTime: 1000 * 60 * 2,
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="card p-4 flex items-center gap-3">
        <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--accent)' }} />
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Running ML evaluation...</span>
      </div>
    )
  }

  if (error || !evaluation) return null

  const isOver = evaluation.recommendation.includes('OVER')
  const edgeColor = isOver ? 'var(--accent-success)' : 'var(--accent-danger)'
  const EdgeIcon = isOver ? TrendingUp : TrendingDown
  const strengthBg = evaluation.strength === 'HIGH'
    ? 'rgba(var(--success-rgb),0.12)' : evaluation.strength === 'MODERATE'
      ? 'rgba(var(--warning-rgb),0.12)' : 'rgba(255,255,255,0.06)'
  const strengthColor = evaluation.strength === 'HIGH'
    ? 'var(--accent-success)' : evaluation.strength === 'MODERATE'
      ? 'var(--accent-warning)' : 'var(--text-muted)'

  return (
    <div
      className="card p-4"
      style={{ borderTop: `2px solid ${edgeColor}` }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>ML MODEL EDGE</span>
        </div>
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded"
          style={{ background: strengthBg, color: strengthColor }}
        >{evaluation.recommendation}</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Prediction */}
        <div>
          <p className="text-[10px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>Prediction</p>
          <p className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
            {evaluation.prediction.toFixed(1)}
          </p>
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{STAT_LABELS[stat]}</p>
        </div>

        {/* Edge */}
        <div>
          <p className="text-[10px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>Edge</p>
          <div className="flex items-center gap-1">
            <EdgeIcon className="w-4 h-4" style={{ color: edgeColor }} />
            <p className="text-xl font-bold font-mono" style={{ color: edgeColor }}>
              {evaluation.diff_pct > 0 ? '+' : ''}{evaluation.diff_pct.toFixed(1)}%
            </p>
          </div>
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>vs line {line}</p>
        </div>

        {/* Prob Over */}
        {evaluation.prob_over != null && (
          <div>
            <p className="text-[10px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>P(Over)</p>
            <p className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
              {evaluation.prob_over.toFixed(0)}%
            </p>
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>probability</p>
          </div>
        )}

        {/* Range */}
        {evaluation.range_low != null && evaluation.range_high != null && (
          <div>
            <p className="text-[10px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>Range</p>
            <p className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
              {evaluation.range_low.toFixed(0)}–{evaluation.range_high.toFixed(0)}
            </p>
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>projected range</p>
          </div>
        )}
      </div>

      {evaluation.high_edge_warning && (
        <p className="text-[10px] mt-2 px-2 py-1 rounded" style={{ background: 'rgba(var(--warning-rgb),0.08)', color: 'var(--accent-warning)' }}>
          Large edge detected — historically less reliable. Consider checking for injuries or lineup changes.
        </p>
      )}
    </div>
  )
}
