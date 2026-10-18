import { ROLE } from '@/config/roles'
import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { MOCK_ARRANGEMENTS, MOCK_BOOKING_EVENTS, MOCK_BOOKING_VENUES } from './bookingFixtures'

/**
 * The booking mock stands in for the venue module's SCRUM-42 and SCRUM-93 endpoints, so these
 * tests pin it to what backend/app/modules/venue/routes.py answers.
 */

const APPROVED_EVENT = MOCK_BOOKING_EVENTS.approved
const ROOMY_VENUE = MOCK_BOOKING_VENUES.roomy
const TINY_VENUE = MOCK_BOOKING_VENUES.tiny

function bookingUrl(reference: string): string {
  return `/api/venues/events/${reference}/booking-requests`
}

function raise(reference: string, body: Record<string, unknown>) {
  return apiRequest<Record<string, unknown>>(bookingUrl(reference), { method: 'POST', body })
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
    const created = await raise(APPROVED_EVENT.reference, validPayload())

    expect(created).toMatchObject({
      event_id: APPROVED_EVENT.id,
      venue_id: ROOMY_VENUE.id,
      status: 'pending',
      // The backend sends it on every request; null until Venue Staff hold it (SCRUM-75).
      hold_expires_at: null,
      purpose: 'Keynote',
      expected_occupancy: APPROVED_EVENT.expected_attendance,
      required_layout: null,
      justification: null,
      preparation_status: 'not_started',
      preparation_notes: null,
      event_proposed_date: APPROVED_EVENT.proposed_date,
      event_end_date: APPROVED_EVENT.end_date,
      event_start_time: APPROVED_EVENT.start_time,
      event_end_time: APPROVED_EVENT.end_time,
      accessibility_needs: APPROVED_EVENT.accessibility_needs,
    })
  })

  it('keeps the occupancy, layout and justification it was given', async () => {
    const created = await raise(
      APPROVED_EVENT.reference,
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
    await raise(APPROVED_EVENT.reference, validPayload())
    await raise(
      APPROVED_EVENT.reference,
      validPayload({ venue_id: TINY_VENUE.id, justification: 'x' }),
    )

    const listed = await apiRequest<{ venue_id: number }[]>(bookingUrl(APPROVED_EVENT.reference))

    expect(listed.map((request) => request.venue_id)).toEqual([ROOMY_VENUE.id, TINY_VENUE.id])
  })

  it('lists nothing for an event with no requests', async () => {
    expect(await apiRequest(bookingUrl(APPROVED_EVENT.reference))).toEqual([])
  })

  it('asks for a justification when the venue is too small for the occupancy', async () => {
    const error = await errorOf(
      raise(APPROVED_EVENT.reference, validPayload({ venue_id: TINY_VENUE.id })),
    )

    expect(error.status).toBe(400)
    expect(error.fieldErrors.justification).toEqual([
      'A justification is required because the venue is not suitable.',
    ])
  })

  it('judges suitability by the occupancy of the request, not the event', async () => {
    const created = await raise(
      APPROVED_EVENT.reference,
      validPayload({ venue_id: TINY_VENUE.id, expected_occupancy: 5 }),
    )

    expect(created.status).toBe('pending')
  })

  it('names every missing required field', async () => {
    const error = await errorOf(raise(APPROVED_EVENT.reference, {}))

    expect(error.status).toBe(400)
    expect(Object.keys(error.fieldErrors).sort()).toEqual([
      'ends_at',
      'purpose',
      'starts_at',
      'venue_id',
    ])
  })

  it('rejects a venue that does not exist', async () => {
    const error = await errorOf(raise(APPROVED_EVENT.reference, validPayload({ venue_id: 999 })))

    expect(error.fieldErrors.venue_id).toEqual(['Venue not found.'])
  })

  it('refuses a second Pending request for the same venue and period', async () => {
    await raise(APPROVED_EVENT.reference, validPayload())

    const error = await errorOf(raise(APPROVED_EVENT.reference, validPayload()))

    expect(error.status).toBe(409)
    expect(error.message).toBe('A pending request for this event, venue and period already exists.')
  })

  it('allows another venue at the same time', async () => {
    await raise(APPROVED_EVENT.reference, validPayload())

    const second = await raise(
      APPROVED_EVENT.reference,
      validPayload({ venue_id: TINY_VENUE.id, expected_occupancy: 5 }),
    )

    expect(second.venue_id).toBe(TINY_VENUE.id)
  })

  it('refuses an event that is not approved, naming its status', async () => {
    const error = await errorOf(raise(MOCK_BOOKING_EVENTS.confirmed.reference, validPayload()))

    expect(error.status).toBe(409)
    expect(error.message).toBe(
      'Only an approved event can have a venue booking request; this one is confirmed.',
    )
  })

  it('answers 404 for an event that is not yours, or does not exist', async () => {
    const notYours = await errorOf(
      raise(MOCK_BOOKING_EVENTS.someoneElses.reference, validPayload()),
    )
    const missing = await errorOf(raise('EVR-NOSUCH00', validPayload()))

    expect([notYours.status, missing.status]).toEqual([404, 404])
  })

  it('shows requests on a confirmed event, but 404s on a list of someone elses', async () => {
    expect(await apiRequest(bookingUrl(MOCK_BOOKING_EVENTS.confirmed.reference))).toEqual([])
    const error = await errorOf(apiRequest(bookingUrl(MOCK_BOOKING_EVENTS.someoneElses.reference)))

    expect(error.status).toBe(404)
  })

  it('answers 401 without a token and 403 to anyone but a coordinator', async () => {
    sendRequestsAs(null)
    const signedOut = await errorOf(raise(APPROVED_EVENT.reference, validPayload()))
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.attendee))
    const attendee = await errorOf(raise(APPROVED_EVENT.reference, validPayload()))

    expect([signedOut.status, attendee.status]).toEqual([401, 403])
  })
})

