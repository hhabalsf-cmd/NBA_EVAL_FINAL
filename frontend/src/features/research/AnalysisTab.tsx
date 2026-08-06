import { Activity, TrendingUp, TrendingDown, AlertTriangle, Target } from 'lucide-react'
import type { ResearchTabProps } from './types'
import { STAT_LABELS, PRIMARY_STATS, getStatValue } from './types'

function ConsistencyGauge({ score, label }: { score: number; label: string }) {
  const color = score >= 70 ? 'var(--accent-success)' : score >= 50 ? 'var(--accent-warning)' : 'var(--accent-danger)'
  const circumference = 2 * Math.PI * 36
  const offset = circumference - (score / 100) * circumference

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="36" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
          <circle
            cx="40" cy="40" r="36" fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round" className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{Math.round(score)}</span>
          <span className="text-[9px] font-medium" style={{ color: 'var(--text-muted)' }}>/ 100</span>
        </div>
      </div>
      <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{label}</span>
    </div>
  )
}

function RangeBar({
  floor, median, avg, ceiling, line, label,
}: {
  floor: number; median: number; avg: number; ceiling: number; line: number | null; label: string
}) {
  const range = ceiling - floor || 1
  const medianPct = ((median - floor) / range) * 100
  const avgPct = ((avg - floor) / range) * 100
  const linePct = line !== null ? ((line - floor) / range) * 100 : null

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <div className="relative h-6 rounded-lg overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        {/* Gradient fill from floor to ceiling */}
        <div className="absolute inset-0 rounded-lg" style={{ background: 'linear-gradient(90deg, rgba(var(--danger-rgb),0.2), rgba(var(--accent-rgb),0.15), rgba(var(--success-rgb),0.2))' }} />
        {/* Median marker */}
        <div className="absolute top-0 bottom-0 w-0.5" style={{ left: `${Math.min(Math.max(medianPct, 2), 98)}%`, background: 'var(--text-primary)' }} />
        {/* Avg marker */}
        <div className="absolute top-0 bottom-0 w-0.5" style={{ left: `${Math.min(Math.max(avgPct, 2), 98)}%`, background: 'var(--accent)', opacity: 0.8 }} />
        {/* Line marker */}
        {linePct !== null && linePct >= 0 && linePct <= 100 && (
          <div className="absolute top-0 bottom-0 w-0.5 border-l border-dashed" style={{ left: `${Math.min(Math.max(linePct, 2), 98)}%`, borderColor: 'var(--accent-warning)' }} />
        )}
      </div>
      <div className="flex justify-between text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
        <span>{floor.toFixed(1)}</span>
        <span>med: {median.toFixed(1)} · avg: {avg.toFixed(1)}</span>
        <span>{ceiling.toFixed(1)}</span>
      </div>
    </div>
  )
}

