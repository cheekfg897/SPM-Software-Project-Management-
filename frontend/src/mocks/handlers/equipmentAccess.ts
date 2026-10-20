import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'

import type { MockAccount } from '../fixtures/accounts'
import { errorResponse, notAllowed, notAuthenticated } from '../responses'

import { accountForRequest } from './auth'
import { MOCK_EVENTS, MOCK_SAFETY_APPROVED_EVENT_REFERENCES } from './equipmentFixtures'
import type { MockEvent } from './equipmentFixtures'

/**
 * Who may reach an event's equipment, shared by the equipment mocks: the caller from their
 * token, and the event as the backend's lookups find it. The events and their safety approvals
 * are kept in memory, as a revised outcome (SCRUM-48) or units out of service (SCRUM-47) can
 * withdraw an approval and send an event back to Approved, until resetMockEquipmentEvents.
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
/** The events whose safety approval stands, by reference. */
let safetyApproved: string[] = []

/** Put every event and approval back as it started. Runs after every test. */
export function resetMockEquipmentEvents(): void {
  events = MOCK_EVENTS.map((event) => ({ ...event }))
  safetyApproved = [...MOCK_SAFETY_APPROVED_EVENT_REFERENCES]
}

/** Whether the event's safety approval stands, so its reservations can be prepared (SCRUM-85). */
export function hasSafetyApproval(reference: string): boolean {
  return safetyApproved.includes(reference)
}

/**
 * Withdraw the event's safety approval, as `withdraw_safety_approval` does: it must pass a new
 * check before it is prepared, and a Confirmed event goes back to Approved, to be sent for that
 * check (ADR-0087). Every Confirmed event has an approval on the backend, which confirms only an
 * approved event, so a Confirmed event here goes back whether or not it is listed as approved.
 */
export function withdrawSafetyApproval(reference: string): void {
  safetyApproved = safetyApproved.filter((approved) => approved !== reference)
  const event = events.find((candidate) => candidate.reference === reference)
  if (event?.status === EVENT_REQUEST_STATUS.CONFIRMED) {
    event.status = EVENT_REQUEST_STATUS.APPROVED
  }
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
