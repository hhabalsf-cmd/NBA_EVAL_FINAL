import { create } from 'zustand'
import { User } from '../types/auth'
import {
  authLogin,
  authRegister,
  authGetMe,
  setAuthToken,
  clearAuthToken,
  getAuthToken,
} from '../api/client'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { token, user } = await authLogin(email, password)
      setAuthToken(token)
      set({ user, isAuthenticated: true, isLoading: false })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  signup: async (email, username, password) => {
    set({ isLoading: true, error: null })
    try {
      const { token, user } = await authRegister(email, username, password)
      setAuthToken(token)
      set({ user, isAuthenticated: true, isLoading: false })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  logout: () => {
    clearAuthToken()
    set({ user: null, isAuthenticated: false, error: null })
  },

  checkAuth: async () => {
    if (!getAuthToken()) return
    set({ isLoading: true })
    try {
      const user = await authGetMe()
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      clearAuthToken()
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),
}))
