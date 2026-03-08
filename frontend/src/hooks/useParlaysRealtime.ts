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
          queryClient.setQueryData<SavedParlay[]>(['parlays'], (old) =>
            old
              ? old.map((p) =>
                  p.id === payload.new.id ? { ...p, ...payload.new } : p
                )
              : old
          )
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [queryClient])
}
