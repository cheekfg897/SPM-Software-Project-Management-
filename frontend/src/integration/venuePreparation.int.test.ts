import {
  fetchApprovedBookingRequests,
  fetchBookingRequests,
  raiseBookingRequest,
  updateBookingPreparation,
} from '@/features/booking/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount } from './backend'
import {
  EVENT_DATE,
  eventReadyForSafetyReview,
  LEAD,
  required,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-84 against the running backend: Venue Staff's approved bookings (ADR-0080) and recording
 * one's preparation (ADR-0049). The refusals run with the staff account every run has (an Event
 * Coordinator); the rest need the accounts plannedEvent.ts reads, and skip without them.
 */

const NOT_PERMITTED = { status: 403, code: 'authorization_error' }
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
/** An id no database has, so the lookup finds nothing. */
const UNKNOWN_BOOKING_ID = 99_999_999
const SAFETY_APPROVAL_MESSAGE =
  "Preparation details can't be recorded until the Safety Officer has approved the event's" +
  ' Operational Safety Check.'

const hasVenueStaff = VENUE_STAFF !== null
const canReachSafetyApproval = hasVenueStaff && LEAD !== null && SAFETY_OFFICER !== null

afterEach(() => sendRequestsAs(null))

describe('SCRUM-84 the approved bookings and their preparation against the backend', () => {
  it('refuses the list and the update without a token', async () => {
    expect(await refusal(fetchApprovedBookingRequests())).toMatchObject(NOT_SIGNED_IN)
    expect(
      await refusal(updateBookingPreparation(UNKNOWN_BOOKING_ID, { status: 'ready' })),
    ).toMatchObject(NOT_SIGNED_IN)
  })

  it('refuses the list and the update to an Event Coordinator', async () => {
    await signInAs(staffAccount())

    expect(await refusal(fetchApprovedBookingRequests())).toMatchObject(NOT_PERMITTED)
    expect(
      await refusal(updateBookingPreparation(UNKNOWN_BOOKING_ID, { status: 'ready' })),
    ).toMatchObject(NOT_PERMITTED)
  })

  it.skipIf(!hasVenueStaff)(
    'names the fields it refuses (400) before looking for the booking',
    async () => {
      await signInAs(required(VENUE_STAFF))

      const error = await refusal(
        updateBookingPreparation(UNKNOWN_BOOKING_ID, { status: 'done', notes: '   ' }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({
        status: ['Status must be not_started, in_progress or ready.'],
        notes: ['Must not be blank.'],
      })
    },
  )

  it.skipIf(!hasVenueStaff)('answers 404 for a booking that does not exist', async () => {
    await signInAs(required(VENUE_STAFF))

    const error = await refusal(updateBookingPreparation(UNKNOWN_BOOKING_ID, { status: 'ready' }))

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Booking request not found.',
    })
  })

  it.skipIf(!canReachSafetyApproval)(
    'refuses a pending booking, and an approved one before the Safety Officer approves (409)',
    async () => {
      const event = await eventReadyForSafetyReview()
      await signInAs(staffAccount())
      const pending = await raiseBookingRequest(event.reference, {
        venue_id: event.venueId,
        starts_at: `${EVENT_DATE}T13:00:00+08:00`,
        ends_at: `${EVENT_DATE}T16:00:00+08:00`,
        purpose: 'Integration afternoon',
      })
      await signInAs(required(VENUE_STAFF))

      const notApproved = await refusal(updateBookingPreparation(pending.id, { status: 'ready' }))
      const noSafetyApproval = await refusal(
        updateBookingPreparation(event.bookingId, { status: 'ready' }),
      )

      expect(notApproved).toMatchObject({
        status: 409,
        code: 'conflict',
        message: 'Preparation can only be recorded for an approved booking; this one is pending.',
      })
      expect(noSafetyApproval).toMatchObject({
        status: 409,
        code: 'conflict',
        message: SAFETY_APPROVAL_MESSAGE,
      })
    },
  )

  it.skipIf(!canReachSafetyApproval)(
    'records the status and trimmed notes, which Venue Staff and the coordinator then read',
    async () => {
      const event = await safetyApprovedEvent()
      await signInAs(required(VENUE_STAFF))

      const saved = await updateBookingPreparation(event.bookingId, {
        status: 'in_progress',
        notes: '  Chairs out, stage to do.  ',
      })
      const approved = await fetchApprovedBookingRequests()
      const listed = approved.find((booking) => booking.id === event.bookingId)
      await signInAs(staffAccount())
      const [coordinatorsCopy] = await fetchBookingRequests(event.reference)

      const recorded = {
        preparation_status: 'in_progress',
        preparation_notes: 'Chairs out, stage to do.',
      }
      expect(saved).toMatchObject({ id: event.bookingId, status: 'approved', ...recorded })
      expect(listed).toMatchObject(recorded)
      expect(approved.every((booking) => booking.status === 'approved')).toBe(true)
      expect(coordinatorsCopy).toMatchObject({ id: event.bookingId, ...recorded })
    },
  )
})
