import type { LiveLegStatus } from '../api/client'
import { getNbaHeadshotUrl } from '../utils/nba'

interface LiveLegRowProps {
  readonly leg: LiveLegStatus
}

function statusBadge(status: LiveLegStatus['leg_status']) {
  switch (status) {
    case 'hit':
    case 'final_hit':
      return (
        <span className="flex items-center gap-1 text-accent-success text-xs font-bold">
          <span className="text-sm">✓</span>
          {status === 'hit' ? 'HIT' : 'FINAL'}
        </span>
      )
    case 'miss':
    case 'final_miss':
      return (
        <span className="flex items-center gap-1 text-accent-danger text-xs font-bold">
          <span className="text-sm">✗</span>
          {status === 'miss' ? 'MISS' : 'FINAL'}
        </span>
      )
    case 'in_progress':
      return (
        <span className="flex items-center gap-1 text-accent text-xs font-bold">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-success animate-pulse-live" />
          LIVE
        </span>
      )
    case 'voided':
      return <span className="text-text-muted text-xs line-through">VOID</span>
    default:
      return <span className="text-text-muted text-xs">⏳ PENDING</span>
  }
}

function progressPercent(leg: LiveLegStatus): number {
  if (leg.current_value == null || leg.line <= 0) return 0
  return Math.min(150, (leg.current_value / leg.line) * 100)
}

function progressColor(leg: LiveLegStatus): string {
  const pct = progressPercent(leg)
  if (leg.direction === 'OVER') {
    return pct >= 100 ? 'bg-accent-success' : 'bg-accent'
  }
  // UNDER: green when below line, red when above
  return pct >= 100 ? 'bg-accent-danger' : 'bg-accent-success'
}

export default function LiveLegRow({ leg }: LiveLegRowProps) {
  const isLive = leg.leg_status === 'in_progress' || leg.leg_status === 'hit' || leg.leg_status === 'miss'
  const isFinal = leg.leg_status === 'final_hit' || leg.leg_status === 'final_miss'
  const hasValue = leg.current_value != null
  const pct = progressPercent(leg)
  const isOver = leg.direction === 'OVER'

  return (
    <div className={`space-y-1.5 ${leg.leg_status === 'voided' ? 'opacity-40' : ''}`}>
      <div className="flex items-center gap-2 text-xs">
        {/* Status badge */}
        <div className="w-16 flex-shrink-0">{statusBadge(leg.leg_status)}</div>

        {/* Player headshot */}
        <img
          src={getNbaHeadshotUrl(leg.player_id ?? 0)}
          alt={leg.player_name}
          className="w-6 h-6 rounded-full object-cover bg-bg-secondary flex-shrink-0"
          onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
        />

        {/* Player name */}
        <span className="font-medium text-text-primary truncate flex-1 min-w-0">
          {leg.player_name}
        </span>

        {/* Stat line */}
        <span className="font-mono text-text-secondary flex-shrink-0">
          {leg.stat} {leg.direction} {leg.line}
        </span>

        {/* Current value */}
        {hasValue && (
          <span
            key={leg.current_value}
            className={`font-mono font-bold flex-shrink-0 ${
              (isOver && leg.current_value! > leg.line) || (!isOver && leg.current_value! < leg.line)
                ? 'text-accent-success'
                : (isOver && leg.current_value! < leg.line) || (!isOver && leg.current_value! > leg.line)
                ? 'text-accent-danger'
                : 'text-text-primary'
            } ${isLive ? 'animate-stat-update' : ''}`}
          >
            → {leg.current_value}
          </span>
        )}
      </div>

      {/* Game score row */}
      {leg.game && (isLive || isFinal) && (
        <div className="flex items-center gap-2 text-[11px] text-text-muted ml-[4.5rem]">
          <span className="font-mono">
            {leg.game.visitor_team} {leg.game.visitor_score} - {leg.game.home_team} {leg.game.home_score}
          </span>
          <span>·</span>
          <span>{leg.game.status}{leg.game.time_remaining && leg.game.time_remaining !== 'Final' ? ` ${leg.game.time_remaining}` : ''}</span>
        </div>
      )}

      {/* Progress bar */}
      {(isLive || isFinal) && hasValue && (
        <div className="h-1 bg-bg-elevated rounded-full overflow-hidden ml-[4.5rem]">
          <div
            className={`h-full rounded-full transition-all duration-700 ${progressColor(leg)}`}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      )}
    </div>
  )
}
