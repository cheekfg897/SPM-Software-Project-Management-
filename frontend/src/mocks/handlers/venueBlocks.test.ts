import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import { UNAVAILABILITY_CATEGORIES } from '@/config/unavailabilityCategories'
import type { CalendarEntry, CreatedBlock, VenueBlock } from '@/features/venues/api'
import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { MOCK_VENUES } from './venueFixtures'

/**
 * The venue mock's blocks (SCRUM-34) and calendar (SCRUM-26), pinned to what
 * backend/app/modules/venue/routes.py answers: who may call each, the messages, what a block
 * cuts into (ADR-0016), and how a calendar pads bookings and words reasons per role (ADR-0011).
 */

const MARINA_HALL = MOCK_VENUES.marinaHall
const BOARDROOM_TWO = MOCK_VENUES.boardroomTwo
const UNKNOWN_VENUE_ID = 4242

const ACCOUNT_BY_ROLE: Record<Role, MockAccount> = {
  [ROLE.ATTENDEE]: MOCK_ACCOUNTS.attendee,
  [ROLE.EVENT_ORGANISER]: MOCK_ACCOUNTS.organiser,
  [ROLE.EVENT_COORDINATOR]: MOCK_ACCOUNTS.coordinator,
  [ROLE.EVENT_COORDINATOR_LEAD]: MOCK_ACCOUNTS.lead,
  [ROLE.VENUE_STAFF]: MOCK_ACCOUNTS.venueStaff,
  [ROLE.TECHNICAL_SUPPORT_STAFF]: MOCK_ACCOUNTS.technicalSupport,
  [ROLE.SAFETY_OFFICER]: MOCK_ACCOUNTS.safetyOfficer,
}
const STAFF_ROLES: Role[] = [
  ROLE.EVENT_COORDINATOR,
  ROLE.EVENT_COORDINATOR_LEAD,
  ROLE.VENUE_STAFF,
  ROLE.TECHNICAL_SUPPORT_STAFF,
  ROLE.SAFETY_OFFICER,
]
const EXTERNAL_ROLES: Role[] = Object.values(ROLE).filter((role) => !STAFF_ROLES.includes(role))
const NOT_VENUE_STAFF: Role[] = Object.values(ROLE).filter((role) => role !== ROLE.VENUE_STAFF)

/** A block on 10 Nov, 11:00 to 14:00, cutting into Marina Hall's two confirmed bookings. */
const MIDDAY_BLOCK = {
  start_time: '2026-11-10T11:00',
  end_time: '2026-11-10T14:00',
  category: 'safety_concern',
  reason: '  Fire alarm test  ',
}
const CATEGORY_UNKNOWN_MESSAGE =
  'Category must be one of maintenance, equipment_failure, renovation, safety_concern or other.'

function signInAs(role: Role) {
  sendRequestsAs(mockTokenFor(ACCOUNT_BY_ROLE[role]))
}

function blocksUrl(venueId: number): string {
  return `/api/venues/${venueId}/blocks`
}

function block(venueId: number, body: unknown) {
  return apiRequest<CreatedBlock>(blocksUrl(venueId), { method: 'POST', body })
}

function listBlocks(venueId: number) {
  return apiRequest<VenueBlock[]>(blocksUrl(venueId))
}

function removeBlock(venueId: number, blockId: number) {
  return apiRequest<null>(`${blocksUrl(venueId)}/${blockId}`, { method: 'DELETE' })
}

function calendar(venueId: number, query: Record<string, string>) {
  return apiRequest<CalendarEntry[]>(`/api/venues/${venueId}/calendar`, { query })
}

/** Marina Hall on 10 Nov, the whole business day. */
const TEN_NOVEMBER = { range_start: '2026-11-10T00:00:00', range_end: '2026-11-11T00:00:00' }

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

