/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    restoreMocks: true,
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/services/sse.ts', 'src/services/chatStream.ts'],
      thresholds: {
        'src/services/sse.ts': {
          statements: 95,
          branches: 85,
          functions: 100,
          lines: 95,
        },
        'src/services/chatStream.ts': {
          statements: 75,
          branches: 65,
          functions: 80,
          lines: 75,
        },
      },
    },
  },
  server: {
    port: 5173,
    // Playwright E2E uses route-level fake APIs; disable proxy so leaks fail loudly.
    proxy: process.env.VITE_E2E_FAKE
      ? undefined
      : {
          '/api': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
        },
  },
})
