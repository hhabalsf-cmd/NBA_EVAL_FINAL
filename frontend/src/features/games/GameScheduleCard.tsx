import { motion } from 'framer-motion'
import { GamePrediction } from './api'
import { hasRealRecord } from './teamStats'
import { useTilt } from '../../shared/hooks/useTilt'

interface GameScheduleCardProps {
  prediction: GamePrediction
}

/**
 * Schedule-only view of a matchup: teams and tip time, nothing the ELO model
 * produced. Rendered in place of `GameCard` when `VITE_ENABLE_PREDICTIONS` is
 * off, so the honest half of the games page survives the gate.
 *
 * Records render only when they are real — see `teamStats.ts`.
 */
export default function GameScheduleCard({ prediction }: GameScheduleCardProps) {
  const { matchup } = prediction
  const { home_team, away_team } = matchup
  const tilt = useTilt({ maxTilt: 5, scale: 1.02 })

  return (
    <motion.div
      ref={tilt.ref}
      onMouseMove={tilt.onMouseMove}
      onMouseEnter={tilt.onMouseEnter}
      onMouseLeave={tilt.onMouseLeave}
      style={tilt.style}
      className="card card-3d p-5"
    >
      <div className="tilt-glare" />
      {matchup.game_time && (
        <div className="text-[11px] text-text-muted text-center mb-4 uppercase tracking-wider">
          {matchup.game_time}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex-1 text-center">
          <div className="font-mono text-xl font-bold mb-0.5 text-text-primary">
            {away_team.team_abbrev}
          </div>
          <div className="text-[11px] text-text-muted">
            {hasRealRecord(away_team) ? away_team.record : away_team.team_name}
          </div>
        </div>
        <div className="flex-shrink-0 mx-4">
          <div className="w-8 h-8 rounded-full bg-bg-elevated flex items-center justify-center text-[11px] text-text-muted font-mono">
            @
          </div>
        </div>
        <div className="flex-1 text-center">
          <div className="font-mono text-xl font-bold mb-0.5 text-text-primary">
            {home_team.team_abbrev}
          </div>
          <div className="text-[11px] text-text-muted">
            {hasRealRecord(home_team) ? home_team.record : home_team.team_name}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
