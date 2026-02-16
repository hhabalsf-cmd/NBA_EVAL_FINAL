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

  return (
    <div onClick={onClick} className={`card p-5 ${onClick ? 'cursor-pointer card-hover' : ''}`}>
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">{getStatLabel()}</span>
        <span className="font-mono font-bold text-sm text-text-secondary">{stat}</span>
      </div>

      <div className="mb-4">
        <div className="font-mono text-3xl font-bold text-text-primary">{prediction.prediction.toFixed(1)}</div>
        <div className="text-xs text-text-muted mt-1">
          Range: {prediction.range_low.toFixed(1)} – {prediction.range_high.toFixed(1)}
        </div>
      </div>

      {prediction.recent_avg !== null && prediction.recent_avg !== undefined && (
        <div className="flex items-center gap-2 mb-4 text-sm">
          <span className="text-text-muted">L10 Avg:</span>
          <span className="text-text-primary font-medium">{prediction.recent_avg.toFixed(1)}</span>
          {prediction.prediction !== prediction.recent_avg && (
            <span className={prediction.prediction > prediction.recent_avg ? 'text-accent-success' : 'text-accent-danger'}>
              ({prediction.prediction > prediction.recent_avg ? '+' : ''}
              {(prediction.prediction - prediction.recent_avg).toFixed(1)})
            </span>
          )}
        </div>
      )}

      <div className="mt-auto">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] text-text-muted">Confidence</span>
          <span className="text-xs font-mono font-medium text-text-secondary">{prediction.confidence.toFixed(0)}%</span>
        </div>
        <div className="confidence-meter">
          <div className={`confidence-fill ${getConfidenceColor()}`} style={{ width: `${prediction.confidence}%` }} />
        </div>
      </div>

      {prediction.uncertainty_std !== null && prediction.uncertainty_std !== undefined && (
        <div className="mt-2 text-[11px] text-text-muted">Uncertainty: ±{prediction.uncertainty_std.toFixed(1)}</div>
      )}
    </div>
  )
}
