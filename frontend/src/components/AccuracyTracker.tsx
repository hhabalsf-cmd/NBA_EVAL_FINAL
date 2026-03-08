import { GameAccuracyStats } from '../api/client'

interface AccuracyTrackerProps {
  stats: GameAccuracyStats
}

export default function AccuracyTracker({ stats }: AccuracyTrackerProps) {
  if (stats.graded_predictions === 0) return null

  return (
    <div className="card p-4 sm:p-5">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 sm:gap-5">
        <div className="grid grid-cols-2 sm:flex sm:flex-wrap sm:items-center gap-4 sm:gap-6">
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Record</div>
            <div className="font-mono text-base sm:text-lg font-semibold">
              <span className="text-accent-success">{stats.correct}W</span>
              <span className="text-text-muted mx-1">-</span>
              <span className="text-accent-danger">{stats.incorrect}L</span>
            </div>
          </div>
          <div className="h-8 w-px bg-border-subtle hidden sm:block" />
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Accuracy</div>
            <div className={`font-mono text-base sm:text-lg font-semibold ${
              stats.accuracy >= 60 ? 'text-accent-success' : stats.accuracy >= 52 ? 'text-accent' : 'text-accent-danger'
            }`}>
              {stats.accuracy.toFixed(1)}%
            </div>
          </div>
          {stats.recent_streak && (
            <>
              <div className="h-8 w-px bg-border-subtle hidden sm:block" />
              <div>
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Recent</div>
                <div className="font-mono text-base sm:text-lg font-semibold text-text-primary">{stats.recent_streak}</div>
              </div>
            </>
          )}
          <div className="h-8 w-px bg-border-subtle hidden sm:block" />
          <div>
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Total</div>
            <div className="font-mono text-base sm:text-lg font-semibold text-text-primary">{stats.total_predictions}</div>
          </div>
        </div>

        {Object.keys(stats.by_confidence_range).length > 0 && (
          <div className="relative">
            <div className="flex items-center gap-3 sm:gap-4 overflow-x-auto pb-1 pr-4"
              style={{ maskImage: 'linear-gradient(to right, black 85%, transparent 100%)', WebkitMaskImage: 'linear-gradient(to right, black 85%, transparent 100%)' }}
            >
            {Object.entries(stats.by_confidence_range).map(([range, data]) => (
              <div key={range} className="text-center flex-shrink-0">
                <div className="text-[10px] text-text-muted uppercase">{range}</div>
                <div className={`font-mono text-sm font-semibold ${
                  data.accuracy >= 60 ? 'text-accent-success' : data.accuracy >= 52 ? 'text-accent' : 'text-accent-danger'
                }`}>
                  {data.accuracy.toFixed(0)}%
                </div>
                <div className="text-[10px] text-text-muted">{data.total}g</div>
              </div>
            ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
