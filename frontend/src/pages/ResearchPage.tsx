import { useState, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Minus,
  Loader2,
  AlertCircle,
  BarChart3,
  Home,
  Plane,
  Zap,
  Shield,
  ShieldOff,
  RefreshCw,
  FlaskConical,
} from 'lucide-react'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts'
import { getPlayerResearch, StatSplits, FullGameLogEntry } from '../api/client'
import { getNbaHeadshotUrl } from '../utils/nba'
import PlayerSearch from '../components/PlayerSearch'

// ─── Constants ──────────────────────────────────────────────────────────────

const STATS = ['PTS', 'REB', 'AST', 'PRA'] as const
type Stat = typeof STATS[number]

const STAT_LABELS: Record<Stat, string> = {
  PTS: 'Points',
  REB: 'Rebounds',
  AST: 'Assists',
  PRA: 'PRA',
}

const TABS = ['Overview', 'Game Log', 'Chart', 'Splits', 'Matchup'] as const
type Tab = typeof TABS[number]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getStatValue(entry: FullGameLogEntry | StatSplits, stat: Stat): number {
  if (stat === 'PTS') return (entry as FullGameLogEntry).pts ?? (entry as StatSplits).pts
  if (stat === 'REB') return (entry as FullGameLogEntry).reb ?? (entry as StatSplits).reb
  if (stat === 'AST') return (entry as FullGameLogEntry).ast ?? (entry as StatSplits).ast
  if (stat === 'PRA') return (entry as FullGameLogEntry).pra ?? (entry as StatSplits).pra
  return 0
}

function delta(val: number, base: number): number {
  return Math.round((val - base) * 10) / 10
}

function hitColor(pct: number): string {
  if (pct >= 60) return 'var(--accent-success)'
  if (pct >= 40) return '#E6A817'
  return 'var(--accent-danger)'
}

// ─── Sub-components ──────────────────────────────────────────────────────────

