import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Home, Gamepad2, History, Dice5, FlaskConical } from 'lucide-react'
import HomePage from './pages/HomePage'
import LandingPage from './pages/LandingPage'
import PlayerPage from './pages/PlayerPage'
import HistoryPage from './pages/HistoryPage'
import GamesPage from './pages/GamesPage'
import ParlayPage from './pages/ParlayPage'
import ResearchPage from './pages/ResearchPage'
import LoginPage from './pages/auth/LoginPage'
import SignupPage from './pages/auth/SignupPage'
import SettingsPage from './pages/SettingsPage'
import ProtectedRoute from './components/auth/ProtectedRoute'
import UserMenu from './components/UserMenu'
import { useAuthStore } from './store/authStore'
import { useQuery } from '@tanstack/react-query'
import { getPicks } from './api/client'

function App() {
  const { isAuthenticated, checkAuth } = useAuthStore()

  // Rehydrate session on app load
  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  const { data: pendingPicks = [] } = useQuery({
    queryKey: ['pending-picks'],
    queryFn: () => getPicks(30, true),
    staleTime: 1000 * 30,
    enabled: isAuthenticated,
  })

  const navItems = [
    { to: '/app', icon: Home, label: 'Home' },
    { to: '/games', icon: Gamepad2, label: 'Games' },
    { to: '/research', icon: FlaskConical, label: 'Research' },
    { to: '/parlay', icon: Dice5, label: 'Parlays', badge: pendingPicks.length },
    { to: '/history', icon: History, label: 'History' },
  ]

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-primary flex flex-col">
        {/* Top Navigation */}
        <nav className="sticky top-0 z-50 bg-bg-secondary/80 backdrop-blur-xl border-b border-border-subtle">
          <div className="max-w-5xl mx-auto px-4 sm:px-8">
            <div className="flex items-center justify-between h-14 sm:h-16">
              {/* Logo */}
              <NavLink to="/" className="flex items-center gap-1 group">
                <span className="font-bold text-[15px] tracking-tight text-text-primary group-hover:text-accent transition-colors duration-150">
                  Bettin&apos;
                </span>
                <span style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '17px', letterSpacing: '0.05em', color: 'var(--accent)' }}>
                  Jrys
                </span>
              </NavLink>

              {/* Desktop Nav Links */}
              <div className="hidden sm:flex items-center gap-1">
                {navItems.map(({ to, icon: Icon, label, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      `flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg transition-all duration-150 ${
                        isActive
                          ? 'bg-accent-muted text-accent'
                          : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary'
                      }`
                    }
                  >
                    <Icon className="w-4 h-4" />
                    {label}
                    {badge != null && badge > 0 && (
                      <span className="flex items-center justify-center w-4 h-4 rounded-full bg-accent text-white text-[10px] font-bold">
                        {badge}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>

              {/* Auth */}
              <div className="flex items-center gap-1">
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
        <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-8 py-6 sm:py-10 pb-24 sm:pb-10">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/app" element={<HomePage />} />
            <Route path="/player/:playerName" element={<PlayerPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/research/:playerName" element={<ResearchPage />} />
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

        {/* Footer - hidden on mobile since bottom nav is there */}
        <footer className="hidden sm:block border-t border-border-subtle py-8 mt-auto">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 flex items-center justify-between">
            <span className="text-text-muted text-xs tracking-wide">ML-Powered Analysis</span>
            <span className="text-text-muted text-xs tracking-wide font-mono">EVAL</span>
          </div>
        </footer>

        {/* Mobile Bottom Navigation */}
        <nav className="sm:hidden fixed bottom-0 left-0 right-0 z-50 bg-bg-secondary/95 backdrop-blur-xl border-t border-border-subtle safe-area-bottom">
          <div className="flex items-center justify-around h-16 px-2">
            {navItems.map(({ to, icon: Icon, label, badge }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex flex-col items-center gap-1 px-3 py-1.5 rounded-lg transition-all duration-150 min-w-[60px] ${
                    isActive
                      ? 'text-accent'
                      : 'text-text-muted'
                  }`
                }
              >
                <div className="relative">
                  <Icon className="w-5 h-5" />
                  {badge != null && badge > 0 && (
                    <span className="absolute -top-1.5 -right-2 flex items-center justify-center w-4 h-4 rounded-full bg-accent text-white text-[9px] font-bold">
                      {badge}
                    </span>
                  )}
                </div>
                <span className="text-[10px] font-medium">{label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
      </div>
    </BrowserRouter>
  )
}

export default App
