import { useEffect, useMemo } from 'react'
import { X } from 'lucide-react'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { GameLogEntry } from '../api/client'

interface StatChartModalProps {
  stat: string
  gameLog: GameLogEntry[]
  onClose: () => void
}

const STAT_LABELS: Record<string, string> = {
  PTS: 'Points',
  REB: 'Rebounds',
  AST: 'Assists',
  PRA: 'PTS+REB+AST',
}

function getStatValue(entry: GameLogEntry, stat: string): number {
  if (stat === 'PRA') return entry.pts + entry.reb + entry.ast
  if (stat === 'PTS') return entry.pts
  if (stat === 'REB') return entry.reb
  if (stat === 'AST') return entry.ast
  return 0
}

export default function StatChartModal({ stat, gameLog, onClose }: StatChartModalProps) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const chartData = useMemo(() => gameLog.map((g, i, arr) => {
    const val = getStatValue(g, stat)
    const window = arr.slice(Math.max(0, i - 9), i + 1)
    const rollAvg = +(
      window.reduce((sum, r) => sum + getStatValue(r, stat), 0) / window.length
    ).toFixed(1)
    return {
      game_date: g.game_date,
      opponent: g.opponent,
      value: val,
      rollAvg,
    }
  }), [gameLog, stat])

  const label = STAT_LABELS[stat] ?? stat

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
      onClick={onClose}
    >
      <div
        className="bg-bg-secondary rounded-2xl p-6 w-full max-w-2xl shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-semibold text-text-primary tracking-tight">{label} — Last {gameLog.length} Games</h2>
            <p className="text-xs text-text-muted mt-0.5">Bars = actual · Line = L10 rolling avg</p>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors p-1"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Chart */}
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--bg-elevated)" />
            <XAxis
              dataKey="game_date"
              tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={30}
            />
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
                if (name === 'value') return [value, label]
                if (name === 'rollAvg') return [value, 'L10 Avg']
                return [value, name]
              }}
              labelFormatter={(label: string, payload) => {
                const entry = payload?.[0]?.payload
                return entry ? `${label} · ${entry.opponent}` : label
              }}
            />
            <Legend
              formatter={(value: string) => value === 'value' ? label : 'L10 Rolling Avg'}
              wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }}
            />
            <Bar dataKey="value" fill="rgba(107,191,138,0.75)" radius={[3, 3, 0, 0]} maxBarSize={28} />
            <Line
              type="monotone"
              dataKey="rollAvg"
              stroke="#FFFFFF"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#FFFFFF' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
