import { useQuery } from '@tanstack/react-query'
import { getLiveParlayStatus } from '../api/client'
import type { LiveParlaysResponse } from '../api/client'

/**
 * Poll the live parlay status endpoint with adaptive refresh intervals.
 *
 * - `enabled` should be true only when the user has pending parlays
 *   AND is viewing the Saved Parlays tab.
 * - Polling stops automatically when `has_live_games` is false.
 * - Respects `next_refresh_seconds` from the backend (60s during games, 300s otherwise).
 */
export function useLiveParlayStatus(enabled: boolean) {
  return useQuery<LiveParlaysResponse>({
    queryKey: ['live-parlay-status'],
    queryFn: getLiveParlayStatus,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data?.has_live_games) return false
      return (data.next_refresh_seconds ?? 60) * 1000
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  })
}
