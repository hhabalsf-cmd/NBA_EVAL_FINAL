import type { GhostPredictionCard, GhostResearchCard } from './GhostStatCard'

/**
 * The large illustrative cards in the landing "sample" section.
 *
 * These are fixed example values in both variants — never live output. The
 * section heading says so (see `copy.ts`).
 */

const WASH = 'linear-gradient(135deg, var(--accent)0A 0%, transparent 60%)'

function CardShell({ player, children }: { player: string; children: React.ReactNode }) {
  return (
    <div className="card p-5 relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none" style={{ background: WASH }} />
      <div className="relative">
        <div className="text-xs text-text-muted uppercase tracking-wider mb-2">{player}</div>
        {children}
      </div>
    </div>
  )
}

export function SamplePredictionCards({ cards }: { cards: readonly GhostPredictionCard[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map(card => (
        <CardShell key={card.player} player={card.player}>
          <div className="flex items-end justify-between gap-3">
            <div>
              <div className="font-mono text-2xl font-bold text-text-primary">{card.value}</div>
              <div className="text-xs text-text-muted mt-0.5">{card.stat} projection</div>
            </div>
            <div className="text-right">
              <div className={`text-xs font-bold px-2 py-1 rounded ${
                card.isOver ? 'text-accent-success bg-accent-success/10' : 'text-accent-danger bg-accent-danger/10'
              }`}>
                {card.isOver ? 'OVER' : 'UNDER'} {card.line}
              </div>
              <div className="text-[10px] text-text-muted mt-1">{card.conf}% confidence</div>
            </div>
          </div>
          <div className="mt-3">
            <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-accent" style={{ width: `${card.conf}%` }} />
            </div>
          </div>
        </CardShell>
      ))}
    </div>
  )
}

export function SampleResearchCards({ cards }: { cards: readonly GhostResearchCard[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map(card => {
        const delta = card.l10 - card.season
        return (
          <CardShell key={card.player} player={card.player}>
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="font-mono text-2xl font-bold text-text-primary">{card.l10.toFixed(1)}</div>
                <div className="text-xs text-text-muted mt-0.5">{card.stat} · last 10 games</div>
              </div>
              <div className="text-right">
                <div className="font-mono text-sm font-semibold text-text-secondary">
                  {card.season.toFixed(1)}
                </div>
                <div className="text-[10px] text-text-muted mt-1">season avg</div>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px] text-text-muted">
              <span>{card.split} split</span>
              <span className="font-mono">{delta >= 0 ? '+' : ''}{delta.toFixed(1)} vs season</span>
            </div>
          </CardShell>
        )
      })}
    </div>
  )
}
