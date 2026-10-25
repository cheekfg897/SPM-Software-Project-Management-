import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { Registrant } from '@/features/eventRequests/api'

import { errorResponse } from '../responses'

import { MOCK_REGISTRATIONS } from './eventRecordSectionFixtures'
import { historyOf } from './eventHistoryStore'
import {
  assignedRequest,
  callerOrRefusal,
  organiserOrRefusal,
  requestForStaff,
  visibleRequest,
} from './eventRequests'
import { listedEventByReference } from './listedEvents'

// The history store moved to eventHistoryStore.ts so the record mock can read it too; the
// mocks that write history still reach it from here.
export { addToHistory, resetMockEventHistory } from './eventHistoryStore'

/**
 * The sections of an event's record that have routes of their own: its history (SCRUM-33,
 * ADR-0025) and who registered (SCRUM-55). Who may read which event is decided as the backend
 * decides it, through the same lookups as the record itself (eventRequests.ts), and so is the
 * count against the capacity. Everyone who may read the history reads all of it: nothing is
 * hidden from the organiser (SCRUM-24 AC10, ADR-0104). An edit adds to the history
 * (eventEdits.ts), so the history is kept here and put back after every test.
 */

const REQUESTS_PATH = '/api/events/requests'
const NOT_FOUND_MESSAGE = 'Event request not found.'
const HISTORY_READERS: readonly Role[] = [...INTERNAL_ROLES, ROLE.EVENT_ORGANISER]
/** The registrants route's roles (SCRUM-55 AC1, AC2): an attendee or other staff get 403. */
const REGISTRANT_READERS: readonly Role[] = [ROLE.EVENT_ORGANISER, ROLE.EVENT_COORDINATOR]

/**
 * The reference of an event staff other than a coordinator may read: any event but a draft,
 * whether the event-request mock or another feature's mock keeps it (ADR-0024, ADR-0095).
 */
function staffEventReference(reference: unknown): string | undefined {
  const stored = requestForStaff(reference)
  if (stored !== undefined) {
    return stored.request.reference
  }
  return listedEventByReference(String(reference))?.reference
}

/**
 * The reference of the event the caller, holding one of `roles`, may read, or the refusal.
 * Staff read any event but a draft, a coordinator only those
 * assigned to them, and an organiser their organisation's; anything else is "not found"
 * (ADR-0012).
 */
function readerOrRefusal(request: Request, roles: readonly Role[], reference: unknown) {
  const found = callerOrRefusal(request, roles)
  if ('refusal' in found) {
    return { refusal: found.refusal }
  }
  const { caller } = found
  let eventReference: string | undefined
  if (caller.role === ROLE.EVENT_ORGANISER) {
    const organiser = organiserOrRefusal(request)
    if ('refusal' in organiser) {
      return { refusal: organiser.refusal }
    }
    const visible = visibleRequest(caller.id, organiser.organisationId, reference)
    eventReference = visible?.request.reference
  } else if (caller.role === ROLE.EVENT_COORDINATOR) {
    eventReference = assignedRequest(caller.id, reference)?.request.reference
  } else {
    eventReference = staffEventReference(reference)
  }
  if (eventReference === undefined) {
    return { refusal: errorResponse(404, 'not_found', NOT_FOUND_MESSAGE) }
  }
  return { eventReference }
}

/** Oldest registration first, as the backend lists them. */
function oldestFirst(a: Registrant, b: Registrant): number {
  return a.registered_at.localeCompare(b.registered_at)
}

/** Places still free: none rather than fewer, and null with no capacity (`_places_left`). */
function placesLeft(capacity: number | null, registeredCount: number): number | null {
  if (capacity === null) {
    return null
  }
  return Math.max(capacity - registeredCount, 0)
}

export const eventRecordSectionHandlers: RequestHandler[] = [
  http.get(`${REQUESTS_PATH}/:reference/history`, ({ request, params }) => {
    const found = readerOrRefusal(request, HISTORY_READERS, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }

    return HttpResponse.json({ history: historyOf(found.eventReference) })
  }),

  http.get(`${REQUESTS_PATH}/:reference/registrations`, ({ request, params }) => {
    const found = readerOrRefusal(request, REGISTRANT_READERS, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }

    const kept = MOCK_REGISTRATIONS[found.eventReference]
    const capacity = kept?.capacity ?? null
    const items = [...(kept?.registrants ?? [])].sort(oldestFirst)
    const registeredCount = items.filter((item) => item.status === 'registered').length
    return HttpResponse.json({
      capacity,
      registered_count: registeredCount,
      places_left: placesLeft(capacity, registeredCount),
      items,
    })
  }),
]
