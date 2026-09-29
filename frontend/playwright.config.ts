import { defineConfig, devices } from '@playwright/test'

/**
 * Port for the app under test, kept apart from the everyday dev server (5173). Set E2E_PORT
 * to run two checkouts' e2e tests at once: locally an already-running server is reused.
 */
const E2E_PORT = Number(process.env.E2E_PORT ?? 4174)

/**
 * End-to-end tests drive the real app in a browser. The app runs in Vite's "mock" mode,
 * so every API call is answered by src/mocks: no backend is needed, and each journey sees
 * the same data. The backend contract itself is checked by the integration tests.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${E2E_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: `npm run dev:mock -- --port ${E2E_PORT} --strictPort`,
    url: `http://localhost:${E2E_PORT}`,
    reuseExistingServer: !process.env.CI,
  },
})
