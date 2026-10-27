import {
  decideBookingRequest,
  fetchBookingRequests,
  fetchFlaggedBookings,
  raiseBookingRequest,
  reconfirmFlaggedBooking,
  rejectFlaggedBooking,
} from '@/features/booking/api'
import type { FlaggedBooking } from '@/features/booking/api'
import { editEventRequest, sendToSafetyReview } from '@/features/eventRequests/api'
import { fetchNotifications } from '@/features/notifications/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount } from './backend'
import { approvedEvent, EVENT_DATE, LEAD, newVenue, required, VENUE_STAFF } from './plannedEvent'

/**
 * SCRUM-59 against the real backend: Venue Staff list the bookings a change flagged, with what
 * reconfirming each gives it, then reconfirm or reject them. Each check takes a new event through
 * approval, books a venue for 300 for it from 09:00 to 12:00, and has the coordinator (the staff
 * account) change the event, as SCRUM-33 lets them, which flags the booking.
 */

const needsAccounts = LEAD === null || VENUE_STAFF === null

/** The day after the event's own, as the backend reads dates ("2026-11-21"). */
const NEXT_DAY = new Date(Date.parse(`${EVENT_DATE}T00:00:00Z`) + 24 * 60 * 60_000)
  .toISOString()
  .slice(0, 10)

function at(day: string, time: string): string {
  return `${day}T${time}:00+08:00`
}

/** An approved event with one approved booking for 120 at a venue for 300, 09:00-12:00. */
async function bookedEvent() {
  const event = await approvedEvent()
  const venueId = await newVenue()
  await signInAs(staffAccount())
  const raised = await raiseBookingRequest(event.reference, {
    venue_id: venueId,
    starts_at: at(EVENT_DATE, '09:00'),
    ends_at: at(EVENT_DATE, '12:00'),
    purpose: 'Integration plenary',
  })
  await signInAs(required(VENUE_STAFF))
  await decideBookingRequest(raised.id, { outcome: 'approved' })
  return { reference: event.reference, bookingId: raised.id }
}

/** As the coordinator, edit the event; then sign Venue Staff in. */
async function coordinatorEdits(reference: string, changes: Record<string, unknown>) {
  await signInAs(staffAccount())
  await editEventRequest(reference, changes)
  await signInAs(required(VENUE_STAFF))
}

/** The flagged booking `id`, as Venue Staff's list shows it. */
async function listed(id: number): Promise<FlaggedBooking | undefined> {
  return (await fetchFlaggedBookings()).find((entry) => entry.booking.id === id)
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-59 flagged bookings against the backend', () => {
  it('refuses the list without a token (401) and to a coordinator (403)', async () => {
    const anonymous = await refusal(fetchFlaggedBookings())
    await signInAs(staffAccount())
    const coordinator = await refusal(fetchFlaggedBookings())

    expect(anonymous).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(coordinator).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it.skipIf(needsAccounts)(
    'lists a booking a date change flagged, pre-filled for the new day, and reconfirms it',
    async () => {
      const { reference, bookingId } = await bookedEvent()
      await coordinatorEdits(reference, { proposed_date: NEXT_DAY, end_date: NEXT_DAY })

      expect(await listed(bookingId)).toMatchObject({
        booking: { flagged_after_change: true, status: 'approved' },
        reconfirm_with: {
          starts_at: at(NEXT_DAY, '09:00'),
          ends_at: at(NEXT_DAY, '12:00'),
          expected_occupancy: 120,
        },
      })
      const outside = await refusal(
        reconfirmFlaggedBooking(bookingId, {
          starts_at: at(EVENT_DATE, '09:00'),
          ends_at: at(EVENT_DATE, '12:00'),
        }),
      )
      expect(outside.status).toBe(400)
      expect(outside.fieldErrors.starts_at?.[0]).toMatch(
        /^The period must lie within the event's start and end: /,
      )

      const reconfirmed = await reconfirmFlaggedBooking(bookingId, {
        starts_at: at(NEXT_DAY, '09:00'),
        ends_at: at(NEXT_DAY, '12:00'),
      })

      expect(reconfirmed).toMatchObject({
        status: 'approved',
        starts_at: at(NEXT_DAY, '09:00'),
        flagged_after_change: false,
        reassessment_flags: [],
      })
      expect(await listed(bookingId)).toBeUndefined()
      // Read back in a fresh session, as the coordinator, who is told.
      await signInAs(staffAccount())
      const saved = (await fetchBookingRequests(reference)).find((each) => each.id === bookingId)
      expect(saved).toMatchObject({ starts_at: at(NEXT_DAY, '09:00'), flagged_after_change: false })
      const kinds = (await fetchNotifications()).map((notification) => notification.kind)
      expect(kinds).toContain('venue_booking_reconfirmed')
    },
  )

  it.skipIf(needsAccounts)(
    'needs a reason to reconfirm a venue too small for the new attendance',
    async () => {
      const { reference, bookingId } = await bookedEvent()
      await coordinatorEdits(reference, { expected_attendance: 400 })
      const period = { starts_at: at(EVENT_DATE, '09:00'), ends_at: at(EVENT_DATE, '12:00') }

      const missing = await refusal(reconfirmFlaggedBooking(bookingId, period))
      expect(missing).toMatchObject({ status: 400 })
      expect(missing.fieldErrors.reason).toEqual([
        "A reason is required because the venue's capacity of 300 is below the booking's expected occupancy of 400.",
      ])

      const reconfirmed = await reconfirmFlaggedBooking(bookingId, {
        ...period,
        reason: 'Standing room agreed.',
      })
      expect(reconfirmed).toMatchObject({
        expected_occupancy: 400,
        decision_reason: 'Standing room agreed.',
      })
    },
  )

  it.skipIf(needsAccounts)(
    'rejects with a reason, which then holds the event back from Safety Review',
    async () => {
      const { reference, bookingId } = await bookedEvent()
      await coordinatorEdits(reference, { end_time: '18:00' })

      const missing = await refusal(rejectFlaggedBooking(bookingId, { reason: '  ' }))
      expect(missing.fieldErrors.reason).toEqual([
        'A reason is required to reject a booking request.',
      ])
      const rejected = await rejectFlaggedBooking(bookingId, { reason: 'Hall closed.' })
      expect(rejected).toMatchObject({ status: 'rejected', decision_reason: 'Hall closed.' })

      await signInAs(staffAccount())
      const held = await refusal(sendToSafetyReview(reference))
      expect(held.status).toBe(409)
    },
  )

  it.skipIf(needsAccounts)('refuses a booking no change flagged (409)', async () => {
    const { bookingId } = await bookedEvent()

    const error = await refusal(rejectFlaggedBooking(bookingId, { reason: 'Hall closed.' }))

    expect(error).toMatchObject({
      status: 409,
      message:
        'This booking is not flagged after a change, so there is nothing to reconfirm or reject.',
    })
  })
})
