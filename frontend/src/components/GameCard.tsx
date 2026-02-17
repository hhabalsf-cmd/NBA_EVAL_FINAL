import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { GamePrediction } from '../api/client'

interface GameCardProps {
  prediction: GamePrediction
}

export default function GameCard({ prediction }: GameCardProps) {
  const [showFactors, setShowFactors] = useState(false)
  const { matchup, predicted_winner, home_win_prob, away_win_prob, confidence, key_factors } = prediction
  const { home_team, away_team } = matchup
  const homeIsWinner = predicted_winner === home_team.team_abbrev

  return (
    <div className="card p-5">
      {matchup.game_time && (
        <div className="text-[11px] text-text-muted text-center mb-4 uppercase tracking-wider">
          {matchup.game_time}
        </div>
      )}

      <div className="flex items-center justify-between mb-5">
        <div className={`flex-1 text-center ${!homeIsWinner ? '' : 'opacity-40'}`}>
          <div className={`font-mono text-xl font-bold mb-0.5 ${!homeIsWinner ? 'text-accent' : 'text-text-primary'}`}>
            {away_team.team_abbrev}
          </div>
          <div className="text-[11px] text-text-muted">{away_team.record}</div>
        </div>
        <div className="flex-shrink-0 mx-4">
          <div className="w-8 h-8 rounded-full bg-bg-elevated flex items-center justify-center text-[11px] text-text-muted font-mono">
            vs
          </div>
        </div>
        <div className={`flex-1 text-center ${homeIsWinner ? '' : 'opacity-40'}`}>
          <div className={`font-mono text-xl font-bold mb-0.5 ${homeIsWinner ? 'text-accent' : 'text-text-primary'}`}>
            {home_team.team_abbrev}
          </div>
          <div className="text-[11px] text-text-muted">{home_team.record}</div>
        </div>
      </div>

      <div className="mb-5">
        <div className="flex justify-between text-[11px] text-text-muted mb-1.5">
          <span>{away_win_prob.toFixed(1)}%</span>
          <span>{home_win_prob.toFixed(1)}%</span>
        </div>
        <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden flex">
          <div
            className={`h-full transition-all duration-500 ${!homeIsWinner ? 'bg-accent' : 'bg-bg-secondary'}`}
            style={{ width: `${away_win_prob}%` }}
          />
          <div
            className={`h-full transition-all duration-500 ${homeIsWinner ? 'bg-accent' : 'bg-bg-secondary'}`}
            style={{ width: `${home_win_prob}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between mb-4">
        <span className="pill pill-neutral">{predicted_winner} WINS</span>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-text-muted">Conf:</span>
          <span className={`font-mono font-semibold text-sm ${
            confidence >= 65 ? 'text-accent-success' : confidence >= 55 ? 'text-accent' : 'text-text-secondary'
          }`}>
            {confidence.toFixed(1)}%
          </span>
        </div>
      </div>

      {key_factors.length > 0 && (
        <div className="border-t border-border-subtle pt-4">
          <button
            onClick={() => setShowFactors(!showFactors)}
            className="w-full flex items-center justify-between text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <span>Key Factors ({key_factors.length})</span>
            {showFactors ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showFactors && (
            <div className="mt-3 space-y-2 animate-slide-up">
              {key_factors.map((factor, idx) => (
                <div key={idx} className="flex items-start gap-2 text-xs">
                  <span className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase ${
                    factor.impact === 'MAJOR' ? 'bg-accent-danger/10 text-accent-danger'
                      : factor.impact === 'MODERATE' ? 'bg-accent/10 text-accent'
                      : 'bg-bg-elevated text-text-muted'
                  }`}>{factor.impact}</span>
                  <span className="text-text-muted flex-1">{factor.description}</span>
                  <span className={`flex-shrink-0 font-medium ${
                    factor.favors === 'HOME' ? 'text-accent-success' : 'text-accent-danger'
                  }`}>
                    {factor.favors === 'HOME' ? home_team.team_abbrev : away_team.team_abbrev}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="border-t border-border-subtle pt-4 mt-4">
        <div className="grid grid-cols-3 gap-3 text-center text-[10px]">
          <div>
            <div className="text-text-muted uppercase tracking-wider mb-1">Off Rtg</div>
            <div className="flex justify-between px-2">
              <span className="text-text-secondary">{away_team.off_rating.toFixed(1)}</span>
              <span className="text-text-secondary">{home_team.off_rating.toFixed(1)}</span>
            </div>
          </div>
          <div>
            <div className="text-text-muted uppercase tracking-wider mb-1">Def Rtg</div>
            <div className="flex justify-between px-2">
              <span className="text-text-secondary">{away_team.def_rating.toFixed(1)}</span>
              <span className="text-text-secondary">{home_team.def_rating.toFixed(1)}</span>
            </div>
          </div>
          <div>
            <div className="text-text-muted uppercase tracking-wider mb-1">Net Rtg</div>
            <div className="flex justify-between px-2">
              <span className={away_team.net_rating > 0 ? 'text-accent-success' : 'text-accent-danger'}>
                {away_team.net_rating > 0 ? '+' : ''}{away_team.net_rating.toFixed(1)}
              </span>
              <span className={home_team.net_rating > 0 ? 'text-accent-success' : 'text-accent-danger'}>
                {home_team.net_rating > 0 ? '+' : ''}{home_team.net_rating.toFixed(1)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
