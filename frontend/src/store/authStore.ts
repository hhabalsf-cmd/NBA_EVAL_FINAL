import { create } from 'zustand'
import { User } from '../types/auth'
import { supabase } from '../lib/supabase'

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

async function fetchProfile(userId: string): Promise<Partial<User>> {
  const { data, error } = await supabase
    .from('profiles')
    .select('username, avatar_url, role, created_at')
    .eq('id', userId)
    .single()
  if (error) {
    console.warn('fetchProfile error:', error.message)
  }
  return data ?? {}
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
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      const profile = await fetchProfile(data.user.id)
      set({
        user: {
          id: data.user.id,
          email: data.user.email!,
          username: profile.username ?? '',
          created_at: profile.created_at ?? data.user.created_at,
          role: (profile.role as 'user' | 'admin') ?? 'user',
          avatar_url: profile.avatar_url,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  signup: async (email, username, password) => {
    set({ isLoading: true, error: null })
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { username } },
      })
      if (error) throw error
      if (!data.user) throw new Error('Sign up failed')
      const profile = await fetchProfile(data.user.id)
      set({
        user: {
          id: data.user.id,
          email: data.user.email!,
          username: profile.username ?? username,
          created_at: profile.created_at ?? new Date().toISOString(),
          role: 'user',
          avatar_url: undefined,
        },
        isAuthenticated: data.session !== null,
        isLoading: false,
      })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  logout: async () => {
    await supabase.auth.signOut()
    set({ user: null, isAuthenticated: false, error: null })
  },

  checkAuth: async () => {
    set({ isLoading: true })
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        set({ user: null, isAuthenticated: false, isLoading: false })
        return
      }
      const profile = await fetchProfile(session.user.id)
      set({
        user: {
          id: session.user.id,
          email: session.user.email!,
          username: profile.username ?? '',
          created_at: profile.created_at ?? session.user.created_at,
          role: (profile.role as 'user' | 'admin') ?? 'user',
          avatar_url: profile.avatar_url,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),

  updateAvatar: async (file) => {
    set({ isUploadingAvatar: true, error: null })
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) throw new Error('Not authenticated')

      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/auth/avatar', {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.access_token}` },
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? 'Upload failed')
      }
      const updated = await res.json()
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
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) throw new Error('Not authenticated')

      const res = await fetch('/api/auth/avatar', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      if (!res.ok) throw new Error('Failed to remove avatar')
      set((state) => ({
        user: state.user ? { ...state.user, avatar_url: undefined } : null,
        isUploadingAvatar: false,
      }))
    } catch (err) {
      set({ isUploadingAvatar: false })
      throw err
    }
  },

  changePassword: async (_curPass, newPass) => {
    const { error } = await supabase.auth.updateUser({ password: newPass })
    if (error) throw error
  },
}))
