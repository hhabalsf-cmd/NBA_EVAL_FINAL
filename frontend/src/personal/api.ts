import type { PlayerInfo } from '../api/types'

export type Stat = 'PTS' | 'REB' | 'AST' | 'PRA'
export const STATS: Stat[] = ['PTS', 'REB', 'AST', 'PRA']
export interface Team { id: string; name: string; abbreviation: string }
export interface Player { id: string; name: string; position: string; headshot?: string; injuries: { status?: string }[] }
export interface Matchup { id: string; name: string; starts_at: string; home: boolean; team: string; opponent: string }
export interface Game { GAME_DATE: string; GAME_ID: string; TEAM: string; MIN: number; PTS: number; REB: number; AST: number; PRA: number; HOME: number }
export interface Quality { verified_games: number; corrections_this_refresh: number; excluded_zero_minute_rows: number; oldest_fetch: number; newest_fetch: number; quarantined_games?: { event_id: string; date: string; reason: string }[]; excluded_non_regular_games?: string[] }
export interface Forecast {
  player_name: string; player_id: string; event_id: string; game_date: string; as_of: string; history_through: string; event: Matchup;
  predictions: Record<Stat, { prediction: number; range_low: number; range_high: number; interval_level: number; uncertainty_std: number }>;
  offers: { stat: Stat; side: string; line: number; book: string; prob_win: number; prob_loss: number; prob_push: number; expected_profit_per_unit_risked: number; reasons: string[] }[];
  notes: string[]; data_quality: Quality; model: { trained_through: string; calibrated_through: string }
}
export interface Archive { forecasts: { id: number; created: number; forecast: Forecast }[]; corrections: { key: string; observed: number; before: Record<string, unknown>; after: Record<string, unknown> }[] }
export interface Status { model: { calibrated_through: string } | null; model_error: string | null }
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch('/api' + path, options) }
  catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new Error('Open Start NBA Eval.cmd to start your local server, then reload this page.')
  }
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Check the input and try again.')
  return body as T
}
export function searchPlayers(query: string, signal?: AbortSignal) {
  return api<PlayerInfo[]>(`/players/search?q=${encodeURIComponent(query)}`, { signal })
}
export const archiveQuery = { queryKey: ['personal-history'], queryFn: () => api<Archive>('/history') }
export const teamQuery = { queryKey: ['personal-teams'], queryFn: () => api<{ teams: Team[] }>('/teams'), staleTime: 86400000 }
export const statusQuery = { queryKey: ['personal-status'], queryFn: () => api<Status>('/status') }
export const timeLabel = (value: string | number) => new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
