import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { supabase } from '../../shared/lib/supabase'
import type { Pick } from './api'

export function usePicksRealtime() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const channel = supabase
      .channel('picks-realtime')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'picks' },
        (payload) => {
          const updated = payload.new as Pick
          // Patch all known picks query key variants
          const keys: unknown[][] = [['picks', false], ['picks', true], ['pending-picks']]
          for (const key of keys) {
            queryClient.setQueryData<Pick[]>(key, (old) =>
              old
                ? old.map((p) => (p.id === updated.id ? { ...p, ...updated } : p))
                : old
            )
          }
        }
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'picks' },
        () => {
          // Invalidate all picks queries — let them refetch with the new pick
          queryClient.invalidateQueries({ queryKey: ['picks'] })
          queryClient.invalidateQueries({ queryKey: ['pending-picks'] })
        }
      )
      .subscribe((_status, err) => {
        if (err) {
          console.error('[usePicksRealtime] subscription error', err)
        }
      })

    return () => { supabase.removeChannel(channel) }
  }, [queryClient])
}
