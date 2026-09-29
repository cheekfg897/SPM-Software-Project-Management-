import type { RequestHandler } from 'msw'

import { authHandlers } from './auth'
import { catalogueHandlers } from './catalogue'

/**
 * Every mock handler, one file per feature. They stand in for the backend in unit tests,
 * in Playwright runs and in `npm run dev:mock`. They follow the backend's real response
 * shapes; the integration tests in src/integration check those shapes against the backend.
 */
export const handlers: RequestHandler[] = [...authHandlers, ...catalogueHandlers]
