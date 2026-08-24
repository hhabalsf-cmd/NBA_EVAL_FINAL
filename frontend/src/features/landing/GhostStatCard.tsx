/**
 * Small decorative card used in the landing hero and the sample section.
 *
 * Two variants so the landing page never has to fake prediction output when
 * `VITE_ENABLE_PREDICTIONS` is off: the research variant shows box-score
 * averages, the prediction variant shows the projection/OVER-UNDER framing.
 */

export interface GhostPredictionCard {
  player: string
  stat: string
  value: number
  line: number
  isOver: boolean
  conf: number
}

export interface GhostResearchCard {
  player: string
  stat: string
  l10: number
  season: number
  split: string
}

export function GhostStatCard({ player, stat, value, line, isOver, conf }: GhostPredictionCard) {
  return (
    <div className="bg-bg-secondary border border-border-subtle rounded-xl p-3 w-40 shadow-lg">
      <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1.5 truncate">{player}</div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="font-mono text-base font-bold text-text-primary leading-none">{value}</div>
          <div className="text-[9px] text-text-muted mt-0.5">{stat} · L{line}</div>
        </div>
        <div className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
          isOver ? 'text-accent-success bg-accent-success/10' : 'text-accent-danger bg-accent-danger/10'
        }`}>
          {isOver ? 'OVER' : 'UNDER'}
        </div>
      </div>
      <div className="mt-2">
        <div className="flex justify-between text-[8px] text-text-muted mb-1">
          <span>Conf</span>
          <span>{conf}%</span>
        </div>
        <div className="h-0.5 bg-bg-elevated rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-accent-success" style={{ width: `${conf}%` }} />
        </div>
      </div>
    </div>
  )
}

export function GhostResearchStatCard({ player, stat, l10, season, split }: GhostResearchCard) {
  const delta = l10 - season
  return (
    <div className="bg-bg-secondary border border-border-subtle rounded-xl p-3 w-40 shadow-lg">
      <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1.5 truncate">{player}</div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="font-mono text-base font-bold text-text-primary leading-none">{l10.toFixed(1)}</div>
          <div className="text-[9px] text-text-muted mt-0.5">{stat} · L10 avg</div>
        </div>
        <div className="text-[9px] font-mono text-text-secondary">
          {delta >= 0 ? '+' : ''}{delta.toFixed(1)}
        </div>
      </div>
      <div className="mt-2 flex justify-between text-[8px] text-text-muted">
        <span>Season {season.toFixed(1)}</span>
        <span>{split}</span>
      </div>
    </div>
  )
}