describe('SCRUM-44 booking mock: approving a request that clashes', () => {
  const DECISION_URL = '/api/venues/booking-requests'
  const WAITING_AT_ROOMY_VENUE = 9001

  function decide(requestId: number, outcome: string) {
    return apiRequest<Record<string, unknown>>(`${DECISION_URL}/${requestId}/decision`, {
      method: 'POST',
      body: { outcome, reason: 'Checked with the venue' },
    })
  }

  /** The period request 9001 waits for at the roomy venue is 09:00 to 12:00 on 20 November. */
  const OVERLAPPING_9001 = {
    starts_at: '2026-11-20T11:00:00+08:00',
    ends_at: '2026-11-20T14:00:00+08:00',
  }

  /** Raise a second request, with ``overrides`` to the payload, as the coordinator would. */
  async function raiseRequest(overrides: Record<string, unknown>): Promise<number> {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    const raised = await raise(APPROVED_EVENT.reference, validPayload(overrides))
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.venueStaff))
    return Number(raised.id)
  }

  it('refuses an approval that overlaps an approved request at the same venue', async () => {
    const overlapping = await raiseRequest(OVERLAPPING_9001)
    await decide(WAITING_AT_ROOMY_VENUE, 'approved')

    const error = await errorOf(decide(overlapping, 'approved'))

    expect(error.status).toBe(409)
    expect(error.message).toBe(
      `Cannot approve: booking #${WAITING_AT_ROOMY_VENUE} already holds this venue during the requested period.`,
    )
  })

  it('still lets the overlapping request be rejected', async () => {
    const overlapping = await raiseRequest(OVERLAPPING_9001)
    await decide(WAITING_AT_ROOMY_VENUE, 'approved')

    const rejected = await decide(overlapping, 'rejected')

    expect(rejected.status).toBe('rejected')
  })

  it.each([
    [
      'at another venue',
      {
        venue_id: TINY_VENUE.id,
        expected_occupancy: 10,
        starts_at: '2026-11-20T09:00:00+08:00',
        ends_at: '2026-11-20T12:00:00+08:00',
      },
    ],
    [
      'ending as the approved one starts',
      { starts_at: '2026-11-20T06:00:00+08:00', ends_at: '2026-11-20T09:00:00+08:00' },
    ],
    [
      'starting as the approved one ends',
      { starts_at: '2026-11-20T12:00:00+08:00', ends_at: '2026-11-20T14:00:00+08:00' },
    ],
  ])('approves a request %s', async (_name, overrides) => {
    const clear = await raiseRequest(overrides)
    await decide(WAITING_AT_ROOMY_VENUE, 'approved')

    const approved = await decide(clear, 'approved')

    expect(approved.status).toBe('approved')
  })
})

