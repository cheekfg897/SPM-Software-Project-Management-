import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'

import { ROLE, STAFF_RECORD_READER_ROLES } from '@/config/roles'
import type {
  CoordinatorContact,
  EventRequest,
  RecordEquipmentLine,
  StaffEventRecord,
  RecordVenueArrangement,
} from '@/features/eventRequests/api'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import { errorResponse } from '../responses'

import { everyArrangementForRecord } from './booking'
import { reservationsForRecord } from './equipmentReservations'
import { equipmentLinesForRecord, shortfallOf } from './equipmentLines'
import { internalNotesOf } from './eventEdits'
import { NOTHING_RECORDED } from './eventRequestFixtures'
import type { MockCoordinator, MockRecordSections } from './eventRequestFixtures'
import { callerOrRefusal, requestForStaff } from './eventRequests'
import { listedEventByReference } from './listedEvents'
import type { ListedEvent } from './listedEvents'
import { safetyEventByReference } from './safety'
import type { MockSafetyEvent } from './safetyFixtures'

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
  const listed = listedEventByReference(reference)
  return listed === undefined ? undefined : listedAsBase(listed)
}

/** Where the Safety Officer's mock's venues are: its list doesn't send a venue's location. */
const SAFETY_VENUE_LOCATIONS: Readonly<Record<string, string>> = {
  'Marina Ballroom': 'Level 2, Marina Wing',
  'Atrium Hall': 'Ground floor, Central Block',
  'Riverside Auditorium': 'River Wing',
}

/**
 * The Safety Officer's mock's venues as arrangements in full: an event reaches Safety Review only
 * with every arrangement approved and unflagged, each for the whole event's attendance, and
 * nothing is prepared before the check (SCRUM-84 AC5).
 */
function safetyArrangementsOf(safetyEvent: MockSafetyEvent | undefined): RecordVenueArrangement[] {
  if (safetyEvent === undefined) {
    return []
  }
  return safetyEvent.venues.map((venue) => ({
    venue_name: venue.name,
    venue_location: SAFETY_VENUE_LOCATIONS[venue.name] ?? '',
    venue_capacity: venue.capacity,
    venue_facilities: venue.facilities,
    venue_accessibility_features: venue.accessibility_features,
    starts_at: venue.starts_at,
    ends_at: venue.ends_at,
    purpose: 'Main programme',
    expected_occupancy: safetyEvent.event.expected_attendance,
    required_layout: null,
    justification: null,
    status: 'approved',
    decision_reason: null,
    suggested_venue_name: null,
    suggested_starts_at: null,
    suggested_ends_at: null,
    hold_expires_at: null,
    needs_alternative_venue: false,
    unavailability: [],
    flagged_after_change: false,
    reassessment_flags: [],
    preparation_status: 'not_started',
    preparation_notes: null,
  }))
}

/** When Technical Support reviewed the Safety Officer's mock's lines, before any check began. */
const SAFETY_LINES_REVIEWED_AT = '2026-10-02T10:00:00+08:00'

/**
 * The Safety Officer's mock's equipment as the record's lines. An event reaches Safety Review only
 * once every line has an outcome, and the backend keeps who recorded it (SCRUM-48 AC5), so each
 * line is shown reviewed by the mock's Technical Support account; that mock keeps no reviewer.
 */
function safetyLinesOf(safetyEvent: MockSafetyEvent | undefined): RecordEquipmentLine[] {
  if (safetyEvent === undefined) {
    return []
  }
  // The record sends no line id (ADR-0104), unlike the Safety Officer's list (SCRUM-99).
  return safetyEvent.equipment.map((line) => ({
    equipment_type_name: line.equipment_type_name,
    quantity: line.quantity,
    notes: line.notes,
    status: line.status,
    provided_quantity: line.provided_quantity,
    outcome_note: line.outcome_note,
    shortfall: shortfallOf(line),
    reviewed_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    reviewed_at: SAFETY_LINES_REVIEWED_AT,
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
    venue_arrangements: [
      ...everyArrangementForRecord(reference),
      ...safetyArrangementsOf(safetyEvent),
    ],
    equipment_lines: [...equipmentLinesForRecord(reference), ...safetyLinesOf(safetyEvent)],
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
