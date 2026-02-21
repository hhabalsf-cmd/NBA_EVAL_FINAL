import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Loader2, BarChart3, Cpu, Users, Zap, Check, X, ChevronDown, ChevronUp } from 'lucide-react'
import GameCard from '../components/GameCard'
import AccuracyTracker from '../components/AccuracyTracker'
import {
  getTodaysGamePredictions,
  getGameAccuracyStats,
  getGamePredictionHistory,
  autoGradeGamePredictions,
  predictTodaysGames,
  GamePrediction,
  GamePredictionHistoryItem,
  ProgressEvent,
} from '../api/client'

export default function GamesPage() {
  const queryClient = useQueryClient()
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamProgress, setStreamProgress] = useState(0)
  const [streamMessage, setStreamMessage] = useState('')
  const [streamedPredictions, setStreamedPredictions] = useState<GamePrediction[] | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [historyDays, setHistoryDays] = useState(7)

  const { data: gamesData, isLoading, error, refetch } = useQuery({
    queryKey: ['todays-games'],
    queryFn: getTodaysGamePredictions,
    staleTime: 1000 * 60 * 5,
    enabled: !isStreaming,
  })

  const { data: accuracyStats } = useQuery({
    queryKey: ['game-accuracy'],
    queryFn: getGameAccuracyStats,
    staleTime: 1000 * 60 * 10,
  })

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['game-history', historyDays],
    queryFn: () => getGamePredictionHistory(historyDays),
    staleTime: 1000 * 60 * 5,
    enabled: showHistory,
  })

  const autoGradeMutation = useMutation({
    mutationFn: autoGradeGamePredictions,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['game-accuracy'] })
      queryClient.invalidateQueries({ queryKey: ['game-history'] })
      queryClient.invalidateQueries({ queryKey: ['todays-games'] })
      if (data.graded_count > 0) {
        setShowHistory(true)
      }
    },
  })

  const predictions = streamedPredictions || gamesData?.predictions || []

  const handlePredict = async () => {
    setIsStreaming(true)
    setStreamProgress(0)
    setStreamMessage('Starting...')
    setStreamedPredictions(null)
    try {
      const result = await predictTodaysGames((event: ProgressEvent) => {
        setStreamProgress(event.progress)
        setStreamMessage(event.message)
      })
      if (result) setStreamedPredictions(result)
    } catch (err) {
      console.error('Prediction error:', err)
    } finally {
      setIsStreaming(false)
      refetch()
    }
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  // Deduplicate history by matchup+date (keep most recent prediction per game)
  const deduplicatedHistory = (() => {
    if (!history) return []
    const seen = new Set<string>()
    return history.filter((item: GamePredictionHistoryItem) => {
      const key = `${item.game_date}-${item.home_team}-${item.away_team}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  })()

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">Today's Games</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => autoGradeMutation.mutate()}
              disabled={autoGradeMutation.isPending}
              className="btn btn-secondary text-sm"
            >
              {autoGradeMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Grading...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  Auto-grade
                </>
              )}
            </button>
            <button onClick={handlePredict} disabled={isStreaming} className="btn btn-primary text-sm">
              {isStreaming ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Predicting...
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </>
              )}
            </button>
          </div>
        </div>
        <p className="text-sm text-text-secondary">ML-powered win predictions for today's NBA matchups</p>
      </section>

      {/* Auto-grade result toast */}
      {autoGradeMutation.isSuccess && autoGradeMutation.data && (
        <div className="card p-4 animate-fade-in border-l-2 border-accent-success">
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 text-accent-success flex-shrink-0" />
            <span className="text-sm text-text-primary">
              Graded {autoGradeMutation.data.graded_count} game{autoGradeMutation.data.graded_count !== 1 ? 's' : ''}
              {autoGradeMutation.data.results && autoGradeMutation.data.results.length > 0 && (
                <span className="text-text-secondary ml-1">
                  — {(autoGradeMutation.data.results as Array<{correct: boolean}>).filter(r => r.correct).length}W-
                  {(autoGradeMutation.data.results as Array<{correct: boolean}>).filter(r => !r.correct).length}L
                </span>
              )}
            </span>
          </div>
          {autoGradeMutation.data.errors && autoGradeMutation.data.errors.length > 0 && (
            <div className="mt-2 text-xs text-accent-danger">
              {autoGradeMutation.data.errors.map((err, i) => (
                <div key={i}>{err}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Streaming Progress */}
      {isStreaming && (
        <div className="card p-5 animate-fade-in">
          <div className="flex items-center gap-3 mb-3">
            <Loader2 className="w-4 h-4 text-accent animate-spin" />
            <span className="text-sm text-text-secondary">{streamMessage}</span>
          </div>
          <div className="progress-bar">
            <div className="progress-bar-fill" style={{ width: `${streamProgress}%` }} />
          </div>
        </div>
      )}

      {/* Accuracy Tracker */}
      {accuracyStats && accuracyStats.graded_predictions > 0 && (
        <AccuracyTracker stats={accuracyStats} />
      )}

      {/* Loading */}
      {isLoading && !isStreaming && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 text-accent animate-spin" />
          <span className="ml-3 text-sm text-text-secondary">Loading predictions...</span>
        </div>
      )}

      {/* Error */}
      {error && !isStreaming && (
        <div className="card p-10 text-center">
          <h3 className="text-base font-medium text-text-primary mb-2">Error Loading Predictions</h3>
          <p className="text-sm text-text-secondary mb-5">
            {error instanceof Error ? error.message : 'Something went wrong'}
          </p>
          <button onClick={() => refetch()} className="btn btn-secondary">Retry</button>
        </div>
      )}

      {/* Games Grid */}
      {!isLoading && !error && predictions.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold text-text-primary tracking-tight">Matchups</h2>
            <span className="text-sm text-text-muted">
              {predictions.length} game{predictions.length !== 1 ? 's' : ''} today
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {predictions.map((pred, idx) => (
              <GameCard key={idx} prediction={pred} />
            ))}
          </div>
        </section>
      )}

      {/* No Games */}
      {!isLoading && !error && !isStreaming && predictions.length === 0 && (
        <div className="card p-12 text-center">
          <h3 className="text-lg font-medium text-text-primary mb-2">No Games Today</h3>
          <p className="text-sm text-text-secondary max-w-md mx-auto leading-relaxed">
            Check back on game days for ML-powered win predictions.
          </p>
        </div>
      )}

      {/* Prediction History */}
      <section className="card overflow-hidden">
        <div className="p-5 border-b border-border-subtle">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full flex items-center justify-between"
          >
            <h2 className="text-base font-semibold text-text-primary tracking-tight">Prediction History</h2>
            <div className="flex items-center gap-3">
              {showHistory && (
                <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5" onClick={e => e.stopPropagation()}>
                  {[7, 14, 30].map(d => (
                    <button
                      key={d}
                      onClick={() => setHistoryDays(d)}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                        historyDays === d ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >{d}d</button>
                  ))}
                </div>
              )}
              {showHistory ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
            </div>
          </button>
        </div>

        {showHistory && (
          historyLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 text-accent animate-spin" />
            </div>
          ) : !deduplicatedHistory.length ? (
            <div className="text-center py-12">
              <p className="text-sm text-text-secondary">No past predictions yet. Run predictions on game days to build history.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Matchup</th>
                    <th>Predicted</th>
                    <th>Prob</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {deduplicatedHistory.map((item: GamePredictionHistoryItem) => {
                    const probPct = item.predicted_winner === item.home_team
                      ? item.home_win_prob
                      : item.away_win_prob
                    return (
                      <tr key={item.id}>
                        <td className="text-xs text-text-muted whitespace-nowrap">
                          {formatDate(item.game_date)}
                        </td>
                        <td className="text-sm">
                          <span className={item.actual_winner === item.away_team ? 'font-semibold text-text-primary' : 'text-text-secondary'}>
                            {item.away_team}
                          </span>
                          <span className="text-text-muted mx-1.5">@</span>
                          <span className={item.actual_winner === item.home_team ? 'font-semibold text-text-primary' : 'text-text-secondary'}>
                            {item.home_team}
                          </span>
                        </td>
                        <td>
                          <span className="font-mono text-sm font-medium text-text-primary">
                            {item.predicted_winner}
                          </span>
                        </td>
                        <td className="font-mono text-sm text-text-secondary">
                          {probPct.toFixed(0)}%
                        </td>
                        <td>
                          {item.actual_winner ? (
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-sm text-text-secondary">{item.actual_winner}</span>
                              {item.correct !== null && item.correct !== undefined && (
                                item.correct ? (
                                  <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-accent-success/10">
                                    <Check className="w-3 h-3 text-accent-success" />
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-accent-danger/10">
                                    <X className="w-3 h-3 text-accent-danger" />
                                  </span>
                                )
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-text-muted">Pending</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
      </section>

      {/* How It Works */}
      <section className="card p-8">
        <h2 className="text-lg font-semibold text-text-primary mb-8 tracking-tight">How Game Predictions Work</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {[
            { icon: BarChart3, t: 'Team Stats', d: 'Offensive & defensive ratings, pace, and net rating' },
            { icon: Zap, t: 'Context', d: 'Rest days, home court, back-to-backs, and head-to-head' },
            { icon: Users, t: 'Injuries', d: 'Star player availability and its impact on team performance' },
            { icon: Cpu, t: 'ML Model', d: 'XGBoost classifier trained on 3 seasons of game data' },
          ].map(s => (
            <div key={s.t} className="flex gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                <s.icon className="w-3.5 h-3.5 text-accent" />
              </div>
              <div>
                <h3 className="font-medium text-text-primary text-sm mb-1">{s.t}</h3>
                <p className="text-xs text-text-secondary leading-relaxed">{s.d}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
