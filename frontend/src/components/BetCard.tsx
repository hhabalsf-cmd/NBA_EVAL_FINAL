import { BestBet } from '../api/client'
import { useNavigate } from 'react-router-dom'

interface BetCardProps {
  bet: BestBet
  rank?: number
}

export default function BetCard({ bet, rank }: BetCardProps) {
  const navigate = useNavigate()
  const isOver = bet.direction === 'OVER'

  const handleClick = () => {
    navigate(`/player/${encodeURIComponent(bet.player)}`)
  }

  return (
    <div
      onClick={handleClick}
      className={`card card-hover cursor-pointer p-5 relative ${
        isOver ? 'border-l-[3px] border-l-accent-success' : 'border-l-[3px] border-l-accent-danger'
      }`}
    >
      {rank && (
        <div className="absolute top-3 right-4 text-xs font-mono font-bold text-text-muted">
          #{rank}
        </div>
      )}

      <div className="mb-4">
        <div className="font-semibold text-text-primary truncate">{bet.player}</div>
        {bet.game_info && (
          <div className="text-sm text-text-secondary truncate">{bet.game_info.matchup}</div>
        )}
        {!bet.game_info && bet.home_team && bet.away_team && (
          <div className="text-sm text-text-secondary truncate">
            {bet.away_team} @ {bet.home_team}
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-4 mb-4">
        <div>
          <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Line</div>
          <div className="font-mono text-lg font-bold text-text-primary">
            {bet.stat} {bet.line}
          </div>
        </div>
        <div className="text-text-muted">&rarr;</div>
        <div>
          <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Pred</div>
          <div className={`font-mono text-lg font-bold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
            {bet.prediction.toFixed(1)}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>
          {bet.recommendation}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-text-muted">Edge</span>
          <span className={`font-mono font-bold text-sm ${Math.abs(bet.edge_pct) >= 8 ? 'text-accent-gold' : 'text-text-primary'}`}>
            {bet.edge_pct > 0 ? '+' : ''}{bet.edge_pct.toFixed(1)}%
          </span>
        </div>
      </div>

      {bet.prob_over !== null && bet.prob_over !== undefined && (
        <div className="mt-4 pt-3 border-t border-border-subtle">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-text-muted">Prob Over</span>
            <span className="text-text-secondary font-medium">{bet.prob_over.toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${bet.prob_over > 50 ? 'bg-accent-success' : 'bg-accent-danger'}`}
              style={{ width: `${bet.prob_over}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
