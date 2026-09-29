import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'

import { resetMockBackend } from '@/mocks/handlers'
import { server } from '@/mocks/server'

import { sendRequestsAs } from './sendRequestsAs'

// A request with no handler fails the test, so a test can never quietly reach a real network.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  server.events.removeAllListeners()
  resetMockBackend()
  sendRequestsAs(null)
  cleanup()
  localStorage.clear()
})
afterAll(() => server.close())
