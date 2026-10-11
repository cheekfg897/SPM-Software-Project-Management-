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
    env: {
      VITE_API_ORIGIN: BACKEND_URL,
      // A staff account made with `flask create-staff-user`; CI makes one for each run.
      INTEGRATION_STAFF_EMAIL: process.env.INTEGRATION_STAFF_EMAIL ?? '',
      INTEGRATION_STAFF_PASSWORD: process.env.INTEGRATION_STAFF_PASSWORD ?? '',
      // A seeded coordinator (flask create-staff-user) for the checks that need one.
      VITE_COORDINATOR_EMAIL: process.env.COORDINATOR_EMAIL ?? '',
      VITE_COORDINATOR_PASSWORD: process.env.COORDINATOR_PASSWORD ?? '',
    },
    // One backend, one database: run the files one after another.
    fileParallelism: false,
  },
})
