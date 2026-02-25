export interface User {
  id: string
  email: string
  username: string
  created_at: string
  role: 'user' | 'admin'
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}
