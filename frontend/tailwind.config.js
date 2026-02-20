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
          primary: '#09090B',
          secondary: '#131316',
          tertiary: '#1A1A1F',
          elevated: '#232329',
        },
        accent: {
          DEFAULT: '#C9A87C',
          hover: '#B8956A',
          muted: 'rgba(201, 168, 124, 0.12)',
          success: '#6BBF8A',
          danger: '#D4736E',
        },
        text: {
          primary: '#EDEDEC',
          secondary: '#8F8B87',
          muted: '#5C5955',
        },
        border: {
          subtle: '#1E1E22',
          DEFAULT: '#2A2A30',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-up': 'slide-up 0.3s ease-out both',
        'fade-in': 'fade-in 0.15s ease-out',
        'slide-out': 'slide-out 0.2s ease-in forwards',
        'pop':       'pop 0.25s ease-out',
        'check-in':  'check-in 0.2s ease-out forwards',
      },
      keyframes: {
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-out': {
          '0%':   { opacity: '1', transform: 'translateX(0)' },
          '100%': { opacity: '0', transform: 'translateX(40px)' },
        },
        'pop': {
          '0%':   { transform: 'scale(1)' },
          '50%':  { transform: 'scale(1.12)' },
          '100%': { transform: 'scale(1)' },
        },
        'check-in': {
          '0%':   { opacity: '0', transform: 'scale(0)' },
          '60%':  { opacity: '1', transform: 'scale(1.2)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
      },
    },
  },
  plugins: [],
}
