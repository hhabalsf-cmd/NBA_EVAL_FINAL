import {
  TrendingUp, TrendingDown,
  Home, Plane, Zap, RefreshCw, Shield, ShieldOff, Trophy, ThumbsDown,
  UserMinus, Swords, Loader2,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import type { StatSplits } from '../../api/client'
import { getPlayerScenarios } from '../../api/client'
import type { PlayerScenario } from '../../api/client'
import type { ResearchTabProps, Stat } from './types'
import { STAT_LABELS, getStatValue, delta } from './types'

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
          <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{title}</span>
        </div>
        <span
          className="text-[11px] rounded px-1.5 py-0.5 font-mono"
          style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-muted)' }}
        >{hasData ? `${splits.games}G` : 'N/A'}</span>
      </div>
      {hasData ? (
        <>
          <span className="text-2xl font-bold font-mono leading-none" style={{ color: 'var(--text-primary)' }}>
            {val.toFixed(1)}
          </span>
          <div className="flex items-center gap-1" style={{ color: arrowColor }}>
            <Arrow className="w-3 h-3" strokeWidth={2.5} />
            <span className="text-xs font-semibold">{d > 0 ? `+${d}` : d} vs season</span>
          </div>
          {/* Mini multi-stat row */}
          <div className="flex gap-2 mt-1 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
            {(['PTS', 'REB', 'AST'] as const).filter(s => s !== stat).map(s => (
              <span key={s} className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {s}: {getStatValue(splits, s).toFixed(1)}
              </span>
            ))}
          </div>
        </>
      ) : (
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>No data</span>
      )}
    </div>
  )
}

function ScenarioCard({
  scenario,
  stat,
}: {
  scenario: PlayerScenario
  stat: Stat
}) {
  const withVal = getStatValue(scenario.with_splits, stat)
  const withoutVal = getStatValue(scenario.without_splits, stat)
  const d = delta(withoutVal, withVal)
  const isUp = d > 0
  const Arrow = isUp ? TrendingUp : TrendingDown
  const arrowColor = isUp ? 'var(--accent-success)' : 'var(--accent-danger)'

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2 min-w-[160px] flex-shrink-0"
      style={{ background: 'var(--bg-elevated)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>
          {scenario.player_name}
        </span>
        <div className="flex items-center gap-1 flex-shrink-0">
          {scenario.currently_out && (
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded"
              style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--accent-danger)' }}
            >OUT</span>
          )}
          <span
            className="text-[10px] rounded px-1.5 py-0.5 font-mono"
            style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--text-muted)' }}
          >{scenario.without_splits.games}G</span>
        </div>
      </div>
      <div>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Without: </span>
        <span className="text-xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>
          {withoutVal.toFixed(1)}
        </span>
      </div>
      <div className="flex items-center gap-1" style={{ color: arrowColor }}>
        <Arrow className="w-3 h-3" strokeWidth={2.5} />
        <span className="text-xs font-semibold">{d > 0 ? `+${d}` : d} vs with</span>
      </div>
      <div className="pt-1" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          With ({scenario.with_splits.games}G): {withVal.toFixed(1)}
        </span>
      </div>
    </div>
  )
}

export default function SplitsTab({ data, activeStat, seasonAvg, playerName }: ResearchTabProps) {
  const { data: scenarios, isLoading: scenariosLoading } = useQuery({
    queryKey: ['player-scenarios', playerName],
    queryFn: () => getPlayerScenarios(playerName),
    enabled: !!playerName,
    staleTime: 1000 * 60 * 5,
    retry: 1,
  })

  // Re-sort scenarios by active stat impact
  const sortedTeammates = (scenarios?.teammate_scenarios ?? []).slice().sort(
    (a, b) => Math.abs(getStatValue(b.without_splits, activeStat) - getStatValue(b.with_splits, activeStat))
            - Math.abs(getStatValue(a.without_splits, activeStat) - getStatValue(a.with_splits, activeStat))
  )

  const sortedOpponents = (scenarios?.opponent_scenarios ?? []).slice().sort(
    (a, b) => Math.abs(getStatValue(b.without_splits, activeStat) - getStatValue(b.with_splits, activeStat))
            - Math.abs(getStatValue(a.without_splits, activeStat) - getStatValue(a.with_splits, activeStat))
  )

  return (
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
          {data.win_splits && (
            <SplitCard title="Team Wins" icon={Trophy} splits={data.win_splits} seasonAvg={seasonAvg} stat={activeStat} />
          )}
          {data.loss_splits && (
            <SplitCard title="Team Losses" icon={ThumbsDown} splits={data.loss_splits} seasonAvg={seasonAvg} stat={activeStat} />
          )}
        </div>
      </div>

      {/* ── Teammate Absence Scenarios ── */}
      <div>
        <div className="flex items-center gap-1.5 mb-3">
          <UserMinus className="w-3.5 h-3.5" style={{ color: 'var(--text-muted)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
            Without Key Teammates
          </h2>
        </div>
        {scenariosLoading ? (
          <div className="flex items-center gap-2 py-4">
            <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--text-muted)' }} />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Loading scenarios...</span>
          </div>
        ) : sortedTeammates.length > 0 ? (
          <div className="flex gap-3 overflow-x-auto pb-2 no-scrollbar">
            {sortedTeammates.map(s => (
              <ScenarioCard key={s.player_id} scenario={s} stat={activeStat} />
            ))}
          </div>
        ) : (
          <p className="text-xs py-3" style={{ color: 'var(--text-muted)' }}>
            No significant teammate absences found
          </p>
        )}
      </div>

      {/* ── Opponent Absence Scenarios ── */}
      {data.next_game && (
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Swords className="w-3.5 h-3.5" style={{ color: 'var(--text-muted)' }} />
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
              vs {data.next_game.opponent} Without Key Players
            </h2>
          </div>
          {scenariosLoading ? (
            <div className="flex items-center gap-2 py-4">
              <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--text-muted)' }} />
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Loading scenarios...</span>
            </div>
          ) : sortedOpponents.length > 0 ? (
            <div className="flex gap-3 overflow-x-auto pb-2 no-scrollbar">
              {sortedOpponents.map(s => (
                <ScenarioCard key={s.player_id} scenario={s} stat={activeStat} />
              ))}
            </div>
          ) : (
            <p className="text-xs py-3" style={{ color: 'var(--text-muted)' }}>
              No matchup history available
            </p>
          )}
        </div>
      )}

      {/* Season average reference */}
      <div
        className="rounded-xl px-4 py-3 flex items-center justify-between"
        style={{ background: 'rgba(6,182,212,0.05)', border: '1px solid rgba(6,182,212,0.12)' }}
      >
        <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
          Season Average ({data.season_averages.games}G sample)
        </span>
        <span className="text-lg font-bold font-mono" style={{ color: 'var(--accent)' }}>
          {seasonAvg.toFixed(1)} {STAT_LABELS[activeStat]}
        </span>
      </div>
    </div>
  )
}
