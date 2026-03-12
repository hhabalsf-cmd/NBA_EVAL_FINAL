import { useState, useCallback, useRef, useEffect } from 'react'
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

  const abortRef = useRef<AbortController | null>(null)

  // Cancel any in-flight prediction when the component unmounts
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const predict = useCallback(async (playerName: string, options: UsePredictionOptions = {}) => {
    // Abort any previous in-flight prediction
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

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
          if (controller.signal.aborted) return
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
        { ...options, signal: controller.signal }
      )

      if (controller.signal.aborted) return null

      setState(prev => ({
        ...prev,
        isLoading: false,
        progress: 100,
        stage: 'complete',
        result,
      }))

      return result
    } catch (err) {
      if ((err as Error).name === 'AbortError' || controller.signal.aborted) return null
      const errorMessage = err instanceof Error ? err.message : 'Prediction failed'
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }))
      return null
    }
  }, [])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setState(prev => ({
      ...prev,
      isLoading: false,
    }))
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
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
    cancel,
    reset,
  }
}
