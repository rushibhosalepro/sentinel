import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/instruction': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/ask': 'http://localhost:8000',
      '/scene': 'http://localhost:8000',
      '/split': 'http://localhost:8000',
      '/bench-strip': 'http://localhost:8000',
      '/examples': 'http://localhost:8000',
      '/incident': 'http://localhost:8000',
      '/rules': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/ws-split': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