describe('SCRUM-34 venue mock: blocking a venue', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it('saves the block in business time with its reason trimmed, listing the confirmed bookings it cuts into', async () => {
    const created = await block(MARINA_HALL.id, MIDDAY_BLOCK)

    expect(created).toMatchObject({
      venue_id: MARINA_HALL.id,
      start_time: '2026-11-10T11:00:00+08:00',
      end_time: '2026-11-10T14:00:00+08:00',
      category: 'safety_concern',
      reason: 'Fire alarm test',
    })
    expect(created.conflicting_bookings).toEqual([
      {
        booking_id: 512,
        event_id: 101,
        start_time: '2026-11-10T08:30:00+08:00',
        end_time: '2026-11-10T12:30:00+08:00',
      },
      {
        booking_id: 511,
        event_id: 105,
        start_time: '2026-11-10T12:30:00+08:00',
        end_time: '2026-11-10T17:30:00+08:00',
      },
    ])
  })

  it('counts a block over only a booking’s setup as cutting into it, and one that only touches as not', async () => {
    const intoSetup = await block(MARINA_HALL.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-11-10T08:00',
      end_time: '2026-11-10T08:31',
    })
    const touching = await block(MARINA_HALL.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-11-10T07:00',
      end_time: '2026-11-10T08:30',
    })

    expect(intoSetup.conflicting_bookings.map((conflict) => conflict.booking_id)).toEqual([512])
    expect(touching.conflicting_bookings).toEqual([])
  })

  it('lists the venue’s blocks in start order, the new one among them', async () => {
    const created = await block(MARINA_HALL.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-11-09T10:00',
      end_time: '2026-11-09T11:00',
    })

    const blocks = await listBlocks(MARINA_HALL.id)

    expect(blocks.map((each) => each.id)).toEqual([created.id, 71])
    expect(await listBlocks(BOARDROOM_TWO.id)).toEqual([
      expect.objectContaining({
        id: 72,
        category: 'maintenance',
        reason: 'Carpet cleaning',
      }) as unknown,
    ])
  })

  it.each(UNAVAILABILITY_CATEGORIES)('saves a block for $label', async ({ value }) => {
    const created = await block(MARINA_HALL.id, { ...MIDDAY_BLOCK, category: value })

    expect(created.category).toBe(value)
    const listed = await listBlocks(MARINA_HALL.id)
    expect(listed.find((each) => each.id === created.id)?.category).toBe(value)
  })

  it.each([
    [
      'nothing',
      {},
      {
        start_time: ['Missing data for required field.'],
        end_time: ['Missing data for required field.'],
        category: ['Missing data for required field.'],
        reason: ['Missing data for required field.'],
      },
    ],
    [
      'a category it does not know',
      { ...MIDDAY_BLOCK, category: 'flood' },
      { category: [CATEGORY_UNKNOWN_MESSAGE] },
    ],
    [
      'a category as its label',
      { ...MIDDAY_BLOCK, category: 'Maintenance' },
      { category: [CATEGORY_UNKNOWN_MESSAGE] },
    ],
    [
      'an empty category',
      { ...MIDDAY_BLOCK, category: '' },
      { category: [CATEGORY_UNKNOWN_MESSAGE] },
    ],
    [
      'a null category',
      { ...MIDDAY_BLOCK, category: null },
      { category: ['Field may not be null.'] },
    ],
    [
      'an unknown category with an end before the start, the field first',
      { ...MIDDAY_BLOCK, category: 'flood', end_time: '2026-11-10T10:00' },
      { category: [CATEGORY_UNKNOWN_MESSAGE] },
    ],
    [
      'a field it does not know',
      { ...MIDDAY_BLOCK, colour: 'red' },
      { colour: ['Unknown field.'] },
    ],
    ['a null reason', { ...MIDDAY_BLOCK, reason: null }, { reason: ['Field may not be null.'] }],
    [
      'a null start',
      { ...MIDDAY_BLOCK, start_time: null },
      { start_time: ['Field may not be null.'] },
    ],
    ['a blank reason', { ...MIDDAY_BLOCK, reason: '   ' }, { reason: ['Must not be blank.'] }],
    [
      'a reason too long once trimmed',
      { ...MIDDAY_BLOCK, reason: `${'r'.repeat(501)}` },
      { reason: ['Reason must be at most 500 characters.'] },
    ],
    [
      'a start that is not a time',
      { ...MIDDAY_BLOCK, start_time: 'soon' },
      { start_time: ['Not a valid datetime.'] },
    ],
    [
      'a start a browser could read but that is not ISO 8601',
      { ...MIDDAY_BLOCK, start_time: '11/10/2026 11:00' },
      { start_time: ['Not a valid datetime.'] },
    ],
    [
      'a start shaped like a time but on no real day',
      { ...MIDDAY_BLOCK, start_time: '2026-13-10T11:00' },
      { start_time: ['Not a valid datetime.'] },
    ],
    [
      'a reason that is not text',
      { ...MIDDAY_BLOCK, reason: 12 },
      { reason: ['Not a valid string.'] },
    ],
    [
      'an end before the start',
      { ...MIDDAY_BLOCK, end_time: '2026-11-10T10:59' },
      { end_time: ['end_time must be after start_time.'] },
    ],
    [
      'an end at the start',
      { ...MIDDAY_BLOCK, end_time: '2026-11-10T11:00' },
      { end_time: ['end_time must be after start_time.'] },
    ],
    [
      'an end before today',
      { ...MIDDAY_BLOCK, start_time: '2026-10-01T09:00', end_time: '2026-10-04T23:59' },
      { end_time: ['Block cannot end before today.'] },
    ],
  ])('refuses %s', async (_name, body, expected) => {
    const error = await errorOf(block(MARINA_HALL.id, body))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual(expected)
  })

  it('accepts a 500-character reason with spaces round it, a block from the past that ends today, and an offset', async () => {
    const longest = await block(MARINA_HALL.id, { ...MIDDAY_BLOCK, reason: ` ${'r'.repeat(500)} ` })
    const endsToday = await block(MARINA_HALL.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-10-01T09:00',
      end_time: '2026-10-05T00:00',
    })
    const withOffset = await block(MARINA_HALL.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-11-12T01:00:00Z',
      end_time: '2026-11-12T02:00:00Z',
    })

    expect(longest.reason).toHaveLength(500)
    expect(endsToday.end_time).toBe('2026-10-05T00:00:00+08:00')
    expect(withOffset.start_time).toBe('2026-11-12T09:00:00+08:00')
  })

  it('checks the body before looking for the venue, then answers 404 for one that does not exist', async () => {
    const refused = await errorOf(block(UNKNOWN_VENUE_ID, {}))
    const missing = await errorOf(block(UNKNOWN_VENUE_ID, MIDDAY_BLOCK))

    expect(refused.status).toBe(400)
    expect(missing).toMatchObject({ status: 404, message: 'Venue not found.' })
  })
})

