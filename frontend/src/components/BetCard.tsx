import { ArrowRight, Bookmark } from 'lucide-react'
import { BestBet } from '../api/client'
import { useNavigate } from 'react-router-dom'
import { getHeadshotUrl } from '../utils/nba'

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
    navigate(`/player/${encodeURIComponent(bet.player)}`, {
      state: { headshot_url: bet.headshot_url },
    })
  }

  return (
    <div
      onClick={handleClick}
      className={`card card-hover cursor-pointer p-2.5 relative border-l-2 ${
        isOver ? 'border-l-accent-success' : 'border-l-accent-danger'
      }`}
    >
      {rank && (
        <div className="absolute top-2 right-2.5 text-[9px] font-mono text-text-muted">
          #{rank}
        </div>
      )}

      <div className="flex items-center gap-2 mb-2">
        <img
          src={getHeadshotUrl(bet.headshot_url, bet.player_id ?? 0)}
          alt={bet.player}
          className="w-7 h-7 rounded-full object-cover bg-bg-secondary flex-shrink-0"
          onError={e => {
            const img = e.target as HTMLImageElement
            img.src = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Ccircle cx='20' cy='20' r='20' fill='%23333'/%3E%3Ccircle cx='20' cy='15' r='7' fill='%23666'/%3E%3Cellipse cx='20' cy='36' rx='11' ry='8' fill='%23666'/%3E%3C/svg%3E`
            img.onerror = null
          }}
        />
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-text-primary truncate">{bet.player}</div>
          {bet.game_info && (
            <div className="text-[10px] text-text-secondary truncate">{bet.game_info.matchup}</div>
          )}
          {!bet.game_info && bet.home_team && bet.away_team && (
            <div className="text-[10px] text-text-secondary truncate">
              {bet.away_team} @ {bet.home_team}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-baseline gap-2 mb-2">
        <div>
          <div className="text-[9px] text-text-muted uppercase tracking-wider mb-0.5">
            Line{bet.line_is_real === false && <span className="ml-1 text-text-muted/60 normal-case">(avg)</span>}
          </div>
          <div className="font-mono text-sm font-semibold text-text-primary">
            {bet.stat} {bet.line}
          </div>
        </div>
        <ArrowRight className="w-2.5 h-2.5 text-text-muted flex-shrink-0 mt-3" />
        <div>
          <div className="text-[9px] text-text-muted uppercase tracking-wider mb-0.5">Pred</div>
          <div className={`font-mono text-sm font-semibold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
            {bet.prediction.toFixed(1)}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>
          {bet.recommendation}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[9px] text-text-muted">Edge</span>
          <span className={`font-mono font-semibold text-[11px] ${Math.abs(bet.edge_pct) >= 8 ? 'text-accent' : 'text-text-primary'}`}>
            {bet.edge_pct > 0 ? '+' : ''}{bet.edge_pct.toFixed(1)}%
          </span>
        </div>
      </div>

      {bet.prob_over !== null && bet.prob_over !== undefined && (
        <div className="mt-2 pt-2 border-t border-border-subtle">
          <div className="flex items-center justify-between text-[9px] mb-1">
            <span className="text-text-muted">Prob Over</span>
            <span className="text-text-secondary font-medium">{bet.prob_over.toFixed(0)}%</span>
          </div>
          <div className="h-0.5 bg-bg-elevated rounded-full overflow-hidden">
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
          className="mt-2 w-full flex items-center justify-center gap-1 py-1 text-[11px] font-medium rounded-lg
                     bg-accent/10 text-accent hover:bg-accent/20 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Bookmark className="w-2.5 h-2.5" />
          {isSaving ? 'Saving...' : 'Save Pick'}
        </button>
      )}
    </div>
  )
}
