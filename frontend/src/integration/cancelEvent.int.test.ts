import { fetchBookingRequests } from '@/features/booking/api'
import { registerForEvent } from '@/features/catalogue/api'
import { cancelEvent, fetchEventHistory, fetchEventRequest } from '@/features/eventRequests/api'
import { fetchNotifications } from '@/features/notifications/api'
import type { Notification } from '@/features/notifications/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import {
  EVENT_DATE,
  eventReadyForSafetyReview,
  LEAD,
  registrableEvent,
  required,
  SAFETY_OFFICER,
  submittedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-61 against the running backend: an Event Organiser cancels their event with a reason
 * (ADR-0122). It is cancelled at once and the history keeps who and why (AC1); its bookings are
 * released (AC2); the coordinator is told with the reason (AC1), each registered Attendee without
 * it (AC4) and Venue Staff of each booking released (AC8); the refusals say which.
 *
 * The checks on a submitted event need only the staff account. The ones on an event with a
 * booking need a Lead and Venue Staff, and the one with an Attendee a Safety Officer too
 * (INTEGRATION_LEAD_*, INTEGRATION_VENUE_STAFF_*, INTEGRATION_SAFETY_OFFICER_*); they skip
 * without them.
 */

const REASON = 'Our keynote speaker has withdrawn.'
const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }

const canBook = LEAD !== null && VENUE_STAFF !== null
const canRegister = canBook && SAFETY_OFFICER !== null

// Taking an event to Confirmed signs in a dozen times, each a password hash on the backend.
vi.setConfig({ testTimeout: 20_000 })

afterEach(() => sendRequestsAs(null))

/** The signed-in user's notification of `kind` about `reference`, if there is one. */
async function noticeOf(kind: string, reference: string): Promise<Notification | undefined> {
  const notices = await fetchNotifications()
  return notices.find(
    (notification) => notification.kind === kind && notification.event_reference === reference,
  )
}

describe('SCRUM-61 an organiser cancelling an event against the backend', () => {
  it('refuses a coordinator by role, and a visitor without a token', async () => {
    const { reference } = await submittedEvent()
    await signInAs(staffAccount())

    expect(await refusal(cancelEvent(reference, { reason: REASON }))).toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
    sendRequestsAs(null)
    expect(await refusal(cancelEvent(reference, { reason: REASON }))).toMatchObject({
      status: 401,
      code: 'authentication_error',
    })
  })

  it("answers another organisation's organiser as not found", async () => {
    const { reference } = await submittedEvent()
    await submittedEvent()

    expect(await refusal(cancelEvent(reference, { reason: REASON }))).toMatchObject(NOT_FOUND)
  })

  it('asks for a reason under its field, and leaves the event as it was', async () => {
    const { reference } = await submittedEvent()

    const missing = await refusal(cancelEvent(reference, {}))
    const blank = await refusal(cancelEvent(reference, { reason: '   ' }))

    expect(missing).toMatchObject({ status: 400, code: 'validation_error' })
    expect(missing.fieldErrors).toEqual({ reason: ['A reason is required to cancel the event.'] })
    expect(blank.fieldErrors).toEqual({ reason: ['Must not be blank.'] })
    expect((await fetchEventRequest(reference)).status).toBe('submitted')
  })

  it('cancels a submitted event at once, and the history names the organiser and the reason', async () => {
    const { reference } = await submittedEvent()

    const cancelled = await cancelEvent(reference, { reason: `  ${REASON}  ` })

    expect(cancelled).toMatchObject({ reference, status: 'cancelled' })
    expect(cancelled).not.toHaveProperty('organiser_id')
    expect((await fetchEventRequest(reference)).status).toBe('cancelled')
    const [entry] = (await fetchEventHistory(reference)).history
    expect(entry).toMatchObject({ kind: 'event_cancelled', details: { reason: REASON } })
    expect(entry?.actor_name).toEqual(expect.any(String))
  })

  it('refuses to cancel it again, naming the status', async () => {
    const { reference } = await submittedEvent()
    await cancelEvent(reference, { reason: REASON })

    expect(await refusal(cancelEvent(reference, { reason: REASON }))).toMatchObject({
      status: 409,
      code: 'cancellation_not_allowed',
      message:
        'Only an event between Submitted and Confirmed can be cancelled; this one is cancelled.',
    })
  })

  it.skipIf(!canBook)(
    'releases its booking and tells the coordinator why and Venue Staff of the booking',
    async () => {
      const { reference, organiser, bookingId } = await eventReadyForSafetyReview()
      await signInAs(organiser)

      await cancelEvent(reference, { reason: REASON })

      await signInAs(staffAccount())
      const [booking] = await fetchBookingRequests(reference)
      expect(booking).toMatchObject({ id: bookingId, status: 'released' })
      expect(await noticeOf('event_cancelled', reference)).toMatchObject({
        message: 'This event has been cancelled by its organiser.',
        detail: REASON,
      })
      await signInAs(required(VENUE_STAFF))
      const notice = await noticeOf('venue_booking_released_by_cancellation', reference)
      expect(notice).toMatchObject({
        message: 'A venue booking or hold was released because its event was cancelled.',
        link: `/events/${reference}`,
      })
      expect(notice?.detail).toMatch(new RegExp(`^Venue arrangement ${String(bookingId)} at `))
      expect(notice?.detail).toContain(
        `, ${EVENT_DATE} 09:00 to ${EVENT_DATE} 12:00, was released.`,
      )
    },
  )

  it.skipIf(!canRegister)('tells a registered attendee, without the reason (AC4)', async () => {
    const event = await registrableEvent()
    const attendee = await signInAsNewAttendee()
    await registerForEvent(event.id)
    await signInAs(event.organiser)

    await cancelEvent(event.reference, { reason: REASON })

    await signInAs(attendee)
    expect(await noticeOf('event_cancelled', event.reference)).toMatchObject({
      message: 'This event has been cancelled by its organiser.',
      detail: null,
    })
  })
})
