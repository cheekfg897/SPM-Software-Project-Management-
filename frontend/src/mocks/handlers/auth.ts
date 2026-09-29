import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { isRecord } from '@/lib/isRecord'

/**
 * The auth endpoints, as the backend answers them (backend/app/modules/auth, with SCRUM-66's
 * organisation_id). Accounts live in memory, starting from MOCK_ACCOUNTS.
 */

interface MockAccount {
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

export const INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password.'
const INVALID_TOKEN_MESSAGE = 'Missing, invalid or expired token.'
const REQUIRED_MESSAGE = 'Missing data for required field.'
const MOCK_TOKEN_PREFIX = 'mock-token-'

const accounts: MockAccount[] = Object.values(MOCK_ACCOUNTS)

/** A signed-in session for `account`, for renderApp's `session` option or a seeded browser. */
export function mockSessionFor(account: MockAccount) {
  return {
    accessToken: `${MOCK_TOKEN_PREFIX}${account.id}`,
    user: { id: account.id, full_name: account.full_name, role: account.role },
  }
}

function publicUser(account: MockAccount) {
  return {
    id: account.id,
    email: account.email,
    full_name: account.full_name,
    role: account.role,
    organisation_id: account.organisation_id,
    created_at: '2026-09-29T10:00:00+08:00',
  }
}

function errorResponse(status: number, error: string, message: string) {
  return HttpResponse.json({ error, message }, { status })
}

function validationError(details: Record<string, string[]>) {
  return HttpResponse.json(
    { error: 'validation_error', message: 'Invalid request.', details },
    { status: 400 },
  )
}

function missingFields(body: Record<string, unknown>, names: string[]): Record<string, string[]> {
  const details: Record<string, string[]> = {}
  for (const name of names) {
    if (body[name] === undefined || body[name] === '') {
      details[name] = [REQUIRED_MESSAGE]
    }
  }
  return details
}

async function readBody(request: Request): Promise<Record<string, unknown>> {
  const body: unknown = await request.json().catch(() => null)
  return isRecord(body) ? body : {}
}

function findByEmail(email: unknown): MockAccount | undefined {
  const wanted = String(email).trim().toLowerCase()
  return accounts.find((account) => account.email === wanted)
}

function accountForToken(request: Request): MockAccount | undefined {
  const header = request.headers.get('Authorization') ?? ''
  const id = Number(header.replace(`Bearer ${MOCK_TOKEN_PREFIX}`, ''))
  return accounts.find((account) => account.id === id)
}

export const authHandlers: RequestHandler[] = [
  http.post('/api/auth/login', async ({ request }) => {
    const body = await readBody(request)
    const missing = missingFields(body, ['email', 'password'])
    if (Object.keys(missing).length > 0) {
      return validationError(missing)
    }
    const account = findByEmail(body.email)
    if (account === undefined || account.password !== body.password) {
      return errorResponse(401, 'authentication_error', INVALID_CREDENTIALS_MESSAGE)
    }
    return HttpResponse.json({
      access_token: `${MOCK_TOKEN_PREFIX}${account.id}`,
      token_type: 'Bearer',
      user: { id: account.id, full_name: account.full_name, role: account.role },
    })
  }),

  http.get('/api/auth/me', ({ request }) => {
    const account = accountForToken(request)
    if (account === undefined) {
      return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
    }
    return HttpResponse.json(publicUser(account))
  }),
]
