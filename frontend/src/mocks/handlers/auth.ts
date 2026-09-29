import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { EXTERNAL_ROLES, ROLE } from '@/config/roles'
import { isRecord } from '@/lib/isRecord'

import { MOCK_ACCOUNTS, MOCK_ORGANISATION_IDS } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

export { MOCK_ACCOUNTS } from '../fixtures/accounts'

/**
 * The auth endpoints, as the backend answers them (backend/app/modules/auth, with SCRUM-66's
 * organisation_id and SCRUM-88's external-only sign-up). Accounts live in memory: sign up, then
 * log in with the same details, and it works until the page reloads or resetMockAccounts runs.
 */

export const INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password.'
export const EMAIL_IN_USE_MESSAGE = 'An account with this email already exists.'
const INVALID_TOKEN_MESSAGE = 'Missing, invalid or expired token.'
const REQUIRED_MESSAGE = 'Missing data for required field.'
const MOCK_TOKEN_PREFIX = 'mock-token-'

let accounts: MockAccount[] = []

/** Forget every account made by sign-up, keeping only MOCK_ACCOUNTS. */
export function resetMockAccounts(): void {
  accounts = Object.values(MOCK_ACCOUNTS).map((account) => ({ ...account }))
}
resetMockAccounts()

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

/** The first rule the password breaks, in the backend's order (ADR-0005). */
function passwordProblem(password: string): string | null {
  if (password.length < 8) {
    return 'Password must be at least 8 characters long.'
  }
  if (!/[A-Za-z]/.test(password)) {
    return 'Password must contain at least one letter.'
  }
  if (!/\d/.test(password)) {
    return 'Password must contain at least one digit.'
  }
  return null
}

function organisationProblem(role: unknown, organisationId: unknown): string | null {
  const hasOrganisation = organisationId !== null && organisationId !== undefined
  if (role === ROLE.EVENT_ORGANISER && !hasOrganisation) {
    return 'Event Organisers must belong to a client organisation.'
  }
  if (role !== ROLE.EVENT_ORGANISER && hasOrganisation) {
    return 'Only Event Organisers belong to a client organisation.'
  }
  if (hasOrganisation && !MOCK_ORGANISATION_IDS.includes(Number(organisationId))) {
    return 'Client organisation not found.'
  }
  return null
}

function registrationProblems(body: Record<string, unknown>): Record<string, string[]> {
  const details = missingFields(body, ['email', 'password', 'full_name', 'role'])
  const password = typeof body.password === 'string' ? body.password : ''
  const passwordMessage = passwordProblem(password)
  if (details.password === undefined && passwordMessage !== null) {
    details.password = [passwordMessage]
  }
  const isExternalRole = EXTERNAL_ROLES.some((role) => role === body.role)
  if (details.role === undefined && !isExternalRole) {
    details.role = ['Role must be one of: attendee, event_organiser.']
  }
  const organisationMessage = organisationProblem(body.role, body.organisation_id)
  if (Object.keys(details).length === 0 && organisationMessage !== null) {
    details.organisation_id = [organisationMessage]
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

  http.post('/api/auth/register', async ({ request }) => {
    const body = await readBody(request)
    const problems = registrationProblems(body)
    if (Object.keys(problems).length > 0) {
      return validationError(problems)
    }
    if (findByEmail(body.email) !== undefined) {
      return errorResponse(409, 'conflict', EMAIL_IN_USE_MESSAGE)
    }
    const account: MockAccount = {
      id: accounts.length + 100,
      email: String(body.email).trim().toLowerCase(),
      password: String(body.password),
      full_name: String(body.full_name).trim(),
      role: body.role === ROLE.EVENT_ORGANISER ? ROLE.EVENT_ORGANISER : ROLE.ATTENDEE,
      organisation_id: typeof body.organisation_id === 'number' ? body.organisation_id : null,
    }
    accounts.push(account)
    return HttpResponse.json(publicUser(account), { status: 201 })
  }),

  http.get('/api/auth/me', ({ request }) => {
    const account = accountForToken(request)
    if (account === undefined) {
      return errorResponse(401, 'authentication_error', INVALID_TOKEN_MESSAGE)
    }
    return HttpResponse.json(publicUser(account))
  }),
]
