import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, BarChart2 } from 'lucide-react'
import { StatPrediction } from './api'
import { useTilt } from '../../shared/hooks/useTilt'

function useCountUp(target: number, duration = 800): number {
  const [value, setValue] = useState(0)
  const started = useRef(false)

  useEffect(() => {
    if (started.current || target === 0) return
    started.current = true
    const startTime = performance.now()
    const tick = (now: number) => {
      const p = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3) // easeOut cubic
      setValue(eased * target)
      if (p < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }, [target, duration])

  return value
}

interface PredictionCardProps {
  stat: string
  prediction: StatPrediction
  onChartClick?: () => void
  /** Render the early-season badge (player has < 10 games this season) */
  earlySeason?: boolean
}

export default function PredictionCard({ stat, prediction, onChartClick, earlySeason }: PredictionCardProps) {
  const animatedPrediction = useCountUp(prediction.prediction)
  const tilt = useTilt({ maxTilt: 8, scale: 1.03 })

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
      ref={tilt.ref}
      onClick={onChartClick}
      onMouseMove={tilt.onMouseMove}
      onMouseEnter={tilt.onMouseEnter}
      onMouseLeave={tilt.onMouseLeave}
      style={tilt.style}
      className={`card card-3d ${getConfidenceClass()} p-5 h-full ${onChartClick ? 'cursor-pointer group' : ''}`}
      whileTap={onChartClick ? { scale: 0.97 } : {}}
    >
      <div className="tilt-glare" />
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">{getStatLabel()}</span>
        <span className="font-mono font-semibold text-sm text-text-secondary">{stat}</span>
      </div>

      {earlySeason && (
        <div
          className="inline-block mb-3 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
          style={{
            color: 'var(--accent-warning, var(--accent))',
            backgroundColor: 'rgba(var(--accent-rgb), 0.12)',
          }}
          title="Fewer than 10 games this season — confidence is reduced and ranges widened while the model relearns this season's role"
        >
          Early-season estimate
        </div>
      )}

      <div className="mb-4">
        <div className="font-mono text-3xl font-bold text-text-primary tracking-tight">
          {animatedPrediction.toFixed(1)}
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
