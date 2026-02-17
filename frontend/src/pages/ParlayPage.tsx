import { X, Trash2 } from 'lucide-react'
import { useParlayStore } from '../store/parlayStore'

export default function ParlayPage() {
  const { legs, removeLeg, clearParlay } = useParlayStore()

  const DECIMAL_PER_LEG = 1.909 // standard -110

  const combinedProb =
    legs.length > 0
      ? legs.reduce((acc, leg) => acc * (leg.prob / 100), 1) * 100
      : 0

  const parlayPayout = Math.pow(DECIMAL_PER_LEG, legs.length)

  const expectedValue =
    legs.length > 0 ? (combinedProb / 100) * parlayPayout - 1 : 0

  const kellyPct =
    legs.length > 0 && parlayPayout > 1
      ? ((combinedProb / 100) * parlayPayout - 1) / (parlayPayout - 1) * 100
      : 0

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">Parlay Builder</h1>
            <p className="text-sm text-text-secondary mt-1">
              {legs.length === 0
                ? 'Add picks from Today\'s Best Bets or any player analysis'
                : `${legs.length} leg${legs.length > 1 ? 's' : ''} selected`}
            </p>
          </div>
          {legs.length > 0 && (
            <button onClick={clearParlay} className="btn btn-secondary text-sm text-accent-danger hover:text-accent-danger">
              <Trash2 className="w-4 h-4" />
              Clear Parlay
            </button>
          )}
        </div>
      </section>

      {legs.length === 0 ? (
        <div className="card p-16 text-center">
          <div className="text-5xl mb-5">🎲</div>
          <h2 className="text-lg font-semibold text-text-primary mb-2">No Legs Yet</h2>
          <p className="text-sm text-text-secondary max-w-sm mx-auto leading-relaxed">
            Add picks from Today's Best Bets or any player analysis page using the{' '}
            <span className="text-accent font-medium">+ Parlay</span> button.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Legs list */}
          <div className="lg:col-span-2 space-y-3">
            {legs.map((leg, i) => {
              const isOver = leg.direction === 'OVER'
              return (
                <div
                  key={`${leg.player}-${leg.stat}-${i}`}
                  className={`card p-4 border-l-2 ${isOver ? 'border-l-accent-success' : 'border-l-accent-danger'}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-medium text-text-primary truncate">{leg.player}</span>
                        <span className={`pill text-[10px] ${isOver ? 'pill-over' : 'pill-under'}`}>
                          {leg.direction}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-4 text-sm">
                        <div>
                          <span className="text-text-muted">Stat: </span>
                          <span className="font-mono font-semibold text-text-primary">{leg.stat}</span>
                        </div>
                        <div>
                          <span className="text-text-muted">Line: </span>
                          <span className="font-mono font-semibold text-text-primary">{leg.line}</span>
                        </div>
                        <div>
                          <span className="text-text-muted">Pred: </span>
                          <span className={`font-mono font-semibold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
                            {leg.prediction.toFixed(1)}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Edge: </span>
                          <span className="font-mono font-semibold text-text-primary">
                            {leg.edge_pct > 0 ? '+' : ''}{leg.edge_pct.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <button
                        onClick={() => removeLeg(i)}
                        className="p-1 rounded text-text-muted hover:text-accent-danger transition-colors"
                        title="Remove leg"
                      >
                        <X className="w-4 h-4" />
                      </button>
                      <div className="text-right">
                        <div className="text-[11px] text-text-muted uppercase tracking-wider">Hit prob</div>
                        <div className="font-mono text-sm font-semibold text-text-primary">
                          {leg.prob.toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Summary panel */}
          <div className="space-y-4">
            <div className="card p-5 space-y-4">
              <h2 className="text-base font-semibold text-text-primary tracking-tight">Parlay Summary</h2>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Legs</div>
                  <div className="font-mono text-2xl font-bold text-text-primary">{legs.length}</div>
                </div>
                <div>
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Combined Prob</div>
                  <div className={`font-mono text-2xl font-bold ${combinedProb >= 20 ? 'text-accent-success' : combinedProb >= 10 ? 'text-accent' : 'text-accent-danger'}`}>
                    {combinedProb.toFixed(1)}%
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-border-subtle space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-muted">Payout (at -110 ea)</span>
                  <span className="font-mono font-semibold text-text-primary">
                    {parlayPayout.toFixed(2)}x
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-muted">Expected Value</span>
                  <span className={`font-mono font-semibold ${expectedValue > 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
                    {expectedValue > 0 ? '+' : ''}{(expectedValue * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-muted">Kelly %</span>
                  <span className={`font-mono font-semibold ${kellyPct > 0 ? 'text-accent' : 'text-text-muted'}`}>
                    {kellyPct > 0 ? kellyPct.toFixed(1) : '0.0'}%
                  </span>
                </div>
              </div>
            </div>

            {/* Probability bar */}
            <div className="card p-4">
              <div className="text-[11px] text-text-muted uppercase tracking-wider mb-3">Leg-by-Leg Breakdown</div>
              <div className="space-y-2">
                {legs.map((leg, i) => (
                  <div key={i} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-secondary truncate max-w-[120px]">{leg.player} {leg.stat}</span>
                      <span className="text-text-muted font-mono">{leg.prob.toFixed(0)}%</span>
                    </div>
                    <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          leg.direction === 'OVER' ? 'bg-accent-success' : 'bg-accent-danger'
                        }`}
                        style={{ width: `${leg.prob}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
