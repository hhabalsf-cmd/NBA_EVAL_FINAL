import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
import { usePicksRealtime } from '../hooks/usePicksRealtime'
import { RefreshCw, Trash2, Check, X, Loader2 } from 'lucide-react'
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
  Legend,
} from 'recharts'

type ResultFilter = 'all' | 'wins' | 'losses'

const PAGE_SIZE = 30

export default function HistoryPage() {
  const queryClient = useQueryClient()
  const { isAuthenticated } = useAuthStore()
  usePicksRealtime()
  const [showPending, setShowPending] = useState(false)
  const [gradePickId, setGradePickId] = useState<number | null>(null)
  const [gradeValue, setGradeValue] = useState('')
  const [page, setPage] = useState(1)
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all')

  const { data: picks, isLoading: picksLoading } = useQuery({
    queryKey: ['picks', showPending],
    queryFn: () => getPicks(showPending),
    enabled: isAuthenticated,
  })

  const filteredPicks = useMemo(() => {
    if (!picks) return []
    if (resultFilter === 'wins') return picks.filter(p => p.won === true)
    if (resultFilter === 'losses') return picks.filter(p => p.won === false)
    return picks
  }, [picks, resultFilter])

  const totalPages = Math.max(1, Math.ceil(filteredPicks.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const displayedPicks = filteredPicks.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const handleFilterChange = (f: ResultFilter) => {
    setResultFilter(f)
    setPage(1)
  }

  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    enabled: isAuthenticated,
  })

  const { data: profitData } = useQuery({
    queryKey: ['cumulative-profit'],
    queryFn: getCumulativeProfit,
    enabled: isAuthenticated,
  })

  const autoGradeMutation = useMutation({
    mutationFn: autoGradePicks,
    onSuccess: (data) => {
      queryClient.refetchQueries({ queryKey: ['picks'] })
      queryClient.refetchQueries({ queryKey: ['performance-stats'] })
      queryClient.refetchQueries({ queryKey: ['cumulative-profit'] })
      queryClient.invalidateQueries({ queryKey: ['parlays'] })
      if (data.parlays_graded > 0) {
        console.log(`Auto-grade: ${data.graded_count} picks graded, ${data.parlays_graded} parlays resolved`)
      }
    },
    onError: () => {},
  })

  const gradePickMutation = useMutation({
    mutationFn: ({ pickId, result }: { pickId: number; result: number }) => gradePick(pickId, result),
    onMutate: async ({ pickId, result }) => {
      await queryClient.cancelQueries({ queryKey: ['picks', showPending] })
      const previous = queryClient.getQueryData<Pick[]>(['picks', showPending])
      queryClient.setQueryData<Pick[]>(['picks', showPending], old =>
        old?.map(p =>
          p.id === pickId
            ? { ...p, actual_result: result, won: result > p.line }
            : p
        )
      )
      setGradePickId(null)
      setGradeValue('')
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['picks', showPending], context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      queryClient.invalidateQueries({ queryKey: ['performance-stats'] })
      queryClient.invalidateQueries({ queryKey: ['cumulative-profit'] })
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

  if (picksLoading) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="skeleton h-7 w-36 rounded-lg" />
            <div className="skeleton h-4 w-52 rounded" />
          </div>
          <div className="skeleton h-9 w-32 rounded-lg" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card p-4 text-center space-y-2">
              <div className="skeleton h-3 w-16 mx-auto rounded" />
              <div className="skeleton h-6 w-12 mx-auto rounded" />
            </div>
          ))}
        </div>
        <div className="card p-4 sm:p-6">
          <div className="skeleton h-5 w-40 rounded mb-5" />
          <div className="skeleton h-44 sm:h-56 w-full rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <section className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Pick History</h1>
          <p className="text-sm text-text-secondary mt-1">Track your picks and performance</p>
        </div>
        <button
          onClick={() => autoGradeMutation.mutate()}
          disabled={autoGradeMutation.isPending}
          className="btn btn-secondary text-sm"
        >
          {autoGradeMutation.isPending ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Auto-grading...
            </>
          ) : (
            <>
              <RefreshCw className="w-3.5 h-3.5" />
              Auto-grade Picks
            </>
          )}
        </button>
      </section>

      {/* Stats Grid */}
      {stats && stats.graded_picks > 0 && (
        <section className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {[
            { label: 'Record', value: `${stats.wins}W - ${stats.losses}L`, color: 'text-text-primary' },
            { label: 'Win Rate', value: `${stats.win_rate.toFixed(1)}%`, color: stats.win_rate >= 55 ? 'text-accent-success' : stats.win_rate >= 50 ? 'text-accent' : 'text-accent-danger' },
            { label: 'ROI', value: `${stats.roi > 0 ? '+' : ''}${stats.roi.toFixed(1)}%`, color: stats.roi > 0 ? 'text-accent-success' : 'text-accent-danger' },
            { label: 'Avg Edge (W)', value: `${stats.avg_edge_winners.toFixed(1)}%`, color: 'text-accent' },
            { label: 'Pending', value: `${stats.total_picks - stats.graded_picks}`, color: 'text-text-primary' },
          ].map(s => (
            <div key={s.label} className="card p-4 text-center">
              <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">{s.label}</div>
              <div className={`font-mono text-lg font-semibold ${s.color}`}>{s.value}</div>
            </div>
          ))}
        </section>
      )}

      {/* Profit Chart */}
      {profitData && profitData.length > 0 && (
        <section className="card p-4 sm:p-6">
          <h2 className="text-base font-semibold text-text-primary mb-5 tracking-tight">Cumulative Profit</h2>
          <div className="h-44 sm:h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={profitData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis
                  dataKey="date"
                  stroke="var(--text-muted)"
                  fontSize={11}
                  tickFormatter={(value) => {
                    const date = new Date(value)
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                  }}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  fontSize={11}
                  tickFormatter={(value) => `${value}u`}
                  label={{ value: 'units', angle: -90, position: 'insideLeft', offset: 10, style: { fontSize: 10, fill: 'var(--text-muted)' } }}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  labelStyle={{ color: 'var(--text-secondary)' }}
                  labelFormatter={(label) => new Date(label).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  formatter={(value: number) => [`${value > 0 ? '+' : ''}${value.toFixed(2)} units`, 'Cumulative Profit']}
                />
                <Legend
                  formatter={() => 'Cumulative Profit (units = 1 standard bet)'}
                  wrapperStyle={{ fontSize: '11px', color: 'var(--text-muted)' }}
                />
                <Line
                  type="monotone"
                  dataKey="cumulative_profit"
                  stroke="#FFFFFF"
                  strokeWidth={2}
                  dot={false}
                  name="Profit (units)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* Performance by Stat */}
      {stats && Object.keys(stats.by_stat).length > 0 && (
        <section className="card p-4 sm:p-6">
          <h2 className="text-base font-semibold text-text-primary mb-5 tracking-tight">Performance by Stat</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-5">
            {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
              const data = stats.by_stat[stat]
              if (!data) return null
              return (
                <div key={stat} className="text-center">
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1.5">{stat}</div>
                  <div className={`font-mono text-xl font-bold ${
                    data.win_rate >= 55 ? 'text-accent-success' : data.win_rate >= 50 ? 'text-accent' : 'text-accent-danger'
                  }`}>
                    {data.win_rate.toFixed(1)}%
                  </div>
                  <div className="text-xs text-text-secondary mt-0.5">{data.wins}W / {data.total}</div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Picks */}
      <section className="card overflow-hidden">
        <div className="p-4 sm:p-5 border-b border-border-subtle space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-text-primary tracking-tight">
              {showPending ? 'Pending Picks' : 'Pick History'}
            </h2>
            <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5">
              <button
                onClick={() => setShowPending(false)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  !showPending ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
                }`}
              >All</button>
              <button
                onClick={() => setShowPending(true)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  showPending ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
                }`}
              >Pending</button>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5">
              {(['all', 'wins', 'losses'] as ResultFilter[]).map(f => (
                <button
                  key={f}
                  onClick={() => handleFilterChange(f)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors ${
                    resultFilter === f ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
                  }`}
                >{f}</button>
              ))}
            </div>
            {totalPages > 1 && (
              <div className="flex items-center gap-1.5 text-xs text-text-muted">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={safePage <= 1}
                  className="px-2 py-1 rounded-md bg-bg-secondary hover:bg-bg-elevated disabled:opacity-30 transition-colors"
                >&#8249;</button>
                <span className="font-mono">{safePage} / {totalPages}</span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={safePage >= totalPages}
                  className="px-2 py-1 rounded-md bg-bg-secondary hover:bg-bg-elevated disabled:opacity-30 transition-colors"
                >&#8250;</button>
              </div>
            )}
          </div>
        </div>

        {picksLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 text-accent animate-spin" />
          </div>
        ) : displayedPicks.length === 0 ? (
          <div className="text-center py-16 px-4">
            <p className="text-sm text-text-secondary">
              {resultFilter !== 'all' ? `No ${resultFilter} to show.` : 'No picks yet. Save picks from the player page to track them here.'}
            </p>
          </div>
        ) : (
          <>
            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
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
                  {displayedPicks.map((pick: Pick) => (
                    <tr key={pick.id}>
                      <td className="text-xs text-text-muted whitespace-nowrap">{formatDate(pick.timestamp)}</td>
                      <td className="font-medium text-text-primary text-sm">{pick.player}</td>
                      <td className="font-mono text-sm">{pick.stat}</td>
                      <td className="text-sm">{pick.line}</td>
                      <td className="text-sm">{pick.prediction.toFixed(1)}</td>
                      <td>
                        <span className={`pill ${pick.direction === 'OVER' ? 'pill-over' : 'pill-under'}`}>
                          {pick.direction}
                        </span>
                      </td>
                      <td className={`font-mono text-sm ${Math.abs(pick.edge) >= 3 ? 'text-accent' : 'text-text-muted'}`}>
                        {pick.edge > 0 ? '+' : ''}{pick.edge.toFixed(1)}
                      </td>
                      <td>
                        {pick.voided ? (
                          <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
                            {pick.void_reason || 'DNP'}
                          </span>
                        ) : pick.actual_result !== null && pick.actual_result !== undefined ? (
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-text-primary">{pick.actual_result}</span>
                            <span className={`text-sm font-semibold ${pick.won ? 'text-accent-success' : 'text-accent-danger'}`}>
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
                            <button
                              onClick={() => handleGradePick(pick)}
                              disabled={gradePickMutation.isPending}
                              className="text-accent-success hover:opacity-80 transition-opacity"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => setGradePickId(null)}
                              className="text-text-muted hover:text-text-primary transition-colors"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setGradePickId(pick.id)}
                            className="text-xs text-text-muted hover:text-text-primary transition-colors"
                          >
                            Grade
                          </button>
                        )}
                      </td>
                      <td>
                        <button
                          onClick={() => { if (confirm('Delete this pick?')) deletePickMutation.mutate(pick.id) }}
                          className="text-text-muted hover:text-accent-danger transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Card View */}
            <div className="md:hidden divide-y divide-border-subtle">
              {displayedPicks.map((pick: Pick) => {
                const isOver = pick.direction === 'OVER'
                return (
                  <div key={pick.id} className={`p-4 border-l-2 ${isOver ? 'border-l-accent-success' : 'border-l-accent-danger'}`}>
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="font-medium text-text-primary text-sm">{pick.player}</div>
                        <div className="text-[11px] text-text-muted mt-0.5">{formatDate(pick.timestamp)}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        {pick.voided ? (
                          <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">
                            {pick.void_reason || 'DNP'}
                          </span>
                        ) : pick.actual_result !== null && pick.actual_result !== undefined ? (
                          <span className={`font-mono text-sm font-semibold ${pick.won ? 'text-accent-success' : 'text-accent-danger'}`}>
                            {pick.actual_result} {pick.won ? 'W' : 'L'}
                          </span>
                        ) : gradePickId === pick.id ? (
                          <div className="flex items-center gap-1.5">
                            <input
                              type="number"
                              value={gradeValue}
                              onChange={e => setGradeValue(e.target.value)}
                              placeholder="Result"
                              className="w-16 px-2 py-1 text-xs"
                            />
                            <button
                              onClick={() => handleGradePick(pick)}
                              disabled={gradePickMutation.isPending}
                              className="text-accent-success hover:opacity-80 transition-opacity p-1"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => setGradePickId(null)}
                              className="text-text-muted hover:text-text-primary transition-colors p-1"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setGradePickId(pick.id)}
                            className="text-xs text-accent font-medium px-2 py-1"
                          >
                            Grade
                          </button>
                        )}
                        <button
                          onClick={() => { if (confirm('Delete this pick?')) deletePickMutation.mutate(pick.id) }}
                          className="text-text-muted hover:text-accent-danger transition-colors p-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>{pick.direction}</span>
                      <span className="font-mono text-sm text-text-primary">{pick.stat} {pick.line}</span>
                      <span className="text-text-muted text-xs">&rarr;</span>
                      <span className="font-mono text-sm text-text-secondary">{pick.prediction.toFixed(1)}</span>
                      <span className={`font-mono text-xs ${Math.abs(pick.edge) >= 3 ? 'text-accent' : 'text-text-muted'}`}>
                        {pick.edge > 0 ? '+' : ''}{pick.edge.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
