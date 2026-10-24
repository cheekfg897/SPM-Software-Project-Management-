import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import type { EventRequestStatus } from '@/config/eventStatus'
import { ROLE, STAFF_RECORD_READER_ROLES } from '@/config/roles'
import type {
  CoordinatorContact,
  EventRequest,
  StaffEventRecord,
  StaffVenueArrangement,
} from '@/features/eventRequests/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import { errorResponse } from '../responses'

import { arrangementsForRecord, bookingEventByReference } from './booking'
import { reservationsForRecord } from './equipment'
import { equipmentLinesForRecord } from './equipmentLines'
import { internalNotesOf } from './eventEdits'
import { NOTHING_RECORDED } from './eventRequestFixtures'
import type { MockCoordinator, MockRecordSections } from './eventRequestFixtures'
import { callerOrRefusal, requestForStaff } from './eventRequests'
import { eventByReference as leadEventByReference } from './lead'
import { safetyEventByReference } from './safety'
import type { MockSafetyEvent } from './safetyFixtures'
import { MOCK_EQUIPMENT_EVENTS } from './techSupportFixtures'

/**
 * Any submitted event's read-only record (GET /api/events/requests/<reference>/staff-record), as
 * the backend answers Venue Staff, Technical Support, the Safety Officer and the Event
 * Coordinator Lead (SCRUM-24 AC9, AC10; ADR-0095). Everyone else is refused by role, a draft or
 * an unknown reference is "not found", and there are no registrants.
 *
 * The mock keeps its events in each feature's own store, so the record is put together from all
 * of them, as they stand: the event-request mock's full records first, then the events only the
 * Lead's, the Safety Officer's, the booking or Technical Support's mock know, so every staff list
 * row opens. Each section is read from the mock that keeps it: the venue arrangements from the
 * booking mock, the equipment and reservations from the equipment mocks, the internal notes from
 * the edits mock and the safety outcome from the Safety Officer's mock.
 */

const NOT_FOUND_MESSAGE = 'Event request not found.'

/** What another feature's mock knows of an event: enough for the record's details. */
interface ListedEvent {
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

/** The event and the sections every record shows, before this record's own sections. */
interface StaffRecordBase {
  request: EventRequest
  coordinator: CoordinatorContact | null
  sections: MockRecordSections
}

function contactOf(coordinator: MockCoordinator): CoordinatorContact {
  return { full_name: coordinator.full_name, email: coordinator.email }
}

/** The coordinator with this account id, as the record names them, or null without one. */
function coordinatorWithId(coordinatorId: number | null): CoordinatorContact | null {
  const coordinator = Object.values(MOCK_ACCOUNTS).find(
    (account) => account.role === ROLE.EVENT_COORDINATOR && account.id === coordinatorId,
  )
  return coordinator === undefined ? null : contactOf(coordinator)
}

/** A listed event as a record: what its mock knows, and nothing written on it yet. */
function listedAsBase(event: ListedEvent): StaffRecordBase {
  const request: EventRequest = {
    reference: event.reference,
    status: event.status,
    name: event.name,
    purpose: null,
    description: null,
    proposed_date: event.proposed_date,
    end_date: event.end_date,
    start_time: event.start_time,
    end_time: event.end_time,
    expected_attendance: event.expected_attendance ?? null,
    venue_requirements: null,
    accessibility_needs: event.accessibility_needs ?? null,
    equipment_requirements: null,
    registration_required: false,
    created_at: event.created_at ?? null,
  }
  return {
    request,
    coordinator: coordinatorWithId(event.coordinator_id ?? null),
    sections: NOTHING_RECORDED,
  }
}

/** Technical Support's mock's event, which only its lists hold. */
function equipmentEventByReference(reference: string): ListedEvent | undefined {
  return MOCK_EQUIPMENT_EVENTS.find((stored) => stored.event.reference === reference)?.event
}

/**
 * The event behind a reference, from the first mock that holds it, or undefined. None of them
 * finds a draft, which staff never see (ADR-0024).
 */
function baseOf(reference: string): StaffRecordBase | undefined {
  const stored = requestForStaff(reference)
  if (stored !== undefined) {
    const coordinator = stored.coordinator === null ? null : contactOf(stored.coordinator)
    return { request: stored.request, coordinator, sections: stored.record }
  }
  const listed =
    leadEventByReference(reference) ??
    safetyEventByReference(reference)?.event ??
    bookingEventByReference(reference) ??
    equipmentEventByReference(reference)
  return listed === undefined ? undefined : listedAsBase(listed)
}

/**
 * The Safety Officer's mock's venues as arrangements: an event reaches Safety Review only with
 * every arrangement approved, and nothing is prepared before the check (SCRUM-84 AC5).
 */
function safetyArrangementsOf(safetyEvent: MockSafetyEvent | undefined): StaffVenueArrangement[] {
  if (safetyEvent === undefined) {
    return []
  }
  return safetyEvent.venues.map((venue) => ({
    venue_name: venue.name,
    starts_at: venue.starts_at,
    ends_at: venue.ends_at,
    status: 'approved',
    preparation_status: 'not_started',
    preparation_notes: null,
  }))
}

/** The whole record, each section from the mock that keeps it. */
function recordOf(base: StaffRecordBase): StaffEventRecord {
  const { reference } = base.request
  const safetyEvent = safetyEventByReference(reference)
  return {
    ...base.request,
    programme_notes: base.sections.programme_notes,
    internal_planning_notes: internalNotesOf(reference),
    coordinator: base.coordinator,
    decision: base.sections.decision,
    clarifications: base.sections.clarifications,
    venue_arrangements: [...arrangementsForRecord(reference), ...safetyArrangementsOf(safetyEvent)],
    equipment_lines: [...equipmentLinesForRecord(reference), ...(safetyEvent?.equipment ?? [])],
    equipment_reservations: reservationsForRecord(reference),
    safety_outcome: safetyEvent?.outcome ?? null,
  }
}

export const staffEventRecordHandlers: RequestHandler[] = [
  http.get('/api/events/requests/:reference/staff-record', ({ request, params }) => {
    const found = callerOrRefusal(request, STAFF_RECORD_READER_ROLES)
    if ('refusal' in found) {
      return found.refusal
    }
    const base = baseOf(String(params.reference))
    if (base === undefined) {
      return errorResponse(404, 'not_found', NOT_FOUND_MESSAGE)
    }
    return HttpResponse.json(recordOf(base))
  }),
]
