// Relative imports, not `@/`: the Playwright tests import this file, and they don't know
// the alias. Keep this file free of msw and browser code for the same reason.
import { ROLE } from '../../config/roles'
import type { Role } from '../../config/roles'

export interface MockAccount {
  id: number
  email: string
  password: string
  full_name: string
  role: Role
  organisation_id: number | null
}

/** Accounts every mock run starts with. Tests and e2e journeys log in as these. */
export const MOCK_ACCOUNTS = {
  attendee: {
    id: 1,
    email: 'alice@example.com',
    password: 'Password123',
    full_name: 'Alice Tan',
    role: ROLE.ATTENDEE,
    organisation_id: null,
  },
  organiser: {
    id: 2,
    email: 'omar@example.com',
    password: 'Password123',
    full_name: 'Omar Rahman',
    role: ROLE.EVENT_ORGANISER,
    organisation_id: 1,
  },
  coordinator: {
    id: 3,
    email: 'chloe@connectsphere.test',
    password: 'Password123',
    full_name: 'Chloe Lim',
    role: ROLE.EVENT_COORDINATOR,
    organisation_id: null,
  },
} as const satisfies Record<string, MockAccount>

/** Client organisations that exist in the mock (ADR-0013). */
export const MOCK_ORGANISATION_IDS: readonly number[] = [1, 2]
