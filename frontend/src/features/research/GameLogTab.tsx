import type { ResearchTabProps } from './types'
import { getStatValue } from './types'

function StatCell({ val, isHighlighted, isOver }: { val: number; isHighlighted: boolean; isOver: boolean | null }) {
  let color = 'var(--text-secondary)'
  let bg: string | undefined

  if (isHighlighted && isOver !== null) {
    color = isOver ? 'var(--accent-success)' : 'var(--accent-danger)'
    bg = isOver ? 'rgba(var(--success-rgb),0.08)' : 'rgba(var(--danger-rgb),0.08)'
  } else if (isHighlighted) {
    color = 'var(--text-primary)'
    bg = 'rgba(var(--accent-rgb),0.06)'
  }

  return (
    <td className="px-3 py-2 text-center font-mono text-sm font-semibold" style={{ color, background: bg }}>
      {val.toFixed(1)}
    </td>
  )
}

export default function GameLogTab({ data, activeStat, parsedLine }: ResearchTabProps) {
  return (
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
              {(['Date', 'Opp', 'W/L', 'MIN', 'PTS', 'REB', 'AST', 'PRA', 'STL', 'BLK', 'TOV', '3PM', 'FG%', '3P%', '+/-'] as const).map(h => (
                <th
                  key={h}
                  className={`px-3 py-2.5 text-xs font-semibold text-center${
                    ['MIN', 'FG%', '3P%', '+/-', 'STL', 'BLK', 'TOV', '3PM'].includes(h) ? ' hidden sm:table-cell' : ''
                  }`}
                  style={{ color: 'var(--text-muted)' }}
                >{h}</th>
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
                  <td className="px-3 py-2 text-center font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{g.game_date}</td>
                  <td className="px-3 py-2 text-center text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>{g.opponent}</td>
                  <td className="px-3 py-2 text-center">
                    {g.result === 'W' ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold" style={{ background: 'rgba(var(--success-rgb),0.12)', color: 'var(--accent-success)' }}>W</span>
                    ) : g.result === 'L' ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold" style={{ background: 'rgba(var(--danger-rgb),0.12)', color: 'var(--accent-danger)' }}>L</span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)' }}>
                        {g.is_home ? 'H' : 'A'}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{g.min.toFixed(0)}</td>
                  <StatCell val={g.pts} isHighlighted={activeStat === 'PTS'} isOver={activeStat === 'PTS' ? isOver : null} />
                  <StatCell val={g.reb} isHighlighted={activeStat === 'REB'} isOver={activeStat === 'REB' ? isOver : null} />
                  <StatCell val={g.ast} isHighlighted={activeStat === 'AST'} isOver={activeStat === 'AST' ? isOver : null} />
                  <StatCell val={g.pra} isHighlighted={activeStat === 'PRA'} isOver={activeStat === 'PRA' ? isOver : null} />
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{g.stl.toFixed(0)}</td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{g.blk.toFixed(0)}</td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{g.tov.toFixed(0)}</td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{g.fg3m.toFixed(0)}</td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>
                    {g.fg_pct != null ? `${g.fg_pct.toFixed(0)}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>
                    {g.fg3_pct != null ? `${g.fg3_pct.toFixed(0)}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-center font-mono text-xs hidden sm:table-cell" style={{
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
  )
}
