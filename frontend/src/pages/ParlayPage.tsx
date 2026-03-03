import { useState, useMemo } from 'react'
import { X, Trash2, RefreshCw, BookmarkCheck, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { getPicks, deletePick, Pick } from '../api/client'
import { useNavigate } from 'react-router-dom'
import { getNbaHeadshotUrl } from '../utils/nba'

const DECIMAL_PER_LEG = 1.909 // standard -110

type SortField = 'edge' | 'team' | 'PTS' | 'REB' | 'AST' | 'PRA'
type SortDir = 'asc' | 'desc'

/** Derive hit-probability for the saved direction from stored data.
 *  Uses prob_over if available; otherwise estimates from edge%.
 *  Capped at 85% — no single-game prop is a near-certainty. */
function hitProb(pick: Pick): number {
  const isOver = pick.direction === 'OVER'
  if (pick.prob_over != null) {
    const raw = isOver ? pick.prob_over : 100 - pick.prob_over
    return Math.min(85, Math.max(15, raw))
  }
  // Rough estimate: 50% base + 1.5× edge% (edge is always positive for the pick direction)
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
      // Sort by stat type: picks matching the stat come first, rest alphabetical
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

export default function ParlayPage() {
  const navigate = useNavigate()
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [exitingIds, setExitingIds] = useState<Set<number>>(new Set())
  const [sortField, setSortField] = useState<SortField>('edge')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: picks = [], isLoading, refetch } = useQuery({
    queryKey: ['pending-picks'],
    queryFn: () => getPicks(30, true),
    staleTime: 1000 * 30,
  })

  const sortedPicks = useMemo(() => sortPicks(picks, sortField, sortDir), [picks, sortField, sortDir])

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      // Edge and stat sorts default desc (highest first); team defaults asc (A→Z)
      setSortDir(field === 'team' ? 'asc' : 'desc')
    }
  }

  const toggle = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleDelete = async (id: number) => {
    setExitingIds(prev => { const n = new Set(prev); n.add(id); return n })
    setDeletingId(id)
    await new Promise(r => setTimeout(r, 220))
    try {
      await deletePick(id)
      setSelectedIds(prev => { const n = new Set(prev); n.delete(id); return n })
      refetch()
    } finally {
      setDeletingId(null)
      setExitingIds(prev => { const n = new Set(prev); n.delete(id); return n })
    }
  }

  const selected = picks.filter(p => selectedIds.has(p.id))

  const combinedProb =
    selected.length > 0
      ? selected.reduce((acc, p) => acc * (hitProb(p) / 100), 1) * 100
      : 0

  const parlayPayout = selected.length > 0 ? Math.pow(DECIMAL_PER_LEG, selected.length) : 0
  const expectedValue = selected.length > 0 ? (combinedProb / 100) * parlayPayout - 1 : 0
  const kellyPct =
    selected.length > 0 && parlayPayout > 1
      ? (((combinedProb / 100) * parlayPayout - 1) / (parlayPayout - 1)) * 100
      : 0

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <div className="flex items-start sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">Parlay Builder</h1>
            <p className="text-sm text-text-secondary mt-1">
              {picks.length === 0
                ? 'Save picks from player analysis to build a parlay'
                : `${picks.length} pending pick${picks.length !== 1 ? 's' : ''} · ${selected.length} selected`}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {selectedIds.size > 0 && (
              <button
                onClick={() => setSelectedIds(new Set())}
                className="btn btn-secondary text-sm"
              >
                <X className="w-4 h-4" />
                <span className="hidden sm:inline">Clear Selection</span>
              </button>
            )}
            <button onClick={() => refetch()} className="btn btn-secondary text-sm" title="Refresh">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>

      {isLoading ? (
        <div className="card p-16 text-center">
          <div className="text-sm text-text-muted">Loading picks…</div>
        </div>
      ) : picks.length === 0 ? (
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Summary panel - shown first on mobile when picks selected */}
          {selected.length > 0 && (
            <div className="lg:hidden space-y-4">
              <div className="card p-4 space-y-3">
                <h2 className="text-sm font-semibold text-text-primary tracking-tight">Parlay Summary</h2>
                <div className="flex items-center gap-6">
                  <div>
                    <div className="text-[10px] text-text-muted uppercase tracking-wider">Legs</div>
                    <div className="font-mono text-lg font-bold text-text-primary">{selected.length}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-text-muted uppercase tracking-wider">Prob</div>
                    <div className={`font-mono text-lg font-bold ${combinedProb >= 20 ? 'text-accent-success' : combinedProb >= 10 ? 'text-accent' : 'text-accent-danger'}`}>
                      {combinedProb.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-text-muted uppercase tracking-wider">Payout</div>
                    <div className="font-mono text-lg font-bold text-text-primary">{parlayPayout.toFixed(2)}x</div>
                  </div>
                  <div title="Expected value as a percentage of your stake. Positive = profitable long-term, negative = losing.">
                    <div className="text-[10px] text-text-muted uppercase tracking-wider cursor-help">EV (?)</div>
                    <div className={`font-mono text-lg font-bold ${expectedValue > 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
                      {expectedValue > 0 ? '+' : ''}{(expectedValue * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Pick list */}
          <div className="lg:col-span-2 space-y-3">
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

            <div className="text-[11px] text-text-muted uppercase tracking-wider px-1">
              Toggle picks to include in parlay
            </div>

            {sortedPicks.map((pick, index) => {
              const isOver = pick.direction === 'OVER'
              const inParlay = selectedIds.has(pick.id)
              const prob = hitProb(pick)
              const headshotId = pick.player_id ?? 0
              const isExiting = exitingIds.has(pick.id)

              return (
                <div
                  key={pick.id}
                  onClick={() => toggle(pick.id)}
                  className={`relative card p-4 border-l-2 cursor-pointer transition-all duration-150 animate-slide-up ${
                    isOver ? 'border-l-accent-success' : 'border-l-accent-danger'
                  } ${inParlay ? 'ring-1 ring-accent/30 bg-accent/[0.02]' : 'opacity-80 hover:opacity-100'} ${
                    isExiting ? 'pointer-events-none' : ''
                  }`}
                  style={{
                    animationDelay: isExiting ? '0ms' : `${index * 60}ms`,
                    animation: isExiting ? 'slide-out 0.2s ease-in forwards' : undefined,
                  }}
                >
                  {inParlay && (
                    <div
                      key={`ring-${pick.id}-${selectedIds.size}`}
                      className="absolute inset-0 rounded-xl ring-1 ring-accent/40 animate-pop pointer-events-none"
                    />
                  )}
                  <div className="flex items-start gap-2 sm:gap-3">
                    {/* Checkbox */}
                    <div className={`mt-1 w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center transition-colors ${
                      inParlay ? 'bg-accent border-accent' : 'border-border-subtle'
                    }`}>
                      {inParlay && (
                        <svg className="w-2.5 h-2.5 text-white animate-check-in" fill="none" viewBox="0 0 10 8">
                          <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      )}
                    </div>

                    {/* Player headshot - hidden on very small screens */}
                    <img
                      src={getNbaHeadshotUrl(headshotId)}
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
                          vs {pick.opponent}{pick.game_date ? ` · ${pick.game_date}` : ''}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      <button
                        onClick={e => { e.stopPropagation(); handleDelete(pick.id) }}
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

          {/* Summary panel - desktop sidebar */}
          <div className="hidden lg:block space-y-4">
            <div className="card p-5 space-y-4">
              <h2 className="text-base font-semibold text-text-primary tracking-tight">Parlay Summary</h2>

              {selected.length === 0 ? (
                <p className="text-sm text-text-muted">Select picks on the left to calculate parlay odds.</p>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">
                        Legs <span className="normal-case font-normal text-text-muted">(max 8)</span>
                      </div>
                      <div key={`legs-${selected.length}`} className="font-mono text-2xl font-bold text-text-primary animate-pop">{selected.length}</div>
                    </div>
                    <div>
                      <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Combined Prob</div>
                      <div key={`prob-${combinedProb.toFixed(1)}`} className={`font-mono text-2xl font-bold animate-pop ${combinedProb >= 20 ? 'text-accent-success' : combinedProb >= 10 ? 'text-accent' : 'text-accent-danger'}`}>
                        {combinedProb.toFixed(1)}%
                      </div>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-border-subtle space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-text-muted">Payout (at -110 ea)</span>
                      <span key={`payout-${parlayPayout.toFixed(2)}`} className="font-mono font-semibold text-text-primary animate-pop">
                        {parlayPayout.toFixed(2)}x
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-text-muted">Expected Value</span>
                      <span key={`ev-${expectedValue.toFixed(3)}`} className={`font-mono font-semibold animate-pop ${expectedValue > 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
                        {expectedValue > 0 ? '+' : ''}{(expectedValue * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-text-muted">Kelly %</span>
                      <span key={`kelly-${kellyPct.toFixed(1)}`} className={`font-mono font-semibold animate-pop ${kellyPct > 0 ? 'text-accent' : 'text-text-muted'}`}>
                        {kellyPct > 0 ? kellyPct.toFixed(1) : '0.0'}%
                      </span>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Leg breakdown */}
            {selected.length > 0 && (
              <div className="card p-4">
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-3">Selected Legs</div>
                <div className="space-y-2">
                  {selected.map((pick, legIndex) => {
                    const prob = hitProb(pick)
                    return (
                      <div key={pick.id} className="space-y-1">
                        <div className="flex items-center gap-2 text-xs">
                          <img
                            src={getNbaHeadshotUrl(pick.player_id ?? 0)}
                            alt={pick.player}
                            className="w-5 h-5 rounded-full object-cover bg-bg-secondary flex-shrink-0"
                            onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
                          />
                          <span className="text-text-secondary truncate max-w-[110px]">
                            {pick.player} {pick.stat} {pick.direction}
                          </span>
                          <span className="text-text-muted font-mono ml-auto flex-shrink-0">{prob.toFixed(0)}%</span>
                        </div>
                        <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              pick.direction === 'OVER' ? 'bg-accent-success' : 'bg-accent-danger'
                            }`}
                            style={{ width: `${prob}%`, transitionDelay: `${legIndex * 80}ms` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
