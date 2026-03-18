import { supabase } from '../../shared/lib/supabase'
import { apiFetch, API_BASE, throwResponseError } from '../../api/client'
import type { ProgressEvent, GamePrediction, TodaysGamesResponse, GamePredictionHistoryItem, GameAccuracyStats } from '../../api/types'

export type { ProgressEvent, TeamInfoGame, GameMatchup, KeyFactor, GamePrediction, TodaysGamesResponse, GamePredictionHistoryItem, ConfidenceRangeItem, GameAccuracyStats } from '../../api/types'

export async function getTodaysGamePredictions(): Promise<TodaysGamesResponse> {
  const response = await apiFetch(`${API_BASE}/games/today`)
  if (!response.ok) await throwResponseError(response, 'Failed to fetch game predictions')
  return response.json()
}

export async function predictTodaysGames(
  onProgress: (event: ProgressEvent) => void,
  signal?: AbortSignal
): Promise<GamePrediction[] | null> {
  const response = await apiFetch(`${API_BASE}/games/predict`, { method: 'POST', signal })

  if (!response.ok) throw new Error('Prediction failed')
  if (!response.body) throw new Error('No response body')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let result: GamePrediction[] | null = null
  let buffer = ''

  try {
    while (true) {
      if (signal?.aborted) break
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)

        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: ProgressEvent = JSON.parse(line.slice(6))
              onProgress(event)

              if (event.stage === 'complete' && event.data) {
                const responseData = event.data as unknown as TodaysGamesResponse
                result = responseData.predictions
              }
            } catch {
              // Ignore parse errors
            }
          }
        }

        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }

  return result
}

export async function getGamePredictionHistory(): Promise<GamePredictionHistoryItem[]> {
  const { data, error } = await supabase
    .from('game_predictions')
    .select('*')
    .order('timestamp', { ascending: false })

  if (error) throw new Error(error.message)
  return (data ?? []).map(item => ({
    ...item,
    key_factors: typeof item.key_factors === 'string'
      ? JSON.parse(item.key_factors)
      : (item.key_factors ?? []),
  }))
}

export async function autoGradeGamePredictions(): Promise<{
  graded_count: number
  errors: string[]
  results: unknown[]
}> {
  const response = await apiFetch(`${API_BASE}/games/auto-grade`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to auto-grade game predictions')
  return response.json()
}

export async function gradeGamePrediction(id: number, actualWinner: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/games/${id}/grade`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actual_winner: actualWinner }),
  })
  if (!response.ok) throw new Error('Failed to grade game prediction')
}

export async function getGameAccuracyStats(): Promise<GameAccuracyStats> {
  const { data, error } = await supabase
    .from('game_accuracy_stats')
    .select('*')
    .single()

  if (error) throw new Error(error.message)
  return {
    total_predictions: data.total_predictions ?? 0,
    graded_predictions: data.graded_predictions ?? 0,
    correct: data.correct ?? 0,
    incorrect: data.incorrect ?? 0,
    accuracy: data.accuracy ?? 0,
    by_confidence_range: {},
    recent_streak: '',
  }
}
