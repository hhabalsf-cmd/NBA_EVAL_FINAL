import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import type { Pick } from '../api/client'

export function usePicksRealtime() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const channel = supabase
      .channel('picks-realtime')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'picks' },
        (payload) => {
          // HistoryPage uses ['picks', showPending] — patch both variants
          // so the live update applies regardless of whether pending filter is on or off.
          for (const pendingOnly of [false, true]) {
            queryClient.setQueryData<Pick[]>(['picks', pendingOnly], (old) =>
              old
                ? old.map((p) =>
                    p.id === payload.new.id ? { ...p, ...payload.new } : p
                  )
                : old
            )
          }
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [queryClient])
}
