import { ArrowRight, Plus, Check } from 'lucide-react'
import { BestBet } from '../api/client'
import { useNavigate } from 'react-router-dom'
import { useParlayStore } from '../store/parlayStore'

interface BetCardProps {
  bet: BestBet
  rank?: number
}

export default function BetCard({ bet, rank }: BetCardProps) {
  const navigate = useNavigate()
  const isOver = bet.direction === 'OVER'
  const { addLeg, removeLeg, hasLeg, legs } = useParlayStore()
  const inParlay = hasLeg(bet.player, bet.stat)

  const handleClick = () => {
    navigate(`/player/${encodeURIComponent(bet.player)}`)
  }

  const handleParlayToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (inParlay) {
      const idx = legs.findIndex(l => l.player === bet.player && l.stat === bet.stat)
      if (idx !== -1) removeLeg(idx)
    } else {
      addLeg({
        player: bet.player,
        stat: bet.stat,
        line: bet.line,
        prediction: bet.prediction,
        direction: bet.direction,
        prob: bet.prob_over ?? (isOver ? 60 : 40),
        edge_pct: bet.edge_pct,
      })
    }
  }

  return (
    <div
      onClick={handleClick}
      className={`card card-hover cursor-pointer p-5 relative border-l-2 ${
        isOver ? 'border-l-accent-success' : 'border-l-accent-danger'
      }`}
    >
      {rank && (
        <div className="absolute top-4 right-5 text-xs font-mono text-text-muted">
          #{rank}
        </div>
      )}

      <div className="mb-5">
        <div className="font-medium text-text-primary truncate">{bet.player}</div>
        {bet.game_info && (
          <div className="text-sm text-text-secondary mt-0.5 truncate">{bet.game_info.matchup}</div>
        )}
        {!bet.game_info && bet.home_team && bet.away_team && (
          <div className="text-sm text-text-secondary mt-0.5 truncate">
            {bet.away_team} @ {bet.home_team}
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-3 mb-5">
        <div>
          <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Line</div>
          <div className="font-mono text-lg font-semibold text-text-primary">
            {bet.stat} {bet.line}
          </div>
        </div>
        <ArrowRight className="w-3.5 h-3.5 text-text-muted flex-shrink-0 mt-5" />
        <div>
          <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Pred</div>
          <div className={`font-mono text-lg font-semibold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
            {bet.prediction.toFixed(1)}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>
          {bet.recommendation}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-text-muted">Edge</span>
            <span className={`font-mono font-semibold text-sm ${Math.abs(bet.edge_pct) >= 8 ? 'text-accent' : 'text-text-primary'}`}>
              {bet.edge_pct > 0 ? '+' : ''}{bet.edge_pct.toFixed(1)}%
            </span>
          </div>
          <button
            onClick={handleParlayToggle}
            title={inParlay ? 'Remove from parlay' : 'Add to parlay'}
            className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-all duration-150 border ${
              inParlay
                ? 'bg-accent/15 border-accent/30 text-accent'
                : 'bg-bg-elevated border-border-subtle text-text-muted hover:text-accent hover:border-accent/30'
            }`}
          >
            {inParlay ? <Check className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
            Parlay
          </button>
        </div>
      </div>

      {bet.prob_over !== null && bet.prob_over !== undefined && (
        <div className="mt-5 pt-4 border-t border-border-subtle">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-text-muted">Prob Over</span>
            <span className="text-text-secondary font-medium">{bet.prob_over.toFixed(0)}%</span>
          </div>
          <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 rounded-full ${bet.prob_over > 50 ? 'bg-accent-success' : 'bg-accent-danger'}`}
              style={{ width: `${bet.prob_over}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
