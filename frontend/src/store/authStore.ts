import { create } from 'zustand'
import { User } from '../types/auth'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  clearError: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email: string, _password: string) => {
    set({ isLoading: true, error: null })
    // TODO: Replace with real API call
    await new Promise(resolve => setTimeout(resolve, 500))
    set({
      user: {
        id: 'mock-user-1',
        email,
        username: email.split('@')[0],
        subscription_tier: 'free',
        created_at: new Date().toISOString(),
      },
      isAuthenticated: true,
      isLoading: false,
    })
  },

  signup: async (email: string, username: string, _password: string) => {
    set({ isLoading: true, error: null })
    // TODO: Replace with real API call
    await new Promise(resolve => setTimeout(resolve, 500))
    set({
      user: {
        id: 'mock-user-1',
        email,
        username,
        subscription_tier: 'free',
        created_at: new Date().toISOString(),
      },
      isAuthenticated: true,
      isLoading: false,
    })
  },

  logout: () => {
    set({ user: null, isAuthenticated: false, error: null })
  },

  clearError: () => {
    set({ error: null })
  },
}))
