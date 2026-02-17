import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, Loader2 } from 'lucide-react'
import { usePrediction } from '../hooks/usePrediction'
import PredictionCard from '../components/PredictionCard'
import { evaluateLine, createPick, LineEvaluation } from '../api/client'
import { getNbaHeadshotUrl } from '../utils/nba'

export default function PlayerPage() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const { isLoading, progress, message, result, error, predict } = usePrediction()

  const [selectedStat, setSelectedStat] = useState<string | null>(null)
  const [lineInput, setLineInput] = useState('')
  const [evaluation, setEvaluation] = useState<LineEvaluation | null>(null)
  const [isEvaluating, setIsEvaluating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  useEffect(() => {
    if (playerName) predict(decodeURIComponent(playerName))
  }, [playerName, predict])

  const handleEvaluateLine = async () => {
    if (!selectedStat || !lineInput || !result) return
    const line = parseFloat(lineInput)
    if (isNaN(line)) return

    setIsEvaluating(true)
    setEvaluation(null)
    try {
      const prediction = result.predictions[selectedStat]?.prediction
      const evalResult = await evaluateLine(result.player_name, selectedStat, line, prediction)
      setEvaluation(evalResult)
    } catch {
      // Error handling
    } finally {
      setIsEvaluating(false)
    }
  }

  const handleSavePick = async () => {
    if (!evaluation || !result) return
    setIsSaving(true)
    setSaveMessage(null)
    try {
      const direction = evaluation.recommendation.includes('OVER') ? 'OVER' : 'UNDER'
      await createPick({
        player: result.player_name,
        player_id: result.player_id,
        team_abbrev: result.team_abbrev || undefined,
        stat: evaluation.stat,
        line: evaluation.line,
        prediction: evaluation.prediction,
        direction,
        edge: evaluation.difference,
        confidence: evaluation.confidence || undefined,
        opponent: result.game_info?.opponent,
        is_home: result.game_info?.is_home,
        model_type: result.model_type,
        game_date: result.game_info?.game_date?.split('T')[0],
      })
      setSaveMessage('Pick saved successfully!')
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
        <button onClick={() => navigate('/')} className="btn btn-primary">Back to Search</button>
      </div>
    )
  }

  if (!result) return null

  const isOver = evaluation?.recommendation.includes('OVER')

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <button
          onClick={() => navigate('/')}
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
              <span className="text-xs text-text-muted font-mono">{result.games_trained_on} games trained</span>
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
          {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
            const prediction = result.predictions[stat]
            if (!prediction) return null
            return (
              <PredictionCard
                key={stat}
                stat={stat}
                prediction={prediction}
                onClick={() => { setSelectedStat(stat); setEvaluation(null) }}
              />
            )
          })}
        </div>
      </section>

      {/* Line Evaluation */}
      <section className="card p-6">
        <h2 className="text-lg font-semibold text-text-primary mb-5 tracking-tight">Evaluate Line</h2>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Stat</label>
            <select
              value={selectedStat || ''}
              onChange={e => { setSelectedStat(e.target.value); setEvaluation(null) }}
              className="bg-bg-secondary border border-border-subtle rounded-lg px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="">Select stat</option>
              {['PTS', 'REB', 'AST', 'PRA'].map(stat => (
                <option key={stat} value={stat}>{stat}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Line</label>
            <input
              type="number"
              step="0.5"
              value={lineInput}
              onChange={e => setLineInput(e.target.value)}
              placeholder="e.g., 26.5"
              className="w-28"
            />
          </div>
          <button
            onClick={handleEvaluateLine}
            disabled={!selectedStat || !lineInput || isEvaluating}
            className="btn btn-primary"
          >
            {isEvaluating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Evaluating...
              </>
            ) : 'Evaluate'}
          </button>
        </div>

        {evaluation && (
          <div className={`mt-6 p-5 rounded-xl border ${isOver ? 'border-accent-success/15 bg-accent-success/[0.03]' : 'border-accent-danger/15 bg-accent-danger/[0.03]'}`}>
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5">
              <div>
                <div className={`pill ${isOver ? 'pill-over' : 'pill-under'} mb-4`}>{evaluation.recommendation}</div>
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
                  onClick={handleSavePick}
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
                  <span className={`text-xs ${saveMessage.includes('success') ? 'text-accent-success' : 'text-accent-danger'}`}>
                    {saveMessage}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
