import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, Loader2, Zap, PlaySquare } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { usePrediction } from '../hooks/usePrediction'
import PredictionCard from '../components/PredictionCard'
import { evaluateLine, createPick, LineEvaluation, getPlayerOdds } from '../api/client'
import { getNbaHeadshotUrl } from '../utils/nba'

const STATS = ['PTS', 'REB', 'AST', 'PRA'] as const

export default function PlayerPage() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const { isLoading, progress, message, result, error, predict } = usePrediction()

  const [lineInputs, setLineInputs] = useState<Record<string, string>>({})
  const [allEvaluations, setAllEvaluations] = useState<LineEvaluation[]>([])
  const [isEvaluatingAll, setIsEvaluatingAll] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  useEffect(() => {
    if (playerName) predict(decodeURIComponent(playerName))
  }, [playerName, predict])

  // Fetch live odds once we have the player name
  const { data: odds, isLoading: oddsLoading } = useQuery({
    queryKey: ['player-odds', playerName],
    queryFn: () => getPlayerOdds(decodeURIComponent(playerName!)),
    enabled: !!playerName && !!result,
    staleTime: 1000 * 60 * 30,
  })

  // Auto-populate line inputs when odds load
  useEffect(() => {
    if (!odds || !odds.found) return
    setLineInputs(prev => {
      const updates: Record<string, string> = { ...prev }
      for (const stat of STATS) {
        const val = odds[stat as keyof typeof odds]
        if (typeof val === 'number' && !prev[stat]) {
          updates[stat] = String(val)
        }
      }
      return updates
    })
  }, [odds])

  const handleEvaluateAll = async () => {
    if (!result) return
    const statsToEval = STATS.filter(s => lineInputs[s] && result.predictions[s])
    if (statsToEval.length === 0) return

    setIsEvaluatingAll(true)
    setAllEvaluations([])
    try {
      const results = await Promise.all(
        statsToEval.map(stat => {
          const line = parseFloat(lineInputs[stat])
          const prediction = result.predictions[stat]?.prediction
          return evaluateLine(result.player_name, stat, line, prediction)
        })
      )
      setAllEvaluations(results)
    } catch {
      // Error handling
    } finally {
      setIsEvaluatingAll(false)
    }
  }

  const handleSavePick = async (evalData?: LineEvaluation) => {
    const evalToSave = evalData
    if (!evalToSave || !result) return
    setIsSaving(true)
    setSaveMessage(null)
    try {
      const direction = evalToSave.recommendation.includes('OVER') ? 'OVER' : 'UNDER'
      await createPick({
        player: result.player_name,
        player_id: result.player_id,
        team_abbrev: result.team_abbrev || undefined,
        stat: evalToSave.stat,
        line: evalToSave.line,
        prediction: evalToSave.prediction,
        direction,
        edge: evalToSave.difference,
        confidence: evalToSave.confidence || undefined,
        opponent: result.game_info?.opponent,
        is_home: result.game_info?.is_home,
        model_type: result.model_type,
        game_date: result.game_info?.game_date?.split('T')[0],
      })
      setSaveMessage('Pick saved!')
      setTimeout(() => setSaveMessage(null), 3000)
    } catch {
      setSaveMessage('Failed to save pick')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <Loader2 className="w-8 h-8 text-accent animate-spin mb-5" />
        <div className="text-sm text-text-primary mb-3">{message}</div>
        <div className="w-48 progress-bar">
          <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="text-xs text-text-muted mt-2">{progress}% complete</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <h2 className="text-lg font-medium text-text-primary mb-2">Couldn't Load Predictions</h2>
        <p className="text-sm text-text-secondary mb-6">{error}</p>
        <button onClick={() => navigate('/app')} className="btn btn-primary">Back to Search</button>
      </div>
    )
  }

  if (!result) return null

  const hasOdds = odds?.found
  const hasAnyLine = STATS.some(s => lineInputs[s])

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <button
          onClick={() => navigate('/app')}
          className="text-sm text-text-muted hover:text-text-primary mb-4 flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <div className="flex items-center gap-5">
          <img
            src={getNbaHeadshotUrl(result.player_id)}
            alt={result.player_name}
            className="w-24 h-24 md:w-28 md:h-28 rounded-2xl object-cover bg-bg-secondary shadow-lg shadow-black/20"
            onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2">
              <div>
                <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">{result.player_name}</h1>
                {result.team_abbrev && (
                  <p className="text-sm text-text-secondary mt-1">{result.team_abbrev}</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                {oddsLoading && (
                  <span className="flex items-center gap-1.5 text-xs text-text-muted">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Fetching odds…
                  </span>
                )}
                {hasOdds && !oddsLoading && (
                  <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-accent/10 text-accent text-[11px] font-medium">
                    <Zap className="w-3 h-3" />
                    Live odds
                  </span>
                )}
                <span className="text-xs text-text-muted font-mono">{result.games_trained_on} games trained</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Game Info */}
      {result.game_info && (
        <section className="card p-5">
          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div>
              <span className="text-text-muted">Matchup: </span>
              <span className="text-text-primary font-medium">{result.game_info.matchup}</span>
            </div>
            <div>
              <span className="text-text-muted">Location: </span>
              <span className="text-text-primary font-medium">{result.game_info.is_home ? 'Home' : 'Away'}</span>
            </div>
            {result.opponent_context && (
              <div>
                <span className="text-text-muted">Opp Def: </span>
                <span className="text-text-primary font-medium">
                  {result.opponent_context.def_rank} ({result.opponent_context.def_rating.toFixed(1)})
                </span>
              </div>
            )}
          </div>

          {result.vs_stats && result.vs_stats.games > 0 && (
            <div className="mt-4 pt-4 border-t border-border-subtle">
              <div className="text-xs text-text-muted mb-2">
                vs {result.game_info.opponent} ({result.vs_stats.games} games)
              </div>
              <div className="flex gap-5 text-sm">
                <span>
                  <span className="text-text-muted">PTS:</span>{' '}
                  <span className="text-text-primary font-medium">{result.vs_stats.avg_pts.toFixed(1)}</span>
                </span>
                <span>
                  <span className="text-text-muted">REB:</span>{' '}
                  <span className="text-text-primary font-medium">{result.vs_stats.avg_reb.toFixed(1)}</span>
                </span>
                <span>
                  <span className="text-text-muted">AST:</span>{' '}
                  <span className="text-text-primary font-medium">{result.vs_stats.avg_ast.toFixed(1)}</span>
                </span>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Predictions Grid */}
      <section>
        <h2 className="text-lg font-semibold text-text-primary mb-5 tracking-tight">ML Predictions</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {STATS.map(stat => {
            const prediction = result.predictions[stat]
            if (!prediction) return null
            return (
              <PredictionCard
                key={stat}
                stat={stat}
                prediction={prediction}
                onClick={() => {
                  const pred = result.predictions[stat]?.prediction
                  if (pred == null) return
                  // Round to nearest 0.5 (standard betting line increment)
                  const rounded = Math.round(pred * 2) / 2
                  setLineInputs(prev => ({ ...prev, [stat]: String(rounded) }))
                }}
              />
            )
          })}
        </div>
      </section>

      {/* Line Evaluation */}
      <section className="card p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-text-primary tracking-tight">Evaluate Lines</h2>
          {hasOdds && !oddsLoading && (
            <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-accent/10 text-accent text-[11px] font-medium">
              <Zap className="w-3 h-3" />
              Lines auto-filled from live odds
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
          {STATS.map(stat => {
            const hasLiveOdd = hasOdds && typeof odds?.[stat as keyof typeof odds] === 'number'
            return (
              <div key={stat}>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">
                  {stat}
                  {hasLiveOdd && <span className="text-accent normal-case font-normal tracking-normal">· live</span>}
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={lineInputs[stat] ?? ''}
                  onChange={e => setLineInputs(prev => ({ ...prev, [stat]: e.target.value }))}
                  placeholder="—"
                  className="w-full"
                />
              </div>
            )
          })}
        </div>

        <button
          onClick={handleEvaluateAll}
          disabled={!hasAnyLine || isEvaluatingAll}
          className="btn btn-primary w-full"
        >
          {isEvaluatingAll ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Evaluating…
            </>
          ) : (
            <>
              <PlaySquare className="w-4 h-4" />
              Evaluate All Lines
            </>
          )}
        </button>

        {allEvaluations.length > 0 && (
          <div className="mt-6 space-y-4">
            {allEvaluations.map(ev => (
              <EvalResult
                key={ev.stat}
                evaluation={ev}
                isSaving={isSaving}
                saveMessage={saveMessage}
                onSave={() => handleSavePick(ev)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function EvalResult({
  evaluation,
  isSaving,
  saveMessage,
  onSave,
}: {
  evaluation: LineEvaluation
  isSaving: boolean
  saveMessage: string | null
  onSave: () => void
}) {
  const isOver = evaluation.recommendation.includes('OVER')
  return (
    <div className={`mt-6 p-5 rounded-xl border ${isOver ? 'border-accent-success/15 bg-accent-success/[0.03]' : 'border-accent-danger/15 bg-accent-danger/[0.03]'}`}>
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5">
        <div>
          <div className="flex items-center gap-2 mb-4">
            <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>{evaluation.recommendation}</div>
            <span className="text-xs text-text-muted font-mono">{evaluation.stat}</span>
          </div>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Line</div>
              <div className="font-mono text-xl font-bold text-text-primary">{evaluation.line}</div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Prediction</div>
              <div className={`font-mono text-xl font-bold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
                {evaluation.prediction.toFixed(1)}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Edge</div>
              <div className={`font-mono text-xl font-bold ${Math.abs(evaluation.diff_pct) >= 8 ? 'text-accent' : 'text-text-primary'}`}>
                {evaluation.diff_pct > 0 ? '+' : ''}{evaluation.diff_pct.toFixed(1)}%
              </div>
            </div>
          </div>

          {evaluation.prob_over !== null && evaluation.prob_over !== undefined && (
            <div className="mt-5">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="text-accent-danger">Under</span>
                <span className="text-text-muted">{evaluation.prob_over.toFixed(0)}% Over</span>
                <span className="text-accent-success">Over</span>
              </div>
              <div className="h-1.5 bg-accent-danger/15 rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent-success transition-all duration-500 rounded-full"
                  style={{ width: `${evaluation.prob_over}%` }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-2">
          <button
            onClick={onSave}
            disabled={isSaving}
            className={`btn ${isOver ? 'btn-over' : 'btn-under'}`}
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                Save Pick
              </>
            )}
          </button>
          {saveMessage && (
            <span className={`text-xs ${saveMessage.includes('saved') ? 'text-accent-success' : 'text-accent-danger'}`}>
              {saveMessage}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
