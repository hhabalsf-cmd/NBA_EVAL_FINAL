import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Loader2, AlertCircle, Zap, RefreshCw, FlaskConical, ChevronDown,
} from 'lucide-react'
import DOMPurify from 'dompurify'
import { getPlayerResearch } from './api'
import { getPlayerOdds } from '../predictions/api'
import { getNbaHeadshotUrl } from '../../shared/utils/nba'
import PlayerSearch from '../../shared/components/PlayerSearch'
import OverviewTab from './OverviewTab'
import GameLogTab from './GameLogTab'
import ChartTab from './ChartTab'
import SplitsTab from './SplitsTab'
import AnalysisTab from './AnalysisTab'
import MatchupTab from './MatchupTab'
import ModelEdgeCard from './ModelEdgeCard'
import { TABS, PRIMARY_STATS, SECONDARY_STATS, getStatValue, type Stat, type Tab } from './types'

export default function ResearchPage() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const decoded = playerName ? decodeURIComponent(playerName) : ''

  const [activeTab, setActiveTab] = useState<Tab>('Overview')
  const [activeStat, setActiveStat] = useState<Stat>('PTS')
  const [lineInput, setLineInput] = useState('')
  const [showMoreStats, setShowMoreStats] = useState(false)

  // ── Data queries ──────────────────────────────────────────────────────────

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['player-research', decoded],
    queryFn: () => getPlayerResearch(decoded),
    enabled: !!decoded,
    staleTime: 1000 * 30,
    retry: 1,
  })

  const { data: odds } = useQuery({
    queryKey: ['player-odds', decoded],
    queryFn: () => getPlayerOdds(decoded),
    enabled: !!decoded,
    staleTime: 1000 * 60 * 5,
    retry: 1,
  })

  // Auto-populate line from sportsbook odds when stat changes
  useEffect(() => {
    if (!odds || !odds.found) return
    const oddsLine = (odds as Record<string, any>)[activeStat]
    if (oddsLine != null && oddsLine > 0) {
      setLineInput(String(oddsLine))
    }
  }, [odds, activeStat])

  // ── Derived values ────────────────────────────────────────────────────────

  const parsedLine = useMemo(() => {
    const n = parseFloat(lineInput)
    return isNaN(n) ? null : n
  }, [lineInput])

  const seasonAvg = useMemo(
    () => (data ? getStatValue(data.season_averages, activeStat) : 0),
    [data, activeStat]
  )

  const hasLiveLine = useMemo(() => {
    if (!odds || !odds.found) return false
    return (odds as Record<string, any>)[activeStat] != null
  }, [odds, activeStat])

  // ── No player selected ────────────────────────────────────────────────────

  if (!decoded) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-6">
        <FlaskConical className="w-10 h-10" style={{ color: 'var(--accent)' }} />
        <div className="text-center">
          <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>Research Mode</h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Search for a player to explore their stats and matchup data
          </p>
        </div>
        <div className="w-full max-w-sm">
          <PlayerSearch
            autoFocus
            placeholder="Search players…"
            onSelect={player => navigate(`/research/${encodeURIComponent(player.player_name)}`)}
          />
        </div>
      </div>
    )
  }

  // ── Loading / error ───────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="w-8 h-8 animate-spin" style={{ color: 'var(--accent)' }} />
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Loading research data…</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <AlertCircle className="w-8 h-8" style={{ color: 'var(--accent-danger)' }} />
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Could not load research data for{' '}
          <span style={{ color: 'var(--accent)' }}>{DOMPurify.sanitize(decoded)}</span>
        </p>
        <button onClick={() => refetch()} className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg btn btn-secondary">
          <RefreshCw className="w-4 h-4" /> Retry
        </button>
      </div>
    )
  }

  // ── Shared tab props ──────────────────────────────────────────────────────

  const tabProps = { data, activeStat, setActiveStat, parsedLine, seasonAvg, playerName: decoded }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-5 pb-10">

      {/* ── Sticky Header ── */}
      <div className="sticky top-0 z-10 -mx-4 px-4 pt-2 pb-3" style={{ background: 'var(--bg-primary)' }}>
        {/* Back + search */}
        <div className="flex items-center justify-between gap-3 mb-3">
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
              onSelect={player => navigate(`/research/${encodeURIComponent(player.player_name)}`)}
              placeholder="Switch player…"
            />
          </div>
        </div>

        {/* Player info */}
        <div className="card p-3 flex items-center gap-2 sm:gap-4">
          <img
            src={getNbaHeadshotUrl(data.player_id)}
            alt={data.player_name}
            className="w-12 h-12 rounded-full object-cover flex-shrink-0"
            style={{ background: 'var(--bg-tertiary)' }}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg font-bold leading-tight truncate" style={{ color: 'var(--text-primary)' }}>
                {DOMPurify.sanitize(data.player_name)}
              </h1>
              {data.team_abbrev && (
                <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}>
                  {data.team_abbrev}
                </span>
              )}
            </div>
            {data.next_game && (
              <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-secondary)' }}>
                {data.next_game.matchup} · {data.next_game.game_date}
                {data.opponent_context && (
                  <span style={{ color: 'var(--text-muted)' }}> · {data.opponent_context.def_rank}</span>
                )}
              </p>
            )}
          </div>
          <Link
            to={`/player/${encodeURIComponent(data.player_name)}`}
            className="btn btn-primary text-xs px-3 py-1.5 flex-shrink-0 hidden sm:flex items-center gap-1.5"
          >
            <Zap className="w-3.5 h-3.5" /> ML Predict
          </Link>
        </div>
      </div>

      {/* ── Stat pills + Line input ── */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          {/* Primary stats */}
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar flex-shrink-0">
            {PRIMARY_STATS.map(s => (
              <button
                key={s}
                onClick={() => setActiveStat(s)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition-all duration-150 flex-shrink-0"
                style={activeStat === s
                  ? { background: 'var(--accent)', color: '#09090B' }
                  : { background: 'var(--bg-elevated)', color: 'var(--text-muted)', border: '1px solid rgba(255,255,255,0.06)' }
                }
              >{s}</button>
            ))}
          </div>

          {/* More toggle */}
          <button
            onClick={() => setShowMoreStats(prev => !prev)}
            className="flex items-center gap-0.5 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors flex-shrink-0"
            style={{ color: showMoreStats ? 'var(--accent)' : 'var(--text-muted)' }}
          >
            More <ChevronDown className={`w-3 h-3 transition-transform ${showMoreStats ? 'rotate-180' : ''}`} />
          </button>

          {/* Line input */}
          <div className="flex items-center gap-2 ml-auto flex-shrink-0">
            <input
              type="number"
              step="0.5"
              min="0.5"
              placeholder="Line"
              value={lineInput}
              onChange={e => {
                const val = e.target.value
                if (val === '' || parseFloat(val) > 0) setLineInput(val)
              }}
              className="w-20 px-2.5 py-1.5 rounded-lg text-xs font-mono text-center bg-bg-elevated border border-border-subtle text-text-primary focus:outline-none focus:border-accent transition-colors"
            />
            {hasLiveLine && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ background: 'rgba(var(--success-rgb),0.12)', color: 'var(--accent-success)' }}>
                LIVE
              </span>
            )}
          </div>
        </div>

        {/* Secondary stats row */}
        {showMoreStats && (
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar pb-1">
            {SECONDARY_STATS.map(s => (
              <button
                key={s}
                onClick={() => setActiveStat(s)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition-all duration-150 flex-shrink-0"
                style={activeStat === s
                  ? { background: 'var(--accent)', color: '#09090B' }
                  : { background: 'var(--bg-elevated)', color: 'var(--text-muted)', border: '1px solid rgba(255,255,255,0.06)' }
                }
              >{s}</button>
            ))}
          </div>
        )}
      </div>

      {/* ── ML Edge Card (when line is set) ── */}
      {parsedLine !== null && PRIMARY_STATS.includes(activeStat) && (
        <ModelEdgeCard playerName={decoded} stat={activeStat} line={parsedLine} />
      )}

      {/* ── Tabs ── */}
      <div className="flex gap-1 overflow-x-auto pb-1 -mb-1 no-scrollbar">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="whitespace-nowrap px-4 py-2 text-sm font-medium rounded-lg transition-all duration-150 flex-shrink-0"
            style={activeTab === tab
              ? { background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid rgba(255,255,255,0.10)' }
              : { color: 'var(--text-muted)' }
            }
          >{tab}</button>
        ))}
      </div>

      {/* ── Tab Content ── */}
      {activeTab === 'Overview' && <OverviewTab {...tabProps} />}
      {activeTab === 'Game Log' && <GameLogTab {...tabProps} />}
      {activeTab === 'Chart' && <ChartTab {...tabProps} />}
      {activeTab === 'Splits' && <SplitsTab {...tabProps} />}
      {activeTab === 'Analysis' && <AnalysisTab {...tabProps} />}
      {activeTab === 'Matchup' && <MatchupTab {...tabProps} />}
    </div>
  )
}
