/**
 * Build-time feature flags.
 *
 * Every `import.meta.env` read for a feature flag belongs here so the parsing
 * convention stays in one place and components never re-implement it.
 *
 * Convention (mirrors `api/config.py` on the backend): a flag is OFF unless the
 * env var is exactly '1' or 'true' (case-insensitive, surrounding whitespace
 * ignored). Absent, empty, 'false' and '0' all mean OFF.
 */

const TRUTHY_FLAG_VALUES: readonly string[] = ['1', 'true']

/** Parse a raw env string into a boolean flag. Defaults to `false`. */
export function parseFlag(raw: string | undefined | null): boolean {
  if (raw == null) return false
  return TRUTHY_FLAG_VALUES.includes(raw.trim().toLowerCase())
}

/**
 * `VITE_ENABLE_PREDICTIONS` — gates every surface that presents model output
 * as a betting recommendation (best bets, prediction cards, model edge,
 * line evaluation, win-rate marketing).
 *
 * Default OFF. The per-player prop model went 40-66 (37.7%) on 106 graded
 * picks against real lines versus a 52.4% breakeven, and loses to a 10-game
 * rolling average on every stat. See `docs/NEXT_STEPS_2026-08-23.md`.
 *
 * The research surfaces (game logs, splits, matchup, charts) are never gated.
 */
export const PREDICTIONS_ENABLED = parseFlag(import.meta.env.VITE_ENABLE_PREDICTIONS)
