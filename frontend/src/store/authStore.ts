import { create } from 'zustand'
import { User } from '../types/auth'
import {
  authLogin,
  authLogout,
  authRegister,
  authGetMe,
  uploadAvatar,
  deleteAvatar,
  changePassword,
} from '../api/client'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isUploadingAvatar: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
  clearError: () => void
  updateAvatar: (file: File) => Promise<void>
  removeAvatar: () => Promise<void>
  changePassword: (curPass: string, newPass: string) => Promise<void>
}

export const useAuthStore = create<AuthStore>((set) => {
  // Auto-logout when any API call returns 401 (e.g. expired cookie)
  if (typeof window !== 'undefined') {
    window.addEventListener('auth:unauthorized', () => {
      set({ user: null, isAuthenticated: false, error: null })
    })
  }

  return {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    isUploadingAvatar: false,
    error: null,

    login: async (email, password) => {
      set({ isLoading: true, error: null })
      try {
        const { user } = await authLogin(email, password)
        set({ user, isAuthenticated: true, isLoading: false })
      } catch (err) {
        set({ error: (err as Error).message, isLoading: false })
      }
    },

    signup: async (email, username, password) => {
      set({ isLoading: true, error: null })
      try {
        const { user } = await authRegister(email, username, password)
        set({ user, isAuthenticated: true, isLoading: false })
      } catch (err) {
        set({ error: (err as Error).message, isLoading: false })
      }
    },

    logout: async () => {
      await authLogout().catch(() => undefined) // clear httpOnly cookie on server
      set({ user: null, isAuthenticated: false, error: null })
    },

    checkAuth: async () => {
      set({ isLoading: true })
      try {
        // Cookie is sent automatically — no token juggling needed
        const user = await authGetMe()
        set({ user, isAuthenticated: true, isLoading: false })
      } catch {
        set({ user: null, isAuthenticated: false, isLoading: false })
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

    changePassword: async (curPass, newPass) => {
      await changePassword(curPass, newPass)
    },
  }
})
