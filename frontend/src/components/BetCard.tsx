import { ArrowRight, Bookmark } from 'lucide-react'
import { BestBet } from '../api/client'
import { useNavigate } from 'react-router-dom'

interface BetCardProps {
  bet: BestBet
  rank?: number
  onSave?: () => void
  isSaving?: boolean
}

export default function BetCard({ bet, rank, onSave, isSaving }: BetCardProps) {
  const navigate = useNavigate()
  const isOver = bet.direction === 'OVER'

  const handleClick = () => {
    navigate(`/player/${encodeURIComponent(bet.player)}`)
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
          <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">
            Line{bet.line_is_real === false && <span className="ml-1 text-text-muted/60 normal-case">(avg)</span>}
          </div>
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
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-text-muted">Edge</span>
          <span className={`font-mono font-semibold text-sm ${Math.abs(bet.edge_pct) >= 8 ? 'text-accent' : 'text-text-primary'}`}>
            {bet.edge_pct > 0 ? '+' : ''}{bet.edge_pct.toFixed(1)}%
          </span>
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

      {onSave && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onSave()
          }}
          disabled={isSaving}
          className="mt-4 w-full flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg
                     bg-accent/10 text-accent hover:bg-accent/20 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Bookmark className="w-3.5 h-3.5" />
          {isSaving ? 'Saving...' : 'Save Pick'}
        </button>
      )}
    </div>
  )
}
