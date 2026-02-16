export interface User {
  id: string
  email: string
  username: string
  subscription_tier: 'free' | 'pro' | 'premium'
  created_at: string
  avatar_url?: string
}

export interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}

export interface SubscriptionTier {
  id: string
  name: string
  price: number
  features: string[]
  limits: {
    daily_predictions: number
    saved_picks: number
    historical_data_days: number
  }
}

export const SUBSCRIPTION_TIERS: SubscriptionTier[] = [
  {
    id: 'free',
    name: 'Free',
    price: 0,
    features: ['Basic predictions', '5 saved picks', '7 days history'],
    limits: { daily_predictions: 5, saved_picks: 5, historical_data_days: 7 },
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 9.99,
    features: ['Unlimited predictions', 'Unlimited picks', '90 days history', 'Game predictions'],
    limits: { daily_predictions: -1, saved_picks: -1, historical_data_days: 90 },
  },
  {
    id: 'premium',
    name: 'Premium',
    price: 19.99,
    features: ['Everything in Pro', 'Best bets alerts', 'Full history', 'Priority support'],
    limits: { daily_predictions: -1, saved_picks: -1, historical_data_days: -1 },
  },
]
