import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../../features/auth/authStore'
import { usePicksRealtime } from './usePicksRealtime'
import { useNavigate } from 'react-router-dom'
import {
  Trash2, Check, X, Loader2, Share2, RefreshCw,
  BookmarkCheck, ArrowUpDown, ArrowUp, ArrowDown,
} from 'lucide-react'
import {
  getPicks,
  getPerformanceStats,
  getCumulativeProfit,
  getCalibrationStats,
  gradePick,
  deletePick,
  Pick,
} from './api'
import { getHeadshotUrl, getNbaHeadshotUrl } from '../../shared/utils/nba'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine,
  ScatterChart, Scatter, ZAxis,
} from 'recharts'

/* ── Pending tab helpers ─────────────────────────────────────────────── */

type SortField = 'edge' | 'team' | 'PTS' | 'REB' | 'AST' | 'PRA'
type SortDir = 'asc' | 'desc'

function hitProb(pick: Pick): number {
  const isOver = pick.direction === 'OVER'
  if (pick.prob_over != null) {
    const raw = isOver ? pick.prob_over : 100 - pick.prob_over
    return Math.min(85, Math.max(15, raw))
  }
  return Math.min(85, Math.max(32, 50 + Math.abs(pick.edge) * 1.5))
}

const STAT_ORDER: Record<string, number> = { PTS: 0, REB: 1, AST: 2, PRA: 3 }

function sortPicks(picks: Pick[], field: SortField, dir: SortDir): Pick[] {
  return [...picks].sort((a, b) => {
    let cmp = 0
    if (field === 'edge') {
      cmp = Math.abs(a.edge) - Math.abs(b.edge)
    } else if (field === 'team') {
      cmp = (a.team_abbrev ?? '').localeCompare(b.team_abbrev ?? '')
    } else {
      const aMatch = a.stat === field ? 0 : 1
      const bMatch = b.stat === field ? 0 : 1
      if (aMatch !== bMatch) return aMatch - bMatch
      cmp = (STAT_ORDER[a.stat] ?? 99) - (STAT_ORDER[b.stat] ?? 99)
    }
    return dir === 'asc' ? cmp : -cmp
  })
}

const SORT_OPTIONS: { field: SortField; label: string }[] = [
  { field: 'edge', label: 'Edge' },
  { field: 'team', label: 'Team' },
  { field: 'PTS', label: 'PTS' },
  { field: 'REB', label: 'REB' },
  { field: 'AST', label: 'AST' },
  { field: 'PRA', label: 'PRA' },
]

/* ── History tab helpers ─────────────────────────────────────────────── */

type ResultFilter = 'all' | 'wins' | 'losses'
const PAGE_SIZE = 30

