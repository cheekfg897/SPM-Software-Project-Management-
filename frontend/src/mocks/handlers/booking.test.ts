import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from './bookingFixtures'

/**
 * The booking mock stands in for the venue module's SCRUM-42 endpoints, so these tests pin it
 * to what backend/app/modules/venue/routes.py answers.
 */

const APPROVED_EVENT = MOCK_BOOKING_EVENTS.approved
const ROOMY_VENUE = MOCK_BOOKING_VENUES.roomy
const TINY_VENUE = MOCK_BOOKING_VENUES.tiny

function bookingUrl(eventId: number): string {
  return `/api/venues/events/${eventId}/booking-requests`
}

function raise(eventId: number, body: Record<string, unknown>) {
  return apiRequest<Record<string, unknown>>(bookingUrl(eventId), { method: 'POST', body })
}

function validPayload(overrides: Record<string, unknown> = {}) {
  return {
    venue_id: ROOMY_VENUE.id,
    starts_at: '2026-11-10T09:00:00+08:00',
    ends_at: '2026-11-10T12:00:00+08:00',
    purpose: 'Keynote',
    ...overrides,
  }
}

async function errorOf(promise: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await promise.then(
    () => null,
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error('Expected the request to fail with an ApiError.')
  }
  return error
}

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
})

describe('SCRUM-42 booking mock: raising a request', () => {
  it('saves a Pending request carrying the event details, defaulting occupancy from the event', async () => {
    const created = await raise(APPROVED_EVENT.id, validPayload())

    expect(created).toMatchObject({
      event_id: APPROVED_EVENT.id,
      venue_id: ROOMY_VENUE.id,
      status: 'pending',
      purpose: 'Keynote',
      expected_occupancy: APPROVED_EVENT.expected_attendance,
      required_layout: null,
      justification: null,
      event_proposed_date: APPROVED_EVENT.proposed_date,
      event_end_date: APPROVED_EVENT.end_date,
      event_start_time: APPROVED_EVENT.start_time,
      event_end_time: APPROVED_EVENT.end_time,
      accessibility_needs: APPROVED_EVENT.accessibility_needs,
    })
  })

  it('keeps the occupancy, layout and justification it was given', async () => {
    const created = await raise(
      APPROVED_EVENT.id,
      validPayload({
        expected_occupancy: 10,
        required_layout: 'boardroom',
        justification: 'Only room free.',
      }),
    )

    expect(created).toMatchObject({
      expected_occupancy: 10,
      required_layout: 'boardroom',
      justification: 'Only room free.',
    })
  })

  it('lists the requests raised, with the details of the event', async () => {
    await raise(APPROVED_EVENT.id, validPayload())
    await raise(APPROVED_EVENT.id, validPayload({ venue_id: TINY_VENUE.id, justification: 'x' }))

    const listed = await apiRequest<{ venue_id: number }[]>(bookingUrl(APPROVED_EVENT.id))

    expect(listed.map((request) => request.venue_id)).toEqual([ROOMY_VENUE.id, TINY_VENUE.id])
  })

  it('lists nothing for an event with no requests', async () => {
    expect(await apiRequest(bookingUrl(APPROVED_EVENT.id))).toEqual([])
  })

  it('asks for a justification when the venue is too small for the occupancy', async () => {
    const error = await errorOf(raise(APPROVED_EVENT.id, validPayload({ venue_id: TINY_VENUE.id })))

    expect(error.status).toBe(400)
    expect(error.fieldErrors.justification).toEqual([
      'A justification is required because the venue is not suitable.',
    ])
  })

  it('judges suitability by the occupancy of the request, not the event', async () => {
    const created = await raise(
      APPROVED_EVENT.id,
      validPayload({ venue_id: TINY_VENUE.id, expected_occupancy: 5 }),
    )

    expect(created.status).toBe('pending')
  })

  it('names every missing required field', async () => {
    const error = await errorOf(raise(APPROVED_EVENT.id, {}))

    expect(error.status).toBe(400)
    expect(Object.keys(error.fieldErrors).sort()).toEqual([
      'ends_at',
      'purpose',
      'starts_at',
      'venue_id',
    ])
  })

  it('rejects a venue that does not exist', async () => {
    const error = await errorOf(raise(APPROVED_EVENT.id, validPayload({ venue_id: 999 })))

    expect(error.fieldErrors.venue_id).toEqual(['Venue not found.'])
  })

  it('refuses a second Pending request for the same venue and period', async () => {
    await raise(APPROVED_EVENT.id, validPayload())

    const error = await errorOf(raise(APPROVED_EVENT.id, validPayload()))

    expect(error.status).toBe(409)
    expect(error.message).toBe('A pending request for this event, venue and period already exists.')
  })

  it('allows another venue at the same time', async () => {
    await raise(APPROVED_EVENT.id, validPayload())

    const second = await raise(
      APPROVED_EVENT.id,
      validPayload({ venue_id: TINY_VENUE.id, expected_occupancy: 5 }),
    )

    expect(second.venue_id).toBe(TINY_VENUE.id)
  })

  it('refuses an event that is not approved, naming its status', async () => {
    const error = await errorOf(raise(MOCK_BOOKING_EVENTS.confirmed.id, validPayload()))

    expect(error.status).toBe(409)
    expect(error.message).toBe(
      'Only an approved event can have a venue booking request; this one is confirmed.',
    )
  })

  it('answers 404 for an event that is not yours, or does not exist', async () => {
    const notYours = await errorOf(raise(MOCK_BOOKING_EVENTS.someoneElses.id, validPayload()))
    const missing = await errorOf(raise(999, validPayload()))

    expect([notYours.status, missing.status]).toEqual([404, 404])
  })

  it('shows requests on a confirmed event, but 404s on a list of someone elses', async () => {
    expect(await apiRequest(bookingUrl(MOCK_BOOKING_EVENTS.confirmed.id))).toEqual([])
    const error = await errorOf(apiRequest(bookingUrl(MOCK_BOOKING_EVENTS.someoneElses.id)))

    expect(error.status).toBe(404)
  })

  it('answers 401 without a token and 403 to anyone but a coordinator', async () => {
    sendRequestsAs(null)
    const signedOut = await errorOf(raise(APPROVED_EVENT.id, validPayload()))
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))
    const attendee = await errorOf(raise(APPROVED_EVENT.id, validPayload()))

    expect([signedOut.status, attendee.status]).toEqual([401, 403])
  })
})
