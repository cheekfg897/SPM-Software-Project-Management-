import {
  decideBookingRequest,
  fetchBookingRequests,
  raiseBookingRequest,
} from '@/features/booking/api'
import { fetchEventRequest } from '@/features/eventRequests/api'
import { fetchNotifications } from '@/features/notifications/api'
import { blockVenue, deactivateVenue } from '@/features/venues/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount } from './backend'
import { approvedEvent, EVENT_DATE, LEAD, newVenue, required, VENUE_STAFF } from './plannedEvent'
import type { PlannedEvent } from './plannedEvent'

/**
 * SCRUM-70 against the running backend (ADR-0123): Venue Staff suggest another venue and another
 * period when they reject a request (AC1); an inactive venue, or a suggestion with an approval, is
 * refused (AC1, AC2); the suggestion comes back on the request, on the organiser's record by the
 * venue's name (AC3) and in the coordinator's one rejection notice (AC6); and the coordinator
 * raises a new request for it while the rejected one stays (AC4). Planning an event takes a Lead
 * and Venue Staff, which plannedEvent.ts reads; the checks skip without them.
 */

const canPlan = LEAD !== null && VENUE_STAFF !== null
const MORNING = {
  starts_at: `${EVENT_DATE}T09:00:00+08:00`,
  ends_at: `${EVENT_DATE}T12:00:00+08:00`,
}
const AFTERNOON = {
  suggested_starts_at: `${EVENT_DATE}T13:00:00+08:00`,
  suggested_ends_at: `${EVENT_DATE}T16:00:00+08:00`,
}

afterEach(() => sendRequestsAs(null))

/** An approved event with a request at one new venue, another venue free, and Venue Staff signed in. */
interface Rejectable extends PlannedEvent {
  requestId: number
  otherVenueId: number
}

async function rejectableRequest(): Promise<Rejectable> {
  const event = await approvedEvent()
  const venueId = await newVenue()
  const otherVenueId = await newVenue()
  await signInAs(staffAccount())
  const raised = await raiseBookingRequest(event.reference, {
    venue_id: venueId,
    ...MORNING,
    purpose: 'Integration keynote',
  })
  await signInAs(required(VENUE_STAFF))
  return { ...event, requestId: raised.id, otherVenueId }
}

async function venueName(venueId: number): Promise<string> {
  const venue = await apiRequest<{ name: string }>(`/api/venues/${String(venueId)}`)
  return venue.name
}

describe('SCRUM-70 suggesting an alternative when rejecting, against the backend', () => {
  it.skipIf(!canPlan)(
    'keeps the suggestion on the request, the record and the notice, and the coordinator raises a new request for it',
    async () => {
      const event = await rejectableRequest()
      const otherName = await venueName(event.otherVenueId)

      const rejected = await decideBookingRequest(event.requestId, {
        outcome: 'rejected',
        reason: 'The hall is being repainted.',
        suggested_venue_id: event.otherVenueId,
        ...AFTERNOON,
      })

      // --- AC1, AC3: on the request, in business time ---
      expect(rejected).toMatchObject({
        status: 'rejected',
        decision_reason: 'The hall is being repainted.',
        suggested_venue_id: event.otherVenueId,
        ...AFTERNOON,
      })
      // --- AC3: on the organiser's record, the venue by name ---
      await signInAs(event.organiser)
      const record = await fetchEventRequest(event.reference)
      expect(record.venue_arrangements?.[0]).toMatchObject({
        decision_reason: 'The hall is being repainted.',
        suggested_venue_name: otherName,
        ...AFTERNOON,
      })
      // --- AC6: the coordinator's one rejection notice names it before the reason ---
      await signInAs(staffAccount())
      const notices = (await fetchNotifications()).filter(
        (notice) =>
          notice.kind === 'venue_booking_rejected' && notice.event_reference === event.reference,
      )
      expect(notices.map((notice) => notice.detail)).toEqual([
        `Suggested instead: ${otherName} from ${EVENT_DATE} 13:00 to ${EVENT_DATE} 16:00. ` +
          'Reason: The hall is being repainted.',
      ])
      // --- AC4: a new request for the suggestion; the rejected one stays ---
      const raised = await raiseBookingRequest(event.reference, {
        venue_id: event.otherVenueId,
        starts_at: AFTERNOON.suggested_starts_at,
        ends_at: AFTERNOON.suggested_ends_at,
        purpose: 'Integration keynote',
      })
      const listed = await fetchBookingRequests(event.reference)
      expect(listed.map((each) => [each.id, each.status])).toEqual([
        [event.requestId, 'rejected'],
        [raised.id, 'pending'],
      ])
    },
  )

  it.skipIf(!canPlan)('refuses a suggestion with an approval (400)', async () => {
    const event = await rejectableRequest()

    const error = await refusal(
      decideBookingRequest(event.requestId, { outcome: 'approved', ...AFTERNOON }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      suggested_starts_at: ['An alternative can only be suggested when rejecting a request.'],
      suggested_ends_at: ['An alternative can only be suggested when rejecting a request.'],
    })
  })

  it.skipIf(!canPlan)('refuses an inactive venue (400)', async () => {
    const event = await rejectableRequest()
    await deactivateVenue(event.otherVenueId, { category: 'renovation', reason: 'Refit.' })

    const error = await refusal(
      decideBookingRequest(event.requestId, {
        outcome: 'rejected',
        reason: 'Closed',
        suggested_venue_id: event.otherVenueId,
      }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      suggested_venue_id: ['The suggested venue must be an active venue.'],
    })
  })

  it.skipIf(!canPlan)('refuses half a period (400)', async () => {
    const event = await rejectableRequest()

    const error = await refusal(
      decideBookingRequest(event.requestId, {
        outcome: 'rejected',
        reason: 'Closed',
        suggested_starts_at: AFTERNOON.suggested_starts_at,
      }),
    )

    expect(error.fieldErrors).toEqual({
      suggested_ends_at: ['A suggested period needs both a start and an end.'],
    })
  })

  it.skipIf(!canPlan)(
    'refuses another period for a replacement that keeps its period (400)',
    async () => {
      // Book the request's venue, block it so the booking needs another venue (SCRUM-92), and
      // raise a replacement, which keeps the booking's period.
      const event = await rejectableRequest()
      const booked = await decideBookingRequest(event.requestId, { outcome: 'approved' })
      await blockVenue(booked.venue_id, {
        start_time: `${EVENT_DATE}T08:00`,
        end_time: `${EVENT_DATE}T18:00`,
        category: 'equipment_failure',
        reason: 'Lift broken',
      })
      await signInAs(staffAccount())
      const replacement = await raiseBookingRequest(event.reference, {
        venue_id: event.otherVenueId,
        ...MORNING,
        purpose: 'Integration replacement',
        replaces_request_id: event.requestId,
      })
      await signInAs(required(VENUE_STAFF))

      const error = await refusal(
        decideBookingRequest(replacement.id, {
          outcome: 'rejected',
          reason: 'Closed',
          ...AFTERNOON,
        }),
      )

      const locked =
        'A replacement keeps the period of the booking it replaces, so only another venue can be suggested.'
      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({
        suggested_starts_at: [locked],
        suggested_ends_at: [locked],
      })
    },
  )
})