function formatDate(timestamp: string) {
  return new Date(timestamp).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

/* ── Page ─────────────────────────────────────────────────────────────── */

export default function PicksPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { isAuthenticated } = useAuthStore()
  usePicksRealtime()

  const [activeTab, setActiveTab] = useState<'pending' | 'history'>('pending')

  /* ── Pending state ── */
  const [sortField, setSortField] = useState<SortField>('edge')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [exitingIds, setExitingIds] = useState<Set<number>>(new Set())

  /* ── History state ── */
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all')
  const [page, setPage] = useState(1)
  const [gradePickId, setGradePickId] = useState<number | null>(null)
  const [gradeValue, setGradeValue] = useState('')
  const [copiedId, setCopiedId] = useState<number | null>(null)

  /* ── Queries ── */
  const { data: pendingPicks = [], isLoading: pendingLoading, refetch: refetchPending } = useQuery({
    queryKey: ['pending-picks'],
    queryFn: () => getPicks(true),
    staleTime: 1000 * 30,
    enabled: isAuthenticated,
  })

  const { data: allPicks = [], isLoading: allPicksLoading } = useQuery({
    queryKey: ['picks', false],
    queryFn: () => getPicks(false),
    enabled: isAuthenticated && activeTab === 'history',
  })

  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    enabled: isAuthenticated && activeTab === 'history',
  })

  const { data: profitData } = useQuery({
    queryKey: ['cumulative-profit'],
    queryFn: getCumulativeProfit,
    enabled: isAuthenticated && activeTab === 'history',
  })

  const { data: calibration } = useQuery({
    queryKey: ['calibration-stats'],
    queryFn: getCalibrationStats,
    enabled: isAuthenticated && activeTab === 'history',
    staleTime: 1000 * 60 * 5,
  })

  /* ── Pending derived ── */
  const sortedPending = useMemo(
    () => sortPicks(pendingPicks, sortField, sortDir),
    [pendingPicks, sortField, sortDir],
  )

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir(field === 'team' ? 'asc' : 'desc')
    }
  }

  const handleDeletePending = async (id: number) => {
    setExitingIds(prev => { const n = new Set(prev); n.add(id); return n })
    setDeletingId(id)
    await new Promise(r => setTimeout(r, 220))
    try {
      await deletePick(id)
      refetchPending()
    } finally {
      setDeletingId(null)
      setExitingIds(prev => { const n = new Set(prev); n.delete(id); return n })
    }
  }

  /* ── History derived ── */
  const filteredPicks = useMemo(() => {
    if (resultFilter === 'wins') return allPicks.filter(p => p.won === true)
    if (resultFilter === 'losses') return allPicks.filter(p => p.won === false)
    return allPicks
  }, [allPicks, resultFilter])

  const totalPages = Math.max(1, Math.ceil(filteredPicks.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const displayedPicks = filteredPicks.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const handleFilterChange = (f: ResultFilter) => {
    setResultFilter(f)
    setPage(1)
  }

  const gradePickMutation = useMutation({
    mutationFn: ({ pickId, result }: { pickId: number; result: number }) => gradePick(pickId, result),
    onMutate: async ({ pickId, result }) => {
      await queryClient.cancelQueries({ queryKey: ['picks', false] })
      const previous = queryClient.getQueryData<Pick[]>(['picks', false])
      queryClient.setQueryData<Pick[]>(['picks', false], old =>
        old?.map(p =>
          p.id === pickId ? { ...p, actual_result: result, won: result > p.line } : p,
        ),
      )
      setGradePickId(null)
      setGradeValue('')
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['picks', false], context.previous)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      queryClient.invalidateQueries({ queryKey: ['pending-picks'] })
      queryClient.invalidateQueries({ queryKey: ['performance-stats'] })
      queryClient.invalidateQueries({ queryKey: ['cumulative-profit'] })
      queryClient.invalidateQueries({ queryKey: ['calibration-stats'] })
    },
  })

  const deletePickMutation = useMutation({
    mutationFn: deletePick,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      queryClient.invalidateQueries({ queryKey: ['pending-picks'] })
      queryClient.invalidateQueries({ queryKey: ['performance-stats'] })
    },
  })

  const handleGradePick = (pick: Pick) => {
    const value = parseFloat(gradeValue)
    if (isNaN(value)) return
    gradePickMutation.mutate({ pickId: pick.id, result: value })
  }

  const handleSharePick = async (pick: Pick) => {
    const result = pick.won ? 'WON' : 'LOST'
    const text = [
      `Bettin' Jrys Pick: ${pick.player} ${pick.stat}`,
      `${pick.direction} ${pick.line} (predicted ${pick.prediction.toFixed(1)})`,
      pick.actual_result != null ? `${result} (actual: ${pick.actual_result})` : result,
      `bettin-jrys.com`,
    ].join(' \u2014 ')
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(pick.id)
      setTimeout(() => setCopiedId(null), 2000)
    } catch { /* fallback */ }
  }

  /* ── Quick stats banner ── */
  const winCount = allPicks.filter(p => p.won === true).length
  const lossCount = allPicks.filter(p => p.won === false).length
  const totalGraded = winCount + lossCount
  const winRate = totalGraded > 0 ? (winCount / totalGraded) * 100 : 0

  /* ── Render ─────────────────────────────────────────────────────────── */

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <div className="flex items-start sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">Picks</h1>
            <p className="text-sm text-text-secondary mt-1">
              {activeTab === 'pending'
                ? pendingPicks.length === 0
                  ? 'Save picks from player analysis to track here'
                  : `${pendingPicks.length} pending pick${pendingPicks.length !== 1 ? 's' : ''}`
                : totalGraded > 0
                  ? `${winCount}W - ${lossCount}L · ${winRate.toFixed(1)}% win rate`
                  : 'Track your picks and performance'}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {activeTab === 'pending' && (
              <button onClick={() => refetchPending()} className="btn btn-secondary text-sm" title="Refresh picks">
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5 mt-4 w-fit">
          <button
            onClick={() => setActiveTab('pending')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'pending' ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Pending
            {pendingPicks.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-accent text-white rounded-full px-1.5 py-0.5 font-mono">
                {pendingPicks.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'history' ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            History
          </button>
        </div>
      </section>

      {/* ── PENDING TAB ── */}
      {activeTab === 'pending' && (
        <>
          {pendingLoading ? (
            <div className="card p-16 text-center">
              <Loader2 className="w-5 h-5 text-accent animate-spin mx-auto mb-3" />
              <div className="text-sm text-text-muted">Loading picks...</div>
            </div>
          ) : pendingPicks.length === 0 ? (
            <div className="card p-16 text-center">
              <BookmarkCheck className="w-10 h-10 text-text-muted mx-auto mb-4 opacity-40" />
              <h2 className="text-lg font-semibold text-text-primary mb-2">No Pending Picks</h2>
              <p className="text-sm text-text-secondary max-w-sm mx-auto leading-relaxed mb-6">
                Evaluate a player's lines and hit <span className="text-accent font-medium">Save Pick</span> to add it here.
              </p>
              <button onClick={() => navigate('/app')} className="btn btn-primary">
                Find Players
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Sort bar */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] text-text-muted uppercase tracking-wider mr-1">Sort:</span>
                {SORT_OPTIONS.map(({ field, label }) => {
                  const active = sortField === field
                  const Icon = active ? (sortDir === 'desc' ? ArrowDown : ArrowUp) : ArrowUpDown
                  return (
                    <button
                      key={field}
                      onClick={() => handleSort(field)}
                      className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 ${
                        active
                          ? 'bg-accent text-white scale-[1.05] shadow-sm'
                          : 'bg-bg-secondary text-text-muted hover:text-text-primary hover:bg-bg-elevated'
                      }`}
                    >
                      {label}
                      <Icon className="w-3 h-3" />
                    </button>
                  )
                })}
              </div>

              {sortedPending.map((pick, index) => {
                const isOver = pick.direction === 'OVER'
                const prob = hitProb(pick)
                const headshotSrc = getHeadshotUrl(pick.headshot_url, pick.player_id ?? 0)
                const isExiting = exitingIds.has(pick.id)

                return (
                  <div
                    key={pick.id}
                    className={`card p-4 border-l-2 transition-all duration-150 animate-slide-up ${
                      isOver ? 'border-l-accent-success' : 'border-l-accent-danger'
                    } ${isExiting ? 'pointer-events-none' : ''}`}
                    style={{
                      animationDelay: isExiting ? '0ms' : `${index * 60}ms`,
                      animation: isExiting ? 'slide-out 0.2s ease-in forwards' : undefined,
                    }}
                  >
                    <div className="flex items-start gap-2 sm:gap-3">
                      {/* Player headshot */}
                      <img
                        src={headshotSrc}
                        alt={pick.player}
                        className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl object-cover bg-bg-secondary flex-shrink-0 shadow-sm hidden xs:block"
                        onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
                      />

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span className="font-medium text-text-primary truncate text-sm sm:text-base">{pick.player}</span>
                          {pick.team_abbrev && (
                            <span className="text-[10px] text-text-muted font-mono">{pick.team_abbrev}</span>
                          )}
                          <span className={`pill text-[10px] ${isOver ? 'pill-over' : 'pill-under'}`}>
                            {pick.direction}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-x-3 gap-y-1 sm:gap-4 text-xs sm:text-sm">
                          <div>
                            <span className="text-text-muted">Stat: </span>
                            <span className="font-mono font-semibold text-text-primary">{pick.stat}</span>
                          </div>
                          <div>
                            <span className="text-text-muted">Line: </span>
                            <span className="font-mono font-semibold text-text-primary">{pick.line}</span>
                          </div>
                          <div>
                            <span className="text-text-muted">Pred: </span>
                            <span className={`font-mono font-semibold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
                              {pick.prediction.toFixed(1)}
                            </span>
                          </div>
                          <div>
                            <span className="text-text-muted">Edge: </span>
                            <span className="font-mono font-semibold text-text-primary">
                              {pick.edge > 0 ? '+' : ''}{pick.edge.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                        {pick.opponent && (
                          <div className="text-[11px] sm:text-xs text-text-muted mt-1">
                            vs {pick.opponent}{pick.game_date ? ` \u00b7 ${pick.game_date}` : ''}
                          </div>
                        )}
                      </div>

                      <div className="flex flex-col items-end gap-2 flex-shrink-0">
                        <button
                          onClick={() => handleDeletePending(pick.id)}
                          disabled={deletingId === pick.id}
                          className="p-1.5 rounded text-text-muted hover:text-accent-danger transition-colors"
                          title="Remove pick"
                        >
                          {deletingId === pick.id ? (
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                        <div className="text-right">
                          <div className="text-[10px] text-text-muted uppercase tracking-wider">Hit prob</div>
                          <div className="font-mono text-sm font-semibold text-text-primary">
                            {prob.toFixed(0)}%
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Mini probability bar */}
                    <div className="mt-3 h-1 bg-bg-elevated rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          isOver ? 'bg-accent-success' : 'bg-accent-danger'
                        }`}
                        style={{ width: `${prob}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* ── HISTORY TAB ── */}
      {activeTab === 'history' && (
        <>
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
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
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

          {/* Model Calibration */}
          {calibration && calibration.sample_size > 0 && (
            <section className="space-y-3">
              <h2 className="text-base font-semibold text-text-primary tracking-tight">Model Calibration</h2>

              {/* Brier Score Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="card p-4 text-center">
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Brier Score</div>
                  <div className={`font-mono text-lg font-semibold ${
                    (calibration.brier_score ?? 1) < 0.22 ? 'text-accent-success' : (calibration.brier_score ?? 1) < 0.25 ? 'text-accent' : 'text-accent-danger'
                  }`}>
                    {calibration.brier_score?.toFixed(4) ?? '-'}
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">lower = better</div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Skill Score</div>
                  <div className={`font-mono text-lg font-semibold ${
                    (calibration.brier_skill_score ?? 0) > 0.05 ? 'text-accent-success' : (calibration.brier_skill_score ?? 0) > 0 ? 'text-accent' : 'text-accent-danger'
                  }`}>
                    {calibration.brier_skill_score != null ? (calibration.brier_skill_score > 0 ? '+' : '') + calibration.brier_skill_score.toFixed(4) : '-'}
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">vs always guessing base rate</div>
                </div>
                {calibration.decomposition && (
                  <>
                    <div className="card p-4 text-center">
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Reliability</div>
                      <div className={`font-mono text-lg font-semibold ${
                        calibration.decomposition.reliability < 0.02 ? 'text-accent-success' : calibration.decomposition.reliability < 0.05 ? 'text-accent' : 'text-accent-danger'
                      }`}>
                        {calibration.decomposition.reliability.toFixed(4)}
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5">calibration error (lower = better)</div>
                    </div>
                    <div className="card p-4 text-center">
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Resolution</div>
                      <div className={`font-mono text-lg font-semibold ${
                        calibration.decomposition.resolution > 0.05 ? 'text-accent-success' : calibration.decomposition.resolution > 0.02 ? 'text-accent' : 'text-text-secondary'
                      }`}>
                        {calibration.decomposition.resolution.toFixed(4)}
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5">discrimination (higher = better)</div>
                    </div>
                  </>
                )}
              </div>

              {/* Calibration Curve */}
              {calibration.calibration_curve.length > 0 && (
                <div className="card p-4 sm:p-6">
                  <h3 className="text-sm font-semibold text-text-primary mb-1 tracking-tight">Reliability Diagram</h3>
                  <p className="text-[11px] text-text-muted mb-4">Perfect calibration follows the diagonal. Below = overconfident, above = underconfident.</p>
                  <div className="h-52 sm:h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                        <XAxis
                          dataKey="predicted"
                          name="Predicted"
                          type="number"
                          domain={[45, 95]}
                          stroke="var(--text-muted)"
                          fontSize={11}
                          label={{ value: 'Predicted Win %', position: 'insideBottom', offset: -12, style: { fontSize: 10, fill: 'var(--text-muted)' } }}
                        />
                        <YAxis
                          dataKey="actual"
                          name="Actual"
                          type="number"
                          domain={[0, 100]}
                          stroke="var(--text-muted)"
                          fontSize={11}
                          label={{ value: 'Actual Win %', angle: -90, position: 'insideLeft', offset: 10, style: { fontSize: 10, fill: 'var(--text-muted)' } }}
                        />
                        <ZAxis dataKey="count" range={[40, 200]} name="Picks" />
                        <Tooltip
                          contentStyle={{
                            background: 'var(--bg-elevated)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: '8px',
                            fontSize: '12px',
                          }}
                          formatter={(value: number, name: string) => {
                            if (name === 'Predicted') return [`${value.toFixed(1)}%`, 'Predicted']
                            if (name === 'Actual') return [`${value.toFixed(1)}%`, 'Actual']
                            return [value, name]
                          }}
                        />
                        <ReferenceLine
                          segment={[{ x: 45, y: 45 }, { x: 95, y: 95 }]}
                          stroke="var(--text-muted)"
                          strokeDasharray="5 5"
                          strokeWidth={1}
                        />
                        <Scatter
                          data={calibration.calibration_curve}
                          fill="var(--accent)"
                          stroke="var(--accent)"
                          strokeWidth={1}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Per-Stat Brier Scores */}
              {Object.keys(calibration.by_stat).length > 0 && (
                <div className="card p-4 sm:p-6">
                  <h3 className="text-sm font-semibold text-text-primary mb-4 tracking-tight">Brier Score by Stat</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-5">
                    {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
                      const data = calibration.by_stat[stat]
                      if (!data) return null
                      return (
                        <div key={stat} className="text-center">
                          <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1.5">{stat}</div>
                          <div className={`font-mono text-xl font-bold ${
                            data.brier_score < 0.22 ? 'text-accent-success' : data.brier_score < 0.25 ? 'text-accent' : 'text-accent-danger'
                          }`}>
                            {data.brier_score.toFixed(3)}
                          </div>
                          <div className="text-[10px] text-text-muted mt-0.5">
                            Skill: {data.skill_score > 0 ? '+' : ''}{data.skill_score.toFixed(3)}
                          </div>
                          <div className="text-xs text-text-secondary mt-0.5">n={data.sample_size}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* CLV Section (when data available) */}
              {calibration.clv && (
                <div className="card p-4 sm:p-6">
                  <h3 className="text-sm font-semibold text-text-primary mb-4 tracking-tight">Closing Line Value</h3>
                  <div className="grid grid-cols-3 gap-5">
                    <div className="text-center">
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Avg CLV</div>
                      <div className={`font-mono text-xl font-bold ${
                        calibration.clv.avg_clv > 0 ? 'text-accent-success' : 'text-accent-danger'
                      }`}>
                        {calibration.clv.avg_clv > 0 ? '+' : ''}{calibration.clv.avg_clv.toFixed(2)}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">+CLV Rate</div>
                      <div className={`font-mono text-xl font-bold ${
                        calibration.clv.positive_clv_rate > 50 ? 'text-accent-success' : 'text-accent-danger'
                      }`}>
                        {calibration.clv.positive_clv_rate.toFixed(1)}%
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Sample</div>
                      <div className="font-mono text-xl font-bold text-text-primary">
                        {calibration.clv.sample_size}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <p className="text-[10px] text-text-muted text-center">
                Based on {calibration.sample_size} graded picks with probability data
              </p>
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

          {/* Picks List */}
          <section className="card overflow-hidden">
            <div className="p-4 sm:p-5 border-b border-border-subtle space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-text-primary tracking-tight">Pick History</h2>
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
              </div>
              {totalPages > 1 && (
                <div className="flex items-center justify-end gap-1.5 text-xs text-text-muted">
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

            {allPicksLoading ? (
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
                          <td>
                            <div className="flex items-center gap-2">
                              <img
                                src={getHeadshotUrl(pick.headshot_url, pick.player_id ?? 0)}
                                alt={pick.player}
                                className="w-7 h-7 rounded-lg object-cover bg-bg-secondary flex-shrink-0"
                                onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
                              />
                              <span className="font-medium text-text-primary text-sm">{pick.player}</span>
                            </div>
                          </td>
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
                            <div className="flex items-center gap-2">
                              {pick.won !== null && pick.won !== undefined && !pick.voided && (
                                <button
                                  onClick={() => handleSharePick(pick)}
                                  className="text-text-muted hover:text-accent transition-colors"
                                  title={copiedId === pick.id ? 'Copied!' : 'Share pick'}
                                >
                                  {copiedId === pick.id ? <Check className="w-3.5 h-3.5 text-accent-success" /> : <Share2 className="w-3.5 h-3.5" />}
                                </button>
                              )}
                              <button
                                onClick={() => { if (confirm('Delete this pick?')) deletePickMutation.mutate(pick.id) }}
                                className="text-text-muted hover:text-accent-danger transition-colors"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
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
                          <div className="flex items-center gap-2">
                            <img
                              src={getHeadshotUrl(pick.headshot_url, pick.player_id ?? 0)}
                              alt={pick.player}
                              className="w-8 h-8 rounded-lg object-cover bg-bg-secondary flex-shrink-0"
                              onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
                            />
                            <div>
                              <div className="font-medium text-text-primary text-sm">{pick.player}</div>
                              <div className="text-[11px] text-text-muted mt-0.5">{formatDate(pick.timestamp)}</div>
                            </div>
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
                            {pick.won !== null && pick.won !== undefined && !pick.voided && (
                              <button
                                onClick={() => handleSharePick(pick)}
                                className="text-text-muted hover:text-accent transition-colors p-1"
                                title={copiedId === pick.id ? 'Copied!' : 'Share pick'}
                              >
                                {copiedId === pick.id ? <Check className="w-3.5 h-3.5 text-accent-success" /> : <Share2 className="w-3.5 h-3.5" />}
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
        </>
      )}
    </div>
  )
}
