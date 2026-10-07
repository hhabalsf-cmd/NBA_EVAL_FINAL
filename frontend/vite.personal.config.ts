import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-personal',
    rollupOptions: { input: path.resolve(__dirname, 'personal.html') },
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
})