describe('SCRUM-44 booking mock: approving a request marks the ones it clashes with', () => {
  const QUEUE_URL = '/api/venues/booking-requests'
  const WAITING_AT_ROOMY_VENUE = 9001

  type Waiting = { id: number; status: string }

  /** Raise a request at the roomy venue, overlapping or clear of the one waiting there. */
  function raiseAt(startsAt: string, endsAt: string, overrides: Record<string, unknown> = {}) {
    return raise(
      APPROVED_EVENT.reference,
      validPayload({ starts_at: startsAt, ends_at: endsAt, ...overrides }),
    )
  }

  /** Approve the request already waiting at the roomy venue, as Venue Staff, and read the queue. */
  async function approveWaitingThenReadQueue(): Promise<Waiting[]> {
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.venueStaff))
    await apiRequest(`${QUEUE_URL}/${String(WAITING_AT_ROOMY_VENUE)}/decision`, {
      method: 'POST',
      body: { outcome: 'approved' },
    })
    return apiRequest<Waiting[]>(QUEUE_URL)
  }

  function statusOf(queue: Waiting[], id: unknown): string | undefined {
    return queue.find((waiting) => waiting.id === id)?.status
  }

  it('leaves an overlapping request Pending until one of them is approved', async () => {
    const raised = await raiseAt('2026-11-20T11:00:00+08:00', '2026-11-20T14:00:00+08:00')

    expect(raised.status).toBe('pending')
  })

  it('marks an overlapping Pending request Conflicting, and keeps it in the queue', async () => {
    const overlapping = await raiseAt('2026-11-20T11:00:00+08:00', '2026-11-20T14:00:00+08:00')

    const queue = await approveWaitingThenReadQueue()

    expect(statusOf(queue, overlapping.id)).toBe('conflicting')
  })

  it('leaves a request on another day Pending', async () => {
    const otherDay = await raiseAt('2026-11-21T11:00:00+08:00', '2026-11-21T14:00:00+08:00')

    const queue = await approveWaitingThenReadQueue()

    expect(statusOf(queue, otherDay.id)).toBe('pending')
  })

  it('leaves a request at another venue Pending', async () => {
    const otherVenue = await raiseAt('2026-11-20T11:00:00+08:00', '2026-11-20T14:00:00+08:00', {
      venue_id: TINY_VENUE.id,
      expected_occupancy: 5,
    })

    const queue = await approveWaitingThenReadQueue()

    expect(statusOf(queue, otherVenue.id)).toBe('pending')
  })
})

const MULTI_VENUE_EVENT = MOCK_BOOKING_EVENTS.multiVenue
const ARRANGEMENT_NOT_FOUND = 'Venue arrangement not found.'

function arrangementUrl(reference: string, arrangementId: number): string {
  return `${bookingUrl(reference)}/${arrangementId}`
}

function withdraw(reference: string, arrangementId: number) {
  return apiRequest<Record<string, unknown>>(
    `${arrangementUrl(reference, arrangementId)}/withdraw`,
    { method: 'POST' },
  )
}