describe('SCRUM-34 venue mock: removing a block (AC4)', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it('removes the block, which leaves the list and the calendar', async () => {
    await removeBlock(MARINA_HALL.id, 71)

    expect(await listBlocks(MARINA_HALL.id)).toEqual([])
    const entries = await calendar(MARINA_HALL.id, TEN_NOVEMBER)
    expect(entries.map((entry) => entry.kind)).not.toContain('block')
  })

  it('removes only the block asked for when two were added', async () => {
    const first = await block(MARINA_HALL.id, MIDDAY_BLOCK)
    const second = await block(MARINA_HALL.id, { ...MIDDAY_BLOCK, reason: 'Second' })

    await removeBlock(MARINA_HALL.id, first.id)

    expect((await listBlocks(MARINA_HALL.id)).map((each) => each.reason)).toEqual([
      'Second',
      'Stage lighting repair',
    ])
    expect(second.id).not.toBe(first.id)
  })

  it('answers 404 for a block on another venue, and leaves it there', async () => {
    const error = await errorOf(removeBlock(MARINA_HALL.id, 72))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Block not found.' })
    expect((await listBlocks(BOARDROOM_TWO.id)).map((each) => each.id)).toEqual([72])
  })

  it('answers 404 for a venue that does not exist', async () => {
    const error = await errorOf(removeBlock(UNKNOWN_VENUE_ID, 71))

    expect(error).toMatchObject({ status: 404, message: 'Venue not found.' })
  })
})

