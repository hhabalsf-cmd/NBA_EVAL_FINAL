import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Home, Gamepad2, History, Activity, Dice5 } from 'lucide-react'
import HomePage from './pages/HomePage'
import LandingPage from './pages/LandingPage'
import PlayerPage from './pages/PlayerPage'
import HistoryPage from './pages/HistoryPage'
import GamesPage from './pages/GamesPage'
import ParlayPage from './pages/ParlayPage'
import LoginPage from './pages/auth/LoginPage'
import SignupPage from './pages/auth/SignupPage'
import SettingsPage from './pages/SettingsPage'
import ProtectedRoute from './components/auth/ProtectedRoute'
import UserMenu from './components/UserMenu'
import { useAuthStore } from './store/authStore'
import { useQuery } from '@tanstack/react-query'
import { getPicks } from './api/client'

function App() {
  const { isAuthenticated } = useAuthStore()
  const { data: pendingPicks = [] } = useQuery({
    queryKey: ['pending-picks'],
    queryFn: () => getPicks(30, true),
    staleTime: 1000 * 30,
  })

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-primary flex flex-col">
        {/* Navigation */}
        <nav className="sticky top-0 z-50 bg-bg-secondary/80 backdrop-blur-xl border-b border-border-subtle">
          <div className="max-w-5xl mx-auto px-5 sm:px-8">
            <div className="flex items-center justify-between h-16">
              {/* Logo → landing */}
              <NavLink to="/" className="flex items-center gap-2.5 group">
                <Activity className="w-5 h-5 text-accent transition-transform group-hover:scale-110" strokeWidth={2.5} />
                <span className="font-mono font-semibold text-[15px] tracking-tight text-text-primary">
                  EVAL
                </span>
              </NavLink>

              {/* Nav Links */}
              <div className="flex items-center gap-1">
                <NavLink
                  to="/app"
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-all duration-150 ${
                      isActive
                        ? 'bg-accent-muted text-accent'
                        : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary'
                    }`
                  }
                >
                  <Home className="w-4 h-4" />
                  <span className="hidden sm:inline">Home</span>
                </NavLink>
                <NavLink
                  to="/games"
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-all duration-150 ${
                      isActive
                        ? 'bg-accent-muted text-accent'
                        : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary'
                    }`
                  }
                >
                  <Gamepad2 className="w-4 h-4" />
                  <span className="hidden sm:inline">Games</span>
                </NavLink>
                <NavLink
                  to="/history"
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-all duration-150 ${
                      isActive
                        ? 'bg-accent-muted text-accent'
                        : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary'
                    }`
                  }
                >
                  <History className="w-4 h-4" />
                  <span className="hidden sm:inline">History</span>
                </NavLink>
<NavLink
                  to="/parlay"
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-all duration-150 ${
                      isActive
                        ? 'bg-accent-muted text-accent'
                        : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary'
                    }`
                  }
                >
                  <Dice5 className="w-4 h-4" />
                  <span className="hidden sm:inline">Parlays</span>
                  {pendingPicks.length > 0 && (
                    <span className="flex items-center justify-center w-4 h-4 rounded-full bg-accent text-white text-[10px] font-bold">
                      {pendingPicks.length}
                    </span>
                  )}
                </NavLink>
              </div>

              {/* Auth */}
              <div className="flex items-center">
                {isAuthenticated ? (
                  <UserMenu />
                ) : (
                  <NavLink
                    to="/login"
                    className="text-sm font-medium text-text-muted hover:text-text-primary transition-colors px-3 py-1.5"
                  >
                    Sign In
                  </NavLink>
                )}
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="flex-1 max-w-5xl w-full mx-auto px-5 sm:px-8 py-10">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/app" element={<HomePage />} />
            <Route path="/player/:playerName" element={<PlayerPage />} />
            <Route path="/games" element={<GamesPage />} />
            <Route path="/history" element={<HistoryPage />} />
<Route path="/parlay" element={<ParlayPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <SettingsPage />
                </ProtectedRoute>
              }
            />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="border-t border-border-subtle py-8 mt-auto">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 flex items-center justify-between">
            <span className="text-text-muted text-xs tracking-wide">ML-Powered Analysis</span>
            <span className="text-text-muted text-xs tracking-wide font-mono">EVAL</span>
          </div>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
