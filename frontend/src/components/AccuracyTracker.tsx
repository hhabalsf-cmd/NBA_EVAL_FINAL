import { GameAccuracyStats } from '../api/client'

interface AccuracyTrackerProps {
  stats: GameAccuracyStats
}

export default function AccuracyTracker({ stats }: AccuracyTrackerProps) {
  if (stats.graded_predictions === 0) return null

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-5">
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Record</div>
            <div className="font-mono text-lg font-bold">
              <span className="text-accent-success">{stats.correct}W</span>
              <span className="text-text-muted mx-0.5">-</span>
              <span className="text-accent-danger">{stats.incorrect}L</span>
            </div>
          </div>
          <div className="h-8 w-px bg-border-subtle" />
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Accuracy</div>
            <div className={`font-mono text-lg font-bold ${stats.accuracy >= 60 ? 'text-accent-success' : stats.accuracy >= 52 ? 'text-accent-gold' : 'text-accent-danger'}`}>
              {stats.accuracy.toFixed(1)}%
            </div>
          </div>
          <div className="h-8 w-px bg-border-subtle" />
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Recent</div>
            <div className="font-mono text-lg font-bold text-text-primary">{stats.recent_streak}</div>
          </div>
          <div className="h-8 w-px bg-border-subtle" />
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Total</div>
            <div className="font-mono text-lg font-bold text-text-primary">{stats.total_predictions}</div>
          </div>
        </div>

        {Object.keys(stats.by_confidence_range).length > 0 && (
          <div className="flex items-center gap-3">
            {Object.entries(stats.by_confidence_range).map(([range, data]) => (
              <div key={range} className="text-center">
                <div className="text-[10px] text-text-muted uppercase">{range}</div>
                <div className={`font-mono text-sm font-bold ${data.accuracy >= 60 ? 'text-accent-success' : data.accuracy >= 52 ? 'text-accent-gold' : 'text-accent-danger'}`}>
                  {data.accuracy.toFixed(0)}%
                </div>
                <div className="text-[10px] text-text-muted">{data.total}g</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
