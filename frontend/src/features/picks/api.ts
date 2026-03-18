import { supabase } from '../../shared/lib/supabase'
import { apiFetch, API_BASE } from '../../api/client'
import type { Pick, PerformanceStats, CumulativeProfitPoint, CalibrationStats } from '../../api/types'

export type { Pick, PerformanceStats, CumulativeProfitPoint, CalibrationBucket, BrierDecomposition, StatBrier, CLVStats, CalibrationStats } from '../../api/types'

export async function getPicks(pendingOnly = false, limit = 100): Promise<Pick[]> {
  let query = supabase
    .from('picks')
    .select('*')
    .order('timestamp', { ascending: false })

  if (pendingOnly) {
    query = query.is('won', null).eq('voided', 0)
  } else {
    query = query.limit(limit)
  }

  const { data, error } = await query
  if (error) throw new Error(error.message)
  return (data ?? []).map(p => ({
    ...p,
    won: p.won === 1 ? true : p.won === 0 ? false : null,
    voided: Boolean(p.voided),
  }))
}

export async function createPick(pick: Omit<Pick, 'id' | 'timestamp' | 'actual_result' | 'won'>): Promise<Pick> {
  const response = await apiFetch(`${API_BASE}/picks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pick),
  })

  if (!response.ok) throw new Error('Failed to create pick')
  return response.json()
}

export async function gradePick(pickId: number, actualResult: number): Promise<Pick> {
  const response = await apiFetch(`${API_BASE}/picks/${pickId}/grade`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actual_result: actualResult }),
  })

  if (!response.ok) throw new Error('Failed to grade pick')
  return response.json()
}

export async function deletePick(pickId: number): Promise<void> {
  const response = await apiFetch(`${API_BASE}/picks/${pickId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete pick')
}

export async function autoGradePicks(): Promise<{ graded_count: number; parlays_graded: number; errors: string[]; results: unknown[] }> {
  const response = await apiFetch(`${API_BASE}/picks/auto-grade`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to auto-grade picks')
  return response.json()
}

export async function getPerformanceStats(): Promise<PerformanceStats> {
  const response = await apiFetch(`${API_BASE}/picks/stats/performance`)
  if (!response.ok) return emptyPerformanceStats()
  const data = await response.json()
  return {
    total_picks: data.total_picks ?? 0,
    graded_picks: data.graded_picks ?? 0,
    wins: data.wins ?? 0,
    losses: data.losses ?? 0,
    pushes: data.pushes ?? 0,
    win_rate: data.win_rate ?? 0,
    roi: data.roi ?? 0,
    avg_edge_winners: data.avg_edge_winners ?? 0,
    by_stat: data.by_stat ?? {},
    by_edge_range: data.by_edge_range ?? {},
  }
}

function emptyPerformanceStats(): PerformanceStats {
  return {
    total_picks: 0, graded_picks: 0, wins: 0, losses: 0, pushes: 0,
    win_rate: 0, roi: 0, avg_edge_winners: 0, by_stat: {}, by_edge_range: {},
  }
}

export async function getCalibrationStats(): Promise<CalibrationStats> {
  const response = await apiFetch(`${API_BASE}/picks/stats/calibration`)
  if (!response.ok) return { brier_score: null, brier_skill_score: null, calibration_curve: [], by_stat: {}, by_confidence: {}, decomposition: null, clv: null, sample_size: 0 }
  return response.json()
}

export async function getCumulativeProfit(): Promise<CumulativeProfitPoint[]> {
  const { data, error } = await supabase
    .from('picks')
    .select('game_date, won, voided')
    .not('won', 'is', null)
    .not('game_date', 'is', null)
    .order('game_date', { ascending: true })

  if (error) throw new Error(error.message)

  let cumulative = 0
  return (data ?? []).map(p => {
    const profit = p.won === 1 ? 1 : (p.voided !== 1 ? -1 : 0)
    cumulative += profit
    return {
      date: p.game_date as string,
      profit,
      cumulative_profit: cumulative,
    }
  })
}