function change(reference: string, arrangementId: number, body: Record<string, unknown>) {
  return apiRequest<Record<string, unknown>>(arrangementUrl(reference, arrangementId), {
    method: 'PATCH',
    body,
  })
}

function cancelAll(reference: string) {
  return apiRequest<Record<string, unknown>[]>(`${bookingUrl(reference)}/cancel-all`, {
    method: 'POST',
  })
}

/** Each of the event's arrangements as `id status`, in the order the list answers with. */
async function statusesOf(reference: string): Promise<string[]> {
  const listed = await apiRequest<{ id: number; status: string }[]>(bookingUrl(reference))
  return listed.map((arrangement) => `${arrangement.id} ${arrangement.status}`)
}

/** Raise a pending request on the approved event and return its id. */
async function raisePending(overrides: Record<string, unknown> = {}): Promise<number> {
  const created = await raise(APPROVED_EVENT.reference, validPayload(overrides))
  return Number(created.id)
}

const {
  rejectedMain,
  withdrawnOverflow,
  rejectedBreakout,
  bookedHall,
  bookedSideRoom,
  releasedHall,
  expiredGallery,
  heldStudio,
} = MOCK_ARRANGEMENTS
const BOOKED_EVENT = MOCK_BOOKING_EVENTS.booked
const REPLACED_EVENT = MOCK_BOOKING_EVENTS.replaced
const HELD_EVENT = MOCK_BOOKING_EVENTS.held

describe('SCRUM-93 booking mock: listing an event with several arrangements', () => {
  it('lists them earliest period first, then by id, whatever order they were saved in', async () => {
    expect(await statusesOf(MULTI_VENUE_EVENT.reference)).toEqual([
      `${withdrawnOverflow.id} withdrawn`,
      `${rejectedBreakout.id} rejected`,
      `${rejectedMain.id} rejected`,
    ])
  })
})

describe('SCRUM-93 booking mock: withdrawing an arrangement', () => {
  it('withdraws a pending arrangement and leaves the event’s other one as it was', async () => {
    const first = await raisePending()
    const second = await raisePending({ venue_id: TINY_VENUE.id, expected_occupancy: 5 })

    const withdrawn = await withdraw(APPROVED_EVENT.reference, first)

    expect(withdrawn).toMatchObject({ id: first, status: 'withdrawn', purpose: 'Keynote' })
    expect(await statusesOf(APPROVED_EVENT.reference)).toEqual([
      `${first} withdrawn`,
      `${second} pending`,
    ])
  })

  it('withdraws a conflicting arrangement, as the backend does since SCRUM-44', async () => {
    const overlapping = await raisePending({
      starts_at: '2026-11-20T11:00:00+08:00',
      ends_at: '2026-11-20T14:00:00+08:00',
    })
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.venueStaff))
    await apiRequest('/api/venues/booking-requests/9001/decision', {
      method: 'POST',
      body: { outcome: 'approved' },
    })
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    expect(await statusesOf(APPROVED_EVENT.reference)).toEqual([`${overlapping} conflicting`])

    const withdrawn = await withdraw(APPROVED_EVENT.reference, overlapping)

    expect(withdrawn.status).toBe('withdrawn')
  })

  it('withdraws a rejected arrangement', async () => {
    const withdrawn = await withdraw(MULTI_VENUE_EVENT.reference, rejectedBreakout.id)

    expect(withdrawn.status).toBe('withdrawn')
  })

  it('withdraws an expired arrangement, as the backend does since SCRUM-94', async () => {
    const withdrawn = await withdraw(REPLACED_EVENT.reference, expiredGallery.id)

    expect(withdrawn.status).toBe('withdrawn')
  })

  it.each([
    [BOOKED_EVENT.reference, bookedHall.id, 'approved'],
    [MULTI_VENUE_EVENT.reference, withdrawnOverflow.id, 'withdrawn'],
    [REPLACED_EVENT.reference, releasedHall.id, 'released'],
    [HELD_EVENT.reference, heldStudio.id, 'on_hold'],
  ])(
    'refuses to withdraw on %s arrangement %i, naming its status (%s)',
    async (reference, id, status) => {
      const error = await errorOf(withdraw(reference, id))

      expect(error.status).toBe(409)
      expect(error.message).toBe(
        `Only a pending, conflicting, rejected or expired arrangement can be withdrawn; this one is ${status}.`,
      )
    },
  )

  it('answers 404 for an arrangement of another event, or one that does not exist', async () => {
    const otherEvents = await errorOf(withdraw(MULTI_VENUE_EVENT.reference, 9001))
    const missing = await errorOf(withdraw(MULTI_VENUE_EVENT.reference, 424242))

    expect([otherEvents.status, otherEvents.message]).toEqual([404, ARRANGEMENT_NOT_FOUND])
    expect([missing.status, missing.message]).toEqual([404, ARRANGEMENT_NOT_FOUND])
  })

  it('answers 404 for an event the coordinator does not coordinate', async () => {
    const error = await errorOf(withdraw(MOCK_BOOKING_EVENTS.someoneElses.reference, 9001))

    expect([error.status, error.message]).toEqual([404, 'Event request not found.'])
  })

  it('frees the venue and period, so the same request can be raised again', async () => {
    const first = await raisePending()
    await withdraw(APPROVED_EVENT.reference, first)

    const again = await raisePending()

    expect(again).not.toBe(first)
  })

  it('lets a request be raised for the slot of a rejected one: only pending ones clash', async () => {
    const sameSlot = {
      venue_id: rejectedBreakout.venue_id,
      starts_at: rejectedBreakout.starts_at,
      ends_at: rejectedBreakout.ends_at,
      purpose: 'Breakout again',
      expected_occupancy: 5,
    }

    const created = await raise(MULTI_VENUE_EVENT.reference, sameSlot)

    expect(created.status).toBe('pending')
  })
})

