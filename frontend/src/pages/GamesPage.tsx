import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
import { RefreshCw, Loader2, BarChart3, Cpu, Users, Zap, X } from 'lucide-react'
import GameCard from '../components/GameCard'
import AccuracyTracker from '../components/AccuracyTracker'
import {
  getTodaysGamePredictions,
  getGameAccuracyStats,
  predictTodaysGames,
  getGamePredictionHistory,
  autoGradeGamePredictions,
  gradeGamePrediction,
  GamePrediction,
  GamePredictionHistoryItem,
  ProgressEvent,
} from '../api/client'

type Tab = 'today' | 'history'
type ResultFilter = 'all' | 'wins' | 'losses'

const PAGE_SIZE = 10
const MAX_PAGES = 4

export default function GamesPage() {
  const queryClient = useQueryClient()
  const { isAuthenticated } = useAuthStore()
  const [activeTab, setActiveTab] = useState<Tab>('today')
  const [gradingId, setGradingId] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all')

  // Today tab state
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamProgress, setStreamProgress] = useState(0)
  const [streamMessage, setStreamMessage] = useState('')
  const [streamedPredictions, setStreamedPredictions] = useState<GamePrediction[] | null>(null)

  const { data: gamesData, isLoading, error, refetch } = useQuery({
    queryKey: ['todays-games'],
    queryFn: getTodaysGamePredictions,
    staleTime: 1000 * 60 * 5,
    enabled: !isStreaming,
  })

  const { data: accuracyStats, refetch: refetchAccuracy } = useQuery({
    queryKey: ['game-accuracy'],
    queryFn: getGameAccuracyStats,
    staleTime: 1000 * 60 * 10,
    enabled: isAuthenticated,
  })

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['game-history'],
    queryFn: () => getGamePredictionHistory(),
    enabled: isAuthenticated && activeTab === 'history',
    staleTime: 1000 * 60 * 2,
  })

  const filteredHistory = useMemo(() => {
    if (!history) return []
    if (resultFilter === 'wins') return history.filter(h => h.actual_winner != null && !!h.correct)
    if (resultFilter === 'losses') return history.filter(h => h.actual_winner != null && h.correct != null && !h.correct)
    return history
  }, [history, resultFilter])

  const totalPages = Math.min(MAX_PAGES, Math.max(1, Math.ceil(filteredHistory.length / PAGE_SIZE)))
  const safePage = Math.min(page, totalPages)
  const displayedHistory = filteredHistory.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const handleFilterChange = (f: ResultFilter) => {
    setResultFilter(f)
    setPage(1)
  }

  const autoGradeMutation = useMutation({
    mutationFn: autoGradeGamePredictions,
    onSuccess: () => {
      queryClient.refetchQueries({ queryKey: ['game-history'] })
      queryClient.refetchQueries({ queryKey: ['game-accuracy'] })
    },
    onError: () => {},
  })

  const gradeMutation = useMutation({
    mutationFn: ({ id, winner }: { id: number; winner: string }) =>
      gradeGamePrediction(id, winner),
    onMutate: async ({ id, winner }) => {
      await queryClient.cancelQueries({ queryKey: ['game-history'] })
      const previous = queryClient.getQueryData<GamePredictionHistoryItem[]>(['game-history'])
      queryClient.setQueryData<GamePredictionHistoryItem[]>(['game-history'], old =>
        old?.map(item =>
          item.id === id
            ? { ...item, actual_winner: winner, correct: item.predicted_winner === winner }
            : item
        )
      )
      setGradingId(null)
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['game-history'], context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['game-history'] })
      queryClient.invalidateQueries({ queryKey: ['game-accuracy'] })
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
      refetchAccuracy()
    }
  }

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr + 'T12:00:00')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <div className="flex items-center justify-between gap-3 mb-2">
          <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">Games</h1>
          <div className="flex items-center gap-2">
            {activeTab === 'today' && (
              <button onClick={handlePredict} disabled={isStreaming} className="btn btn-primary text-sm flex-shrink-0">
                {isStreaming ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="hidden sm:inline">Predicting...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    <span className="hidden sm:inline">Refresh</span>
                  </>
                )}
              </button>
            )}
            {activeTab === 'history' && (
              <button
                onClick={() => autoGradeMutation.mutate()}
                disabled={autoGradeMutation.isPending}
                className="btn btn-secondary text-sm flex-shrink-0"
              >
                {autoGradeMutation.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="hidden sm:inline">Grading...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Auto-grade</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
        <p className="text-sm text-text-secondary">ML-powered win predictions for NBA matchups</p>
      </section>

      {/* Tab Toggle */}
      <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5 w-fit">
        {(['today', 'history'] as Tab[]).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${
              activeTab === tab
                ? 'bg-bg-elevated text-text-primary'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            {tab === 'today' ? "Today" : "History"}
          </button>
        ))}
      </div>

      {/* ── TODAY TAB ── */}
      {activeTab === 'today' && (
        <>
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
              <h3 className="text-lg font-medium text-text-primary mb-2">No Scheduled Games Found</h3>
              <p className="text-sm text-text-secondary max-md mx-auto leading-relaxed">
                Check back on game days for ML-powered win predictions.
              </p>
            </div>
          )}

          {/* How It Works */}
          <section className="card p-5 sm:p-8">
            <h2 className="text-lg font-semibold text-text-primary mb-6 sm:mb-8 tracking-tight">How Game Predictions Work</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-5 sm:gap-6">
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
        </>
      )}

      {/* ── HISTORY TAB ── */}
      {activeTab === 'history' && (
        <>
          {/* Accuracy Tracker */}
          {accuracyStats && accuracyStats.graded_predictions > 0 && (
            <AccuracyTracker stats={accuracyStats} />
          )}

          {/* History List */}
          <section className="card overflow-hidden">
            <div className="p-4 sm:p-5 border-b border-border-subtle space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-text-primary tracking-tight">Past Predictions</h2>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1 bg-bg-secondary rounded-lg p-0.5">
                  {(['all', 'wins', 'losses'] as ResultFilter[]).map(f => (
                    <button
                      key={f}
                      onClick={() => handleFilterChange(f)}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors ${
                        resultFilter === f ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >{f}</button>
                  ))}
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center gap-1 text-xs">
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                      <button
                        key={p}
                        onClick={() => setPage(p)}
                        className={`w-7 h-7 rounded-md font-mono transition-colors ${
                          safePage === p
                            ? 'bg-accent text-white'
                            : 'bg-bg-secondary text-text-muted hover:bg-bg-elevated hover:text-text-primary'
                        }`}
                      >{p}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {historyLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-5 h-5 text-accent animate-spin" />
              </div>
            ) : displayedHistory.length === 0 ? (
              <div className="text-center py-16 px-4">
                <p className="text-sm text-text-secondary">
                  {resultFilter !== 'all' ? `No ${resultFilter} to show.` : 'No prediction history yet.'}
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border-subtle">
                {displayedHistory.map((item: GamePredictionHistoryItem) => {
                  const isGraded = item.actual_winner != null
                  const isCorrect = isGraded && !!item.correct
                  const isIncorrect = isGraded && !item.correct
                  const isGradingThis = gradingId === item.id

                  return (
                    <div key={item.id} className={`p-4 sm:p-5 border-l-2 ${
                      isCorrect ? 'border-l-accent-success' : isIncorrect ? 'border-l-accent-danger' : 'border-l-border-subtle'
                    }`}>
                      <div className="flex items-start justify-between gap-3">
                        {/* Left: date + matchup */}
                        <div className="min-w-0">
                          <div className="text-[11px] text-text-muted mb-1">{formatDate(item.game_date)}</div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`font-mono text-sm font-semibold ${
                              item.predicted_winner === item.away_team ? 'text-accent' : 'text-text-primary'
                            }`}>
                              {item.away_team}
                            </span>
                            <span className="text-text-muted text-xs">@</span>
                            <span className={`font-mono text-sm font-semibold ${
                              item.predicted_winner === item.home_team ? 'text-accent' : 'text-text-primary'
                            }`}>
                              {item.home_team}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            <span className="pill pill-neutral text-[10px]">
                              {item.predicted_winner} WINS
                            </span>
                            {item.confidence != null && (
                              <span className={`text-[11px] font-mono ${
                                item.confidence >= 65 ? 'text-accent-success'
                                  : item.confidence >= 55 ? 'text-accent-warning'
                                  : 'text-text-muted'
                              }`}>
                                {item.confidence.toFixed(1)}%
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Right: result / grading */}
                        <div className="flex-shrink-0 text-right">
                          {isGraded ? (
                            <div className="flex flex-col items-end gap-1">
                              <span className="text-xs text-text-muted">Actual: {item.actual_winner}</span>
                              <span className={`font-mono font-bold text-base ${
                                isCorrect ? 'text-accent-success' : 'text-accent-danger'
                              }`}>
                                {isCorrect ? 'W' : 'L'}
                              </span>
                            </div>
                          ) : isGradingThis ? (
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => gradeMutation.mutate({ id: item.id, winner: item.away_team })}
                                disabled={gradeMutation.isPending}
                                className="px-2 py-1 rounded text-xs font-mono font-medium bg-bg-elevated text-text-primary hover:bg-accent/20 hover:text-accent transition-colors"
                              >
                                {item.away_team}
                              </button>
                              <button
                                onClick={() => gradeMutation.mutate({ id: item.id, winner: item.home_team })}
                                disabled={gradeMutation.isPending}
                                className="px-2 py-1 rounded text-xs font-mono font-medium bg-bg-elevated text-text-primary hover:bg-accent/20 hover:text-accent transition-colors"
                              >
                                {item.home_team}
                              </button>
                              <button
                                onClick={() => setGradingId(null)}
                                className="text-text-muted hover:text-text-primary transition-colors p-1"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setGradingId(item.id)}
                              className="text-xs text-text-muted hover:text-accent transition-colors font-medium px-2 py-1"
                            >
                              Grade
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
