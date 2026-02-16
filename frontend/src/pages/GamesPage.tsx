import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import GameCard from '../components/GameCard'
import AccuracyTracker from '../components/AccuracyTracker'
import {
  getTodaysGamePredictions,
  getGameAccuracyStats,
  predictTodaysGames,
  GamePrediction,
  ProgressEvent,
} from '../api/client'

export default function GamesPage() {
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

  const { data: accuracyStats } = useQuery({
    queryKey: ['game-accuracy'],
    queryFn: getGameAccuracyStats,
    staleTime: 1000 * 60 * 10,
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <section>
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl md:text-3xl font-bold text-text-primary">Today's Games</h1>
          <button onClick={handlePredict} disabled={isStreaming} className="btn btn-primary text-sm">
            {isStreaming ? 'Predicting...' : 'Refresh'}
          </button>
        </div>
        <p className="text-sm text-text-secondary">ML-powered win predictions for today's NBA matchups</p>
      </section>

      {/* Streaming Progress */}
      {isStreaming && (
        <div className="card p-4 animate-fade-in">
          <div className="flex items-center gap-3 mb-2">
            <div className="spinner" />
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
        <div className="flex items-center justify-center py-12">
          <div className="spinner" />
          <span className="ml-3 text-sm text-text-secondary">Loading predictions...</span>
        </div>
      )}

      {/* Error */}
      {error && !isStreaming && (
        <div className="card p-8 text-center">
          <h3 className="text-base font-semibold text-text-primary mb-1.5">Error Loading Predictions</h3>
          <p className="text-sm text-text-secondary mb-4">
            {error instanceof Error ? error.message : 'Something went wrong'}
          </p>
          <button onClick={() => refetch()} className="btn btn-secondary">Retry</button>
        </div>
      )}

      {/* Games Grid */}
      {!isLoading && !error && predictions.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-bold text-text-primary">Matchups</h2>
            <span className="text-sm text-text-muted">{predictions.length} game{predictions.length !== 1 ? 's' : ''} today</span>
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
        <div className="card p-10 text-center">
          <h3 className="text-lg font-semibold text-text-primary mb-1.5">No Games Today</h3>
          <p className="text-sm text-text-secondary max-w-md mx-auto">
            Check back on game days for ML-powered win predictions.
          </p>
        </div>
      )}

      {/* How It Works */}
      <section className="card p-8">
        <h2 className="text-lg font-bold text-text-primary mb-6">How Game Predictions Work</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
          {[
            { n: '01', t: 'Team Stats', d: 'Offensive & defensive ratings, pace, and net rating' },
            { n: '02', t: 'Context', d: 'Rest days, home court, back-to-backs, and head-to-head' },
            { n: '03', t: 'Injuries', d: 'Star player availability and its impact on team performance' },
            { n: '04', t: 'ML Model', d: 'XGBoost classifier trained on 3 seasons of game data' },
          ].map(s => (
            <div key={s.n}>
              <div className="text-sm font-mono font-bold text-accent mb-2">{s.n}</div>
              <h3 className="font-semibold text-text-primary text-sm mb-1">{s.t}</h3>
              <p className="text-xs text-text-secondary">{s.d}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