export default function AnalysisTab({ data, activeStat, parsedLine, seasonAvg }: ResearchTabProps) {
  const analysis = data.analysis
  if (!analysis) {
    return (
      <div className="card p-8 flex flex-col items-center gap-3">
        <Activity className="w-8 h-8" style={{ color: 'var(--text-muted)' }} />
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Analysis data unavailable</p>
      </div>
    )
  }

  const activeAnalysis = analysis[activeStat]
  const isVolatile = activeAnalysis && activeAnalysis.consistency_score < 55

  return (
    <div className="flex flex-col gap-5">
      {/* Consistency scores */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>Consistency Scores</h2>
        <div className="flex justify-around flex-wrap gap-4">
          {PRIMARY_STATS.map(stat => {
            const a = analysis[stat]
            if (!a) return null
            return <ConsistencyGauge key={stat} score={a.consistency_score} label={stat} />
          })}
        </div>
      </div>

      {/* Active stat detail */}
      {activeAnalysis && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
              {STAT_LABELS[activeStat]} Distribution
            </h2>
            {isVolatile && (
              <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-semibold"
                style={{ background: 'rgba(var(--warning-rgb),0.12)', color: 'var(--accent-warning)' }}>
                <AlertTriangle className="w-3 h-3" />
                High Variance
              </div>
            )}
          </div>

          <RangeBar
            floor={activeAnalysis.floor}
            median={activeAnalysis.median}
            avg={seasonAvg}
            ceiling={activeAnalysis.ceiling}
            line={parsedLine}
            label={`${STAT_LABELS[activeStat]} range (Last 20)`}
          />

          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
            <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <p className="text-[10px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Std Dev</p>
              <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{activeAnalysis.std_dev.toFixed(1)}</p>
            </div>
            <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <p className="text-[10px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Median</p>
              <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{activeAnalysis.median.toFixed(1)}</p>
            </div>
            <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <p className="text-[10px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Floor</p>
              <p className="text-lg font-bold font-mono" style={{ color: 'var(--accent-danger)' }}>{activeAnalysis.floor.toFixed(1)}</p>
            </div>
            <div className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <p className="text-[10px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Ceiling</p>
              <p className="text-lg font-bold font-mono" style={{ color: 'var(--accent-success)' }}>{activeAnalysis.ceiling.toFixed(1)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Streak tracker */}
      {activeAnalysis && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>Streak Tracker</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {activeAnalysis.over_streak > 0 && (
              <div className="flex items-center gap-3 rounded-xl p-4"
                style={{ background: 'rgba(var(--success-rgb),0.08)', border: '1px solid rgba(var(--success-rgb),0.15)' }}>
                <TrendingUp className="w-5 h-5" style={{ color: 'var(--accent-success)' }} />
                <div>
                  <p className="text-sm font-semibold" style={{ color: 'var(--accent-success)' }}>
                    {activeAnalysis.over_streak} game over streak
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Consecutive games at or above {seasonAvg.toFixed(1)} {STAT_LABELS[activeStat]}
                  </p>
                </div>
              </div>
            )}
            {activeAnalysis.under_streak > 0 && (
              <div className="flex items-center gap-3 rounded-xl p-4"
                style={{ background: 'rgba(var(--danger-rgb),0.08)', border: '1px solid rgba(var(--danger-rgb),0.15)' }}>
                <TrendingDown className="w-5 h-5" style={{ color: 'var(--accent-danger)' }} />
                <div>
                  <p className="text-sm font-semibold" style={{ color: 'var(--accent-danger)' }}>
                    {activeAnalysis.under_streak} game under streak
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Consecutive games below {seasonAvg.toFixed(1)} {STAT_LABELS[activeStat]}
                  </p>
                </div>
              </div>
            )}
            {activeAnalysis.over_streak === 0 && activeAnalysis.under_streak === 0 && (
              <div className="flex items-center gap-3 rounded-xl p-4 col-span-full"
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <Target className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No active streak</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* All stats consistency summary */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>All Stats Summary</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                {['Stat', 'Avg', 'Med', 'Std', 'Floor', 'Ceil', 'Consist.'].map(h => (
                  <th key={h} className="px-3 py-2.5 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(analysis).map(([stat, a]) => (
                <tr key={stat} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td className="px-3 py-2 text-center">
                    <span className="text-xs font-mono font-bold" style={{ color: 'var(--text-muted)' }}>{stat}</span>
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                    {getStatValue(data.season_averages, stat as Parameters<typeof getStatValue>[1]).toFixed(1)}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{a.median.toFixed(1)}</td>
                  <td className="px-3 py-2 text-center font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{a.std_dev.toFixed(1)}</td>
                  <td className="px-3 py-2 text-center font-mono text-sm" style={{ color: 'var(--accent-danger)' }}>{a.floor.toFixed(1)}</td>
                  <td className="px-3 py-2 text-center font-mono text-sm" style={{ color: 'var(--accent-success)' }}>{a.ceiling.toFixed(1)}</td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className="text-xs font-semibold font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: a.consistency_score >= 70
                          ? 'rgba(var(--success-rgb),0.12)'
                          : a.consistency_score >= 50
                            ? 'rgba(var(--warning-rgb),0.12)'
                            : 'rgba(var(--danger-rgb),0.12)',
                        color: a.consistency_score >= 70
                          ? 'var(--accent-success)'
                          : a.consistency_score >= 50
                            ? 'var(--accent-warning)'
                            : 'var(--accent-danger)',
                      }}
                    >{Math.round(a.consistency_score)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
