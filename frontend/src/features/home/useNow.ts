import { useEffect, useState } from 'react'

/** Default tick: relative ages are rendered to the minute, so match that. */
const DEFAULT_INTERVAL_MS = 60 * 1000

/**
 * A clock that re-renders on an interval.
 *
 * Relative timestamps ("entered 4h ago") are computed at render time, so
 * without a ticker a line's displayed age freezes the moment the panel mounts
 * — which is precisely the staleness the admin is being asked to act on.
 */
export function useNow(intervalMs: number = DEFAULT_INTERVAL_MS): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])

  return now
}
