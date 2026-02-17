/**
 * Returns the official NBA headshot URL for a given player ID.
 * Uses the NBA CDN press day photos (1040x760).
 * Passing 0 or an invalid ID returns a generic silhouette fallback from the CDN.
 */
export function getNbaHeadshotUrl(playerId: number): string {
  return `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`
}
