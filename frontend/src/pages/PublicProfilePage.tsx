import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UserPlus, UserMinus, Lock, Target, TrendingUp, BarChart3 } from 'lucide-react'
import { motion, type Variants } from 'framer-motion'
import {
  getPublicProfile,
  getPublicPicks,
  followUser,
  unfollowUser,
  type PublicPick,
} from '../api/client'
import { useAuthStore } from '../store/authStore'

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
}

const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
}

export default function PublicProfilePage() {
  const { username } = useParams<{ username: string }>()
  const { isAuthenticated, user } = useAuthStore()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['public-profile', username],
    queryFn: () => getPublicProfile(username!),
    enabled: !!username,
  })

  const { data: picks = [], isLoading: picksLoading } = useQuery({
    queryKey: ['public-picks', username, page],
    queryFn: () => getPublicPicks(username!, page),
    enabled: !!username && !!profile?.is_public,
  })

  const followMutation = useMutation({
    mutationFn: () => followUser(profile!.user_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['public-profile', username] }),
  })

  const unfollowMutation = useMutation({
    mutationFn: () => unfollowUser(profile!.user_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['public-profile', username] }),
  })

  const isOwnProfile = user && profile && user.id === profile.user_id
  const canFollow = isAuthenticated && profile?.is_public && !isOwnProfile

  if (profileLoading) {
    return (
      <div className="space-y-6 pt-6">
        <div className="card p-8 animate-pulse">
          <div className="flex items-center gap-4">
            <div className="skeleton w-16 h-16 rounded-full" />
            <div className="space-y-2">
              <div className="skeleton h-5 w-40 rounded" />
              <div className="skeleton h-4 w-24 rounded" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="pt-6">
        <div className="card p-12 text-center">
          <p className="text-sm text-text-secondary">User not found</p>
        </div>
      </div>
    )
  }

  // Private profile
  if (!profile.is_public) {
    return (
      <div className="pt-6">
        <div className="card p-12 text-center">
          <Lock className="w-10 h-10 text-text-muted mx-auto mb-4 opacity-30" />
          <h2 className="text-lg font-semibold text-text-primary mb-1">{profile.username}</h2>
          <p className="text-sm text-text-secondary">This profile is private</p>
        </div>
      </div>
    )
  }

  return (
    <motion.div className="space-y-8 pt-4" variants={stagger} initial="hidden" animate="show">
      {/* Profile Header */}
      <motion.section className="card p-6" variants={fadeUp} transition={{ duration: 0.4 }}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            {profile.avatar_url ? (
              <img
                src={profile.avatar_url}
                alt={profile.username}
                className="w-16 h-16 rounded-full object-cover"
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-accent/15 flex items-center justify-center">
                <span className="text-2xl font-bold text-accent">
                  {profile.username.charAt(0).toUpperCase()}
                </span>
              </div>
            )}
            <div>
              <h1 className="text-xl font-bold text-text-primary tracking-tight">{profile.username}</h1>
              <div className="flex items-center gap-3 mt-1 text-xs text-text-muted">
                <span>{profile.followers_count} follower{profile.followers_count !== 1 ? 's' : ''}</span>
                <span>&middot;</span>
                <span>{profile.following_count} following</span>
              </div>
            </div>
          </div>
          {canFollow && (
            <button
              onClick={() => profile.is_following ? unfollowMutation.mutate() : followMutation.mutate()}
              disabled={followMutation.isPending || unfollowMutation.isPending}
              className={`btn text-sm px-4 py-2 ${
                profile.is_following ? 'btn-secondary' : 'btn-primary'
              }`}
            >
              {profile.is_following ? (
                <>
                  <UserMinus className="w-4 h-4" />
                  Unfollow
                </>
              ) : (
                <>
                  <UserPlus className="w-4 h-4" />
                  Follow
                </>
              )}
            </button>
          )}
        </div>
      </motion.section>

      {/* Stats Cards */}
      <motion.div className="grid grid-cols-2 sm:grid-cols-4 gap-4" variants={fadeUp}>
        <StatCard
          icon={Target}
          label="Win Rate"
          value={`${profile.win_rate.toFixed(1)}%`}
          color={profile.win_rate >= 55 ? 'var(--accent-success)' : profile.win_rate >= 50 ? 'var(--accent)' : 'var(--accent-danger)'}
        />
        <StatCard
          icon={TrendingUp}
          label="ROI"
          value={`${profile.roi_units > 0 ? '+' : ''}${profile.roi_units.toFixed(1)}u`}
          color={profile.roi_units > 0 ? 'var(--accent-success)' : 'var(--accent-danger)'}
        />
        <StatCard
          icon={BarChart3}
          label="Record"
          value={`${profile.total_won}W - ${profile.total_graded - profile.total_won}L`}
          color="var(--text-primary)"
        />
        <StatCard
          icon={BarChart3}
          label="Total Picks"
          value={String(profile.total_graded)}
          color="var(--text-primary)"
        />
      </motion.div>

      {/* Pick History */}
      <motion.section variants={fadeUp} transition={{ duration: 0.38 }}>
        <h2 className="text-lg font-semibold text-text-primary mb-4 tracking-tight">Pick History</h2>

        {picksLoading && (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="card p-4 animate-pulse">
                <div className="skeleton h-4 w-48 rounded" />
              </div>
            ))}
          </div>
        )}

        {!picksLoading && picks.length === 0 && (
          <div className="card p-8 text-center">
            <p className="text-sm text-text-secondary">No graded picks to display</p>
          </div>
        )}

        {!picksLoading && picks.length > 0 && (
          <div className="space-y-2">
            {picks.map((pick: PublicPick) => (
              <PickRow key={pick.id} pick={pick} />
            ))}
            {picks.length >= 20 && (
              <div className="flex items-center justify-center gap-3 pt-4">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="btn btn-secondary text-sm px-4 py-2 disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-xs text-text-muted">Page {page}</span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  className="btn btn-secondary text-sm px-4 py-2"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        )}
      </motion.section>
    </motion.div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Target
  label: string
  value: string
  color: string
}) {
  return (
    <div className="card p-4 text-center">
      <Icon className="w-4 h-4 mx-auto mb-2 text-text-muted" />
      <div className="label-xs mb-1">{label}</div>
      <div className="font-mono text-lg font-bold" style={{ color }}>{value}</div>
    </div>
  )
}

function PickRow({ pick }: { pick: PublicPick }) {
  const wonLabel = pick.won === true ? 'W' : pick.won === false ? 'L' : '—'
  const wonColor = pick.won === true ? 'text-accent-success' : pick.won === false ? 'text-accent-danger' : 'text-text-muted'

  return (
    <div className="card p-4 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${wonColor} ${
          pick.won === true ? 'bg-accent-success/10' : pick.won === false ? 'bg-accent-danger/10' : 'bg-bg-elevated'
        }`}>
          {wonLabel}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium text-text-primary truncate">{pick.player}</div>
          <div className="text-xs text-text-muted">
            {pick.stat} · {pick.direction.toUpperCase()} {pick.line} · {pick.game_date ?? ''}
          </div>
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="font-mono text-sm text-text-primary">{pick.prediction.toFixed(1)}</div>
        {pick.actual_result != null && (
          <div className="text-xs text-text-muted">Actual: {pick.actual_result}</div>
        )}
      </div>
    </div>
  )
}
