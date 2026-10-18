/** Every page's path. Link to pages through these, never with a typed-out string. */
export const ROUTES = {
  HOME: '/',
  EVENTS: '/events',
  MY_EVENTS: '/my-events',
  NOTIFICATIONS: '/notifications',
  LOGIN: '/login',
  SIGN_UP: '/signup',
  STAFF_LOGIN: '/staff/login',
  ORGANISER_HOME: '/organiser',
  NEW_EVENT_REQUEST: '/organiser/requests/new',
  /** A route pattern: `:reference` is one of the organiser's own drafts. */
  EDIT_DRAFT: '/organiser/requests/:reference/edit',
  STAFF_HOME: '/staff',
  /** A route pattern: `:reference` is the event's `EVR-…` reference. */
  VENUE_REQUESTS: '/events/:reference/venue-requests',
  EVENT_EQUIPMENT: '/events/:reference/equipment',
  LEAD_QUEUE: '/staff/queue',
  /** Venue Staff's queue of booking requests waiting for a decision (SCRUM-43). */
  BOOKING_DECISIONS: '/staff/venue-requests',
  /** The Safety Officer's events awaiting the safety check (SCRUM-97, SCRUM-98). */
  SAFETY_REVIEW: '/staff/safety-review',
  /** A coordinator's venue search and suitability check (SCRUM-35, SCRUM-36). */
  VENUE_SEARCH: '/staff/venue-search',
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

/** The page for editing one of the organiser's own drafts, by its EVR- reference. */
export function editDraftPath(reference: string): string {
  return ROUTES.EDIT_DRAFT.replace(':reference', encodeURIComponent(reference))
}
