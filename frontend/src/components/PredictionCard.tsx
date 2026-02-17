import { TrendingUp, TrendingDown } from 'lucide-react'
import { StatPrediction } from '../api/client'

interface PredictionCardProps {
  stat: string
  prediction: StatPrediction
  onClick?: () => void
}

export default function PredictionCard({ stat, prediction, onClick }: PredictionCardProps) {
  const getStatLabel = () => {
    switch (stat) {
      case 'PTS': return 'Points'
      case 'REB': return 'Rebounds'
      case 'AST': return 'Assists'
      case 'PRA': return 'PTS+REB+AST'
      default: return stat
    }
  }

  const getConfidenceColor = () => {
    if (prediction.confidence >= 80) return 'bg-accent-success'
    if (prediction.confidence >= 65) return 'bg-accent'
    return 'bg-accent-danger'
  }

  const trendUp = prediction.recent_avg !== null && prediction.recent_avg !== undefined && prediction.prediction > prediction.recent_avg

  return (
    <div onClick={onClick} className={`card p-5 ${onClick ? 'cursor-pointer card-hover' : ''}`}>
      <div className="flex items-center justify-between mb-5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">{getStatLabel()}</span>
        <span className="font-mono font-semibold text-sm text-text-secondary">{stat}</span>
      </div>

      <div className="mb-5">
        <div className="font-mono text-3xl font-bold text-text-primary tracking-tight">
          {prediction.prediction.toFixed(1)}
        </div>
        <div className="text-xs text-text-muted mt-1.5">
          Range: {prediction.range_low.toFixed(1)} - {prediction.range_high.toFixed(1)}
        </div>
      </div>

      {prediction.recent_avg !== null && prediction.recent_avg !== undefined && (
        <div className="flex items-center gap-2 mb-5 text-sm">
          <span className="text-text-muted">L10:</span>
          <span className="text-text-secondary font-medium">{prediction.recent_avg.toFixed(1)}</span>
          {prediction.prediction !== prediction.recent_avg && (
            <span className={`flex items-center gap-0.5 ${trendUp ? 'text-accent-success' : 'text-accent-danger'}`}>
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
          <span className="text-xs font-mono font-medium text-text-secondary">{prediction.confidence.toFixed(0)}%</span>
        </div>
        <div className="confidence-meter">
          <div className={`confidence-fill ${getConfidenceColor()}`} style={{ width: `${prediction.confidence}%` }} />
        </div>
      </div>

      {prediction.uncertainty_std !== null && prediction.uncertainty_std !== undefined && (
        <div className="mt-2.5 text-[11px] text-text-muted">
          Uncertainty: +/-{prediction.uncertainty_std.toFixed(1)}
        </div>
      )}
    </div>
  )
}
