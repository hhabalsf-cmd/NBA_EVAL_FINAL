export interface User {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
  avatar_url?: string
  tos_accepted_at?: string
  is_public?: boolean
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}
