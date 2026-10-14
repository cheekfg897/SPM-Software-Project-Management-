/**
 * Helpers shared by the integration tests. Every call goes to the real backend at
 * VITE_API_ORIGIN (set by vitest.integration.config.ts).
 */

/** An email no earlier run has used, so tests never collide with leftover accounts. */
export function uniqueEmail(label: string): string {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`
  return `${label}-${suffix}@integration.test`
}

/** A password that meets the backend's policy (ADR-0005). */
export const VALID_PASSWORD = 'Password123'

export interface Credentials {
  email: string
  password: string
}

const MISSING_STAFF_ACCOUNT =
  'Set INTEGRATION_STAFF_EMAIL and INTEGRATION_STAFF_PASSWORD to a staff account on the ' +
  'backend, made with `flask create-staff-user` (frontend/README.md).'

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
