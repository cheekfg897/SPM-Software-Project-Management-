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
  /** The assigned coordinator changes an event's details (SCRUM-33). */
  EDIT_EVENT: '/events/:reference/edit',
  /** A route pattern: any submitted event's read-only record, for other staff (ADR-0095). */
  STAFF_EVENT: '/staff/events/:reference',
  LEAD_QUEUE: '/staff/queue',
  /** Venue Staff's queue of booking requests waiting for a decision (SCRUM-43). */
  BOOKING_DECISIONS: '/staff/venue-requests',
  /** The Safety Officer's events awaiting the safety check (SCRUM-97, SCRUM-98). */
  SAFETY_REVIEW: '/staff/safety-review',
  /** A coordinator's venue search and suitability check (SCRUM-35, SCRUM-36). */
  VENUE_SEARCH: '/staff/venue-search',
  /** The Lead's workload and active events, where an event is reassigned (SCRUM-96). */
  LEAD_OVERSIGHT: '/staff/oversight',
  /** Staff record and list client organisations (SCRUM-66). */
  ORGANISATIONS: '/staff/organisations',
  /** The equipment catalogue (SCRUM-27): every member of staff reads it. */
  EQUIPMENT_CATALOGUE: '/staff/equipment',
  NEW_EQUIPMENT_TYPE: '/staff/equipment/new',
  /** A route pattern: `:equipmentTypeId` is the equipment type's id. */
  EQUIPMENT_TYPE: '/staff/equipment/:equipmentTypeId',
  EDIT_EQUIPMENT_TYPE: '/staff/equipment/:equipmentTypeId/edit',
  /** The venue catalogue: every staff role browses it, Venue Staff keep it (SCRUM-25). */
  VENUES: '/venues',
  NEW_VENUE: '/venues/new',
  /** A route pattern: `:venueId` is the venue's id. */
  VENUE: '/venues/:venueId',
  EDIT_VENUE: '/venues/:venueId/edit',
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

/** An event an Attendee registered for, at the address its notifications link to (ADR-0109). */
export function myEventPath(reference: string): string {
  return withReference(ROUTES.COORDINATOR_EVENT, reference)
}

/** An event's read-only record, as Venue Staff, Technical Support, the Safety Officer or the Lead open it. */
export function staffEventPath(reference: string): string {
  return withReference(ROUTES.STAFF_EVENT, reference)
}

/** The venue requests page for one event, by its EVR- reference. */
export function venueRequestsPath(reference: string): string {
  return withReference(ROUTES.VENUE_REQUESTS, reference)
}

/**
 * The search parameters of a replacement venue request (SCRUM-92): the flagged arrangement it
 * replaces, and the venue chosen for it.
 */
export const REPLACEMENT_PARAMS = { ARRANGEMENT: 'replaces', VENUE: 'venue' } as const

/** The event's venue requests, its request form set to replace an arrangement with a venue. */
export function replacementRequestPath(
  reference: string,
  arrangementId: number,
  venueId: number,
): string {
  const params = new URLSearchParams({
    [REPLACEMENT_PARAMS.ARRANGEMENT]: String(arrangementId),
    [REPLACEMENT_PARAMS.VENUE]: String(venueId),
  })
  return `${venueRequestsPath(reference)}?${params.toString()}`
}

/** The search parameter naming a rejected request whose suggested alternative the form starts from. */
export const SUGGESTION_PARAM = 'suggestion'

/**
 * The event's venue requests, its request form started from the alternative Venue Staff suggested
 * when they rejected one (SCRUM-70 AC4).
 */
export function suggestionRequestPath(reference: string, rejectedId: number): string {
  const params = new URLSearchParams({ [SUGGESTION_PARAM]: String(rejectedId) })
  return `${venueRequestsPath(reference)}?${params.toString()}`
}

/** The equipment page for one event, by its EVR- reference. */
export function eventEquipmentPath(reference: string): string {
  return withReference(ROUTES.EVENT_EQUIPMENT, reference)
}

/** Where the assigned coordinator changes an event's details, by its EVR- reference. */
export function editEventPath(reference: string): string {
  return withReference(ROUTES.EDIT_EVENT, reference)
}

/** The page for editing one of the organiser's own drafts, by its EVR- reference. */
export function editDraftPath(reference: string): string {
  return withReference(ROUTES.EDIT_DRAFT, reference)
}

/** The page for one equipment type, by its id. */
export function equipmentTypePath(equipmentTypeId: number): string {
  return ROUTES.EQUIPMENT_TYPE.replace(':equipmentTypeId', String(equipmentTypeId))
}

/** The page for changing one equipment type, by its id. */
export function editEquipmentTypePath(equipmentTypeId: number): string {
  return ROUTES.EDIT_EQUIPMENT_TYPE.replace(':equipmentTypeId', String(equipmentTypeId))
}

/** One venue's page, by its id. */
export function venuePath(venueId: number): string {
  return ROUTES.VENUE.replace(':venueId', String(venueId))
}

/** The page for changing one venue's details, by its id. */
export function editVenuePath(venueId: number): string {
  return ROUTES.EDIT_VENUE.replace(':venueId', String(venueId))
}
