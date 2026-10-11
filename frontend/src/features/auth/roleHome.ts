import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { ROUTES } from '@/config/routes'
import type { RoutePath } from '@/config/routes'

/** Where each role lands after logging in (SCRUM-6 AC3). */
const ROLE_HOME: Record<Role, RoutePath> = {
  [ROLE.ATTENDEE]: ROUTES.EVENTS,
  [ROLE.EVENT_ORGANISER]: ROUTES.ORGANISER_HOME,
  [ROLE.EVENT_COORDINATOR]: ROUTES.STAFF_HOME,
  [ROLE.EVENT_COORDINATOR_LEAD]: ROUTES.LEAD_QUEUE,
  [ROLE.VENUE_STAFF]: ROUTES.STAFF_HOME,
  [ROLE.TECHNICAL_SUPPORT_STAFF]: ROUTES.STAFF_HOME,
}

export function homeFor(role: Role): RoutePath {
  return ROLE_HOME[role]
}

/**
 * True for a path on this site. `//host` and `/\host` are other sites to a browser, so a
 * `next` value like those would send the user away after logging in.
 */
function isPathOnThisSite(path: string): boolean {
  return path.startsWith('/') && !path.startsWith('//') && !path.startsWith('/\\')
}

/** The page to open after signing in: the one the user came from, else their role's home. */
export function destinationAfterSignIn(role: Role, next: string | null): string {
  if (next !== null && isPathOnThisSite(next)) {
    return next
  }
  return homeFor(role)
}
