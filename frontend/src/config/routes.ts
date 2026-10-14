/** Every page's path. Link to pages through these, never with a typed-out string. */
export const ROUTES = {
  HOME: '/',
  EVENTS: '/events',
  NOTIFICATIONS: '/notifications',
  LOGIN: '/login',
  SIGN_UP: '/signup',
  STAFF_LOGIN: '/staff/login',
  ORGANISER_HOME: '/organiser',
  STAFF_HOME: '/staff',
  /** A route pattern: `:reference` is the event's `EVR-…` reference. */
  VENUE_REQUESTS: '/events/:reference/venue-requests',
  EVENT_EQUIPMENT: '/events/:reference/equipment',
  LEAD_QUEUE: '/staff/queue',
  /** Venue Staff's queue of booking requests waiting for a decision (SCRUM-43). */
  BOOKING_DECISIONS: '/staff/venue-requests',
} as const

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES]

/** The search parameter that carries the page to return to after logging in. */
export const NEXT_PARAM = 'next'

/** The two log-in pages: one for Organisers and Attendees, one for staff. */
export type LoginRoute = typeof ROUTES.LOGIN | typeof ROUTES.STAFF_LOGIN

/** The log-in page, set to bring the user back to `path` once they've logged in. */
export function loginPathReturningTo(path: string, loginRoute: LoginRoute = ROUTES.LOGIN): string {
  const params = new URLSearchParams({ [NEXT_PARAM]: path })
  return `${loginRoute}?${params.toString()}`
}

/** The equipment page for one event, by its EVR- reference. */
export function eventEquipmentPath(reference: string): string {
  return ROUTES.EVENT_EQUIPMENT.replace(':reference', encodeURIComponent(reference))
}
