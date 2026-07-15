import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardEdit, Plus, Trash2, Loader2 } from 'lucide-react'
import PlayerSearch from '../../shared/components/PlayerSearch'
import {
  getManualLines,
  upsertManualLines,
  deleteManualLine,
  type ManualLine,
} from './api'

const STATS: ManualLine['stat'][] = ['PTS', 'REB', 'AST', 'PRA']

/**
 * Fallback line source: paste today's lines from your book when the
 * Odds API is unavailable. Feeds the daily best-bets pipeline.
 */
export default function ManualLinesPanel() {
  const queryClient = useQueryClient()
  const [player, setPlayer] = useState('')
  const [stat, setStat] = useState<ManualLine['stat']>('PTS')
  const [line, setLine] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: lines = [], isLoading } = useQuery({
    queryKey: ['manual-lines'],
    queryFn: () => getManualLines(),
    staleTime: 1000 * 60,
  })

  const addMutation = useMutation({
    mutationFn: () => upsertManualLines([{ player, stat, line: Number(line) }]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manual-lines'] })
      setLine('')
      setError(null)
    },
    onError: (e: Error) => setError(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteManualLine(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['manual-lines'] }),
    onError: (e: Error) => setError(e.message),
  })

  const lineNum = Number(line)
  const canAdd = player.trim().length >= 2 && line !== '' && lineNum > 0 && !addMutation.isPending

  return (
    <div className="card p-5 mt-4">
      <div className="flex items-center gap-2 mb-1">
        <ClipboardEdit className="w-4 h-4 text-accent" />
        <h3 className="heading-display text-lg text-text-primary">Manual Lines</h3>
      </div>
      <p className="text-xs text-text-muted mb-4">
        Backup line source — enter today&apos;s lines from your book when live odds are unavailable.
        Best bets are generated from these.
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

      {/* Current lines */}
      {isLoading && <div className="skeleton h-10 w-full rounded" />}

      {!isLoading && lines.length === 0 && (
        <p className="text-xs text-text-muted italic">No manual lines entered for today.</p>
      )}

      {!isLoading && lines.length > 0 && (
        <div className="overflow-x-auto no-scrollbar">
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Stat</th>
                <th>Line</th>
                <th className="w-10" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id}>
                  <td className="font-medium">{l.player}</td>
                  <td><span className="pill pill-neutral">{l.stat}</span></td>
                  <td className="font-mono">{l.line}</td>
                  <td>
                    <button
                      onClick={() => deleteMutation.mutate(l.id)}
                      disabled={deleteMutation.isPending}
                      className="p-1.5 rounded-lg text-text-muted hover:text-accent-danger hover:bg-bg-secondary transition-colors"
                      aria-label={`Delete ${l.player} ${l.stat} line`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
