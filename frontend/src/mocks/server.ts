import { setupServer } from 'msw/node'

import { handlers } from './handlers'

/** The mock backend for Vitest. Tests override single routes with `server.use(...)`. */
export const server = setupServer(...handlers)
