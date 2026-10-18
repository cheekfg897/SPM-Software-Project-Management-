import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { INTERNAL_ROLES, ROLE } from '@/config/roles'
import type { EventHistoryEntry } from '@/features/eventRequests/api'
import { EVENT_HISTORY_KIND } from '@/features/eventRequests/eventHistory'

import { errorResponse } from '../responses'

import { MOCK_EVENT_HISTORY } from './eventRecordSectionFixtures'
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
 * ADR-0025). Who may read which event is decided as the backend decides it, through the same
 * lookups as the record itself (eventRequests.ts), and so is what an organiser is not shown.
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
 * The event whose history the caller may read, and whether they read it as an organiser; or
 * the refusal. Staff read any event but a draft, a coordinator only those assigned to them, and
 * an organiser their organisation's; anything else is "not found" (ADR-0012).
 */
function historyReaderOrRefusal(request: Request, reference: unknown) {
  const found = callerOrRefusal(request, [...INTERNAL_ROLES, ROLE.EVENT_ORGANISER])
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

export const eventRecordSectionHandlers: RequestHandler[] = [
  http.get(`${REQUESTS_PATH}/:reference/history`, ({ request, params }) => {
    const found = historyReaderOrRefusal(request, params.reference)
    if ('refusal' in found) {
      return found.refusal
    }

    const history = MOCK_EVENT_HISTORY[found.stored.request.reference] ?? []
    const shown = found.isOrganiser ? history.filter(shownToOrganiser) : history
    return HttpResponse.json({ history: shown })
  }),
]
