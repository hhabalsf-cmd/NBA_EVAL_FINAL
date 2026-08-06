import { create } from 'zustand'
import { User } from '../../features/auth/types'
import { supabase } from '../../shared/lib/supabase'

const API_BASE = (import.meta.env.VITE_API_URL ?? '') + '/api'

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isUploadingAvatar: boolean
  error: string | null
  needsEmailConfirmation: boolean
  login: (emailOrUsername: string, password: string) => Promise<boolean>
  signup: (email: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
  clearError: () => void
  updateAvatar: (file: File) => Promise<void>
  removeAvatar: () => Promise<void>
  changePassword: (curPass: string, newPass: string) => Promise<void>
  acceptTos: () => Promise<void>
}

async function fetchProfile(userId: string): Promise<Partial<User>> {
  const { data, error } = await supabase
    .from('profiles')
    .select('username, avatar_url, role, created_at, tos_accepted_at, is_public')
    .eq('id', userId)
    .single()
  if (error) {
    console.warn('fetchProfile error:', error.message)
  }
  return data ?? {}
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  isUploadingAvatar: false,
  error: null,
  needsEmailConfirmation: false,

  login: async (emailOrUsername, password) => {
    set({ isLoading: true, error: null })
    try {
      // Resolve username → email if input doesn't look like an email
      let email = emailOrUsername.trim()
      if (!email.includes('@')) {
        const { data: resolvedEmail, error: rpcError } = await supabase
          .rpc('get_email_by_username', { lookup_username: email })
        if (rpcError || !resolvedEmail) {
          throw new Error('Invalid credentials')
        }
        email = resolvedEmail
      }

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
          tos_accepted_at: profile.tos_accepted_at ?? undefined,
          is_public: profile.is_public ?? false,
        },
        isAuthenticated: true,
        isLoading: false,
      })
      return true
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
      return false
    }
  },

  signup: async (email, username, password) => {
    set({ isLoading: true, error: null })
    try {
      // Cap new registrations while in early access
      const MAX_ACCOUNTS = 10
      const { count, error: countError } = await supabase
        .from('profiles')
        .select('*', { count: 'exact', head: true })
      if (countError) throw new Error('Unable to verify registration availability')
      if (count !== null && count >= MAX_ACCOUNTS) {
        throw new Error('Registration is currently closed — we\'re at capacity during the free trial. Check back soon!')
      }

      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { username } },
      })
      if (error) throw error
      if (!data.user) throw new Error('Sign up failed')

      // No session means Supabase requires email confirmation first
      if (!data.session) {
        set({
          needsEmailConfirmation: true,
          isLoading: false,
        })
        return
      }

      const profile = await fetchProfile(data.user.id)
      set({
        user: {
          id: data.user.id,
          email: data.user.email!,
          username: profile.username ?? username,
          created_at: profile.created_at ?? new Date().toISOString(),
          role: 'user',
          avatar_url: undefined,
          tos_accepted_at: undefined,
          is_public: false,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err) {
      // The DB trigger enforcing the cap raises REGISTRATION_CLOSED, which
      // Supabase auth surfaces as a generic "Database error saving new user".
      const raw = (err as Error).message ?? ''
      const message =
        raw.includes('REGISTRATION_CLOSED') || raw.includes('Database error saving new user')
          ? "Registration is currently closed — we're at capacity during the free trial. Check back soon!"
          : raw
      set({ error: message, isLoading: false })
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
          tos_accepted_at: profile.tos_accepted_at ?? undefined,
          is_public: profile.is_public ?? false,
        },
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err) {
      console.warn('[checkAuth] failed to restore session:', err)
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
      const res = await fetch(`${API_BASE}/auth/avatar`, {
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

      const res = await fetch(`${API_BASE}/auth/avatar`, {
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

  changePassword: async (curPass, newPass) => {
    const email = get().user?.email
    if (!email) throw new Error('Not authenticated')
    // Re-authenticate to verify current password
    const { error: authError } = await supabase.auth.signInWithPassword({ email, password: curPass })
    if (authError) throw new Error('Current password is incorrect')
    // Now update to new password
    const { error } = await supabase.auth.updateUser({ password: newPass })
    if (error) throw error
  },

  acceptTos: async () => {
    const userId = get().user?.id
    if (!userId) throw new Error('Not authenticated')
    const now = new Date().toISOString()
    const { error } = await supabase
      .from('profiles')
      .update({ tos_accepted_at: now })
      .eq('id', userId)
    if (error) throw error
    set((state) => ({
      user: state.user ? { ...state.user, tos_accepted_at: now } : null,
    }))
  },
}))
