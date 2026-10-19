import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

import type { MockAccount } from '../fixtures/accounts'
import { errorResponse, notAllowed, notAuthenticated } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_EVENTS } from './equipmentFixtures'
import type { MockEvent } from './equipmentFixtures'

/**
 * Who may reach an event's equipment, shared by the equipment mocks: the caller from their
 * token, and the event as the backend's lookups find it. The events are kept in memory, as a
 * revised outcome can send one back to Approved, until resetMockEquipmentEvents.
 */

/**
 * Events that won't run, so nothing can be reserved for them and no outcome recorded on their
 * lines (EQUIPMENT_NOT_NEEDED_STATUSES).
 */
export const EQUIPMENT_NOT_NEEDED_STATUSES: readonly EventRequestStatus[] = [
  EVENT_REQUEST_STATUS.COMPLETED,
  EVENT_REQUEST_STATUS.CANCELLED,
  EVENT_REQUEST_STATUS.REJECTED,
]

let events: MockEvent[] = []

/** Put every event back as it started. Runs after every test. */
export function resetMockEquipmentEvents(): void {
  events = MOCK_EVENTS.map((event) => ({ ...event }))
}

resetMockEquipmentEvents()

/** The caller, or the refusal for a missing token or a role that may not call this. */
export function callerOrRefusal(
  request: Request,
  allowedRoles: readonly Role[],
): MockAccount | Response {
  const user = accountForRequest(request)
  if (user === undefined) {
    return notAuthenticated()
  }
  if (!allowedRoles.includes(user.role)) {
    return notAllowed()
  }
  return user
}

export function eventNotFound() {
  return errorResponse(404, 'not_found', 'Event request not found.')
}

/**
 * The event a reference names, as staff find it: case and surrounding spaces are ignored
 * (ADR-0004), and a draft is hidden, since it is its author's alone (ADR-0024).
 */
export function eventForStaff(reference: string): MockEvent | undefined {
  const normalised = reference.trim().toUpperCase()
  const event = events.find((candidate) => candidate.reference === normalised)
  if (event === undefined || event.status === EVENT_REQUEST_STATUS.DRAFT) {
    return undefined
  }
  return event
}

/**
 * The event, if the reader may see its equipment: Technical Support any event's, a coordinator
 * only one assigned to them. Anything else is the same 404 as an unknown event (ADR-0019).
 */
export function eventForReader(reader: MockAccount, reference: string): MockEvent | undefined {
  const event = eventForStaff(reference)
  if (event === undefined) {
    return undefined
  }
  if (reader.role === ROLE.TECHNICAL_SUPPORT_STAFF || event.coordinator_id === reader.id) {
    return event
  }
  return undefined
}
