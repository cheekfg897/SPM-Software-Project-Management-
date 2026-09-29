/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend's address in development. Requests to /api are proxied there, so the
// browser only ever talks to the Vite server and the backend needs no CORS setup.
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:5000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: { '/api': BACKEND_URL },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Integration tests need a running backend; they have their own config and command.
    exclude: ['src/integration/**', 'node_modules/**'],
    coverage: {
      provider: 'v8',
      // cobertura-coverage.xml feeds diff-cover in CI (changed lines must be 100% covered).
      reporter: ['text', 'html', 'cobertura'],
      include: ['src/**/*.{ts,tsx}'],
      // main.tsx and App.tsx only wire the real browser together; the e2e tests cover them.
      exclude: [
        'src/**/*.test.{ts,tsx}',
        // Test helpers: src/test for shared ones, <feature>/test for a feature's own.
        'src/**/test/**',
        'src/mocks/**',
        'src/integration/**',
        'src/main.tsx',
        'src/app/App.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: { lines: 90, branches: 90, functions: 90, statements: 90 },
    },
  },
})
