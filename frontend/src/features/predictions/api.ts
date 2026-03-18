import { apiFetch, API_BASE, throwResponseError } from '../../api/client'
import type { PlayerInfo, PredictionResult, LineEvaluation, PlayerOdds, ProgressEvent, TeamInjuriesData } from '../../api/types'

export type { PlayerInfo, StatPrediction, GameInfo, OpponentContext, VsStats, GameLogEntry, PredictionResult, LineEvaluation, PlayerOdds, ProgressEvent, InjuredPlayer, TeamInjuryInfo, TeamInjuriesData } from '../../api/types'

export async function getPlayerOdds(playerName: string): Promise<PlayerOdds> {
  const response = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/odds`)
  if (!response.ok) return { found: false }
  return response.json()
}

export async function searchPlayers(query: string, signal?: AbortSignal): Promise<PlayerInfo[]> {
  const response = await apiFetch(`${API_BASE}/players/search?q=${encodeURIComponent(query)}`, { signal })
  if (!response.ok) await throwResponseError(response, 'Search failed')
  const data = await response.json()
  return data.players
}

export async function predictPlayer(
  playerName: string,
  onProgress: (event: ProgressEvent) => void,
  options: {
    modelType?: string
    useEnsemble?: boolean
    retrain?: boolean
    signal?: AbortSignal
  } = {}
): Promise<PredictionResult | null> {
  const response = await apiFetch(`${API_BASE}/players/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_name: playerName,
      model_type: options.modelType || 'gradient_boost',
      use_ensemble: options.useEnsemble || false,
      retrain: options.retrain || false,
    }),
    signal: options.signal,
  })

  if (!response.ok) await throwResponseError(response, 'Prediction failed')
  if (!response.body) throw new Error('No response body')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let result: PredictionResult | null = null
  let buffer = ''

  try {
    while (true) {
      if (options.signal?.aborted) break
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
                result = event.data
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

export async function evaluateLine(
  playerName: string,
  stat: string,
  line: number,
  prediction?: number
): Promise<LineEvaluation> {
  const response = await apiFetch(`${API_BASE}/players/evaluate-line`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_name: playerName, stat, line, prediction }),
  })

  if (!response.ok) await throwResponseError(response, 'Evaluation failed')
  return response.json()
}

export async function getTeamInjuries(playerName: string): Promise<TeamInjuriesData> {
  const res = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/team-injuries`)
  if (!res.ok) throw new Error('Failed to fetch injuries')
  return res.json()
}
