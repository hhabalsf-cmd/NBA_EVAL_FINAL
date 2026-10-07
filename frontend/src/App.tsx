import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Home, Gamepad2, ClipboardList, FlaskConical, Trophy, ChartNoAxesCombined } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import HomePage from './features/home/HomePage'
import LandingPage from './features/landing/LandingPage'
import PlayerPage from './features/predictions/PlayerPage'
import GamesPage from './features/games/GamesPage'
import PicksPage from './features/picks/PicksPage'
import ResearchPage from './features/research/ResearchPage'
import ForecastPage from './features/forecasts/ForecastPage'
import LoginPage from './features/auth/LoginPage'
import SignupPage from './features/auth/SignupPage'
import SettingsPage from './features/settings/SettingsPage'
import LeaderboardPage from './features/social/LeaderboardPage'
import PublicProfilePage from './features/social/PublicProfilePage'
import ProtectedRoute from './features/auth/ProtectedRoute'
import UserMenu from './shared/components/UserMenu'
import AppShell from './shared/components/AppShell'
import { useAuthStore } from './features/auth/authStore'
import { supabase } from './shared/lib/supabase'
import { useQuery } from '@tanstack/react-query'
import { getPicks } from './features/picks/api'

const pageVariants = {
  initial: { opacity: 0, y: 12, rotateX: 2 },
  animate: { opacity: 1, y: 0, rotateX: 0 },
  exit: { opacity: 0, y: -8, rotateX: -1 },
}

function AppRoutes() {
  const location = useLocation()
  const { isAuthenticated } = useAuthStore()

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: 0.25, ease: 'easeOut' }}
        style={{ perspective: 1200 }}
      >
        <Routes location={location}>
          <Route path="/" element={isAuthenticated ? <Navigate to="/app" replace /> : <LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/app" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
          <Route path="/player/:playerName" element={<ProtectedRoute><PlayerPage /></ProtectedRoute>} />
          <Route path="/research" element={<ProtectedRoute><ResearchPage /></ProtectedRoute>} />
          <Route path="/forecasts" element={<ProtectedRoute><ForecastPage /></ProtectedRoute>} />
          <Route path="/research/:playerName" element={<ProtectedRoute><ResearchPage /></ProtectedRoute>} />
          <Route path="/games" element={<ProtectedRoute><GamesPage /></ProtectedRoute>} />
          <Route path="/picks" element={<ProtectedRoute><PicksPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/users/:username" element={<PublicProfilePage />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  )
}

function App() {
  const { isAuthenticated, checkAuth } = useAuthStore()

  useEffect(() => {
    checkAuth()

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (!session) {
        useAuthStore.setState({ user: null, isAuthenticated: false })
      } else if (event === 'TOKEN_REFRESHED' || event === 'SIGNED_IN') {
        // Re-sync store — checkAuth handles profile fetch
        useAuthStore.getState().checkAuth()
      }
    })

    const handleUnauthorized = () => {
      useAuthStore.setState({ user: null, isAuthenticated: false })
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)

    return () => {
      subscription.unsubscribe()
      window.removeEventListener('auth:unauthorized', handleUnauthorized)
    }
  }, [checkAuth])

  const { data: pendingPicks = [] } = useQuery({
    queryKey: ['picks', true],
    queryFn: () => getPicks(true),
    staleTime: 1000 * 30,
    enabled: isAuthenticated,
  })

  const navItems = [
    { to: '/app', icon: Home, label: 'Home' },
    { to: '/games', icon: Gamepad2, label: 'Games' },
    { to: '/research', icon: FlaskConical, label: 'Research' },
    { to: '/forecasts', icon: ChartNoAxesCombined, label: 'Forecasts' },
    { to: '/picks', icon: ClipboardList, label: 'Picks', badge: pendingPicks.length },
    { to: '/leaderboard', icon: Trophy, label: 'Leaders' },
  ]

  return (
    <BrowserRouter>
      <AppShell navItems={navItems} isAuthenticated={isAuthenticated} userMenu={<UserMenu />}><AppRoutes /></AppShell>
    </BrowserRouter>
  )
}

export default App
