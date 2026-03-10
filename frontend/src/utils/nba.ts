/**
 * Returns the official NBA headshot URL for a given player ID.
 * Uses the NBA CDN press day photos (1040x760).
 */
export function getNbaHeadshotUrl(playerId: number): string {
  return `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`
}

/**
 * Returns the best headshot URL for a player.
 * Prefers the Sleeper CDN URL from the API; falls back to NBA CDN.
 */
export function getHeadshotUrl(headshotUrl: string | undefined, playerId: number): string {
  return headshotUrl || getNbaHeadshotUrl(playerId)
}
