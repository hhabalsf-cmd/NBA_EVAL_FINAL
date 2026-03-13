import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Trophy, ArrowUpDown, TrendingUp, Target } from 'lucide-react'
import { motion, type Variants } from 'framer-motion'
import { getLeaderboard, type LeaderboardEntry } from '../api/client'

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
}

const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
}

const rowVariant: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0 },
}

type SortField = 'win_rate' | 'roi_units'

export default function LeaderboardPage() {
  const [sortBy, setSortBy] = useState<SortField>('win_rate')

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['leaderboard', sortBy],
    queryFn: () => getLeaderboard(sortBy),
    staleTime: 1000 * 60 * 5,
  })

  const toggleSort = () => {
    setSortBy(prev => prev === 'win_rate' ? 'roi_units' : 'win_rate')
  }

  return (
    <motion.div className="space-y-8" variants={stagger} initial="hidden" animate="show">
      {/* Header */}
      <motion.section className="pt-4" variants={fadeUp} transition={{ duration: 0.4 }}>
        <div className="flex items-center gap-3 mb-2">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--accent)18', border: '1px solid var(--accent)30' }}
          >
            <Trophy className="w-5 h-5 text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text-primary tracking-tight">Leaderboard</h1>
            <p className="text-sm text-text-secondary">Top performers ranked by {sortBy === 'win_rate' ? 'win rate' : 'ROI'}</p>
          </div>
        </div>
      </motion.section>

      {/* Sort toggle */}
      <motion.div className="flex items-center gap-2" variants={fadeUp}>
        <button
          onClick={toggleSort}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg
                     border border-border-default text-text-secondary
                     hover:bg-bg-secondary hover:text-text-primary transition-colors"
        >
          <ArrowUpDown className="w-3.5 h-3.5" />
          Sort by: {sortBy === 'win_rate' ? 'Win Rate' : 'ROI'}
        </button>
      </motion.div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card p-4 animate-pulse flex items-center gap-4">
              <div className="skeleton w-8 h-8 rounded-full" />
              <div className="flex-1 space-y-2">
                <div className="skeleton h-4 w-32 rounded" />
                <div className="skeleton h-3 w-48 rounded" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && entries.length === 0 && (
        <motion.div
          className="card p-12 text-center"
          variants={fadeUp}
        >
          <Trophy className="w-10 h-10 text-text-muted mx-auto mb-4 opacity-30" />
          <p className="text-sm text-text-secondary mb-1">No leaderboard entries yet</p>
          <p className="text-xs text-text-muted">Users with 10+ graded picks and public profiles will appear here</p>
        </motion.div>
      )}

      {/* Leaderboard table */}
      {!isLoading && entries.length > 0 && (
        <motion.div className="space-y-2" variants={stagger}>
          {entries.map((entry: LeaderboardEntry, idx: number) => (
            <motion.div key={entry.user_id} variants={rowVariant} transition={{ duration: 0.25 }}>
              <Link
                to={`/users/${entry.username}`}
                className="card p-4 flex items-center gap-4 hover:bg-bg-secondary transition-colors group"
              >
                {/* Rank */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                  idx === 0 ? 'bg-yellow-500/15 text-yellow-500' :
                  idx === 1 ? 'bg-gray-400/15 text-gray-400' :
                  idx === 2 ? 'bg-orange-600/15 text-orange-600' :
                  'bg-bg-elevated text-text-muted'
                }`}>
                  {idx + 1}
                </div>

                {/* Avatar + Name */}
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {entry.avatar_url ? (
                    <img
                      src={entry.avatar_url}
                      alt={entry.username}
                      className="w-9 h-9 rounded-full object-cover flex-shrink-0"
                    />
                  ) : (
                    <div className="w-9 h-9 rounded-full bg-accent/15 flex items-center justify-center flex-shrink-0">
                      <span className="text-sm font-bold text-accent">
                        {entry.username.charAt(0).toUpperCase()}
                      </span>
                    </div>
                  )}
                  <span className="font-medium text-text-primary text-sm truncate group-hover:text-accent transition-colors">
                    {entry.username}
                  </span>
                </div>

                {/* Stats */}
                <div className="flex items-center gap-6 flex-shrink-0">
                  <div className="text-right hidden sm:block">
                    <div className="flex items-center gap-1 text-xs text-text-muted mb-0.5">
                      <Target className="w-3 h-3" />
                      <span>Win Rate</span>
                    </div>
                    <div className={`font-mono text-sm font-semibold ${
                      entry.win_rate >= 55 ? 'text-accent-success' :
                      entry.win_rate >= 50 ? 'text-accent' :
                      'text-accent-danger'
                    }`}>
                      {entry.win_rate.toFixed(1)}%
                    </div>
                  </div>
                  <div className="text-right hidden sm:block">
                    <div className="flex items-center gap-1 text-xs text-text-muted mb-0.5">
                      <TrendingUp className="w-3 h-3" />
                      <span>ROI</span>
                    </div>
                    <div className={`font-mono text-sm font-semibold ${
                      entry.roi_units > 0 ? 'text-accent-success' : 'text-accent-danger'
                    }`}>
                      {entry.roi_units > 0 ? '+' : ''}{entry.roi_units.toFixed(1)}u
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-text-muted mb-0.5">Picks</div>
                    <div className="font-mono text-sm text-text-primary">{entry.total_graded}</div>
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  )
}
