import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardEdit, Plus, Loader2, AlertTriangle } from 'lucide-react'
import PlayerSearch from '../../shared/components/PlayerSearch'
import LineObservationRow from './LineObservationRow'
import { useNow } from './useNow'
import {
  mergeLinesWithSnapshots,
  observationKey,
  type ObservedLine,
} from './lineObservations'
import {
  getManualLines,
  getLineSnapshots,
  upsertManualLines,
  captureLineSnapshots,
  deleteManualLine,
  type ManualLine,
  type ManualLineInput,
} from './api'

const STATS: ManualLine['stat'][] = ['PTS', 'REB', 'AST', 'PRA']

const LINES_KEY = ['manual-lines']
const SNAPSHOTS_KEY = ['line-snapshots']

/** Drop one key from a draft map, returning a new map. */
function withoutKey(drafts: Record<number, string>, id: number): Record<number, string> {
  const remaining: Record<number, string> = {}
  for (const [key, value] of Object.entries(drafts)) {
    if (Number(key) !== id) remaining[Number(key)] = value
  }
  return remaining
}

/**
 * Fallback line source *and* the closing-line record.
 *
 * Entering a line once is not enough: closing line value needs the same line
 * observed a second time, nearer tip-off. Every row therefore shows how many
 * observations it has and how stale the newest one is, and carries a Capture
 * action that appends a fresh observation instead of overwriting the first.
 */
export default function ManualLinesPanel() {
  const queryClient = useQueryClient()
  const nowMs = useNow()

  const [player, setPlayer] = useState('')
  const [stat, setStat] = useState<ManualLine['stat']>('PTS')
  const [line, setLine] = useState('')
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [error, setError] = useState<string | null>(null)

  const { data: lines = [], isLoading } = useQuery({
    queryKey: LINES_KEY,
    queryFn: () => getManualLines(),
    staleTime: 1000 * 60,
  })

  const { data: snapshots = [], error: snapshotsError } = useQuery({
    queryKey: SNAPSHOTS_KEY,
    queryFn: () => getLineSnapshots(),
    staleTime: 1000 * 30,
  })

  const observed: ObservedLine[] = useMemo(
    () => mergeLinesWithSnapshots(lines, snapshots),
    [lines, snapshots],
  )

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: LINES_KEY })
    queryClient.invalidateQueries({ queryKey: SNAPSHOTS_KEY })
  }

  // Add stays on the plain upsert on purpose. It is the live fallback line
  // source Best Bets runs off, so it must not start failing because the
  // measurement table is unavailable. A first observation that never reached
  // the log still shows up loudly below, as a red "not logged" badge.
  const addMutation = useMutation({
    mutationFn: () => upsertManualLines([{ player, stat, line: Number(line) }]),
    onSuccess: () => {
      refresh()
      setLine('')
      setError(null)
    },
    onError: (e: Error) => setError(e.message),
  })

  const captureMutation = useMutation({
    mutationFn: (input: ManualLineInput & { id: number }) =>
      captureLineSnapshots([{ player: input.player, stat: input.stat, line: input.line }]),
    onSuccess: (_data, input) => {
      refresh()
      setDrafts((prev) => withoutKey(prev, input.id))
      setError(null)
    },
    onError: (e: Error) => setError(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteManualLine(id),
    onSuccess: (_data, id) => {
      refresh()
      setDrafts((prev) => withoutKey(prev, id))
    },
    onError: (e: Error) => setError(e.message),
  })

  const lineNum = Number(line)
  const canAdd = player.trim().length >= 2 && line !== '' && lineNum > 0 && !addMutation.isPending

  const needSecondObservation = observed.filter((o) => o.status !== 'closable').length
  const capturingId = captureMutation.isPending ? captureMutation.variables?.id : undefined

  return (
    <div className="card p-5 mt-4">
      <div className="flex items-center gap-2 mb-1">
        <ClipboardEdit className="w-4 h-4 text-accent" />
        <h3 className="heading-display text-lg text-text-primary">Manual Lines</h3>
      </div>
      <p className="text-xs text-text-muted mb-1">
        Backup line source — enter today&apos;s lines from your book when live odds are unavailable.
        Best bets are generated from these.
      </p>
      <p className="text-xs text-text-muted mb-4">
        Then <span className="text-text-secondary font-medium">capture each line again near tip-off</span>.
        Closing line value needs two observations of the same line; with only one, every pick on it is
        permanently stuck without a closing line. Tip-off times aren&apos;t stored against a line, so
        use your book&apos;s clock.
      </p>

      {/* Add row */}
      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <div className="flex-1 min-w-0">
          <PlayerSearch
            placeholder={player || 'Player name...'}
            onSelect={(p) => setPlayer(p.player_name)}
          />
          {player && (
            <p className="text-[11px] text-text-secondary mt-1 pl-1">
              Selected: <span className="text-accent font-medium">{player}</span>
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <select
            value={stat}
            onChange={(e) => setStat(e.target.value as ManualLine['stat'])}
            className="bg-bg-secondary border border-border-subtle rounded-lg px-3 text-sm text-text-primary"
            aria-label="Stat"
          >
            {STATS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input
            type="number"
            inputMode="decimal"
            step="0.5"
            min="0.5"
            value={line}
            onChange={(e) => setLine(e.target.value)}
            placeholder="Line"
            className="w-24"
            aria-label="Line value"
          />
          <button
            onClick={() => addMutation.mutate()}
            disabled={!canAdd}
            className="btn btn-primary px-4"
            aria-label="Add line"
          >
            {addMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Add
          </button>
        </div>
      </div>

      {error && (
        <p className="text-xs mb-3" style={{ color: 'var(--accent-danger)' }}>{error}</p>
      )}

      {snapshotsError && (
        <p className="text-xs mb-3 flex items-start gap-1.5" style={{ color: 'var(--accent-warning)' }}>
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
          <span>
            Observation history unavailable ({(snapshotsError as Error).message}). Lines still save,
            but nothing below can report whether a closing line is possible.
          </span>
        </p>
      )}

      {/* Current lines */}
      {isLoading && <div className="skeleton h-10 w-full rounded" />}

      {!isLoading && lines.length === 0 && (
        <p className="text-xs text-text-muted italic">No manual lines entered for today.</p>
      )}

      {!isLoading && lines.length > 0 && (
        <>
          {needSecondObservation > 0 && (
            <p className="text-xs mb-3" style={{ color: 'var(--accent-warning)' }}>
              {needSecondObservation} of {observed.length} lines have a single observation — capture
              them again near tip-off or they can never produce CLV.
            </p>
          )}
          <div className="overflow-x-auto no-scrollbar">
            <table>
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Stat</th>
                  <th>Line</th>
                  <th>Observed</th>
                  <th>First seen</th>
                  <th className="w-10" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {observed.map((o) => {
                  const value = drafts[o.line.id] ?? String(o.line.line)
                  return (
                    <LineObservationRow
                      key={observationKey(o.line.player, o.line.stat)}
                      observed={o}
                      value={value}
                      nowMs={nowMs}
                      isCapturing={capturingId === o.line.id}
                      isDeleting={deleteMutation.isPending && deleteMutation.variables === o.line.id}
                      onChange={(next) =>
                        setDrafts((prev) => ({ ...prev, [o.line.id]: next }))
                      }
                      onCapture={() =>
                        captureMutation.mutate({
                          id: o.line.id,
                          player: o.line.player,
                          stat: o.line.stat,
                          line: Number(value),
                        })
                      }
                      onDelete={() => deleteMutation.mutate(o.line.id)}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
