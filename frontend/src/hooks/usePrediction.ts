import { useState, useCallback } from 'react'
import { predictPlayer, PredictionResult, ProgressEvent } from '../api/client'

interface UsePredictionState {
  isLoading: boolean
  progress: number
  stage: string
  message: string
  result: PredictionResult | null
  error: string | null
}

interface UsePredictionOptions {
  modelType?: string
  useEnsemble?: boolean
  retrain?: boolean
}

export function usePrediction() {
  const [state, setState] = useState<UsePredictionState>({
    isLoading: false,
    progress: 0,
    stage: '',
    message: '',
    result: null,
    error: null,
  })

  const predict = useCallback(async (playerName: string, options: UsePredictionOptions = {}) => {
    setState({
      isLoading: true,
      progress: 0,
      stage: 'starting',
      message: 'Initializing...',
      result: null,
      error: null,
    })

    try {
      const result = await predictPlayer(
        playerName,
        (event: ProgressEvent) => {
          setState(prev => ({
            ...prev,
            progress: event.progress,
            stage: event.stage,
            message: event.message,
          }))

          if (event.stage === 'error') {
            setState(prev => ({
              ...prev,
              isLoading: false,
              error: event.message,
            }))
          }
        },
        options
      )

      setState(prev => ({
        ...prev,
        isLoading: false,
        progress: 100,
        stage: 'complete',
        result,
      }))

      return result
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Prediction failed'
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }))
      return null
    }
  }, [])

  const reset = useCallback(() => {
    setState({
      isLoading: false,
      progress: 0,
      stage: '',
      message: '',
      result: null,
      error: null,
    })
  }, [])

  return {
    ...state,
    predict,
    reset,
  }
}
