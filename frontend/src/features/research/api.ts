import { apiFetch, API_BASE } from '../../api/client'
import type { PlayerResearchData, ScenariosData } from '../../api/types'

export type { FullGameLogEntry, StatSplits, StatAnalysis, RollingAverages, PlayerResearchData, PlayerScenario, ScenariosData } from '../../api/types'

export async function getPlayerResearch(playerName: string): Promise<PlayerResearchData> {
  const res = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/research`)
  if (!res.ok) throw new Error(`Failed to fetch research data for ${playerName}`)
  return res.json()
}

export async function getPlayerScenarios(playerName: string): Promise<ScenariosData> {
  const res = await apiFetch(`${API_BASE}/players/${encodeURIComponent(playerName)}/scenarios`)
  if (!res.ok) throw new Error(`Failed to fetch scenarios for ${playerName}`)
  return res.json()
}
