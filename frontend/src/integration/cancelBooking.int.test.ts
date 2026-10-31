import {
  cancelBooking,
  decideBookingRequest,
  fetchBookingRequests,
  raiseBookingRequest,
} from '@/features/booking/api'
import {
  confirmEvent,
  fetchEventHistory,
  fetchEventRequest,
  sendToSafetyReview,
} from '@/features/eventRequests/api'
import { fetchNotifications } from '@/features/notifications/api'
import { recordSafetyOutcome } from '@/features/safety/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import type { Credentials } from './backend'
import {
  approvedEvent,
  CHECKLIST,
  EVENT_DATE,
  eventReadyForSafetyReview,
  LEAD,
  newVenue,
  required,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-111 against the running backend: the assigned coordinator cancels one approved venue
 * booking with a reason (ADR-0117). Its arrangement becomes `cancelled` and the event's others
 * stay (AC1, AC2); an event in Safety Review goes back to `approved` when its pass no longer counts
 * or its last venue went, and otherwise stays, with every Safety Officer told (AC2); Venue Staff
 * are told (AC3); the refusals say which (AC4); the history keeps the reason (AC5).
 *
 * The refusals that need no event of the coordinator's run with the staff account and a new
 * attendee. The rest need a Lead, Venue Staff and a Safety Officer (INTEGRATION_LEAD_*,
 * INTEGRATION_VENUE_STAFF_*, INTEGRATION_SAFETY_OFFICER_*) and skip without them.
 */

/** A well-formed reference and an id no database has. */
const UNKNOWN_EVENT_REFERENCE = 'EVR-NOSUCH00'
const UNKNOWN_ARRANGEMENT_ID = 99_999_999
const REASON = 'The breakout sessions moved into the main hall.'
const BACK_IN_PLANNING = ' It is back in planning until it can be sent to Safety Review again.'

const canBook = LEAD !== null && VENUE_STAFF !== null
const canReview = canBook && SAFETY_OFFICER !== null

// An event with two venues taken to Safety Review signs in a dozen times, each a password hash
// on the backend, which can pass the default 5 seconds.
vi.setConfig({ testTimeout: 20_000 })

afterEach(() => sendRequestsAs(null))

/** As the staff account, raise a second request on the event, 13:00-16:00, and approve it. */
async function secondApprovedBooking(reference: string): Promise<number> {
  const venueId = await newVenue()
  await signInAs(staffAccount())
  const raised = await raiseBookingRequest(reference, {
    venue_id: venueId,
    starts_at: `${EVENT_DATE}T13:00:00+08:00`,
    ends_at: `${EVENT_DATE}T16:00:00+08:00`,
    purpose: 'Integration afternoon',
  })
  await signInAs(required(VENUE_STAFF))
  await decideBookingRequest(raised.id, { outcome: 'approved' })
  return raised.id
}

/** As the staff account, cancel the booking with the reason. */
async function cancelAsCoordinator(reference: string, bookingId: number) {
  await signInAs(staffAccount())
  return cancelBooking(reference, bookingId, { reason: REASON })
}

/** The notices about the event of `kind` the account has, newest first. */
async function noticesOf(account: Credentials, reference: string, kind: string) {
  await signInAs(account)
  const notices = await fetchNotifications()
  return notices.filter((notice) => notice.kind === kind && notice.event_reference === reference)
}

/** The detail a notice gives the booking: its id, then its venue (newVenue's unique name). */
function cancelledDetail(bookingId: number): RegExp {
  return new RegExp(
    `^Venue arrangement ${String(bookingId)} at Integration Hall .+, ${EVENT_DATE} 09:00 to ${EVENT_DATE} 12:00, was cancelled\\.`,
  )
}

describe('SCRUM-111 cancelling one approved venue booking against the backend', () => {
  it('refuses without a token (401)', async () => {
    const error = await refusal(
      cancelBooking(UNKNOWN_EVENT_REFERENCE, UNKNOWN_ARRANGEMENT_ID, { reason: REASON }),
    )

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses a role other than the Event Coordinator (403)', async () => {
    await signInAsNewAttendee()

    const error = await refusal(
      cancelBooking(UNKNOWN_EVENT_REFERENCE, UNKNOWN_ARRANGEMENT_ID, { reason: REASON }),
    )

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('answers 404 for an event the coordinator has none of', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      cancelBooking(UNKNOWN_EVENT_REFERENCE, UNKNOWN_ARRANGEMENT_ID, { reason: REASON }),
    )

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Event request not found.',
    })
  })

  it.skipIf(!canBook)(
    'cancels the booking, leaves the event approved and its other booking approved, and keeps the reason in the history',
    async () => {
      const { reference, bookingId } = await eventReadyForSafetyReview()
      const otherId = await secondApprovedBooking(reference)

      const cancelled = await cancelAsCoordinator(reference, bookingId)

      expect(cancelled).toMatchObject({ id: bookingId, status: 'cancelled' })
      const statuses = (await fetchBookingRequests(reference)).map((arrangement) => [
        arrangement.id,
        arrangement.status,
      ])
      expect(statuses).toEqual([
        [bookingId, 'cancelled'],
        [otherId, 'approved'],
      ])
      expect((await fetchEventRequest(reference)).status).toBe('approved')
      const { history } = await fetchEventHistory(reference)
      expect(history.at(-1)).toMatchObject({
        kind: 'venue_booking_cancelled',
        details: {
          venue_booking_request_id: bookingId,
          reason: REASON,
          starts_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T01:00:00\+00:00$/) as unknown,
        },
      })
    },
  )

  it.skipIf(!canBook)('tells Venue Staff, naming the event, the venue and the period', async () => {
    const { reference, bookingId } = await eventReadyForSafetyReview()

    await cancelAsCoordinator(reference, bookingId)

    const notices = await noticesOf(required(VENUE_STAFF), reference, 'venue_booking_cancelled')
    expect(notices).toHaveLength(1)
    expect(notices[0]).toMatchObject({
      message: "The event's coordinator cancelled a venue booking, so the venue is free again.",
      link: `/events/${reference}`,
    })
    expect(notices[0]?.detail).toMatch(cancelledDetail(bookingId))
  })

  it.skipIf(!canBook)(
    'refuses a missing reason, then a booking already cancelled, each saying which',
    async () => {
      const { reference, bookingId } = await eventReadyForSafetyReview()
      await signInAs(staffAccount())

      const noReason = await refusal(cancelBooking(reference, bookingId, {}))
      await cancelBooking(reference, bookingId, { reason: REASON })
      const again = await refusal(cancelBooking(reference, bookingId, { reason: REASON }))

      expect(noReason).toMatchObject({ status: 400, code: 'validation_error' })
      expect(noReason.fieldErrors).toEqual({
        reason: ['A reason is required to cancel a booking.'],
      })
      expect(again).toMatchObject({
        status: 409,
        message: 'Only an approved booking can be cancelled; this one is cancelled.',
      })
    },
  )

  it.skipIf(!canBook)('answers 404 for another event’s booking', async () => {
    const { reference } = await approvedEvent()
    const { bookingId } = await eventReadyForSafetyReview()
    await signInAs(staffAccount())

    const error = await refusal(cancelBooking(reference, bookingId, { reason: REASON }))

    expect(error).toMatchObject({ status: 404, message: 'Venue arrangement not found.' })
  })

  it.skipIf(!canReview)(
    'sends a confirmed event’s cancellation back with its status named (409)',
    async () => {
      const { reference, bookingId } = await safetyApprovedEvent()
      await signInAs(staffAccount())
      await confirmEvent(reference)

      const error = await refusal(cancelBooking(reference, bookingId, { reason: REASON }))

      expect(error).toMatchObject({
        status: 409,
        message:
          'Only an approved event or one in Safety Review can have a venue booking cancelled; this one is confirmed.',
      })
    },
  )

  it.skipIf(!canReview)(
    'keeps an event in Safety Review with another venue left, and tells every Safety Officer the venue dropped',
    async () => {
      const { reference, bookingId } = await eventReadyForSafetyReview()
      await secondApprovedBooking(reference)
      await signInAs(staffAccount())
      await sendToSafetyReview(reference)

      await cancelAsCoordinator(reference, bookingId)

      expect((await fetchEventRequest(reference)).status).toBe('safety_review')
      const notices = await noticesOf(
        required(SAFETY_OFFICER),
        reference,
        'safety_review_venue_cancelled',
      )
      expect(notices).toHaveLength(1)
      expect(notices[0]?.message).toBe('A venue was dropped from an event in Safety Review.')
      expect(notices[0]?.detail).toMatch(cancelledDetail(bookingId))
      expect(notices[0]?.detail).not.toContain(BACK_IN_PLANNING)
    },
  )

  it.skipIf(!canReview)(
    'sends an event in Safety Review back to approved when its last venue goes, and says so',
    async () => {
      const { reference, bookingId } = await eventReadyForSafetyReview()
      await signInAs(staffAccount())
      await sendToSafetyReview(reference)

      await cancelAsCoordinator(reference, bookingId)

      expect((await fetchEventRequest(reference)).status).toBe('approved')
      const notices = await noticesOf(
        required(SAFETY_OFFICER),
        reference,
        'safety_review_venue_cancelled',
      )
      expect(notices[0]?.detail).toMatch(new RegExp(`${BACK_IN_PLANNING}$`))
    },
  )

  it.skipIf(!canReview)(
    'withdraws the Safety Officer’s pass even with another venue left, so the event goes back to approved',
    async () => {
      const { reference, bookingId } = await eventReadyForSafetyReview()
      await secondApprovedBooking(reference)
      await signInAs(staffAccount())
      await sendToSafetyReview(reference)
      await signInAs(required(SAFETY_OFFICER))
      await recordSafetyOutcome({ reference, outcome: 'approved', checklist: CHECKLIST })

      await cancelAsCoordinator(reference, bookingId)

      expect((await fetchEventRequest(reference)).status).toBe('approved')
      const { history } = await fetchEventHistory(reference)
      expect(history.map((entry) => entry.kind).slice(-2)).toEqual([
        'venue_booking_cancelled',
        'safety_approval_withdrawn',
      ])
      const notices = await noticesOf(
        required(SAFETY_OFFICER),
        reference,
        'safety_review_venue_cancelled',
      )
      expect(notices[0]?.detail).toMatch(new RegExp(`${BACK_IN_PLANNING}$`))
    },
  )
})
