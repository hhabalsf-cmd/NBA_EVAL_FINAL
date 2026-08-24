import type { TeamInfoGame } from './api'

/**
 * Placeholder detection for team stats.
 *
 * `get_team_stats()` has returned `{}` since the BDL tier downgrade, so every
 * stored game-prediction payload carries a synthetic team block: record "0-0"
 * and the fallback ratings 110 / 110 / 0 / 100. Rendering those as real team
 * data is wrong regardless of any feature flag, so both the prediction card and
 * the schedule card check here before showing a record or a ratings row.
 *
 * Remove this guard once `get_team_stats()` has a working data source again —
 * real values will simply start passing the check.
 */

const PLACEHOLDER_RECORD = '0-0'
const PLACEHOLDER_OFF_RATING = 110
const PLACEHOLDER_DEF_RATING = 110
const PLACEHOLDER_NET_RATING = 0

/** True when the team's win-loss record is real rather than the "0-0" fallback. */
export function hasRealRecord(team: Pick<TeamInfoGame, 'record'>): boolean {
  const record = team.record?.trim()
  return !!record && record !== PLACEHOLDER_RECORD
}

/** True when the off/def/net ratings are real rather than the 110/110/0 fallback. */
export function hasRealRatings(
  team: Pick<TeamInfoGame, 'off_rating' | 'def_rating' | 'net_rating'>,
): boolean {
  return !(
    team.off_rating === PLACEHOLDER_OFF_RATING &&
    team.def_rating === PLACEHOLDER_DEF_RATING &&
    team.net_rating === PLACEHOLDER_NET_RATING
  )
}

/** Ratings are only worth showing when both sides of the matchup are real. */
export function matchupHasRealRatings(
  home: Pick<TeamInfoGame, 'off_rating' | 'def_rating' | 'net_rating'>,
  away: Pick<TeamInfoGame, 'off_rating' | 'def_rating' | 'net_rating'>,
): boolean {
  return hasRealRatings(home) && hasRealRatings(away)
}
