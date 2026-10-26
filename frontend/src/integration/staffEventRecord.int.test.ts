import {
  raiseBookingRequest,
  updateBookingPreparation,
  withdrawArrangement,
} from '@/features/booking/api'
import { addEquipmentLine, recordEquipmentOutcome } from '@/features/equipment/api'
import { fetchStaffEventRecord, saveDraftEventRequest } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  hasTechSupport,
  refusal,
  signInAs,
  signInAsNewAttendee,
  signInAsTechSupport,
  staffAccount,
  uniqueEmail,
} from './backend'
import type { Credentials } from './backend'
import {
  approvedEvent,
  CHECKLIST,
  EVENT_DATE,
  LEAD,
  newVenue,
  required,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  submittedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * Any submitted event's read-only record against the running backend
 * (GET /api/events/requests/<reference>/staff-record, ADR-0095): Venue Staff, Technical Support
 * and the Safety Officer open it (SCRUM-24 AC9), and so does the Event Coordinator Lead (AC10),
 * with the venue preparation (SCRUM-84 AC2) and the safety outcome on it. The refusals run every
 * time; the reads need the accounts plannedEvent.ts reads, and skip without them.
 */

const NOT_PERMITTED = { status: 403, code: 'authorization_error' }
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
/** Every key the record has: the request's, both notes, and each section. No registrants. */
const RECORD_KEYS = [
  'accessibility_needs',
  'clarifications',
  'coordinator',
  'created_at',
  'decision',
  'description',
  'end_date',
  'end_time',
  'equipment_lines',
  'equipment_requirements',
  'equipment_reservations',
  'expected_attendance',
  'internal_planning_notes',
  'name',
  'programme_notes',
  'proposed_date',
  'purpose',
  'reference',
  'registration_required',
  'safety_outcome',
  'start_time',
  'status',
  'venue_arrangements',
  'venue_requirements',
]

const hasLead = LEAD !== null
const canReachSafetyApproval = hasLead && VENUE_STAFF !== null && SAFETY_OFFICER !== null
const canReviewForEveryReader = canReachSafetyApproval && hasTechSupport

afterEach(() => sendRequestsAs(null))

describe('SCRUM-24 the read-only staff record against the backend', () => {
  it('refuses a visitor with no token', async () => {
    const event = await submittedEvent()
    sendRequestsAs(null)

    expect(await refusal(fetchStaffEventRecord(event.reference))).toMatchObject(NOT_SIGNED_IN)
  })

  it('refuses the event’s own organiser and an attendee', async () => {
    // submittedEvent leaves its organiser signed in.
    const event = await submittedEvent()
    expect(await refusal(fetchStaffEventRecord(event.reference))).toMatchObject(NOT_PERMITTED)

    await signInAsNewAttendee()
    expect(await refusal(fetchStaffEventRecord(event.reference))).toMatchObject(NOT_PERMITTED)
  })

  it('refuses an Event Coordinator the event is not assigned to (AC10)', async () => {
    const event = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(fetchStaffEventRecord(event.reference))).toMatchObject(NOT_PERMITTED)
  })

  it.skipIf(!hasLead)('opens a submitted event no one is assigned to for the Lead', async () => {
    const event = await submittedEvent()
    await signInAs(required(LEAD))

    const record = await fetchStaffEventRecord(event.reference)

    expect(Object.keys(record).sort()).toEqual(RECORD_KEYS)
    expect(record).toMatchObject({
      reference: event.reference,
      name: event.name,
      status: 'submitted',
      expected_attendance: 120,
      accessibility_needs: 'Step-free entrance',
      programme_notes: null,
      internal_planning_notes: null,
      coordinator: null,
      decision: null,
      clarifications: [],
      venue_arrangements: [],
      equipment_lines: [],
      equipment_reservations: [],
      safety_outcome: null,
    })
  })

  it.skipIf(!hasLead)('answers a draft as not found, even for the Lead', async () => {
    // submittedEvent leaves its organiser signed in, who saves a draft too.
    await submittedEvent()
    const draft = await saveDraftEventRequest({ name: 'Integration private draft' })
    await signInAs(required(LEAD))

    expect(await refusal(fetchStaffEventRecord(draft.reference))).toMatchObject(NOT_FOUND)
  })

  it.skipIf(!canReachSafetyApproval)(
    'shows Venue Staff’s preparation and the safety outcome to each reader',
    async () => {
      const event = await safetyApprovedEvent()
      await signInAs(required(VENUE_STAFF))
      await updateBookingPreparation(event.bookingId, { status: 'ready', notes: 'Stage built.' })

      for (const reader of [required(VENUE_STAFF), required(SAFETY_OFFICER), required(LEAD)]) {
        await signInAs(reader)
        const record = await fetchStaffEventRecord(event.reference)

        expect(record.venue_arrangements).toEqual([
          expect.objectContaining({
            status: 'approved',
            preparation_status: 'ready',
            preparation_notes: 'Stage built.',
          }),
        ])
        expect(record.safety_outcome).toMatchObject({
          outcome: 'approved',
          checklist: CHECKLIST,
          reason: null,
        })
        expect(record.coordinator?.email).toBe(staffAccount().email)
      }
    },
  )

  it.skipIf(!canReachSafetyApproval)(
    'lists a withdrawn arrangement with its status, as every other (AC9, ADR-0105)',
    async () => {
      const event = await approvedEvent()
      const venueId = await newVenue()
      await signInAs(staffAccount())
      const raised = await raiseBookingRequest(event.reference, {
        venue_id: venueId,
        starts_at: `${EVENT_DATE}T09:00:00+08:00`,
        ends_at: `${EVENT_DATE}T12:00:00+08:00`,
        purpose: 'Integration withdrawn hall',
      })
      await withdrawArrangement(event.reference, raised.id)
      await signInAs(required(LEAD))

      const record = await fetchStaffEventRecord(event.reference)

      expect(record.venue_arrangements).toEqual([
        expect.objectContaining({
          purpose: 'Integration withdrawn hall',
          status: 'withdrawn',
          venue_location: 'Level 1',
          hold_expires_at: null,
        }),
      ])
    },
  )

  it.skipIf(!canReviewForEveryReader)(
    'shows every reader who reviewed a line and when (SCRUM-48 AC5, ADR-0105)',
    async () => {
      const event = await approvedEvent()
      await signInAsTechSupport()
      const type = await apiRequest<{ id: number }>('/api/equipment/types', {
        method: 'POST',
        body: {
          name: `Integration Mic ${uniqueEmail('type')}`,
          total_quantity: 10,
          store_name: 'Integration store',
        },
      })
      await signInAs(staffAccount())
      const line = await addEquipmentLine(event.reference, {
        equipment_type_id: type.id,
        quantity: 4,
      })
      await signInAsTechSupport()
      const recorded = await recordEquipmentOutcome(event.reference, {
        lineId: line.id,
        body: { provided_quantity: 3, note: 'One is out for repair.' },
      })
      const readers: (Credentials | null)[] = [VENUE_STAFF, SAFETY_OFFICER, LEAD]

      for (const reader of readers) {
        await signInAs(required(reader))
        const record = await fetchStaffEventRecord(event.reference)

        expect(record.equipment_lines).toEqual([
          expect.objectContaining({
            status: 'partially_fulfilled',
            provided_quantity: 3,
            shortfall: 1,
            outcome_note: 'One is out for repair.',
            reviewed_by: recorded.reviewed_by,
            reviewed_at: recorded.reviewed_at,
          }),
        ])
      }
      await signInAsTechSupport()
      const technicalSupportsCopy = await fetchStaffEventRecord(event.reference)
      expect(technicalSupportsCopy.equipment_lines[0]?.reviewed_by).toEqual(expect.any(String))
    },
  )

  it.skipIf(!canReachSafetyApproval)(
    'refuses the event’s assigned coordinator, who has their own record',
    async () => {
      const event = await safetyApprovedEvent()
      await signInAs(staffAccount())

      expect(await refusal(fetchStaffEventRecord(event.reference))).toMatchObject(NOT_PERMITTED)
    },
  )
})
