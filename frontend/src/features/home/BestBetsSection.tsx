import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { ChevronDown, TrendingUp } from 'lucide-react'
import BetCard from './BetCard'
import ModelAccuracyBanner from '../../shared/components/ModelAccuracyBanner'
import { getTodaysDailyPicks, saveDailyPickToMyPicks, dailyPickToBestBet, type DailyPick } from './api'

const PICKS_PER_PAGE = 9

/**
 * Model-generated daily picks.
 *
 * Only mounted when `VITE_ENABLE_PREDICTIONS` is on — the caller decides, so
 * that with the flag off neither the query nor the cards ever run. Admin line
 * entry deliberately lives in `AdminLinesSection`, outside this gate.
 */
export default function BestBetsSection() {
  const [visibleCount, setVisibleCount] = useState(PICKS_PER_PAGE)
  const queryClient = useQueryClient()
  const [savingId, setSavingId] = useState<number | null>(null)

  const { data: dailyPicks, isLoading } = useQuery({
    queryKey: ['daily-picks'],
    queryFn: getTodaysDailyPicks,
    staleTime: 1000 * 60 * 15,
  })

  const saveMutation = useMutation({
    mutationFn: (pick: DailyPick) => saveDailyPickToMyPicks(pick),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['picks'] })
      setSavingId(null)
    },
    onError: () => setSavingId(null),
  })

  const handleSave = (pick: DailyPick) => {
    setSavingId(pick.id)
    saveMutation.mutate(pick)
  }

  const hasMore = dailyPicks != null && visibleCount < dailyPicks.length

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-accent" />
          <h2 className="heading-display text-2xl font-semibold text-text-primary">Best Bets Today</h2>
        </div>
        {dailyPicks && dailyPicks.length > 0 && (
          <span className="text-xs text-text-muted font-mono">{dailyPicks.length} picks</span>
        )}
      </div>

      <ModelAccuracyBanner className="mb-6" />

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="card p-5 animate-pulse">
              <div className="skeleton h-4 w-32 rounded mb-3" />
              <div className="skeleton h-3 w-24 rounded mb-5" />
              <div className="skeleton h-8 w-full rounded" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && dailyPicks && dailyPicks.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {dailyPicks.slice(0, visibleCount).map((pick) => (
              <BetCard
                key={pick.id}
                bet={dailyPickToBestBet(pick)}
                rank={pick.rank ?? undefined}
                onSave={() => handleSave(pick)}
                isSaving={savingId === pick.id}
              />
            ))}
          </div>
          {hasMore && (
            <button
              onClick={() => setVisibleCount((c) => c + PICKS_PER_PAGE)}
              className="mt-4 w-full flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium
                         rounded-lg border border-border-default text-text-secondary
                         hover:bg-bg-secondary hover:text-text-primary transition-colors"
            >
              Show More
              <ChevronDown className="w-4 h-4" />
            </button>
          )}
        </>
      )}

      {!isLoading && (!dailyPicks || dailyPicks.length === 0) && (
        <div className="card p-10 text-center border-dashed opacity-60">
          <p className="text-sm text-text-secondary">Daily picks are generated at 8 AM ET. Check back soon.</p>
        </div>
      )}
    </div>
  )
}
