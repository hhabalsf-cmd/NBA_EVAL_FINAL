/**
 * Line observation bookkeeping — the arithmetic behind closing line value.
 *
 * A line has to be observed *twice* before CLV can ever exist: once when the
 * pick is taken, and once nearer tip-off. `manual_lines` holds one mutable row
 * per (game_date, player, stat), so an admin who enters a line and never comes
 * back leaves exactly one observation on record and `picks.closing_line` stays
 * NULL forever. Everything here exists to make that state visible.
 *
 * Pure functions only — no React, no fetching. Kept out of the components so
 * the panel stays presentational and this logic is inspectable on its own.
 */
import type { ManualLine } from './api'

/** A line is CLV-eligible only once it has been observed at least this often. */
export const OBSERVATIONS_FOR_CLOSING_LINE = 2

/** How long a line may go unobserved before the panel calls it stale. */
export const STALE_AFTER_MS = 4 * 60 * 60 * 1000

const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

/** One line's observation history, as summarised by the API. */
export interface LineSnapshotSummary {
  game_date: string
  player: string
  stat: ManualLine['stat']
  observations: number
  first_line: number
  last_line: number
  first_captured_at: string
  last_captured_at: string
}

/**
 * `unlogged`   — no snapshot at all. The entry never reached the log; CLV is
 *                impossible and something is broken.
 * `entryOnly`  — observed once. CLV is impossible until a second capture.
 * `closable`   — observed twice or more. A closing line can be derived.
 */
export type ObservationStatus = 'unlogged' | 'entryOnly' | 'closable'

export interface ObservedLine {
  line: ManualLine
  status: ObservationStatus
  observations: number
  firstObservedAt: string | null
  lastObservedAt: string | null
  /** The observed line path; null below two observations. */
  firstLine: number | null
  lastLine: number | null
  /** Signed line movement across the observed window; null below two. */
  movement: number | null
}

/**
 * Match key between a manual line and its snapshot summary.
 *
 * Mirrors `tracking_schema.snapshot_key` on the backend: whitespace collapsed,
 * case folded. Keep the two in step — a mismatch silently shows every line as
 * unlogged.
 */
export function observationKey(player: string, stat: string): string {
  const normalizedPlayer = String(player ?? '').trim().replace(/\s+/g, ' ').toLowerCase()
  return `${normalizedPlayer}|${String(stat ?? '').trim().toUpperCase()}`
}

/** Milliseconds since epoch, or null when the value is absent or unparseable. */
export function parseTimestamp(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

/** Compact relative age: "just now", "12m ago", "4h ago", "2d ago". */
export function formatAgo(value: string | null | undefined, nowMs: number): string | null {
  const then = parseTimestamp(value)
  if (then === null) return null

  const elapsed = nowMs - then
  // Negative elapsed means server/client clock skew, not a future observation.
  if (elapsed < MINUTE_MS) return 'just now'
  if (elapsed < HOUR_MS) return `${Math.floor(elapsed / MINUTE_MS)}m ago`
  if (elapsed < DAY_MS) return `${Math.floor(elapsed / HOUR_MS)}h ago`
  return `${Math.floor(elapsed / DAY_MS)}d ago`
}

/** Absolute local time, for the title attribute behind the relative age. */
export function formatAbsolute(value: string | null | undefined): string {
  const parsed = parseTimestamp(value)
  return parsed === null ? 'unknown' : new Date(parsed).toLocaleString()
}

/** True when the newest observation is old enough to warrant a fresh capture. */
export function isStale(value: string | null | undefined, nowMs: number): boolean {
  const then = parseTimestamp(value)
  return then === null ? false : nowMs - then > STALE_AFTER_MS
}

function statusFor(observations: number): ObservationStatus {
  if (observations < 1) return 'unlogged'
  return observations >= OBSERVATIONS_FOR_CLOSING_LINE ? 'closable' : 'entryOnly'
}

/**
 * Join today's manual lines to their observation summaries.
 *
 * Returns a new array of new objects; neither input is mutated. A line with no
 * matching summary falls back to `created_at` for its first-seen time so the
 * row still says something honest when the snapshot log is unavailable.
 */
export function mergeLinesWithSnapshots(
  lines: readonly ManualLine[],
  snapshots: readonly LineSnapshotSummary[],
): ObservedLine[] {
  const byKey = new Map<string, LineSnapshotSummary>()
  for (const snapshot of snapshots) {
    byKey.set(observationKey(snapshot.player, snapshot.stat), snapshot)
  }

  return lines.map((line) => {
    const snapshot = byKey.get(observationKey(line.player, line.stat)) ?? null
    const observations = snapshot?.observations ?? 0
    const canMove = observations >= OBSERVATIONS_FOR_CLOSING_LINE && snapshot !== null

    return {
      line,
      status: statusFor(observations),
      observations,
      firstObservedAt: snapshot?.first_captured_at ?? line.created_at ?? null,
      lastObservedAt: snapshot?.last_captured_at ?? line.created_at ?? null,
      firstLine: canMove ? snapshot.first_line : null,
      lastLine: canMove ? snapshot.last_line : null,
      movement: canMove ? snapshot.last_line - snapshot.first_line : null,
    }
  })
}

export interface ObservationBadge {
  label: string
  title: string
  background: string
  color: string
  borderColor: string
}

const BADGE_PALETTE: Record<ObservationStatus, { rgb: string; color: string }> = {
  unlogged: { rgb: '--danger-rgb', color: '--accent-danger' },
  entryOnly: { rgb: '--warning-rgb', color: '--accent-warning' },
  closable: { rgb: '--success-rgb', color: '--accent-success' },
}

const BADGE_TITLE: Record<ObservationStatus, string> = {
  unlogged: 'This line never reached the snapshot log — CLV is impossible and the write failed. Capture again.',
  entryOnly: 'Observed once. A closing line only exists after a SECOND observation, so no pick on this line can ever have CLV until you capture again near tip-off.',
  closable: 'Observed more than once — a closing line can be derived, so picks on this line can carry CLV.',
}

/** Colours and copy for the observation-count badge. Theme vars only. */
export function observationBadge(observed: ObservedLine): ObservationBadge {
  const palette = BADGE_PALETTE[observed.status]
  return {
    label: observed.status === 'unlogged' ? 'not logged' : `${observed.observations} obs`,
    title: BADGE_TITLE[observed.status],
    background: `rgba(var(${palette.rgb}), 0.10)`,
    color: `var(${palette.color})`,
    borderColor: `rgba(var(${palette.rgb}), 0.20)`,
  }
}

/** Signed line movement: "+1.0", "-0.5"; null when there is nothing to compare. */
export function formatMovement(movement: number | null): string | null {
  if (movement === null) return null
  return `${movement > 0 ? '+' : ''}${movement.toFixed(1)}`
}

/**
 * The observed line path: "25.5 -> 26.5 (+1.0)", or "25.5 held".
 *
 * An unmoved line is reported as held rather than "+0.0" — it is a real
 * observation, and saying so is the point of allowing the capture at all.
 */
export function formatPath(observed: ObservedLine): string | null {
  const { firstLine, lastLine, movement } = observed
  if (movement === null || firstLine === null || lastLine === null) return null
  if (movement === 0) return `${firstLine} held`
  return `${firstLine} \u2192 ${lastLine} (${formatMovement(movement)})`
}
