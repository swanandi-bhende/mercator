import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
  server: {
    port: 5173,
    open: true,
    proxy: {
      // Proxy API requests to local backend during development to avoid CORS
      '/api': 'http://localhost:8000',
      '/ops': 'http://localhost:8000',
      '/traces': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      // Backend root endpoints
      '/auth': 'http://localhost:8000',
      '/wallet/balance': 'http://localhost:8000',
      '/wallet/is_custodial': 'http://localhost:8000',
      '/wallet/export': 'http://localhost:8000',
      '/ipfs': 'http://localhost:8000',
    },
  }
})
