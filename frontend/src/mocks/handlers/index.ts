import type { RequestHandler } from 'msw'

import { authHandlers, resetMockAccounts } from './auth'
import { catalogueHandlers, resetMockCatalogue } from './catalogue'
import { eventRequestHandlers } from './eventRequests'
import { notificationHandlers, resetMockNotifications } from './notifications'

/**
 * Every mock handler, one file per feature. They stand in for the backend in unit tests,
 * in Playwright runs and in `npm run dev:mock`. They follow the backend's real response
 * shapes; the integration tests in src/integration check those shapes against the backend.
 */
export const handlers: RequestHandler[] = [
  ...authHandlers,
  ...catalogueHandlers,
  ...eventRequestHandlers,
  ...notificationHandlers,
]

/** Put the mock backend's data back as it started, so no test sees another's sign-ups or registrations. */
export function resetMockBackend(): void {
  resetMockAccounts()
  resetMockCatalogue()
  resetMockNotifications()
}
