import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { usePrediction } from '../hooks/usePrediction'
import PredictionCard from '../components/PredictionCard'
import { evaluateLine, createPick, LineEvaluation } from '../api/client'

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
      <div className="flex flex-col items-center justify-center py-20">
        <div className="spinner mb-4" style={{ width: 40, height: 40 }} />
        <div className="text-sm text-text-primary mb-2">{message}</div>
        <div className="w-48 progress-bar">
          <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="text-xs text-text-muted mt-1.5">{progress}% complete</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <h2 className="text-lg font-semibold text-text-primary mb-2">Couldn't Load Predictions</h2>
        <p className="text-sm text-text-secondary mb-4">{error}</p>
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
          className="text-sm text-text-muted hover:text-text-primary mb-3 flex items-center gap-1 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </button>
        <div className="flex items-baseline justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-text-primary">{result.player_name}</h1>
            {result.team_abbrev && <p className="text-sm text-text-secondary">{result.team_abbrev}</p>}
          </div>
          <span className="text-xs text-text-muted">{result.games_trained_on} games trained</span>
        </div>
      </section>

      {/* Game Info */}
      {result.game_info && (
        <section className="card p-4">
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
                <span className="text-text-primary font-medium">{result.opponent_context.def_rank} ({result.opponent_context.def_rating.toFixed(1)})</span>
              </div>
            )}
          </div>

          {result.vs_stats && result.vs_stats.games > 0 && (
            <div className="mt-3 pt-3 border-t border-border-subtle">
              <div className="text-xs text-text-muted mb-1.5">vs {result.game_info.opponent} ({result.vs_stats.games} games)</div>
              <div className="flex gap-4 text-sm">
                <span><span className="text-text-muted">PTS:</span> <span className="text-text-primary font-medium">{result.vs_stats.avg_pts.toFixed(1)}</span></span>
                <span><span className="text-text-muted">REB:</span> <span className="text-text-primary font-medium">{result.vs_stats.avg_reb.toFixed(1)}</span></span>
                <span><span className="text-text-muted">AST:</span> <span className="text-text-primary font-medium">{result.vs_stats.avg_ast.toFixed(1)}</span></span>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Predictions Grid */}
      <section>
        <h2 className="text-lg font-bold text-text-primary mb-4">ML Predictions</h2>
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
      <section className="card p-5">
        <h2 className="text-lg font-bold text-text-primary mb-4">Evaluate Line</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-text-muted mb-1.5">Stat</label>
            <select
              value={selectedStat || ''}
              onChange={e => { setSelectedStat(e.target.value); setEvaluation(null) }}
              className="bg-bg-tertiary border border-border-subtle rounded-lg px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="">Select stat</option>
              {['PTS', 'REB', 'AST', 'PRA'].map(stat => (
                <option key={stat} value={stat}>{stat}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1.5">Line</label>
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
              <><div className="spinner w-4 h-4" /> Evaluating...</>
            ) : 'Evaluate'}
          </button>
        </div>

        {evaluation && (
          <div className={`mt-5 p-5 rounded-lg border ${isOver ? 'border-accent-success/20' : 'border-accent-danger/20'}`}>
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <div className={`pill ${isOver ? 'pill-over' : 'pill-under'} mb-3`}>{evaluation.recommendation}</div>
                <div className="grid grid-cols-3 gap-5">
                  <div>
                    <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Line</div>
                    <div className="font-mono text-xl font-bold text-text-primary">{evaluation.line}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Prediction</div>
                    <div className={`font-mono text-xl font-bold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
                      {evaluation.prediction.toFixed(1)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Edge</div>
                    <div className={`font-mono text-xl font-bold ${Math.abs(evaluation.diff_pct) >= 8 ? 'text-accent-gold' : 'text-text-primary'}`}>
                      {evaluation.diff_pct > 0 ? '+' : ''}{evaluation.diff_pct.toFixed(1)}%
                    </div>
                  </div>
                </div>

                {evaluation.prob_over !== null && evaluation.prob_over !== undefined && (
                  <div className="mt-4">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="text-accent-danger">Under</span>
                      <span className="text-text-muted">{evaluation.prob_over.toFixed(0)}% Over</span>
                      <span className="text-accent-success">Over</span>
                    </div>
                    <div className="h-2 bg-accent-danger/20 rounded-full overflow-hidden">
                      <div className="h-full bg-accent-success transition-all duration-500 rounded-full" style={{ width: `${evaluation.prob_over}%` }} />
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
                    <><div className="spinner w-4 h-4" /> Saving...</>
                  ) : (
                    <>
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
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
