import { apiFetch, API_BASE, throwResponseError } from '../../api/client'
import type { LeaderboardEntry, PublicProfile, PublicPick, FollowInfo, FeedPick } from '../../api/types'

export type { LeaderboardEntry, PublicProfile, PublicPick, FollowInfo, FeedPick } from '../../api/types'

export async function getLeaderboard(sortBy = 'win_rate', limit = 50): Promise<LeaderboardEntry[]> {
  const res = await apiFetch(`${API_BASE}/leaderboard?sort_by=${sortBy}&limit=${limit}`)
  if (!res.ok) await throwResponseError(res, 'Failed to fetch leaderboard')
  return res.json()
}

export async function getPublicProfile(username: string): Promise<PublicProfile> {
  const res = await apiFetch(`${API_BASE}/users/${encodeURIComponent(username)}/profile`)
  if (!res.ok) await throwResponseError(res, 'Failed to fetch profile')
  return res.json()
}

export async function getPublicPicks(username: string, page = 1, perPage = 20): Promise<PublicPick[]> {
  const res = await apiFetch(`${API_BASE}/users/${encodeURIComponent(username)}/picks?page=${page}&per_page=${perPage}`)
  if (!res.ok) await throwResponseError(res, 'Failed to fetch picks')
  return res.json()
}

export async function followUser(userId: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/follows/${userId}`, { method: 'POST' })
  if (!res.ok) await throwResponseError(res, 'Failed to follow user')
}

export async function unfollowUser(userId: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/follows/${userId}`, { method: 'DELETE' })
  if (!res.ok) await throwResponseError(res, 'Failed to unfollow user')
}

export async function getFollows(): Promise<FollowInfo> {
  const res = await apiFetch(`${API_BASE}/follows`)
  if (!res.ok) await throwResponseError(res, 'Failed to fetch follows')
  return res.json()
}

export async function getFeed(limit = 20): Promise<FeedPick[]> {
  const res = await apiFetch(`${API_BASE}/feed?limit=${limit}`)
  if (!res.ok) await throwResponseError(res, 'Failed to fetch feed')
  return res.json()
}
