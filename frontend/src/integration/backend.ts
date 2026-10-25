/**
 * Helpers shared by the integration tests. Every call goes to the real backend at
 * VITE_API_ORIGIN (set by vitest.integration.config.ts).
 */

import { ROLE } from '@/config/roles'
import { logIn, register } from '@/features/auth/api'
import { ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

export interface Credentials {
  email: string
  password: string
}

const MISSING_STAFF_ACCOUNT =
  'Set INTEGRATION_STAFF_EMAIL and INTEGRATION_STAFF_PASSWORD to a staff account on the ' +
  'backend, made with `flask create-staff-user` (frontend/README.md).'

/** An email no earlier run has used, so tests never collide with leftover accounts. */
export function uniqueEmail(label: string): string {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`
  return `${label}-${suffix}@integration.test`
}

/** A password that meets the backend's policy (ADR-0005). */
export const VALID_PASSWORD = 'Password123'

/**
 * The staff account the tests sign in as: an Event Coordinator made with
 * `flask create-staff-user`. CI makes a fresh one for each run (frontend.yml).
 */
export function staffAccount(): Credentials {
  const email = import.meta.env.INTEGRATION_STAFF_EMAIL ?? ''
  const password = import.meta.env.INTEGRATION_STAFF_PASSWORD ?? ''
  if (email === '' || password === '') {
    throw new Error(MISSING_STAFF_ACCOUNT)
  }
  return { email, password }
}

/** Log in, and send that user's token with every request from now on. */
export async function signInAs(credentials: Credentials): Promise<void> {
  const session = await logIn(credentials)
  sendRequestsAs(session.access_token)
}

/**
 * Sign a brand-new attendee up and send every later request as them. Answers their credentials,
 * so a later step can sign in as them again.
 */
export async function signInAsNewAttendee(): Promise<Credentials> {
  const credentials = { email: uniqueEmail('attendee'), password: VALID_PASSWORD }
  await register({ full_name: 'Integration Attendee', ...credentials, role: ROLE.ATTENDEE })
  await signInAs(credentials)
  return credentials
}

/** The ApiError a call was refused with. Fails the test if it succeeded or failed another way. */
export async function refusal(call: Promise<unknown>): Promise<ApiError> {
  const error = await call.then(
    () => expect.fail('Expected the backend to refuse the request.'),
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error(`Expected an ApiError, got ${String(error)}`)
  }
  return error
}

/** A sign-up for a new Event Organiser of `organisationId` (null to leave it out, SCRUM-66). */
export function newOrganiser(organisationId: number | null) {
  return {
    full_name: 'Integration Organiser',
    email: uniqueEmail('organiser'),
    password: VALID_PASSWORD,
    role: ROLE.EVENT_ORGANISER,
    organisation_id: organisationId,
  }
}

/**
 * A Technical Support account, for the checks only they can reach. CI makes one (frontend.yml); a
 * local run reads it from these variables and skips those checks without them:
 * INTEGRATION_TECH_SUPPORT_EMAIL=... INTEGRATION_TECH_SUPPORT_PASSWORD=... npm run test:integration
 */
const TECH_SUPPORT_EMAIL = import.meta.env.INTEGRATION_TECH_SUPPORT_EMAIL ?? ''
const TECH_SUPPORT_PASSWORD = import.meta.env.INTEGRATION_TECH_SUPPORT_PASSWORD ?? ''
export const hasTechSupport = TECH_SUPPORT_EMAIL !== '' && TECH_SUPPORT_PASSWORD !== ''

export function signInAsTechSupport(): Promise<void> {
  return signInAs({ email: TECH_SUPPORT_EMAIL, password: TECH_SUPPORT_PASSWORD })
}
