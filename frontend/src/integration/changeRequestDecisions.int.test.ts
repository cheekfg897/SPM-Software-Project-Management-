import { fetchBookingRequests } from '@/features/booking/api'
import {
  confirmEvent,
  decideChangeRequest,
  editEventRequest,
  fetchEventHistory,
  fetchEventRequest,
  raiseChangeRequest,
  sendToSafetyReview,
} from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount } from './backend'
import {
  approvedEvent,
  eventReadyForSafetyReview,
  LEAD,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'
import type { PlannedEvent } from './plannedEvent'

/**
 * SCRUM-57 against the running backend (ADR-0127): the event's coordinator approves a change
 * request, which applies it to the event, or rejects it with a reason, which leaves the event as
 * it was; the record shows who decided it, when and why. A request a later edit overtook, one
 * already decided, and the event's own decision while one is Pending are refused with the codes
 * and messages the page shows. An approved change reassesses the venue bookings and any safety
 * approval, as an edit does (SCRUM-58, ADR-0129). The events come from plannedEvent.ts: approved
 * by the staff account, 09:00 to 17:00, 120 expected. They need the Lead's account to be assigned,
 * and those with a booking or a safety check the Venue Staff's and the Safety Officer's.
 */

const REASON = 'Our keynote speaker lands at 9:30.'
const LATER_START = { start_time: '10:00', expected_attendance: 150, reason: REASON }
/** Every field the frontend's ChangeRequest type reads, and nothing more (no internal ids). */
const CHANGE_REQUEST_FIELDS = [
  'changes',
  'decided_at',
  'decided_by',
  'decision_reason',
  'id',
  'raised_at',
  'raised_by',
  'reason',
  'status',
  'withdrawal_note',
  'withdrawn_at',
]
const hasLead = LEAD !== null
const needsVenueStaff = !hasLead || VENUE_STAFF === null
const needsSafetyOfficer = needsVenueStaff || SAFETY_OFFICER === null

/** The organiser asks for a later start on their approved event; the coordinator is then signed in. */
async function raisedOn(event: PlannedEvent): Promise<number> {
  await signInAs(event.organiser)
  const raised = await raiseChangeRequest(event.reference, LATER_START)
  await signInAs(staffAccount())
  return raised.id
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-57 deciding a change request against the backend', () => {
  it.skipIf(!hasLead)(
    'approves one, applying it, in exactly the shape the record shows',
    async () => {
      const event = await approvedEvent()
      const id = await raisedOn(event)

      const approved = await decideChangeRequest(event.reference, id, {
        outcome: 'approved',
        reason: 'The hall holds 150.',
      })

      expect(Object.keys(approved).sort()).toEqual(CHANGE_REQUEST_FIELDS)
      expect(approved).toMatchObject({
        id,
        status: 'approved',
        decided_by: expect.any(String) as string,
        decision_reason: 'The hall holds 150.',
      })
      expect(approved.decided_at).toMatch(/\+08:00$/)
      const record = await fetchEventRequest(event.reference)
      expect(record).toMatchObject({ start_time: '10:00:00', expected_attendance: 150 })
      expect(record.change_requests).toEqual([approved])
    },
  )

  it.skipIf(needsVenueStaff)(
    'flags the booking an approved change affects, and holds the event back (SCRUM-58 AC1, AC3)',
    async () => {
      const event = await eventReadyForSafetyReview()
      const id = await raisedOn(event)

      await decideChangeRequest(event.reference, id, { outcome: 'approved' })

      const [booking] = await fetchBookingRequests(event.reference)
      expect(booking).toMatchObject({
        id: event.bookingId,
        status: 'approved',
        flagged_after_change: true,
        reassessment_flags: [
          { kind: 'requires_reconfirmation', reason: "The event's date or time changed." },
          {
            kind: 'requires_reconfirmation',
            reason:
              "The event's expected attendance rose from 120 to 150, above this arrangement's " +
              'expected occupancy of 120.',
          },
        ],
      })
      const held = await refusal(sendToSafetyReview(event.reference))
      expect(held).toMatchObject({ status: 409, code: 'safety_review_not_allowed' })
      expect(held.fieldErrors.venue_arrangements).toHaveLength(2)
    },
  )

  it.skipIf(needsVenueStaff)(
    'marks a booking an earlier rise outgrew when the attendance passes capacity (SCRUM-58 AC2)',
    async () => {
      const event = await eventReadyForSafetyReview()
      const id = await raisedOn(event)
      await decideChangeRequest(event.reference, id, { outcome: 'approved' })

      await editEventRequest(event.reference, { expected_attendance: 350 })

      const [booking] = await fetchBookingRequests(event.reference)
      expect(booking?.reassessment_flags.at(-1)).toEqual({
        kind: 'no_longer_suitable',
        reason: "Expected attendance of 350 exceeds the venue's capacity of 300.",
      })
    },
  )

  it.skipIf(needsSafetyOfficer)(
    'sends a Confirmed event back to Approved, with its approval withdrawn (SCRUM-58 AC6, AC7)',
    async () => {
      const event = await safetyApprovedEvent()
      await signInAs(staffAccount())
      await confirmEvent(event.reference)
      const id = await raisedOn(event)

      await decideChangeRequest(event.reference, id, { outcome: 'approved' })

      const record = await fetchEventRequest(event.reference)
      expect(record.status).toBe('approved')
      const { history } = await fetchEventHistory(event.reference)
      const kinds = history.map((entry) => entry.kind)
      expect(kinds).toContain('safety_approval_withdrawn')
    },
  )

  it.skipIf(!hasLead)('needs a reason to reject one, and leaves the event as it was', async () => {
    const event = await approvedEvent()
    const id = await raisedOn(event)

    const unexplained = await refusal(
      decideChangeRequest(event.reference, id, { outcome: 'rejected' }),
    )
    const rejected = await decideChangeRequest(event.reference, id, {
      outcome: 'rejected',
      reason: 'The hall holds 120.',
    })

    expect(unexplained).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { reason: ['Say why the change request is rejected.'] },
    })
    expect(rejected).toMatchObject({ status: 'rejected', decision_reason: 'The hall holds 120.' })
    const record = await fetchEventRequest(event.reference)
    expect(record).toMatchObject({ start_time: '09:00:00', expected_attendance: 120 })
  })

  it.skipIf(!hasLead)('refuses one decided already, naming its status', async () => {
    const event = await approvedEvent()
    const id = await raisedOn(event)
    await decideChangeRequest(event.reference, id, { outcome: 'approved' })

    const refused = await refusal(decideChangeRequest(event.reference, id, { outcome: 'approved' }))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_not_pending',
      message: 'Only a pending change request can be decided; this one is approved.',
    })
  })

  it.skipIf(!hasLead)(
    'refuses approving one a later edit overtook, and keeps it Pending',
    async () => {
      const event = await approvedEvent()
      const id = await raisedOn(event)
      await editEventRequest(event.reference, { expected_attendance: 100 })

      const refused = await refusal(
        decideChangeRequest(event.reference, id, { outcome: 'approved' }),
      )

      expect(refused).toMatchObject({
        status: 409,
        code: 'change_request_stale',
        message:
          "This change request can't be approved because the event has changed since it was " +
          'raised. Expected attendance: 120 when the change was requested, 100 now. Reject it, ' +
          'and the organiser can raise a new one.',
      })
      const record = await fetchEventRequest(event.reference)
      expect(record.change_requests[0]?.status).toBe('pending')
    },
  )

  it.skipIf(!hasLead)("refuses the event's own decision while one is Pending", async () => {
    const event = await approvedEvent()
    await raisedOn(event)

    const refused = await refusal(
      apiRequest(`/api/events/requests/${event.reference}/decide`, {
        method: 'POST',
        body: { outcome: 'rejected', reason: 'The client withdrew.' },
      }),
    )

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_pending',
      message:
        'The organiser has a change request waiting for your decision. Decide the change ' +
        'request first.',
    })
  })
})
