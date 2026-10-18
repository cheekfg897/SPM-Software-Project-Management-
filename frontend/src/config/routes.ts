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
  /** A route pattern: one of the organisation's requests, as its organisers see it (ADR-0056). */
  ORGANISER_REQUEST: '/organiser/requests/:reference',
  STAFF_HOME: '/staff',
  /** A route pattern: an event's record, as its assigned coordinator sees it (ADR-0056). */
  COORDINATOR_EVENT: '/events/:reference',
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

/** `pattern` with an event's EVR- reference in place of `:reference`. */
function withReference(pattern: string, reference: string): string {
  return pattern.replace(':reference', encodeURIComponent(reference))
}

/** An event request's record, as its organisation's organisers open it. */
export function organiserRequestPath(reference: string): string {
  return withReference(ROUTES.ORGANISER_REQUEST, reference)
}

/** An event's record, as its assigned coordinator opens it. */
export function coordinatorEventPath(reference: string): string {
  return withReference(ROUTES.COORDINATOR_EVENT, reference)
}

/** The venue requests page for one event, by its EVR- reference. */
export function venueRequestsPath(reference: string): string {
  return withReference(ROUTES.VENUE_REQUESTS, reference)
}

/** The equipment page for one event, by its EVR- reference. */
export function eventEquipmentPath(reference: string): string {
  return withReference(ROUTES.EVENT_EQUIPMENT, reference)
}

/** The page for editing one of the organiser's own drafts, by its EVR- reference. */
export function editDraftPath(reference: string): string {
  return withReference(ROUTES.EDIT_DRAFT, reference)
}
