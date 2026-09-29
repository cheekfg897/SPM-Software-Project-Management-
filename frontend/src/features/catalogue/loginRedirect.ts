import { ROUTES } from '@/config/routes'

/**
 * The log-in page, told to come back to `pathAndSearch` afterwards, e.g.
 * `/login?next=%2Fevents%3Fq%3Djazz`. The log-in page reads `next`.
 */
// TODO(frontend): use the shared loginPathReturningTo in src/config/routes.ts once the auth
// pages land, and delete this file.
export function loginPathReturningTo(pathAndSearch: string): string {
  return `${ROUTES.LOGIN}?next=${encodeURIComponent(pathAndSearch)}`
}
