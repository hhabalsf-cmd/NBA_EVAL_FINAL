import { create } from 'zustand'
import { User } from '../types/auth'
import {
  authLogin,
  authRegister,
  authGetMe,
  authRefresh,
  uploadAvatar,
  deleteAvatar,
  changePassword,
  setAuthToken,
  clearAuthToken,
  getAuthToken,
} from '../api/client'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isUploadingAvatar: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
  updateAvatar: (file: File) => Promise<void>
  removeAvatar: () => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  isUploadingAvatar: false,
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
      // Proactively refresh if token is older than 6 days (TTL is 7 days)
      await authRefresh().catch(() => undefined)
    } catch {
      // /me failed — try to refresh the token before giving up
      try {
        const { user } = await authRefresh()
        set({ user, isAuthenticated: true, isLoading: false })
      } catch {
        clearAuthToken()
        set({ user: null, isAuthenticated: false, isLoading: false })
      }
    }
  },

  clearError: () => set({ error: null }),

  updateAvatar: async (file) => {
    set({ isUploadingAvatar: true, error: null })
    try {
      const updated = await uploadAvatar(file)
      set((state) => ({
        user: state.user ? { ...state.user, avatar_url: updated.avatar_url } : null,
        isUploadingAvatar: false,
      }))
    } catch (err) {
      set({ isUploadingAvatar: false })
      throw err
    }
  },

  removeAvatar: async () => {
    set({ isUploadingAvatar: true, error: null })
    try {
      const updated = await deleteAvatar()
      set((state) => ({
        user: state.user ? { ...state.user, avatar_url: updated.avatar_url } : null,
        isUploadingAvatar: false,
      }))
    } catch (err) {
      set({ isUploadingAvatar: false })
      throw err
    }
  },

  changePassword: async (currentPassword, newPassword) => {
    await changePassword(currentPassword, newPassword)
  },
}))