describe('SCRUM-93 booking mock: changing an arrangement', () => {
  it('changes only the fields sent and answers with the arrangement as it now is', async () => {
    const id = await raisePending({ required_layout: 'theatre', justification: 'Kept' })

    const changed = await change(APPROVED_EVENT.reference, id, {
      purpose: 'Opening plenary',
      expected_occupancy: 120,
    })

    expect(changed).toMatchObject({
      id,
      status: 'pending',
      purpose: 'Opening plenary',
      expected_occupancy: 120,
      required_layout: 'theatre',
      justification: 'Kept',
      venue_id: ROOMY_VENUE.id,
    })
    const listed = await apiRequest<Record<string, unknown>[]>(bookingUrl(APPROVED_EVENT.reference))
    expect(listed).toEqual([changed])
  })

  it('clears the layout when it is sent as null', async () => {
    const id = await raisePending({ required_layout: 'theatre' })

    const changed = await change(APPROVED_EVENT.reference, id, { required_layout: null })

    expect(changed.required_layout).toBeNull()
  })

  it.each([
    [BOOKED_EVENT.reference, bookedHall.id, 'approved'],
    [MULTI_VENUE_EVENT.reference, rejectedBreakout.id, 'rejected'],
    [MULTI_VENUE_EVENT.reference, withdrawnOverflow.id, 'withdrawn'],
    [REPLACED_EVENT.reference, releasedHall.id, 'released'],
    [REPLACED_EVENT.reference, expiredGallery.id, 'expired'],
    [HELD_EVENT.reference, heldStudio.id, 'on_hold'],
  ])(
    'refuses to change on %s arrangement %i, naming its status (%s)',
    async (reference, id, status) => {
      const error = await errorOf(change(reference, id, { purpose: 'New' }))

      expect(error.status).toBe(409)
      expect(error.message).toBe(
        `Only a pending arrangement can be changed; this one is ${status}.`,
      )
    },
  )

  it('asks for a justification when the changed occupancy outgrows the venue, changing nothing', async () => {
    const id = await raisePending({ venue_id: TINY_VENUE.id, expected_occupancy: 5 })

    const error = await errorOf(
      change(APPROVED_EVENT.reference, id, { purpose: 'Bigger', expected_occupancy: 50 }),
    )

    expect(error.status).toBe(400)
    expect(error.fieldErrors.justification).toEqual([
      'A justification is required because the venue is not suitable.',
    ])
    expect(await apiRequest(bookingUrl(APPROVED_EVENT.reference))).toMatchObject([
      { id, purpose: 'Keynote', expected_occupancy: 5 },
    ])
  })

  it('needs no justification for an occupancy that exactly fills the venue', async () => {
    const id = await raisePending({ venue_id: TINY_VENUE.id, expected_occupancy: 5 })

    const changed = await change(APPROVED_EVENT.reference, id, {
      expected_occupancy: TINY_VENUE.capacity,
    })

    expect(changed.expected_occupancy).toBe(TINY_VENUE.capacity)
  })

  it('judges suitability on the stored occupancy when only other fields change', async () => {
    const id = await raisePending({ venue_id: TINY_VENUE.id, expected_occupancy: 5 })

    const changed = await change(APPROVED_EVENT.reference, id, { purpose: 'Still small' })

    expect(changed.purpose).toBe('Still small')
  })

  it('accepts an outgrown venue when a justification is sent with the change', async () => {
    const id = await raisePending({ venue_id: TINY_VENUE.id, expected_occupancy: 5 })

    const changed = await change(APPROVED_EVENT.reference, id, {
      expected_occupancy: 50,
      justification: 'Standing room',
    })

    expect(changed).toMatchObject({ expected_occupancy: 50, justification: 'Standing room' })
  })

  it('accepts an outgrown venue when the arrangement already has a justification', async () => {
    const id = await raisePending({
      venue_id: TINY_VENUE.id,
      expected_occupancy: 5,
      justification: 'Only room free',
    })

    const changed = await change(APPROVED_EVENT.reference, id, { expected_occupancy: 50 })

    expect(changed.expected_occupancy).toBe(50)
  })

  it.each([
    ['purpose', { purpose: '   ' }, 'Must not be blank.'],
    ['justification', { justification: '  ' }, 'Must not be blank.'],
    [
      'expected_occupancy',
      { expected_occupancy: 0 },
      'expected_occupancy must be a positive number.',
    ],
    ['expected_occupancy', { expected_occupancy: true }, 'Not a valid integer.'],
    ['purpose', { purpose: null }, 'Field may not be null.'],
    ['justification', { justification: 7 }, 'Not a valid string.'],
    [
      'required_layout',
      { required_layout: 'cabaret' },
      'Must be one of: classroom, theatre, boardroom, banquet, exhibition, other.',
    ],
    ['venue_id', { venue_id: TINY_VENUE.id }, 'Unknown field.'],
    ['starts_at', { starts_at: '2026-11-10T10:00:00+08:00' }, 'Unknown field.'],
  ])('refuses %s in %j before looking for the event', async (field, body, message) => {
    const error = await errorOf(change('EVR-NOSUCH00', 1, body))

    expect(error.status).toBe(400)
    expect(error.fieldErrors).toEqual({ [field]: [message] })
  })

  it('accepts an occupancy of 1, the smallest it allows', async () => {
    const id = await raisePending()

    const changed = await change(APPROVED_EVENT.reference, id, { expected_occupancy: 1 })

    expect(changed.expected_occupancy).toBe(1)
  })

  it('answers 404 for an arrangement of another event', async () => {
    const error = await errorOf(change(APPROVED_EVENT.reference, bookedHall.id, { purpose: 'x' }))

    expect([error.status, error.message]).toEqual([404, ARRANGEMENT_NOT_FOUND])
  })
})

