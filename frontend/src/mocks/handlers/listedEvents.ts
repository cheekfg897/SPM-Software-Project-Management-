import type { EventRequestStatus } from '@/config/eventStatus'

import { bookingEventByReference } from './booking'
import { eventByReference as leadEventByReference } from './lead'
import { safetyEventByReference } from './safety'
import { MOCK_EQUIPMENT_EVENTS } from './techSupportFixtures'

/**
 * The events other feature mocks keep in their own stores, outside the event-request mock: the
 * Lead's, the Safety Officer's, the booking mock's and Technical Support's (ADR-0095). Staff open
 * any of them, as the backend lets them open any event but a draft, so the staff record mock and
 * the history mock both look here after the event-request mock's own store.
 *
 * It imports only those feature mocks, never the history or edit mocks, so either can import it.
 */

/** What another feature's mock knows of an event: enough for the record's details. */
export interface ListedEvent {
  reference: string
  name: string
  status: EventRequestStatus
  proposed_date: string | null
  end_date: string | null
  start_time: string | null
  end_time: string | null
  expected_attendance?: number | null
  accessibility_needs?: string | null
  created_at?: string
  coordinator_id?: number | null
}

/** Technical Support's mock's event, which only its lists hold. */
function equipmentEventByReference(reference: string): ListedEvent | undefined {
  return MOCK_EQUIPMENT_EVENTS.find((stored) => stored.event.reference === reference)?.event
}

/**
 * The event behind a reference from the first of the other feature mocks that holds it, or
 * undefined. None of them holds a draft, which staff never see (ADR-0024).
 */
export function listedEventByReference(reference: string): ListedEvent | undefined {
  return (
    leadEventByReference(reference) ??
    safetyEventByReference(reference)?.event ??
    bookingEventByReference(reference) ??
    equipmentEventByReference(reference)
  )
}
