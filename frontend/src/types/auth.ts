export interface User {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
  avatar_url?: string
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}
