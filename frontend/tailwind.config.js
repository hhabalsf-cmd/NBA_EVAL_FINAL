/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#080B11',
          secondary: '#111827',
          tertiary: '#1A2233',
          elevated: '#243044',
        },
        accent: {
          DEFAULT: '#38BDF8',
          hover: '#0EA5E9',
          gold: '#FBBF24',
          success: '#34D399',
          danger: '#F87171',
        },
        text: {
          primary: '#F8FAFC',
          secondary: '#A5B4CB',
          muted: '#6B7FA0',
        },
        border: {
          subtle: '#1E2D42',
          DEFAULT: '#2E4263',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