describe('SCRUM-93 booking mock: cancelling all of an event’s arrangements', () => {
  it('withdraws every pending one and answers with them, earliest period first', async () => {
    const later = await raisePending({
      starts_at: '2026-11-10T13:00:00+08:00',
      ends_at: '2026-11-10T15:00:00+08:00',
    })
    const earlier = await raisePending()

    const cancelled = await cancelAll(APPROVED_EVENT.reference)

    expect(cancelled.map((arrangement) => [arrangement.id, arrangement.status])).toEqual([
      [earlier, 'withdrawn'],
      [later, 'withdrawn'],
    ])
  })

  it('answers with an empty list when the event has nothing left to cancel', async () => {
    expect(await cancelAll(APPROVED_EVENT.reference)).toEqual([])
  })

  it('withdraws the rejected ones too, and leaves out the ones already withdrawn', async () => {
    const cancelled = await cancelAll(MULTI_VENUE_EVENT.reference)

    expect(cancelled.map((arrangement) => [arrangement.id, arrangement.status])).toEqual([
      [rejectedBreakout.id, 'withdrawn'],
      [rejectedMain.id, 'withdrawn'],
    ])
  })

  it('withdraws an expired one and leaves out a released one, as the backend does', async () => {
    const cancelled = await cancelAll(REPLACED_EVENT.reference)

    expect(cancelled.map((arrangement) => [arrangement.id, arrangement.status])).toEqual([
      [expiredGallery.id, 'withdrawn'],
    ])
    expect(await statusesOf(REPLACED_EVENT.reference)).toEqual([
      `${releasedHall.id} released`,
      `${expiredGallery.id} withdrawn`,
    ])
  })

  it('refuses while an arrangement is on hold, naming its status', async () => {
    const error = await errorOf(cancelAll(HELD_EVENT.reference))

    expect(error.status).toBe(409)
    expect(error.message).toBe(
      'Only a pending, conflicting, rejected or expired arrangement can be withdrawn; this one is on_hold.',
    )
  })

  it('refuses while an arrangement is approved, and withdraws none of the others', async () => {
    const error = await errorOf(cancelAll(BOOKED_EVENT.reference))

    expect(error.status).toBe(409)
    expect(error.message).toBe(
      'Only a pending, conflicting, rejected or expired arrangement can be withdrawn; this one is approved.',
    )
    expect(await statusesOf(BOOKED_EVENT.reference)).toEqual([
      `${bookedSideRoom.id} rejected`,
      `${bookedHall.id} approved`,
    ])
  })

  it('answers 404 for an event the coordinator does not coordinate', async () => {
    const error = await errorOf(cancelAll(MOCK_BOOKING_EVENTS.someoneElses.reference))

    expect(error.status).toBe(404)
  })
})

