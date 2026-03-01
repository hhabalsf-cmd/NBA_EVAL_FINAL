import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, BarChart2 } from 'lucide-react'
import { StatPrediction } from '../api/client'

interface PredictionCardProps {
  stat: string
  prediction: StatPrediction
  onChartClick?: () => void
}

export default function PredictionCard({ stat, prediction, onChartClick }: PredictionCardProps) {
  const getStatLabel = () => {
    switch (stat) {
      case 'PTS': return 'Points'
      case 'REB': return 'Rebounds'
      case 'AST': return 'Assists'
      case 'PRA': return 'PTS+REB+AST'
      default: return stat
    }
  }

  const getConfidenceClass = () => {
    if (prediction.confidence >= 80) return 'confidence-high'
    if (prediction.confidence >= 65) return 'confidence-medium'
    return 'confidence-low'
  }

  const getConfidenceBarClass = () => {
    if (prediction.confidence >= 80) return 'bg-accent-success'
    if (prediction.confidence >= 65) return 'bg-accent-warning'
    return 'bg-accent-danger'
  }

  const getConfidenceTextStyle = (): React.CSSProperties => ({
    color: prediction.confidence >= 80
      ? 'var(--accent-success)'
      : prediction.confidence >= 65
        ? 'var(--accent-warning)'
        : 'var(--accent-danger)',
  })

  const trendUp =
    prediction.recent_avg !== null &&
    prediction.recent_avg !== undefined &&
    prediction.prediction > prediction.recent_avg

  return (
    <motion.div
      onClick={onChartClick}
      className={`card ${getConfidenceClass()} p-5 h-full ${onChartClick ? 'cursor-pointer group' : ''}`}
      whileHover={onChartClick ? { scale: 1.025, y: -3 } : {}}
      whileTap={onChartClick ? { scale: 0.97 } : {}}
      transition={{ duration: 0.15, ease: 'easeOut' }}
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">{getStatLabel()}</span>
        <span className="font-mono font-semibold text-sm text-text-secondary">{stat}</span>
      </div>

      <div className="mb-4">
        <div className="font-mono text-3xl font-bold text-text-primary tracking-tight">
          {prediction.prediction.toFixed(1)}
        </div>
        <div className="text-xs text-text-muted mt-1.5">
          {prediction.range_low.toFixed(1)} – {prediction.range_high.toFixed(1)}
        </div>
      </div>

      {prediction.recent_avg !== null && prediction.recent_avg !== undefined && (
        <div className="flex items-center gap-2 mb-4 text-sm flex-wrap">
          <span className="text-text-muted text-xs">L10:</span>
          <span className="text-text-secondary font-medium text-xs">{prediction.recent_avg.toFixed(1)}</span>
          {prediction.prediction !== prediction.recent_avg && (
            <span className={`flex items-center gap-0.5 text-xs font-mono ${trendUp ? 'text-accent-success' : 'text-accent-danger'}`}>
              {trendUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {trendUp ? '+' : ''}
              {(prediction.prediction - prediction.recent_avg).toFixed(1)}
            </span>
          )}
        </div>
      )}

      <div className="mt-auto">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] text-text-muted">Confidence</span>
          <span className="text-xs font-mono font-semibold" style={getConfidenceTextStyle()}>
            {prediction.confidence.toFixed(0)}%
          </span>
        </div>
        <div className="confidence-meter">
          <div className={`confidence-fill ${getConfidenceBarClass()}`} style={{ width: `${prediction.confidence}%` }} />
        </div>
      </div>

      {prediction.uncertainty_std != null && (
        <div className="mt-2.5 text-[11px] text-text-muted">
          ±{prediction.uncertainty_std.toFixed(1)} uncertainty
        </div>
      )}

      {onChartClick && (
        <div className="mt-3 flex items-center gap-1 text-[10px] text-text-muted opacity-0 group-hover:opacity-100 transition-opacity">
          <BarChart2 className="w-3 h-3" />
          View chart
        </div>
      )}
    </motion.div>
  )
}
