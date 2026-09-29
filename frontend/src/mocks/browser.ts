import { setupWorker } from 'msw/browser'

import { handlers } from './handlers'

/** The mock backend in the browser, for `npm run dev:mock` and the Playwright tests. */
export const worker = setupWorker(...handlers)
