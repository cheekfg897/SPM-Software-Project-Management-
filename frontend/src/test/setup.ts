import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'

import { resetMockBackend } from '@/mocks/handlers'
import { server } from '@/mocks/server'

// A request with no handler fails the test, so a test can never quietly reach a real network.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  server.events.removeAllListeners()
  resetMockBackend()
  cleanup()
  localStorage.clear()
})
afterAll(() => server.close())
