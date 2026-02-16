import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import HomePage from './pages/HomePage'
import PlayerPage from './pages/PlayerPage'
import HistoryPage from './pages/HistoryPage'
import GamesPage from './pages/GamesPage'
import LoginPage from './pages/auth/LoginPage'
import SignupPage from './pages/auth/SignupPage'
import SettingsPage from './pages/SettingsPage'
import ProtectedRoute from './components/auth/ProtectedRoute'
import UserMenu from './components/UserMenu'
import { useAuthStore } from './store/authStore'

function App() {
  const { isAuthenticated } = useAuthStore()

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-primary">
        {/* Navigation */}
        <nav className="sticky top-0 z-50 bg-bg-secondary border-b border-border-subtle">
          <div className="max-w-6xl mx-auto px-4 sm:px-6">
            <div className="flex items-center justify-between h-14">
              {/* Logo */}
              <NavLink to="/" className="flex items-center gap-2">
                <span className="font-mono font-bold text-lg text-accent">Bettin'Jrys</span>
              </NavLink>

              {/* Nav Links */}
              <div className="flex items-center gap-1">
                <NavLink
                  to="/"
                  end
                  className={({ isActive }) =>
                    `px-3 py-1.5 text-sm font-medium transition-colors border-b-2 ${
                      isActive
                        ? 'border-accent text-text-primary'
                        : 'border-transparent text-text-secondary hover:text-text-primary'
                    }`
                  }
                >
                  Home
                </NavLink>
                <NavLink
                  to="/games"
                  className={({ isActive }) =>
                    `px-3 py-1.5 text-sm font-medium transition-colors border-b-2 ${
                      isActive
                        ? 'border-accent text-text-primary'
                        : 'border-transparent text-text-secondary hover:text-text-primary'
                    }`
                  }
                >
                  Games
                </NavLink>
                <NavLink
                  to="/history"
                  className={({ isActive }) =>
                    `px-3 py-1.5 text-sm font-medium transition-colors border-b-2 ${
                      isActive
                        ? 'border-accent text-text-primary'
                        : 'border-transparent text-text-secondary hover:text-text-primary'
                    }`
                  }
                >
                  History
                </NavLink>
              </div>

              {/* Auth */}
              <div className="flex items-center gap-3">
                {isAuthenticated ? (
                  <UserMenu />
                ) : (
                  <NavLink
                    to="/login"
                    className="text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
                  >
                    Sign In
                  </NavLink>
                )}
              </div>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/player/:playerName" element={<PlayerPage />} />
            <Route path="/games" element={<GamesPage />} />
            <Route path="/history" element={<HistoryPage />} />
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
        <footer className="border-t border-border-subtle py-6 mt-auto">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 text-center text-text-muted text-xs">
            ML-Powered Player Prop Analysis
          </div>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
