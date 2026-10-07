import type { ReactNode, ElementType } from 'react'
import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'

export interface NavigationItem { to: string; icon: ElementType; label: string; badge?: number }

export default function AppShell({ children, navItems, isAuthenticated, userMenu }: { children: ReactNode; navItems: NavigationItem[]; isAuthenticated: boolean; userMenu: ReactNode }) {
  return (
      <div className="min-h-screen bg-bg-primary flex flex-col">
        {/* Top Navigation */}
        <nav className="sticky top-0 z-50 bg-bg-secondary/80 backdrop-blur-xl border-b border-border-subtle">
          <div className="max-w-5xl mx-auto px-4 sm:px-8">
            <div className="flex items-center justify-between h-20 sm:h-24">
              {/* Logo */}
              <NavLink to="/" className="flex items-center group -ml-4 sm:-ml-8">
                <img
                  src="/logo-full.png"
                  alt="Bettin' Jrys"
                  className="h-14 sm:h-[68px] object-contain group-hover:opacity-80 transition-opacity duration-150"
                />
              </NavLink>

              {/* Desktop Nav Links */}
              <div className="hidden sm:flex items-center gap-1">
                {navItems
                  .filter(item => isAuthenticated || item.to === '/leaderboard')
                  .map(({ to, icon: Icon, label, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      `relative flex items-center gap-2 px-3.5 py-2 font-display text-[15px] font-semibold uppercase tracking-wide rounded-lg transition-all duration-150 ${isActive
                        ? 'text-accent'
                        : 'text-text-muted hover:text-text-secondary hover:bg-bg-tertiary hover:-translate-y-px'
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon className="w-4 h-4" />
                        {label}
                        {badge != null && badge > 0 && (
                          <span className="flex items-center justify-center w-4 h-4 rounded-full bg-accent text-white text-[10px] font-bold">
                            {badge}
                          </span>
                        )}
                        {isActive && (
                          <motion.div
                            layoutId="nav-underline"
                            className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                            style={{
                              background: 'var(--accent)',
                              boxShadow: '0 2px 8px var(--accent-glow)',
                              transform: 'translateZ(2px)',
                            }}
                            transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                          />
                        )}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>

              {/* Auth */}
              <div className="flex items-center gap-1">
                {isAuthenticated ? (
                  userMenu
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

        {/* Accent glow */}
        <div className="page-glow" />

        {/* Main Content */}
        <main className="relative z-10 flex-1 max-w-5xl w-full mx-auto px-4 sm:px-8 py-6 sm:py-10 pb-24 sm:pb-10">
          {children}
        </main>

        {/* Footer */}
        <footer className="hidden sm:block border-t border-border-subtle py-8 mt-auto">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 flex items-center justify-between">
            <span className="text-text-muted text-xs tracking-wide font-mono">ML-Powered Analysis</span>
            <span className="text-text-muted text-sm font-display font-semibold uppercase tracking-widest">Bettin' Jrys</span>
          </div>
        </footer>

        {/* Mobile Bottom Navigation */}
        <nav className="sm:hidden fixed bottom-0 left-0 right-0 z-50 bg-bg-secondary/95 backdrop-blur-xl border-t border-border-subtle safe-area-bottom">
          <div className="flex items-center justify-around h-16 px-2">
            {navItems
              .filter(item => isAuthenticated || item.to === '/leaderboard')
              .map(({ to, icon: Icon, label, badge }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex flex-col items-center gap-1 px-3 py-1.5 rounded-lg transition-all duration-150 min-w-[60px] ripple ${isActive ? 'text-accent' : 'text-text-muted'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <motion.div
                      className="relative"
                      whileTap={{ scale: 0.82 }}
                      transition={{ duration: 0.1 }}
                    >
                      <Icon className="w-5 h-5" />
                      {badge != null && badge > 0 && (
                        <span className="absolute -top-1.5 -right-2 flex items-center justify-center w-4 h-4 rounded-full bg-accent text-white text-[9px] font-bold">
                          {badge}
                        </span>
                      )}
                    </motion.div>
                    <span className={`text-[10px] font-medium ${isActive ? 'text-accent' : 'text-text-muted'}`}>{label}</span>
                    {isActive && (
                      <motion.div
                        layoutId="mobile-nav-dot"
                        className="absolute -bottom-0.5 w-1 h-1 rounded-full"
                        style={{ background: 'var(--accent)' }}
                        transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                      />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </nav>
      </div>
  )
}
