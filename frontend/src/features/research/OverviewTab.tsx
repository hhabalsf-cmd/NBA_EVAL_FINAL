import { useMemo } from 'react'
import {
  TrendingUp, TrendingDown, Minus, BarChart3,
} from 'lucide-react'
import { type ResearchTabProps, type Stat, STATS, STAT_LABELS, getStatValue, delta, hitColor } from './types'

// ── Hit Rate Card ──────────────────────────────────────────────────────────
function HitRateCard({ label, hits, total }: { label: string; hits: number; total: number }) {
  const pct = total > 0 ? Math.round((hits / total) * 100) : 0
  const color = hitColor(pct)

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{ background: 'var(--bg-elevated)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-bold font-mono leading-none" style={{ color: 'var(--text-primary)' }}>
          {hits}/{total}
        </span>
        <span className="text-base font-semibold font-mono" style={{ color }}>({pct}%)</span>
      </div>
      <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>OVER line</span>
    </div>
  )
}

// ── Rolling Avg Cell ───────────────────────────────────────────────────────
function RollCell({ value, seasonAvg, className = '' }: { value: number; seasonAvg: number; className?: string }) {
  const d = delta(value, seasonAvg)
  const isUp = d > 0
  const isFlat = d === 0
  const Arrow = isFlat ? Minus : isUp ? TrendingUp : TrendingDown
  const arrowColor = isFlat ? 'var(--text-muted)' : isUp ? 'var(--accent-success)' : 'var(--accent-danger)'

  return (
    <td className={`px-3 py-2 text-center ${className}`}>
      <div className="flex flex-col items-center gap-0.5">
        <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{value.toFixed(1)}</span>
        <span className="flex items-center gap-0.5 text-[10px] font-medium" style={{ color: arrowColor }}>
          <Arrow className="w-2.5 h-2.5" strokeWidth={2.5} />
          {d > 0 ? `+${d}` : d}
        </span>
      </div>
    </td>
  )
}

// ── Overview Tab ───────────────────────────────────────────────────────────
export default function OverviewTab({ data, activeStat, setActiveStat, parsedLine }: ResearchTabProps) {
  const rolling = data.rolling_averages

  const hitRates = useMemo(() => {
    if (parsedLine === null) return null
    const log = data.game_log
    const windows = [
      { label: 'Last 5 Games', n: 5 },
      { label: 'Last 10 Games', n: 10 },
      { label: 'Last 20 Games', n: 20 },
    ]
    return windows.map(({ label, n }) => {
      const slice = log.slice(0, n)
      const hits = slice.filter(g => getStatValue(g, activeStat) >= parsedLine).length
      return { label, hits, total: slice.length }
    })
  }, [data, activeStat, parsedLine])

  return (
    <div className="flex flex-col gap-6">
      {/* Hit Rates */}
      {parsedLine !== null && hitRates ? (
        <div>
          <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
            Hit Rate — {STAT_LABELS[activeStat]} over {parsedLine}
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {hitRates.map(hr => <HitRateCard key={hr.label} {...hr} />)}
          </div>
        </div>
      ) : (
        <div
          className="rounded-xl p-4 flex items-center gap-3 border"
          style={{ background: 'rgba(var(--accent-rgb),0.05)', borderColor: 'rgba(var(--accent-rgb),0.15)' }}
        >
          <BarChart3 className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--accent)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Enter a line above to see hit rates for{' '}
            <span style={{ color: 'var(--text-primary)' }}>{STAT_LABELS[activeStat]}</span>
          </p>
        </div>
      )}

      {/* Rolling averages table */}
      <div>
        <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>Rolling Averages</h2>
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  <th className="px-3 py-2.5 text-left text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Stat</th>
                  {(['L3', 'L5', 'L10', 'L15', 'L20'] as const).map(w => (
                    <th
                      key={w}
                      className={`px-3 py-2.5 text-center text-xs font-semibold${(w === 'L3' || w === 'L20') ? ' hidden sm:table-cell' : ''}`}
                      style={{ color: 'var(--text-muted)' }}
                    >{w}</th>
                  ))}
                  <th className="px-3 py-2.5 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Season</th>
                </tr>
              </thead>
              <tbody>
                {STATS.filter(s => ['PTS', 'REB', 'AST', 'PRA', 'STL', 'BLK'].includes(s)).map((stat: Stat) => {
                  const base = getStatValue(data.season_averages, stat)
                  const isActive = stat === activeStat
                  return (
                    <tr
                      key={stat}
                      onClick={() => setActiveStat(stat)}
                      className="cursor-pointer transition-colors"
                      style={{
                        background: isActive ? 'rgba(var(--accent-rgb),0.05)' : undefined,
                        borderBottom: '1px solid rgba(255,255,255,0.04)',
                      }}
                    >
                      <td className="px-3 py-2.5">
                        <span
                          className="text-xs font-mono font-bold px-1.5 py-0.5 rounded"
                          style={{
                            background: isActive ? 'var(--accent-muted)' : 'rgba(255,255,255,0.04)',
                            color: isActive ? 'var(--accent)' : 'var(--text-muted)',
                          }}
                        >{stat}</span>
                      </td>
                      {(['L3', 'L5', 'L10', 'L15', 'L20'] as const).map(w => (
                        <RollCell
                          key={w}
                          value={getStatValue(rolling[w], stat)}
                          seasonAvg={base}
                          className={(w === 'L3' || w === 'L20') ? 'hidden sm:table-cell' : ''}
                        />
                      ))}
                      <td className="px-3 py-2 text-center">
                        <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                          {base.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  )
                })}
                {/* MIN row */}
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td className="px-3 py-2.5">
                    <span className="text-xs font-mono font-semibold" style={{ color: 'var(--text-muted)' }}>MIN</span>
                  </td>
                  {(['L3', 'L5', 'L10', 'L15', 'L20'] as const).map(w => (
                    <RollCell
                      key={w}
                      value={rolling[w].min}
                      seasonAvg={data.season_averages.min}
                      className={(w === 'L3' || w === 'L20') ? 'hidden sm:table-cell' : ''}
                    />
                  ))}
                  <td className="px-3 py-2 text-center">
                    <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      {data.season_averages.min.toFixed(1)}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Next game context strip */}
      {data.next_game && (
        <div className="card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>NEXT GAME</p>
            <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{data.next_game.matchup}</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{data.next_game.game_date}</p>
          </div>
          {data.opponent_context && (
            <div className="flex gap-4">
              <div className="text-center">
                <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Def Rtg</p>
                <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{data.opponent_context.def_rating}</p>
              </div>
              <div className="text-center">
                <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Pace</p>
                <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{data.opponent_context.pace}</p>
                <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{data.opponent_context.pace_desc}</p>
              </div>
              <div className="text-center hidden sm:block">
                <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Rank</p>
                <p className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                  {data.opponent_context.def_rank.split(' ')[0]}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
