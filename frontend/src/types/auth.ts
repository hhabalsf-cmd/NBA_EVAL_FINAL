export interface User {
  id: string
  email: string
  username: string
  created_at: string
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}