describe('SCRUM-34 venue mock: only Venue Staff see and change blocks', () => {
  const blockActions: [string, () => Promise<unknown>][] = [
    ['block', () => block(MARINA_HALL.id, MIDDAY_BLOCK)],
    ['list blocks', () => listBlocks(MARINA_HALL.id)],
    ['remove a block', () => removeBlock(MARINA_HALL.id, 71)],
  ]

  it.each(blockActions)('refuses every other role to %s (403)', async (_name, act) => {
    for (const role of NOT_VENUE_STAFF) {
      signInAs(role)

      const error = await errorOf(act())

      expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
    }
  })

  it.each(blockActions)('refuses to %s without a token (401)', async (_name, act) => {
    const error = await errorOf(act())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })
})

describe('SCRUM-26 venue mock: which bookings still hold the venue (SCRUM-75, SCRUM-44)', () => {
  /** Marina Hall on 14 Nov, where a Conflicting booking and two holds sit. */
  const FOURTEEN_NOVEMBER = { range_start: '2026-11-14T00:00:00', range_end: '2026-11-15T00:00:00' }
  /** When the earlier of the two holds on 14 Nov expires. */
  const HOLD_EXPIRY = Date.parse('2026-11-01T09:00:00+08:00')

  beforeEach(() => signInAs(ROLE.VENUE_STAFF))
  afterEach(() => vi.useRealTimers())

  function kindsOn14November() {
    return calendar(MARINA_HALL.id, FOURTEEN_NOVEMBER).then((entries) =>
      entries.map((entry) => [entry.kind, entry.event_start]),
    )
  }

  it('shows a Conflicting booking as the confirmed booking it is, and a hold until it expires', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(HOLD_EXPIRY - 1)

    expect(await kindsOn14November()).toEqual([
      ['confirmed_booking', '2026-11-14T10:00:00+08:00'],
      ['tentative_hold', '2026-11-14T13:00:00+08:00'],
      ['tentative_hold', '2026-11-14T15:00:00+08:00'],
    ])
  })

  it('leaves out a hold from the moment it expires, keeping one that expires later', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(HOLD_EXPIRY)

    expect(await kindsOn14November()).toEqual([
      ['confirmed_booking', '2026-11-14T10:00:00+08:00'],
      ['tentative_hold', '2026-11-14T15:00:00+08:00'],
    ])
  })

  it('lists a Conflicting booking a block cuts into, as the confirmed bookings are', async () => {
    const created = await block(MARINA_HALL.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-11-14T10:30',
      end_time: '2026-11-14T15:30',
    })

    expect(created.conflicting_bookings.map((conflict) => conflict.booking_id)).toEqual([531])
  })
})