// Hit rate progress card
function HitRateCard({
  label,
  hits,
  total,
}: {
  label: string
  hits: number
  total: number
}) {
  const pct = total > 0 ? Math.round((hits / total) * 100) : 0
  const color = hitColor(pct)

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{ background: 'var(--bg-elevated)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <div className="flex items-baseline gap-1.5">
        <span
          className="text-2xl font-bold font-mono leading-none"
          style={{ color: 'var(--text-primary)' }}
        >
          {hits}/{total}
        </span>
        <span className="text-base font-semibold font-mono" style={{ color }}>
          ({pct}%)
        </span>
      </div>
      {/* Progress bar */}
      <div
        className="w-full h-2 rounded-full overflow-hidden"
        style={{ background: 'rgba(255,255,255,0.06)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
        OVER line
      </span>
    </div>
  )
}

// Rolling avg cell with delta arrow
function RollCell({
  value,
  seasonAvg,
}: {
  value: number
  seasonAvg: number
}) {
  const d = delta(value, seasonAvg)
  const isUp = d > 0
  const isFlat = d === 0
  const Arrow = isFlat ? Minus : isUp ? TrendingUp : TrendingDown
  const arrowColor = isFlat
    ? 'var(--text-muted)'
    : isUp
    ? 'var(--accent-success)'
    : 'var(--accent-danger)'

  return (
    <td className="px-3 py-2 text-center">
      <div className="flex flex-col items-center gap-0.5">
        <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {value.toFixed(1)}
        </span>
        <span className="flex items-center gap-0.5 text-[10px] font-medium" style={{ color: arrowColor }}>
          <Arrow className="w-2.5 h-2.5" strokeWidth={2.5} />
          {d > 0 ? `+${d}` : d}
        </span>
      </div>
    </td>
  )
}

// Split card
function SplitCard({
  title,
  icon: Icon,
  splits,
  seasonAvg,
  stat,
}: {
  title: string
  icon: React.ElementType
  splits: StatSplits
  seasonAvg: number
  stat: Stat
}) {
  const val = getStatValue(splits, stat)
  const d = delta(val, seasonAvg)
  const isUp = d > 0
  const hasData = splits.games > 0
  const Arrow = isUp ? TrendingUp : TrendingDown
  const arrowColor = isUp ? 'var(--accent-success)' : 'var(--accent-danger)'

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{ background: 'var(--bg-elevated)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Icon className="w-3.5 h-3.5" style={{ color: 'var(--text-muted)' }} />
          <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
            {title}
          </span>
        </div>
        <span
          className="text-[11px] rounded px-1.5 py-0.5 font-mono"
          style={{
            background: 'rgba(255,255,255,0.04)',
            color: 'var(--text-muted)',
          }}
        >
          {hasData ? `${splits.games}G` : 'N/A'}
        </span>
      </div>
      {hasData ? (
        <>
          <span
            className="text-2xl font-bold font-mono leading-none"
            style={{ color: 'var(--text-primary)' }}
          >
            {val.toFixed(1)}
          </span>
          <div className="flex items-center gap-1" style={{ color: arrowColor }}>
            <Arrow className="w-3 h-3" strokeWidth={2.5} />
            <span className="text-xs font-semibold">
              {d > 0 ? `+${d}` : d} vs season
            </span>
          </div>
        </>
      ) : (
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
          No data
        </span>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ResearchPage() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const decoded = playerName ? decodeURIComponent(playerName) : ''

  const [activeTab, setActiveTab] = useState<Tab>('Overview')
  const [activeStat, setActiveStat] = useState<Stat>('PTS')
  const [lineInput, setLineInput] = useState('')

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['player-research', decoded],
    queryFn: () => getPlayerResearch(decoded),
    enabled: !!decoded,
    staleTime: 1000 * 30, // 30 seconds
    retry: 1,
  })

  // ── Derived values ──────────────────────────────────────────────────────────

  const parsedLine = useMemo(() => {
    const n = parseFloat(lineInput)
    return isNaN(n) ? null : n
  }, [lineInput])

  const seasonAvg = useMemo(
    () => (data ? getStatValue(data.season_averages, activeStat) : 0),
    [data, activeStat]
  )

  // Hit rates computed from game_log
  const hitRates = useMemo(() => {
    if (!data || parsedLine === null) return null
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

  // Chart data with rolling average
  const chartData = useMemo(() => {
    if (!data) return []
    const log = [...data.game_log].reverse() // chronological order for chart
    return log.map((g, i, arr) => {
      const val = getStatValue(g, activeStat)
      const window = arr.slice(Math.max(0, i - 9), i + 1)
      const rollAvg = +(
        window.reduce((sum, r) => sum + getStatValue(r, activeStat), 0) / window.length
      ).toFixed(1)
      return {
        game_date: g.game_date,
        opponent: g.opponent,
        value: val,
        rollAvg,
        isOver: parsedLine !== null ? val >= parsedLine : null,
      }
    })
  }, [data, activeStat, parsedLine])

  // ── No player selected state ───────────────────────────────────────────────

  if (!decoded) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-6">
        <FlaskConical className="w-10 h-10" style={{ color: 'var(--accent)' }} />
        <div className="text-center">
          <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
            Research Mode
          </h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Search for a player to explore their stats and matchup data
          </p>
        </div>
        <div className="w-full max-w-sm">
          <PlayerSearch
            autoFocus
            placeholder="Search players…"
            onSelect={(player) => navigate(`/research/${encodeURIComponent(player.player_name)}`)}
          />
        </div>
      </div>
    )
  }

  // ── Loading / error states ─────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="w-8 h-8 animate-spin" style={{ color: 'var(--accent)' }} />
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Loading research data…
        </p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <AlertCircle className="w-8 h-8" style={{ color: 'var(--accent-danger)' }} />
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Could not load research data for{' '}
          <span style={{ color: 'var(--accent)' }}>{decoded}</span>
        </p>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg btn btn-secondary"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    )
  }

  const rolling = data.rolling_averages

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-6 pb-10">

      {/* ── Header ── */}
      <div className="flex flex-col gap-4">
        {/* Back + search */}
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 text-sm transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back</span>
          </button>
          <div className="flex-1 max-w-xs">
            <PlayerSearch
              onSelect={(player) => navigate(`/research/${encodeURIComponent(player.player_name)}`)}
              placeholder="Switch player…"
            />
          </div>
        </div>

        {/* Player info row */}
        <div className="card p-4 flex items-center gap-4">
          <img
            src={getNbaHeadshotUrl(data.player_id)}
            alt={data.player_name}
            className="w-14 h-14 rounded-full object-cover bg-bg-tertiary flex-shrink-0"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-text-primary leading-tight truncate">
                {data.player_name}
              </h1>
              {data.team_abbrev && (
                <span
                  className="text-xs font-mono px-2 py-0.5 rounded"
                  style={{
                    background: 'var(--accent-muted)',
                    color: 'var(--accent)',
                  }}
                >
                  {data.team_abbrev}
                </span>
              )}
              <span
                className="flex items-center gap-1 text-xs px-2 py-0.5 rounded"
                style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)' }}
              >
                <FlaskConical className="w-3 h-3" />
                Research Mode
              </span>
            </div>
            {data.next_game && (
              <p className="text-sm mt-1 truncate" style={{ color: 'var(--text-secondary)' }}>
                {data.next_game.matchup} · {data.next_game.game_date}
                {data.opponent_context && (
                  <span style={{ color: 'var(--text-muted)' }}>
                    {' '}· {data.opponent_context.def_rank}
                  </span>
                )}
              </p>
            )}
          </div>
          <Link
            to={`/player/${encodeURIComponent(data.player_name)}`}
            className="btn btn-primary text-xs px-3 py-1.5 flex-shrink-0 hidden sm:flex items-center gap-1.5"
          >
            <Zap className="w-3.5 h-3.5" />
            ML Predict
          </Link>
        </div>
      </div>

      {/* ── Stat selector + Line input ── */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        {/* Stat pills */}
        <div className="flex gap-2">
          {STATS.map((s) => (
            <button
              key={s}
              onClick={() => setActiveStat(s)}
              className="px-3.5 py-1.5 rounded-lg text-sm font-semibold font-mono transition-all duration-150"
              style={
                activeStat === s
                  ? { background: 'var(--accent)', color: '#09090B' }
                  : {
                      background: 'var(--bg-elevated)',
                      color: 'var(--text-muted)',
                      border: '1px solid rgba(255,255,255,0.06)',
                    }
              }
            >
              {s}
            </button>
          ))}
        </div>

        {/* Line input */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
            Line to analyze:
          </label>
          <input
            type="number"
            step="0.5"
            min="0.5"
            placeholder="e.g. 25.5"
            value={lineInput}
            onChange={(e) => {
              const val = e.target.value
              if (val === '' || parseFloat(val) > 0) setLineInput(val)
            }}
            className="w-24 px-3 py-1.5 rounded-lg text-sm font-mono text-center bg-bg-elevated border border-border-subtle text-text-primary focus:outline-none focus:border-accent transition-colors"
          />
          {parsedLine !== null && (
            <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: 'rgba(201,168,124,0.1)', color: 'var(--accent)' }}>
              {parsedLine}
            </span>
          )}
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-1 overflow-x-auto pb-1 -mb-1 no-scrollbar">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="whitespace-nowrap px-4 py-2 text-sm font-medium rounded-lg transition-all duration-150 flex-shrink-0"
            style={
              activeTab === tab
                ? { background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid rgba(255,255,255,0.10)' }
                : { color: 'var(--text-muted)' }
            }
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ════════════════════════ TAB CONTENT ════════════════════════ */}

      {/* ── Overview ── */}
      {activeTab === 'Overview' && (
        <div className="flex flex-col gap-6">

          {/* Hit Rates */}
          {parsedLine !== null && hitRates ? (
            <div>
              <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
                Hit Rate — {STAT_LABELS[activeStat]} over {parsedLine}
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {hitRates.map((hr) => (
                  <HitRateCard key={hr.label} {...hr} />
                ))}
              </div>
            </div>
          ) : (
            <div
              className="rounded-xl p-4 flex items-center gap-3 border"
              style={{
                background: 'rgba(201,168,124,0.05)',
                borderColor: 'rgba(201,168,124,0.15)',
              }}
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
            <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
              Rolling Averages
            </h2>
            <div className="card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                      <th className="px-3 py-2.5 text-left text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
                        Stat
                      </th>
                      {(['L3', 'L5', 'L10', 'L15', 'L20'] as const).map((w) => (
                        <th key={w} className="px-3 py-2.5 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
                          {w}
                        </th>
                      ))}
                      <th className="px-3 py-2.5 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
                        Season
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {STATS.map((stat) => {
                      const base = getStatValue(data.season_averages, stat)
                      const isActive = stat === activeStat
                      return (
                        <tr
                          key={stat}
                          onClick={() => setActiveStat(stat)}
                          className="cursor-pointer transition-colors"
                          style={{
                            background: isActive ? 'rgba(201,168,124,0.05)' : undefined,
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
                            >
                              {stat}
                            </span>
                          </td>
                          {(['L3', 'L5', 'L10', 'L15', 'L20'] as const).map((w) => (
                            <RollCell key={w} value={getStatValue(rolling[w], stat)} seasonAvg={base} />
                          ))}
                          <td className="px-3 py-2 text-center">
                            <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                              {base.toFixed(1)}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                    <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td className="px-3 py-2.5">
                        <span className="text-xs font-mono font-semibold" style={{ color: 'var(--text-muted)' }}>MIN</span>
                      </td>
                      {(['L3', 'L5', 'L10', 'L15', 'L20'] as const).map((w) => (
                        <RollCell key={w} value={rolling[w].min} seasonAvg={data.season_averages.min} />
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
                <p className="text-xs font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>
                  NEXT GAME
                </p>
                <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {data.next_game.matchup}
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                  {data.next_game.game_date}
                </p>
              </div>
              {data.opponent_context && (
                <div className="flex gap-4">
                  <div className="text-center">
                    <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Def Rtg</p>
                    <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
                      {data.opponent_context.def_rating}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Pace</p>
                    <p className="text-lg font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
                      {data.opponent_context.pace}
                    </p>
                    <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      {data.opponent_context.pace_desc}
                    </p>
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
      )}

      {/* ── Game Log ── */}
      {activeTab === 'Game Log' && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Last {data.game_log.length} Games
              {parsedLine !== null && (
                <span className="ml-2 text-xs font-normal" style={{ color: 'var(--text-muted)' }}>
                  · cells colored vs line {parsedLine}
                </span>
              )}
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  {['Date', 'Opp', 'H/A', 'MIN', 'PTS', 'REB', 'AST', 'PRA', 'FG%', '3P%', 'FT%', '+/-'].map((h) => (
                    <th
                      key={h}
                      className="px-3 py-2.5 text-xs font-semibold text-center"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.game_log.map((g, i) => {
                  const statVal = getStatValue(g, activeStat)
                  const isOver = parsedLine !== null ? statVal >= parsedLine : null

                  return (
                    <tr
                      key={i}
                      style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                      className="hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-3 py-2 text-center font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                        {g.game_date}
                      </td>
                      <td className="px-3 py-2 text-center text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                        {g.opponent}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {g.is_home ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold" style={{ background: 'rgba(107,191,138,0.12)', color: 'var(--accent-success)' }}>HOME</span>
                        ) : (
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)' }}>AWAY</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                        {g.min.toFixed(0)}
                      </td>
                      {/* PTS */}
                      <StatCell val={g.pts} isHighlighted={activeStat === 'PTS'} isOver={activeStat === 'PTS' ? isOver : null} />
                      {/* REB */}
                      <StatCell val={g.reb} isHighlighted={activeStat === 'REB'} isOver={activeStat === 'REB' ? isOver : null} />
                      {/* AST */}
                      <StatCell val={g.ast} isHighlighted={activeStat === 'AST'} isOver={activeStat === 'AST' ? isOver : null} />
                      {/* PRA */}
                      <StatCell val={g.pra} isHighlighted={activeStat === 'PRA'} isOver={activeStat === 'PRA' ? isOver : null} />
                      <td className="px-3 py-2 text-center font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                        {g.fg_pct != null ? `${(g.fg_pct * 100).toFixed(0)}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                        {g.fg3_pct != null ? `${(g.fg3_pct * 100).toFixed(0)}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                        {g.ft_pct != null ? `${(g.ft_pct * 100).toFixed(0)}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-xs" style={{
                        color: (g.plus_minus ?? 0) > 0 ? 'var(--accent-success)' : (g.plus_minus ?? 0) < 0 ? 'var(--accent-danger)' : 'var(--text-muted)',
                      }}>
                        {g.plus_minus != null ? (g.plus_minus > 0 ? `+${g.plus_minus}` : g.plus_minus) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Chart ── */}
      {activeTab === 'Chart' && (
        <div className="card p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {STAT_LABELS[activeStat]} — Last {chartData.length} Games
              </h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Bars = actual · Line = L10 rolling avg
                {parsedLine !== null && ' · Dashed = line threshold'}
              </p>
            </div>
            {parsedLine !== null && (
              <div
                className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-semibold font-mono"
                style={{ background: 'rgba(230,168,23,0.12)', color: '#E6A817' }}
              >
                <span>Line: {parsedLine}</span>
              </div>
            )}
          </div>

          <ResponsiveContainer width="100%" height={300}>
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
                  if (name === 'value') return [value, STAT_LABELS[activeStat]]
                  if (name === 'rollAvg') return [value, 'L10 Avg']
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
                  label={{
                    value: parsedLine,
                    position: 'right',
                    fill: 'var(--accent-warning)',
                    fontSize: 11,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                />
              )}
              <Bar dataKey="value" radius={[3, 3, 0, 0]} maxBarSize={28}>
                {chartData.map((_entry, index) => (
                  <Cell
                    key={index}
                    fill="rgba(107,191,138,0.75)"
                  />
                ))}
              </Bar>
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

          {/* Legend */}
          <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-muted)' }}>
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
                <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--accent)' }} />
                <span>Actual {STAT_LABELS[activeStat]}</span>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-0.5" style={{ background: 'var(--accent)' }} />
              <span>L10 Rolling Avg</span>
            </div>
            {parsedLine !== null && (
              <div className="flex items-center gap-1.5">
                <div className="w-6 h-0.5 border-dashed border-t" style={{ borderColor: '#E6A817' }} />
                <span>Line ({parsedLine})</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Splits ── */}
      {activeTab === 'Splits' && (
        <div className="flex flex-col gap-5">
          <div>
            <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
              {STAT_LABELS[activeStat]} by Situation
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <SplitCard title="Home" icon={Home} splits={data.home_splits} seasonAvg={seasonAvg} stat={activeStat} />
              <SplitCard title="Away" icon={Plane} splits={data.away_splits} seasonAvg={seasonAvg} stat={activeStat} />
              <SplitCard title="Back-to-Back" icon={Zap} splits={data.b2b_splits} seasonAvg={seasonAvg} stat={activeStat} />
              <SplitCard title="2+ Days Rest" icon={RefreshCw} splits={data.rest_splits} seasonAvg={seasonAvg} stat={activeStat} />
              <SplitCard title="vs Elite D (Top 10)" icon={Shield} splits={data.vs_elite_def} seasonAvg={seasonAvg} stat={activeStat} />
              <SplitCard title="vs Weak D (Bot 10)" icon={ShieldOff} splits={data.vs_weak_def} seasonAvg={seasonAvg} stat={activeStat} />
            </div>
          </div>

          {/* Season average reference */}
          <div
            className="rounded-xl px-4 py-3 flex items-center justify-between"
            style={{ background: 'rgba(201,168,124,0.05)', border: '1px solid rgba(201,168,124,0.12)' }}
          >
            <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
              Season Average ({data.season_averages.games}G sample)
            </span>
            <span className="text-lg font-bold font-mono" style={{ color: 'var(--accent)' }}>
              {seasonAvg.toFixed(1)} {STAT_LABELS[activeStat]}
            </span>
          </div>
        </div>
      )}

      {/* ── Matchup ── */}
      {activeTab === 'Matchup' && (
        <div className="flex flex-col gap-5">
          {data.next_game ? (
            <>
              {/* Opponent defensive context */}
              {data.opponent_context && (
                <div className="card p-5">
                  <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
                    Opponent: {data.next_game.opponent_name || data.next_game.opponent}
                  </h2>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center">
                      <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Def Rating</p>
                      <p className="text-2xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
                        {data.opponent_context.def_rating}
                      </p>
                      <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>pts per 100</p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Pace</p>
                      <p className="text-2xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
                        {data.opponent_context.pace}
                      </p>
                      <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {data.opponent_context.pace_desc}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Defense</p>
                      <p
                        className="text-sm font-bold"
                        style={{
                          color:
                            data.opponent_context.def_rank.includes('Elite') || data.opponent_context.def_rank.includes('Strong')
                              ? 'var(--accent-danger)'
                              : data.opponent_context.def_rank.includes('Weak')
                              ? 'var(--accent-success)'
                              : 'var(--text-secondary)',
                        }}
                      >
                        {data.opponent_context.def_rank}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* H2H History */}
              {data.vs_stats && data.vs_stats.games > 0 ? (
                <div className="card p-5">
                  <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
                    vs {data.next_game.opponent} — Career History ({data.vs_stats.games} games)
                  </h2>
                  <div className="grid grid-cols-4 gap-3">
                    {[
                      { label: 'PTS', val: data.vs_stats.avg_pts },
                      { label: 'REB', val: data.vs_stats.avg_reb },
                      { label: 'AST', val: data.vs_stats.avg_ast },
                      { label: 'PRA', val: +(data.vs_stats.avg_pts + data.vs_stats.avg_reb + data.vs_stats.avg_ast).toFixed(1) },
                    ].map(({ label, val }) => (
                      <div key={label} className="text-center">
                        <p className="text-xs font-mono font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>
                          {label}
                        </p>
                        <p className="text-2xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
                          {val.toFixed(1)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="card p-5 flex items-center gap-3">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--text-muted)' }} />
                  <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                    No head-to-head history found vs {data.next_game.opponent}
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="card p-8 flex flex-col items-center gap-3">
              <BarChart3 className="w-8 h-8" style={{ color: 'var(--text-muted)' }} />
              <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
                No upcoming game found
              </p>
              <p className="text-xs text-center" style={{ color: 'var(--text-muted)' }}>
                Matchup data will appear here once a game is scheduled
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Stat cell helper for the game log table
function StatCell({
  val,
  isHighlighted,
  isOver,
}: {
  val: number
  isHighlighted: boolean
  isOver: boolean | null
}) {
  let color = 'var(--text-secondary)'
  let bg: string | undefined

  if (isHighlighted && isOver !== null) {
    color = isOver ? 'var(--accent-success)' : 'var(--accent-danger)'
    bg = isOver ? 'rgba(107,191,138,0.08)' : 'rgba(212,115,110,0.08)'
  } else if (isHighlighted) {
    color = 'var(--text-primary)'
    bg = 'rgba(201,168,124,0.06)'
  }

  return (
    <td
      className="px-3 py-2 text-center font-mono text-sm font-semibold"
      style={{ color, background: bg }}
    >
      {val.toFixed(1)}
    </td>
  )
}