describe('SCRUM-93 booking mock: who may change, withdraw or cancel', () => {
  /** The backend's `requires_role(Role.EVENT_COORDINATOR)` refuses every other role with 403. */
  const NOT_COORDINATORS = Object.values(MOCK_ACCOUNTS).filter(
    (account) => account.role !== ROLE.EVENT_COORDINATOR,
  )
  const CALLS = {
    change: () => change(MULTI_VENUE_EVENT.reference, rejectedBreakout.id, { purpose: 'x' }),
    withdraw: () => withdraw(MULTI_VENUE_EVENT.reference, rejectedBreakout.id),
    'cancel all': () => cancelAll(MULTI_VENUE_EVENT.reference),
  }

  it.each(Object.entries(CALLS))('answers %s with 401 without a token', async (_name, call) => {
    sendRequestsAs(null)

    expect((await errorOf(call())).status).toBe(401)
  })

  it.each(Object.entries(CALLS))(
    'answers %s with 403 for every role but the Event Coordinator',
    async (_name, call) => {
      for (const account of NOT_COORDINATORS) {
        sendRequestsAs(mockTokenFor(account))

        const error = await errorOf(call())

        expect({ role: account.role, status: error.status }).toEqual({
          role: account.role,
          status: 403,
        })
      }
    },
  )
})
