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

/** The accounts written out in full; MOCK_ACCOUNTS adds ones built from them. */
const BASE_ACCOUNTS = {
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
  technicalSupport: {
    id: 5,
    email: 'tariq@connectsphere.test',
    password: 'Password123',
    full_name: 'Tariq Hassan',
    role: ROLE.TECHNICAL_SUPPORT_STAFF,
    organisation_id: null,
  },
  venueStaff: {
    id: 6,
    email: 'vera@connectsphere.test',
    password: 'Password123',
    full_name: 'Vera Goh',
    role: ROLE.VENUE_STAFF,
    organisation_id: null,
  },
  // id 7: 1 to 6 are taken by the accounts above and the unlinked organiser below.
  lead: {
    id: 7,
    email: 'leon@connectsphere.test',
    password: 'Password123',
    full_name: 'Leon Goh',
    role: ROLE.EVENT_COORDINATOR_LEAD,
    organisation_id: null,
  },
} as const satisfies Record<string, MockAccount>

/** Accounts every mock run starts with. Tests and e2e journeys log in as these. */
export const MOCK_ACCOUNTS = {
  ...BASE_ACCOUNTS,
  /**
   * An organiser from before every organiser needed an organisation (ADR-0020). Otherwise
   * like the organiser, password included.
   */
  unlinkedOrganiser: {
    ...BASE_ACCOUNTS.organiser,
    id: 4,
    email: 'umar@example.com',
    full_name: 'Umar Hassan',
    organisation_id: null,
  },
  /** An attendee who has registered for nothing, so their events are empty. */
  freshAttendee: {
    ...BASE_ACCOUNTS.attendee,
    id: 8,
    email: 'ben@example.com',
    full_name: 'Ben Koh',
  },
  /** A Safety Officer (SCRUM-97). Otherwise like Venue Staff: internal, no organisation. */
  safetyOfficer: {
    ...BASE_ACCOUNTS.venueStaff,
    id: 9,
    email: 'sana@connectsphere.test',
    full_name: 'Sana Iyer',
    role: ROLE.SAFETY_OFFICER,
  },
} as const satisfies Record<string, MockAccount>

const MOCK_TOKEN_PREFIX = 'mock-token-'

/** The access token the mock backend issues to `account` when it logs in. */
export function mockTokenFor(account: MockAccount): string {
  return `${MOCK_TOKEN_PREFIX}${account.id}`
}

/** The account id inside a mock token, or null for anything that isn't one. */
export function accountIdFromMockToken(token: string): number | null {
  if (!token.startsWith(MOCK_TOKEN_PREFIX)) {
    return null
  }
  const id = Number(token.slice(MOCK_TOKEN_PREFIX.length))
  return Number.isInteger(id) ? id : null
}

/** A signed-in session for `account`: for renderApp's `session` option or a seeded browser. */
export function mockSessionFor(account: MockAccount) {
  return {
    accessToken: mockTokenFor(account),
    user: { id: account.id, full_name: account.full_name, role: account.role },
  }
}

/**
 * Client organisations that exist in the mock (ADR-0013). Organisation 1 is the mock
 * organiser's, 2 has another organisation's request, and 3 has no event requests yet.
 */
export const MOCK_ORGANISATION_IDS: readonly number[] = [1, 2, 3]
