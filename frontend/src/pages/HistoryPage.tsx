import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getPicks,
  getPerformanceStats,
  getCumulativeProfit,
  autoGradePicks,
  gradePick,
  deletePick,
  Pick,
} from '../api/client'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

export default function HistoryPage() {
  const queryClient = useQueryClient()
  const [showPending, setShowPending] = useState(false)
  const [gradePickId, setGradePickId] = useState<number | null>(null)
  const [gradeValue, setGradeValue] = useState('')

  const { data: picks, isLoading: picksLoading } = useQuery({
    queryKey: ['picks', showPending],
    queryFn: () => getPicks(30, showPending),
  })

  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
  })

  const { data: profitData } = useQuery({
    queryKey: ['cumulative-profit'],
    queryFn: getCumulativeProfit,
  })

  const autoGradeMutation = useMutation({
    mutationFn: autoGradePicks,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      queryClient.invalidateQueries({ queryKey: ['performance-stats'] })
      queryClient.invalidateQueries({ queryKey: ['cumulative-profit'] })
    },
  })

  const gradePickMutation = useMutation({
    mutationFn: ({ pickId, result }: { pickId: number; result: number }) => gradePick(pickId, result),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      queryClient.invalidateQueries({ queryKey: ['performance-stats'] })
      queryClient.invalidateQueries({ queryKey: ['cumulative-profit'] })
      setGradePickId(null)
      setGradeValue('')
    },
  })

  const deletePickMutation = useMutation({
    mutationFn: deletePick,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      queryClient.invalidateQueries({ queryKey: ['performance-stats'] })
    },
  })

  const handleGradePick = (pick: Pick) => {
    const value = parseFloat(gradeValue)
    if (isNaN(value)) return
    gradePickMutation.mutate({ pickId: pick.id, result: value })
  }

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <section className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Pick History</h1>
          <p className="text-sm text-text-secondary">Track your picks and performance</p>
        </div>
        <button
          onClick={() => autoGradeMutation.mutate()}
          disabled={autoGradeMutation.isPending}
          className="btn btn-secondary text-sm"
        >
          {autoGradeMutation.isPending ? (
            <><div className="spinner w-4 h-4" /> Auto-grading...</>
          ) : 'Auto-grade Picks'}
        </button>
      </section>

      {/* Stats Grid */}
      {stats && stats.graded_picks > 0 && (
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { label: 'Record', value: `${stats.wins}W - ${stats.losses}L`, color: 'text-text-primary' },
            { label: 'Win Rate', value: `${stats.win_rate.toFixed(1)}%`, color: stats.win_rate >= 55 ? 'text-accent-success' : stats.win_rate >= 50 ? 'text-accent-gold' : 'text-accent-danger' },
            { label: 'ROI', value: `${stats.roi > 0 ? '+' : ''}${stats.roi.toFixed(1)}%`, color: stats.roi > 0 ? 'text-accent-success' : 'text-accent-danger' },
            { label: 'Avg Edge (W)', value: `${stats.avg_edge_winners.toFixed(1)}%`, color: 'text-accent-gold' },
            { label: 'Pending', value: `${stats.total_picks - stats.graded_picks}`, color: 'text-text-primary' },
          ].map(s => (
            <div key={s.label} className="card p-3 text-center">
              <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">{s.label}</div>
              <div className={`font-mono text-lg font-bold ${s.color}`}>{s.value}</div>
            </div>
          ))}
        </section>
      )}

      {/* Profit Chart */}
      {profitData && profitData.length > 0 && (
        <section className="card p-5">
          <h2 className="text-base font-bold text-text-primary mb-4">Cumulative Profit</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={profitData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E2D42" />
                <XAxis
                  dataKey="date"
                  stroke="#6B7FA0"
                  fontSize={11}
                  tickFormatter={(value) => {
                    const date = new Date(value)
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                  }}
                />
                <YAxis stroke="#6B7FA0" fontSize={11} tickFormatter={(value) => `${value}u`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1A2233', border: '1px solid #1E2D42', borderRadius: '8px', fontSize: '12px' }}
                  labelStyle={{ color: '#A5B4CB' }}
                />
                <Line type="monotone" dataKey="cumulative_profit" stroke="#38BDF8" strokeWidth={2} dot={false} name="Profit (units)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* Performance by Stat */}
      {stats && Object.keys(stats.by_stat).length > 0 && (
        <section className="card p-5">
          <h2 className="text-base font-bold text-text-primary mb-4">Performance by Stat</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
              const data = stats.by_stat[stat]
              if (!data) return null
              return (
                <div key={stat} className="text-center">
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">{stat}</div>
                  <div className={`font-mono text-xl font-bold ${data.win_rate >= 55 ? 'text-accent-success' : data.win_rate >= 50 ? 'text-accent-gold' : 'text-accent-danger'}`}>
                    {data.win_rate.toFixed(1)}%
                  </div>
                  <div className="text-xs text-text-secondary">{data.wins}W / {data.total}</div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Picks Table */}
      <section className="card overflow-hidden">
        <div className="p-4 border-b border-border-subtle flex items-center justify-between">
          <h2 className="text-base font-bold text-text-primary">
            {showPending ? 'Pending Picks' : 'All Picks'}
          </h2>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowPending(false)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${!showPending ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'}`}
            >All</button>
            <button
              onClick={() => setShowPending(true)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${showPending ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'}`}
            >Pending</button>
          </div>
        </div>

        {picksLoading ? (
          <div className="flex items-center justify-center py-12"><div className="spinner" /></div>
        ) : !picks || picks.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-sm text-text-secondary">No picks yet. Save picks from the player page to track them here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Player</th>
                  <th>Stat</th>
                  <th>Line</th>
                  <th>Prediction</th>
                  <th>Direction</th>
                  <th>Edge</th>
                  <th>Result</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {picks.map((pick: Pick) => (
                  <tr key={pick.id}>
                    <td className="text-xs text-text-muted">{formatDate(pick.timestamp)}</td>
                    <td className="font-medium text-text-primary text-sm">{pick.player}</td>
                    <td className="font-mono text-sm">{pick.stat}</td>
                    <td className="text-sm">{pick.line}</td>
                    <td className="text-sm">{pick.prediction.toFixed(1)}</td>
                    <td>
                      <span className={`pill ${pick.direction === 'OVER' ? 'pill-over' : 'pill-under'}`}>{pick.direction}</span>
                    </td>
                    <td className={`font-mono text-sm ${Math.abs(pick.edge) >= 3 ? 'text-accent-gold' : 'text-text-muted'}`}>
                      {pick.edge > 0 ? '+' : ''}{pick.edge.toFixed(1)}
                    </td>
                    <td>
                      {pick.voided ? (
                        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">{pick.void_reason || 'DNP'}</span>
                      ) : pick.actual_result !== null && pick.actual_result !== undefined ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm text-text-primary">{pick.actual_result}</span>
                          <span className={`text-sm font-bold ${pick.won ? 'text-accent-success' : 'text-accent-danger'}`}>
                            {pick.won ? 'W' : 'L'}
                          </span>
                        </div>
                      ) : gradePickId === pick.id ? (
                        <div className="flex items-center gap-1.5">
                          <input
                            type="number"
                            value={gradeValue}
                            onChange={e => setGradeValue(e.target.value)}
                            placeholder="Result"
                            className="w-16 px-2 py-1 text-xs"
                          />
                          <button onClick={() => handleGradePick(pick)} disabled={gradePickMutation.isPending} className="text-accent-success hover:opacity-80 text-sm font-bold">&#x2713;</button>
                          <button onClick={() => setGradePickId(null)} className="text-text-muted hover:text-text-primary text-sm">&#x2717;</button>
                        </div>
                      ) : (
                        <button onClick={() => setGradePickId(pick.id)} className="text-xs text-text-muted hover:text-text-primary transition-colors">Grade</button>
                      )}
                    </td>
                    <td>
                      <button
                        onClick={() => { if (confirm('Delete this pick?')) deletePickMutation.mutate(pick.id) }}
                        className="text-text-muted hover:text-accent-danger transition-colors"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
