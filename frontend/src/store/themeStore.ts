import { create } from 'zustand'

type Theme = 'dark' | 'light'

interface ThemeStore {
  theme: Theme
  toggleTheme: () => void
}

function applyTheme(theme: Theme) {
  if (theme === 'light') {
    document.documentElement.classList.add('light')
  } else {
    document.documentElement.classList.remove('light')
  }
}

// Read saved theme or system preference on init
const savedTheme = localStorage.getItem('eval-theme') as Theme | null
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
const initialTheme: Theme = savedTheme ?? (prefersDark ? 'dark' : 'dark')

// Apply immediately before first render to avoid flash
applyTheme(initialTheme)

export const useThemeStore = create<ThemeStore>(() => ({
  theme: initialTheme,
  toggleTheme: () => {
    useThemeStore.setState((state) => {
      const next: Theme = state.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('eval-theme', next)
      applyTheme(next)
      return { theme: next }
    })
  },
}))
