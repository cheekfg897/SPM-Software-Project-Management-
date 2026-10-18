import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { EventHistoryEntry, Registrant } from '@/features/eventRequests/api'
import { EVENT_HISTORY_KIND } from '@/features/eventRequests/eventHistory'

import { errorResponse } from '../responses'

import { MOCK_EVENT_HISTORY, MOCK_REGISTRATIONS } from './eventRecordSectionFixtures'
import {
  assignedRequest,
  callerOrRefusal,
  organiserOrRefusal,
  requestForStaff,
  visibleRequest,
} from './eventRequests'
import type { MockEventRequest } from './eventRequestFixtures'

/**
 * The sections of an event's record that have routes of their own: its history (SCRUM-33,
 * ADR-0025) and who registered (SCRUM-55). Who may read which event is decided as the backend
 * decides it, through the same lookups as the record itself (eventRequests.ts), and so are what
 * an organiser is not shown and the count against the capacity.
 */

const REQUESTS_PATH = '/api/events/requests'
const NOT_FOUND_MESSAGE = 'Event request not found.'
/** Kinds the backend never shows an organiser (INTERNAL_ONLY_KINDS in events/services.py). */
const INTERNAL_ONLY_KINDS: readonly string[] = [
  EVENT_HISTORY_KIND.EQUIPMENT_RESERVED,
  EVENT_HISTORY_KIND.EQUIPMENT_OUTCOME_RECORDED,
  EVENT_HISTORY_KIND.SAFETY_OUTCOME_RECORDED,
]
/** Fields whose changes the backend never shows an organiser (INTERNAL_ONLY_FIELDS). */
const INTERNAL_ONLY_FIELDS: readonly unknown[] = ['internal_planning_notes']
const HISTORY_READERS: readonly Role[] = [...INTERNAL_ROLES, ROLE.EVENT_ORGANISER]
/** The registrants route's roles (SCRUM-55 AC1, AC2): an attendee or other staff get 403. */
const REGISTRANT_READERS: readonly Role[] = [ROLE.EVENT_ORGANISER, ROLE.EVENT_COORDINATOR]

/** Whether the backend shows `entry` to an organiser (`_shown_to_organiser`, ADR-0025). */
function shownToOrganiser(entry: EventHistoryEntry): boolean {
  if (INTERNAL_ONLY_KINDS.includes(entry.kind)) {
    return false
  }
  if (entry.kind !== EVENT_HISTORY_KIND.FIELD_CHANGED) {
    return true
  }
  return !INTERNAL_ONLY_FIELDS.includes(entry.details.field)
}

/**
 * The event the caller, holding one of `roles`, may read, and whether they read it as an
 * organiser; or the refusal. Staff read any event but a draft, a coordinator only those assigned
 * to them, and an organiser their organisation's; anything else is "not found" (ADR-0012).
 */
function readerOrRefusal(request: Request, roles: readonly Role[], reference: unknown) {
  const found = callerOrRefusal(request, roles)
  if ('refusal' in found) {
    return { refusal: found.refusal }
  }
  const { caller } = found
  const isOrganiser = caller.role === ROLE.EVENT_ORGANISER
  let stored: MockEventRequest | undefined
  if (isOrganiser) {
    const organiser = organiserOrRefusal(request)
    if ('refusal' in organiser) {
      return { refusal: organiser.refusal }
    }
    stored = visibleRequest(caller.id, organiser.organisationId, reference)
  } else if (caller.role === ROLE.EVENT_COORDINATOR) {
    stored = assignedRequest(caller.id, reference)
  } else {
    stored = requestForStaff(reference)
  }
  if (stored === undefined) {
    return { refusal: errorResponse(404, 'not_found', NOT_FOUND_MESSAGE) }
  }
  return { stored, isOrganiser }
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

    const history = MOCK_EVENT_HISTORY[found.stored.request.reference] ?? []
    const shown = found.isOrganiser ? history.filter(shownToOrganiser) : history
    return HttpResponse.json({ history: shown })
  }),

  http.get(`${REQUESTS_PATH}/:reference/registrations`, ({ request, params }) => {
    const found = readerOrRefusal(request, REGISTRANT_READERS, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }

    const kept = MOCK_REGISTRATIONS[found.stored.request.reference]
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
