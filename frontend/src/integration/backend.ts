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
