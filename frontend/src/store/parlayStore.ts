import { create } from 'zustand'

export interface ParlayLeg {
  player: string
  stat: string
  line: number
  prediction: number
  direction: string
  prob: number
  edge_pct: number
}

interface ParlayStore {
  legs: ParlayLeg[]
  addLeg: (leg: ParlayLeg) => void
  removeLeg: (index: number) => void
  clearParlay: () => void
  hasLeg: (player: string, stat: string) => boolean
}

export const useParlayStore = create<ParlayStore>((set, get) => ({
  legs: [],

  addLeg: (leg) => {
    const { legs } = get()
    if (legs.length >= 8) return
    // Don't add duplicate player+stat combos
    const exists = legs.some(l => l.player === leg.player && l.stat === leg.stat)
    if (exists) return
    set({ legs: [...legs, leg] })
  },

  removeLeg: (index) => {
    set(state => ({ legs: state.legs.filter((_, i) => i !== index) }))
  },

  clearParlay: () => set({ legs: [] }),

  hasLeg: (player, stat) => {
    return get().legs.some(l => l.player === player && l.stat === stat)
  },
}))
