import { CameraIcon, Loader2, Trash2 } from 'lucide-react'
import {
  formatAbsolute,
  formatAgo,
  formatPath,
  isStale,
  observationBadge,
  type ObservedLine,
} from './lineObservations'

interface Props {
  observed: ObservedLine
  /** Draft line value; the admin edits this before capturing if the line moved. */
  value: string
  nowMs: number
  isCapturing: boolean
  isDeleting: boolean
  onChange: (value: string) => void
  onCapture: () => void
  onDelete: () => void
}

/**
 * One entered line, with its observation history and a capture control.
 *
 * The capture appends a new observation; it never edits the original. If the
 * line moved, the admin corrects the number first. If it did not move,
 * capturing the same number still counts — "the line held" is a measurement.
 */
export default function LineObservationRow({
  observed, value, nowMs, isCapturing, isDeleting, onChange, onCapture, onDelete,
}: Props) {
  const { line, status, firstObservedAt, lastObservedAt } = observed
  const badge = observationBadge(observed)

  const draft = Number(value)
  const canCapture = value !== '' && Number.isFinite(draft) && draft > 0 && !isCapturing

  const enteredAgo = formatAgo(firstObservedAt, nowMs)
  const lastAgo = formatAgo(lastObservedAt, nowMs)
  const stale = isStale(lastObservedAt, nowMs)
  const pathLabel = formatPath(observed)

  return (
    <tr>
      <td className="font-medium">{line.player}</td>
      <td><span className="pill pill-neutral">{line.stat}</span></td>
      <td>
        <input
          type="number"
          inputMode="decimal"
          step="0.5"
          min="0.5"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-20 font-mono"
          aria-label={`${line.player} ${line.stat} current line`}
        />
      </td>
      <td>
        <span
          className="pill"
          title={badge.title}
          style={{
            background: badge.background,
            color: badge.color,
            border: `1px solid ${badge.borderColor}`,
          }}
        >
          {badge.label}
        </span>
        {pathLabel && (
          <div className="text-[11px] font-mono mt-1 text-text-secondary" title="Observed line path">
            {pathLabel}
          </div>
        )}
      </td>
      <td className="whitespace-nowrap">
        <div
          className="text-[11px]"
          style={{ color: stale ? 'var(--accent-warning)' : 'var(--text-secondary)' }}
          title={`First observed ${formatAbsolute(firstObservedAt)}`}
        >
          {enteredAgo ? `entered ${enteredAgo}` : 'entry time unknown'}
        </div>
        {status === 'closable' && lastAgo && (
          <div
            className="text-[11px] text-text-muted"
            title={`Last observed ${formatAbsolute(lastObservedAt)}`}
          >
            last seen {lastAgo}
          </div>
        )}
      </td>
      <td>
        <div className="flex items-center gap-1">
          <button
            onClick={onCapture}
            disabled={!canCapture}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium
                       bg-accent-muted text-accent border border-border-accent transition-colors
                       hover:bg-bg-elevated disabled:opacity-40 disabled:cursor-not-allowed"
            title={
              status === 'closable'
                ? 'Record another observation of this line.'
                : 'Record a SECOND observation so a closing line — and CLV — can exist.'
            }
            aria-label={`Capture current ${line.player} ${line.stat} line`}
          >
            {isCapturing
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <CameraIcon className="w-3.5 h-3.5" />}
            Capture
          </button>
          <button
            onClick={onDelete}
            disabled={isDeleting}
            className="p-1.5 rounded-lg text-text-muted hover:text-accent-danger hover:bg-bg-secondary transition-colors"
            aria-label={`Delete ${line.player} ${line.stat} line`}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  )
}