describe('SCRUM-26 venue mock: the calendar', () => {
  it('lists bookings padded by setup and turnaround with their event times, and blocks, in time order, as Venue Staff see them', async () => {
    signInAs(ROLE.VENUE_STAFF)

    const entries = await calendar(MARINA_HALL.id, TEN_NOVEMBER)

    expect(entries).toEqual([
      {
        start_time: '2026-11-10T08:30:00+08:00',
        end_time: '2026-11-10T12:30:00+08:00',
        event_start: '2026-11-10T09:00:00+08:00',
        event_end: '2026-11-10T12:00:00+08:00',
        kind: 'confirmed_booking',
        reason: 'Event #101',
      },
      {
        start_time: '2026-11-10T11:30:00+08:00',
        end_time: '2026-11-10T13:30:00+08:00',
        event_start: '2026-11-10T12:00:00+08:00',
        event_end: '2026-11-10T13:00:00+08:00',
        kind: 'tentative_hold',
        reason: 'Event #104',
      },
      {
        start_time: '2026-11-10T12:30:00+08:00',
        end_time: '2026-11-10T17:30:00+08:00',
        event_start: '2026-11-10T13:00:00+08:00',
        event_end: '2026-11-10T17:00:00+08:00',
        kind: 'confirmed_booking',
        reason: 'Event #105',
      },
      {
        start_time: '2026-11-10T17:30:00+08:00',
        end_time: '2026-11-10T20:00:00+08:00',
        event_start: null,
        event_end: null,
        kind: 'block',
        reason: 'Stage lighting repair',
      },
    ])
  })

  it.each(STAFF_ROLES.filter((role) => role !== ROLE.VENUE_STAFF))(
    'tells %s only that a period is a booking or maintenance (AC3)',
    async (role) => {
      signInAs(role)

      const entries = await calendar(MARINA_HALL.id, TEN_NOVEMBER)

      expect(entries.map((entry) => entry.reason)).toEqual([
        'booking',
        'booking',
        'booking',
        'maintenance',
      ])
    },
  )

  it('names a booking with no event as such for Venue Staff', async () => {
    signInAs(ROLE.VENUE_STAFF)

    const entries = await calendar(BOARDROOM_TWO.id, TEN_NOVEMBER)

    expect(entries.map((entry) => entry.reason)).toEqual([
      'Booking (no linked event)',
      'Event #102',
      'Carpet cleaning',
    ])
  })

  it('finds a booking whose padding alone reaches into the range, and leaves out one that only touches it', async () => {
    signInAs(ROLE.VENUE_STAFF)

    const intoPadding = await calendar(MARINA_HALL.id, {
      range_start: '2026-11-10T17:15:00',
      range_end: '2026-11-10T17:29:00',
    })
    const touching = await calendar(MARINA_HALL.id, {
      range_start: '2026-11-10T20:00:00',
      range_end: '2026-11-10T21:00:00',
    })

    expect(intoPadding.map((entry) => entry.reason)).toEqual(['Event #105'])
    expect(touching).toEqual([])
  })

  it.each(EXTERNAL_ROLES)('refuses %s (403, AC4)', async (role) => {
    signInAs(role)

    const error = await errorOf(calendar(MARINA_HALL.id, TEN_NOVEMBER))

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('refuses without a token (401)', async () => {
    const error = await errorOf(calendar(MARINA_HALL.id, TEN_NOVEMBER))

    expect(error).toMatchObject({ status: 401 })
  })

  it.each([
    [
      'no range',
      {},
      {
        range_start: ['Missing data for required field.'],
        range_end: ['Missing data for required field.'],
      },
    ],
    [
      'a start that is not a time',
      { ...TEN_NOVEMBER, range_start: 'T00:00:00' },
      { range_start: ['Not a valid datetime.'] },
    ],
    [
      'an end at the start',
      { ...TEN_NOVEMBER, range_end: TEN_NOVEMBER.range_start },
      { range_end: ['range_end must be after range_start.'] },
    ],
    [
      'a parameter it does not know',
      { ...TEN_NOVEMBER, venue: '1' },
      { venue: ['Unknown field.'] },
    ],
  ])('refuses %s', async (_name, query, expected) => {
    signInAs(ROLE.EVENT_COORDINATOR)

    const error = await errorOf(calendar(MARINA_HALL.id, query))

    expect(error.fieldErrors).toEqual(expected)
  })

  it('checks the range before looking for the venue, then answers 404', async () => {
    signInAs(ROLE.EVENT_COORDINATOR)

    const refused = await errorOf(calendar(UNKNOWN_VENUE_ID, {}))
    const missing = await errorOf(calendar(UNKNOWN_VENUE_ID, TEN_NOVEMBER))

    expect(refused.status).toBe(400)
    expect(missing).toMatchObject({ status: 404, message: 'Venue not found.' })
  })

  it('shows a new block, and pads by a changed turnaround', async () => {
    signInAs(ROLE.VENUE_STAFF)
    await block(BOARDROOM_TWO.id, {
      ...MIDDAY_BLOCK,
      start_time: '2026-11-10T18:00',
      end_time: '2026-11-10T19:00',
    })
    await apiRequest(`/api/venues/${BOARDROOM_TWO.id}`, {
      method: 'PATCH',
      body: { turnaround_minutes: 60 },
    })

    const entries = await calendar(BOARDROOM_TWO.id, TEN_NOVEMBER)

    expect(entries.map((entry) => [entry.kind, entry.end_time])).toEqual([
      ['confirmed_booking', '2026-11-10T13:00:00+08:00'],
      ['confirmed_booking', '2026-11-10T15:00:00+08:00'],
      ['block', '2026-11-10T16:00:00+08:00'],
      ['block', '2026-11-10T19:00:00+08:00'],
    ])
  })
})
