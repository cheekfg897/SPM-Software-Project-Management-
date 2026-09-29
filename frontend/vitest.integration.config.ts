import { defineConfig } from 'vitest/config'

import viteConfig from './vite.config'

/** The running backend these tests call. Start it first (frontend/CLAUDE.md §Tests). */
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:5000'

/**
 * Integration tests: the real API functions in src/features/<name>/api.ts against a real,
 * running backend. No mocks. They check that the shapes the frontend expects are the shapes
 * the backend sends, including error bodies.
 *
 * Only the plugins and the `@` alias are borrowed from vite.config.ts: merging the whole
 * config would also merge in the unit tests' include list and mock-server setup.
 */
export default defineConfig({
  plugins: viteConfig.plugins,
  resolve: viteConfig.resolve,
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['src/integration/**/*.int.test.ts'],
    env: { VITE_API_ORIGIN: BACKEND_URL },
    // One backend, one database: run the files one after another.
    fileParallelism: false,
  },
})
