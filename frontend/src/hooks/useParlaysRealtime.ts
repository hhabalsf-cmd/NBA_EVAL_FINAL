import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import type { SavedParlay } from '../api/client'

export function useParlaysRealtime() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const channel = supabase
      .channel('parlays-realtime')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'parlays' },
        (payload) => {
          const updated = payload.new as SavedParlay
          queryClient.setQueryData<SavedParlay[]>(['parlays'], (old) =>
            old
              ? old.map((p) => (p.id === updated.id ? { ...p, ...updated } : p))
              : old
          )
        }
      )
      .subscribe((_status, err) => {
        if (err) {
          console.error('[useParlaysRealtime] subscription error', err)
        }
      })

    return () => { supabase.removeChannel(channel) }
  }, [queryClient])
}
