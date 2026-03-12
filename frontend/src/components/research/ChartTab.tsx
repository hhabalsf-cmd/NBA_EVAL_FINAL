import { useMemo, useState } from 'react'
import {
  ComposedChart, Bar, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell,
  BarChart,
} from 'recharts'
import { BarChart3 } from 'lucide-react'
import type { ResearchTabProps } from './types'
import { STAT_LABELS, getStatValue } from './types'

export default function ChartTab({ data, activeStat, parsedLine }: ResearchTabProps) {
  const [view, setView] = useState<'trend' | 'distribution'>('trend')

  const chartData = useMemo(() => {
    const log = [...data.game_log].reverse() // chronological
    return log.map((g, i, arr) => {
      const val = getStatValue(g, activeStat)
      const window = arr.slice(Math.max(0, i - 9), i + 1)
      const rollAvg = +(window.reduce((sum, r) => sum + getStatValue(r, activeStat), 0) / window.length).toFixed(1)

      // Std dev band
      const windowVals = window.map(r => getStatValue(r, activeStat))
      const mean = windowVals.reduce((a, b) => a + b, 0) / windowVals.length
      const variance = windowVals.reduce((a, b) => a + (b - mean) ** 2, 0) / windowVals.length
      const std = Math.sqrt(variance)

      return {
        game_date: g.game_date,
        opponent: g.opponent,
        value: val,
        rollAvg,
        bandHigh: +(rollAvg + std).toFixed(1),
        bandLow: +(rollAvg - std).toFixed(1),
        isOver: parsedLine !== null ? val >= parsedLine : null,
      }
    })
  }, [data, activeStat, parsedLine])

  // Distribution histogram
  const histogramData = useMemo(() => {
    const log = data.game_log
    const vals = log.map(g => getStatValue(g, activeStat))
    if (vals.length === 0) return []

    const min = Math.floor(Math.min(...vals))
    const max = Math.ceil(Math.max(...vals))
    const bucketSize = max <= 10 ? 1 : max <= 30 ? 2 : 5
    const buckets: Record<string, { label: string; count: number; isOver: boolean }> = {}

    for (let b = Math.floor(min / bucketSize) * bucketSize; b <= max; b += bucketSize) {
      const label = `${b}-${b + bucketSize}`
      buckets[label] = { label, count: 0, isOver: parsedLine !== null ? b + bucketSize / 2 >= parsedLine : true }
    }

    for (const v of vals) {
      const b = Math.floor(v / bucketSize) * bucketSize
      const label = `${b}-${b + bucketSize}`
      if (buckets[label]) buckets[label] = { ...buckets[label], count: buckets[label].count + 1 }
    }

    return Object.values(buckets).filter(b => b.count > 0)
  }, [data, activeStat, parsedLine])

  return (
    <div className="card p-4 flex flex-col gap-3">
      {/* Header + view toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {STAT_LABELS[activeStat]} — Last {data.game_log.length} Games
          </h2>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {view === 'trend'
              ? <>Bars = actual · Line = L10 avg · Shaded = 1 std dev{parsedLine !== null && ' · Dashed = line'}</>
              : 'Distribution of stat values'
            }
          </p>
        </div>
        <div className="flex gap-1">
          {(['trend', 'distribution'] as const).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className="px-2.5 py-1 rounded-md text-xs font-medium transition-colors capitalize"
              style={view === v
                ? { background: 'var(--accent-muted)', color: 'var(--accent)' }
                : { color: 'var(--text-muted)' }
              }
            >{v === 'distribution' ? 'Dist' : v}</button>
          ))}
          {parsedLine !== null && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-semibold font-mono" style={{ background: 'rgba(230,168,23,0.12)', color: '#E6A817' }}>
              <span>Line: {parsedLine}</span>
            </div>
          )}
        </div>
      </div>

      {/* Trend chart */}
      {view === 'trend' && (
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--bg-elevated)" />
            <XAxis dataKey="game_date" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} axisLine={false} width={30} />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-elevated)',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '10px',
                fontSize: '12px',
              }}
              labelStyle={{ color: 'var(--text-primary)', fontWeight: 600, marginBottom: 4 }}
              itemStyle={{ color: 'var(--text-secondary)' }}
              formatter={(value: number, name: string) => {
                if (name === 'value') return [value, STAT_LABELS[activeStat]]
                if (name === 'rollAvg') return [value, 'L10 Avg']
                if (name === 'bandHigh' || name === 'bandLow') return [null, '']
                return [value, name]
              }}
              labelFormatter={(label: string, payload) => {
                const entry = payload?.[0]?.payload
                return entry ? `${label} · ${entry.opponent}` : label
              }}
            />
            {parsedLine !== null && (
              <ReferenceLine
                y={parsedLine}
                stroke="var(--accent-warning)"
                strokeDasharray="5 3"
                strokeWidth={1.5}
                label={{ value: parsedLine, position: 'right', fill: 'var(--accent-warning)', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
              />
            )}
            {/* Std dev band */}
            <Area type="monotone" dataKey="bandHigh" stroke="none" fill="rgba(6,182,212,0.08)" />
            <Area type="monotone" dataKey="bandLow" stroke="none" fill="var(--bg-primary)" />
            <Bar dataKey="value" radius={[3, 3, 0, 0]} maxBarSize={28}>
              {chartData.map((entry, index) => (
                <Cell
                  key={index}
                  fill={parsedLine !== null
                    ? (entry.isOver ? 'rgba(107,191,138,0.75)' : 'rgba(212,115,110,0.75)')
                    : 'rgba(6,182,212,0.6)'
                  }
                />
              ))}
            </Bar>
            <Line type="monotone" dataKey="rollAvg" stroke="#FFFFFF" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#FFFFFF' }} />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* Distribution histogram */}
      {view === 'distribution' && (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={histogramData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--bg-elevated)" />
            <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} tickLine={false} axisLine={false} width={30} allowDecimals={false} />
            {parsedLine !== null && (
              <ReferenceLine
                x={histogramData.find(b => {
                  const [lo, hi] = b.label.split('-').map(Number)
                  return parsedLine >= lo && parsedLine < hi
                })?.label}
                stroke="var(--accent-warning)"
                strokeDasharray="5 3"
              />
            )}
            <Tooltip
              contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '10px', fontSize: '12px' }}
              labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
              formatter={(value: number) => [value, 'Games']}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={40}>
              {histogramData.map((entry, index) => (
                <Cell
                  key={index}
                  fill={parsedLine !== null
                    ? (entry.isOver ? 'rgba(107,191,138,0.75)' : 'rgba(212,115,110,0.75)')
                    : 'rgba(6,182,212,0.6)'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs flex-wrap" style={{ color: 'var(--text-muted)' }}>
        {parsedLine !== null ? (
          <>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm" style={{ background: 'rgba(107,191,138,0.75)' }} />
              <span>OVER {parsedLine}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm" style={{ background: 'rgba(212,115,110,0.75)' }} />
              <span>UNDER {parsedLine}</span>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ background: 'rgba(6,182,212,0.6)' }} />
            <span>Actual {STAT_LABELS[activeStat]}</span>
          </div>
        )}
        {view === 'trend' && (
          <>
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-0.5" style={{ background: '#FFFFFF' }} />
              <span>L10 Rolling Avg</span>
            </div>
            <div className="flex items-center gap-1.5">
              <BarChart3 className="w-3 h-3" style={{ color: 'rgba(6,182,212,0.3)' }} />
              <span>1 Std Dev Band</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
