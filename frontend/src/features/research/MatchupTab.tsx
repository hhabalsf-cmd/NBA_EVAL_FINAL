import { useQuery } from '@tanstack/react-query'
import { AlertCircle, BarChart3, Activity, Loader2 } from 'lucide-react'
import { getTeamInjuries, type InjuredPlayer } from '../predictions/api'
import type { ResearchTabProps } from './types'

export default function MatchupTab({ data }: ResearchTabProps) {
  if (!data.next_game) {
    return (
      <div className="card p-8 flex flex-col items-center gap-3">
        <BarChart3 className="w-8 h-8" style={{ color: 'var(--text-muted)' }} />
        <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>No upcoming game found</p>
        <p className="text-xs text-center" style={{ color: 'var(--text-muted)' }}>
          Matchup data will appear here once a game is scheduled
        </p>
      </div>
    )
  }

  const oppAbbrev = data.next_game.opponent

  // Fetch opponent injuries (API takes player name, returns {team, opponent})
  const { data: injuries, isLoading: injuriesLoading } = useQuery({
    queryKey: ['team-injuries-research', data.player_name],
    queryFn: () => getTeamInjuries(data.player_name),
    enabled: !!data.player_name,
    staleTime: 1000 * 60 * 5,
    retry: 1,
  })

  // Flatten opponent injuries into a single list
  const oppInjuries: InjuredPlayer[] = injuries?.opponent
    ? [...injuries.opponent.out, ...injuries.opponent.questionable]
    : []

  return (
    <div className="flex flex-col gap-5">
      {/* Opponent defensive context */}
      {data.opponent_context && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            Opponent: {data.next_game.opponent_name || data.next_game.opponent}
          </h2>

          {/* Primary stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            <div className="text-center">
              <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Def Rating</p>
              <p className="text-2xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{data.opponent_context.def_rating}</p>
              <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>pts per 100</p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Pace</p>
              <p className="text-2xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{data.opponent_context.pace}</p>
              <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{data.opponent_context.pace_desc}</p>
            </div>
            <div className="text-center">
              <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Defense</p>
              <p
                className="text-sm font-bold"
                style={{
                  color: data.opponent_context.def_rank.includes('Elite') || data.opponent_context.def_rank.includes('Strong')
                    ? 'var(--accent-danger)'
                    : data.opponent_context.def_rank.includes('Weak')
                      ? 'var(--accent-success)'
                      : 'var(--text-secondary)',
                }}
              >{data.opponent_context.def_rank}</p>
            </div>
          </div>

          {/* Advanced stats (new) */}
          {data.opponent_context.efg_pct != null && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <p className="text-xs font-semibold mb-3" style={{ color: 'var(--text-muted)' }}>ADVANCED METRICS</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { label: 'Off Rtg', value: data.opponent_context.off_rating, format: (v: number) => v.toFixed(1) },
                  { label: 'Net Rtg', value: data.opponent_context.net_rating, format: (v: number) => (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1)) },
                  { label: 'eFG%', value: data.opponent_context.efg_pct, format: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: 'TS%', value: data.opponent_context.ts_pct, format: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: 'AST%', value: data.opponent_context.ast_pct, format: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: 'TOV%', value: data.opponent_context.tov_pct, format: (v: number) => `${v.toFixed(1)}%` },
                  { label: 'OREB%', value: data.opponent_context.oreb_pct, format: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: 'DREB%', value: data.opponent_context.dreb_pct, format: (v: number) => `${(v * 100).toFixed(1)}%` },
                ].map(({ label, value, format }) => value != null && (
                  <div key={label} className="rounded-lg p-2 text-center" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <p className="text-[10px] font-medium" style={{ color: 'var(--text-muted)' }}>{label}</p>
                    <p className="text-sm font-bold font-mono mt-0.5" style={{ color: 'var(--text-primary)' }}>{format(value)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* H2H History */}
      {data.vs_stats && data.vs_stats.games > 0 ? (
        <div className="card p-5">
          <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            vs {data.next_game.opponent} — Career History ({data.vs_stats.games} games)
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
            {[
              { label: 'PTS', val: data.vs_stats.avg_pts },
              { label: 'REB', val: data.vs_stats.avg_reb },
              { label: 'AST', val: data.vs_stats.avg_ast },
              { label: 'PRA', val: +(data.vs_stats.avg_pts + data.vs_stats.avg_reb + data.vs_stats.avg_ast).toFixed(1) },
            ].map(({ label, val }) => (
              <div key={label} className="text-center">
                <p className="text-xs font-mono font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>{label}</p>
                <p className="text-2xl font-bold font-mono" style={{ color: 'var(--text-primary)' }}>{val.toFixed(1)}</p>
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

      {/* Opponent Injury Report */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
            {oppAbbrev} Injury Report
          </h2>
          {injuriesLoading && <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--text-muted)' }} />}
        </div>
        {oppInjuries.length > 0 ? (
          <div className="flex flex-col gap-2">
            {oppInjuries.map((p, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
                <span
                  className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                  style={{
                    background: p.status === 'out'
                      ? 'rgba(212,115,110,0.12)' : 'rgba(232,164,48,0.12)',
                    color: p.status === 'out'
                      ? 'var(--accent-danger)' : 'var(--accent-warning)',
                  }}
                >{p.status.toUpperCase()}</span>
              </div>
            ))}
          </div>
        ) : !injuriesLoading ? (
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4" style={{ color: 'var(--accent-success)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No injuries reported</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
