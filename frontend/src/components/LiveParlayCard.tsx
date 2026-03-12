import { Trash2 } from 'lucide-react'
import type { LiveParlayStatus } from '../api/client'
import LiveLegRow from './LiveLegRow'

const DECIMAL_PER_LEG = 1.909

interface LiveParlayCardProps {
  readonly parlay: LiveParlayStatus
  readonly onDelete: (id: number) => void
}

function overallStatusLabel(parlay: LiveParlayStatus): {
  label: string
  color: string
  bgClass: string
} {
  const { legs_hit, legs_miss, legs_in_progress, legs_pending, legs_count } = parlay

  if (legs_miss > 0) {
    return {
      label: 'BUST',
      color: 'text-accent-danger',
      bgClass: 'bg-accent-danger/10 border-accent-danger/20',
    }
  }
  if (legs_hit === legs_count && legs_pending === 0 && legs_in_progress === 0) {
    return {
      label: 'ALL HIT',
      color: 'text-accent-success',
      bgClass: 'bg-accent-success/10 border-accent-success/20',
    }
  }
  if (legs_in_progress > 0 || legs_hit > 0) {
    return {
      label: 'LIVE',
      color: 'text-accent',
      bgClass: 'bg-accent/10 border-accent/20',
    }
  }
  return {
    label: 'PENDING',
    color: 'text-text-muted',
    bgClass: 'bg-bg-secondary border-border-subtle',
  }
}

export default function LiveParlayCard({ parlay, onDelete }: LiveParlayCardProps) {
  const effectiveLegs = parlay.legs.filter(l => l.leg_status !== 'voided').length
  const payout = effectiveLegs > 0 ? Math.pow(DECIMAL_PER_LEG, effectiveLegs) : 0
  const { label, color, bgClass } = overallStatusLabel(parlay)
  const isLive = label === 'LIVE'
  const isBust = label === 'BUST'

  return (
    <div className={`card p-4 space-y-3 ${isBust ? 'opacity-60' : ''}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${bgClass} ${color} flex items-center gap-1`}>
              {isLive && (
                <span className="w-1.5 h-1.5 rounded-full bg-accent-success animate-pulse-live" />
              )}
              {label}
            </span>
            <span className="text-[11px] text-text-muted font-mono">
              {effectiveLegs}-leg · {payout.toFixed(2)}x
            </span>
          </div>

          {/* Progress summary */}
          <div className="flex items-center gap-3 mt-1.5 text-[11px]">
            {parlay.legs_hit > 0 && (
              <span className="text-accent-success font-medium">
                {parlay.legs_hit} hit
              </span>
            )}
            {parlay.legs_in_progress > 0 && (
              <span className="text-accent font-medium">
                {parlay.legs_in_progress} live
              </span>
            )}
            {parlay.legs_pending > 0 && (
              <span className="text-text-muted">
                {parlay.legs_pending} pending
              </span>
            )}
            {parlay.legs_miss > 0 && (
              <span className="text-accent-danger font-medium">
                {parlay.legs_miss} miss
              </span>
            )}
          </div>

          <div className="text-[11px] text-text-muted mt-0.5">
            {new Date(parlay.created_at).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
            })}
          </div>
        </div>

        <button
          onClick={() => { if (confirm('Delete this parlay?')) onDelete(parlay.parlay_id) }}
          className="p-1.5 rounded text-text-muted hover:text-accent-danger transition-colors flex-shrink-0"
          title="Delete parlay"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Parlay-level progress bar */}
      {effectiveLegs > 0 && (
        <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden flex">
          {parlay.legs_hit > 0 && (
            <div
              className="h-full bg-accent-success transition-all duration-500"
              style={{ width: `${(parlay.legs_hit / effectiveLegs) * 100}%` }}
            />
          )}
          {parlay.legs_in_progress > 0 && (
            <div
              className="h-full bg-accent transition-all duration-500"
              style={{ width: `${(parlay.legs_in_progress / effectiveLegs) * 100}%` }}
            />
          )}
          {parlay.legs_miss > 0 && (
            <div
              className="h-full bg-accent-danger transition-all duration-500"
              style={{ width: `${(parlay.legs_miss / effectiveLegs) * 100}%` }}
            />
          )}
        </div>
      )}

      {/* Legs */}
      <div className="space-y-3 pt-2 border-t border-border-subtle">
        {parlay.legs.map(leg => (
          <LiveLegRow key={leg.pick_id} leg={leg} />
        ))}
      </div>
    </div>
  )
}
