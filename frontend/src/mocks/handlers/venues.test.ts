import { ROLE } from '@/config/roles'
import type { Role } from '@/config/roles'
import type { UpdatedVenue, Venue } from '@/features/venues/api'
import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { MOCK_VENUES } from './venueFixtures'

/**
 * The venue mock stands in for the catalogue routes in backend/app/modules/venue/routes.py
 * (SCRUM-25, SCRUM-67), so these tests pin it to what the backend answers: who may call each
 * route, its validation messages, its order, and what a buffer change reports (ADR-0033).
 */

const MARINA_HALL = MOCK_VENUES.marinaHall
const BOARDROOM_TWO = MOCK_VENUES.boardroomTwo
const ANNEXE_STUDIO = MOCK_VENUES.annexeStudio
/** An id no fixture uses. */
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
const NOT_VENUE_STAFF: Role[] = Object.values(ROLE).filter((role) => role !== ROLE.VENUE_STAFF)

function venueUrl(venueId: number): string {
  return `/api/venues/${venueId}`
}

function signInAs(role: Role) {
  sendRequestsAs(mockTokenFor(ACCOUNT_BY_ROLE[role]))
}

function newVenue(overrides: Record<string, unknown> = {}) {
  return { name: 'Skyline Room', location: 'Level 9', capacity: 64, ...overrides }
}

function create(body: unknown) {
  return apiRequest<Venue>('/api/venues', { method: 'POST', body })
}

function change(venueId: number, body: unknown) {
  return apiRequest<UpdatedVenue>(venueUrl(venueId), { method: 'PATCH', body })
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

/** The writes only Venue Staff may make, each on a venue that exists. */
const STAFF_WRITES: [string, () => Promise<unknown>][] = [
  ['create', () => create(newVenue())],
  ['change', () => change(MARINA_HALL.id, { name: 'Renamed' })],
  ['deactivate', () => apiRequest(`${venueUrl(MARINA_HALL.id)}/deactivate`, { method: 'POST' })],
  ['reactivate', () => apiRequest(`${venueUrl(ANNEXE_STUDIO.id)}/reactivate`, { method: 'POST' })],
]

describe('SCRUM-25 venue mock: reading', () => {
  it('lists the active venues by name, leaving the deactivated one out', async () => {
    signInAs(ROLE.EVENT_COORDINATOR)

    const venues = await apiRequest<Venue[]>('/api/venues')

    expect(venues.map((venue) => venue.name)).toEqual([
      'Boardroom Two',
      'Garden Pavilion',
      'Marina Hall',
    ])
  })

  it('lets any signed-in role read the list and a venue', async () => {
    for (const role of Object.values(ROLE)) {
      signInAs(role)

      await expect(apiRequest<Venue[]>('/api/venues')).resolves.toHaveLength(3)
      await expect(apiRequest<Venue>(venueUrl(BOARDROOM_TWO.id))).resolves.toMatchObject({
        name: 'Boardroom Two',
      })
    }
  })

  it('refuses reading without a token (401)', async () => {
    for (const read of [() => apiRequest('/api/venues'), () => apiRequest(venueUrl(2))]) {
      const error = await errorOf(read())

      expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
    }
  })

  it('opens a deactivated venue by its id', async () => {
    signInAs(ROLE.VENUE_STAFF)

    const venue = await apiRequest<Venue>(venueUrl(ANNEXE_STUDIO.id))

    expect(venue).toEqual(ANNEXE_STUDIO)
  })

  it('answers 404 for a venue that does not exist', async () => {
    signInAs(ROLE.VENUE_STAFF)

    const error = await errorOf(apiRequest(venueUrl(UNKNOWN_VENUE_ID)))

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: 'Venue not found.' })
  })
})

describe('SCRUM-25 venue mock: only Venue Staff write', () => {
  it.each(STAFF_WRITES)('refuses every other role to %s (403)', async (_name, write) => {
    for (const role of NOT_VENUE_STAFF) {
      signInAs(role)

      const error = await errorOf(write())

      expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
    }
  })

  it.each(STAFF_WRITES)('refuses to %s without a token (401)', async (_name, write) => {
    const error = await errorOf(write())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.each([
    ['change', () => change(UNKNOWN_VENUE_ID, { name: 'Renamed' })],
    [
      'deactivate',
      () => apiRequest(`${venueUrl(UNKNOWN_VENUE_ID)}/deactivate`, { method: 'POST' }),
    ],
    [
      'reactivate',
      () => apiRequest(`${venueUrl(UNKNOWN_VENUE_ID)}/reactivate`, { method: 'POST' }),
    ],
  ])('answers 404 to %s a venue that does not exist', async (_name, write) => {
    signInAs(ROLE.VENUE_STAFF)

    const error = await errorOf(write())

    expect(error).toMatchObject({ status: 404, message: 'Venue not found.' })
  })
})

describe('SCRUM-25 venue mock: creating', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it('saves a trimmed venue with lower-case items, the standard times and hours, and lists it', async () => {
    const created = await create(
      newVenue({
        name: '  Skyline Room ',
        location: ' Level 9 ',
        facilities: [' Projector ', 'Stage'],
        accessibility_features: ['Hearing Loop'],
        supported_layouts: ['boardroom'],
      }),
    )

    expect(created).toMatchObject({
      name: 'Skyline Room',
      location: 'Level 9',
      capacity: 64,
      facilities: ['projector', 'stage'],
      accessibility_features: ['hearing loop'],
      supported_layouts: ['boardroom'],
      setup_minutes: 30,
      turnaround_minutes: 30,
      is_active: true,
    })
    expect(created.opening_hours).toHaveLength(7)
    expect(created.opening_hours[6]).toEqual({
      open: { day: 'sunday', time: '09:00' },
      close: { day: 'sunday', time: '18:00' },
    })
    const listed = await apiRequest<Venue[]>('/api/venues')
    expect(listed.map((venue) => venue.name)).toContain('Skyline Room')
    await expect(apiRequest<Venue>(venueUrl(created.id))).resolves.toEqual(created)
  })

  it('keeps the times and hours it is sent, hours in week order', async () => {
    const created = await create(
      newVenue({
        setup_minutes: 0,
        turnaround_minutes: 75,
        opening_hours: [
          { open: { day: 'friday', time: '09:00' }, close: { day: 'friday', time: '12:00' } },
          { open: { day: 'monday', time: '18:00' }, close: { day: 'monday', time: '20:00' } },
          { open: { day: 'monday', time: '09:00' }, close: { day: 'monday', time: '12:00' } },
        ],
      }),
    )

    expect(created).toMatchObject({ setup_minutes: 0, turnaround_minutes: 75 })
    expect(created.opening_hours.map(({ open }) => `${open.day} ${open.time}`)).toEqual([
      'monday 09:00',
      'monday 18:00',
      'friday 09:00',
    ])
  })

  it('names each required field left out', async () => {
    const error = await errorOf(create({}))

    expect(error.fieldErrors).toEqual({
      name: ['Missing data for required field.'],
      location: ['Missing data for required field.'],
      capacity: ['Missing data for required field.'],
    })
  })

  it('refuses a body that is not an object', async () => {
    const error = await errorOf(create(['Skyline Room']))

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Request body must be a JSON object.',
    })
  })
})

describe('SCRUM-25 venue mock: each field as the backend checks it', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it.each([
    ['a blank name', { name: '   ' }, { name: ['Must not be blank.'] }],
    [
      'a name too long',
      { name: 'n'.repeat(201) },
      { name: ['Name must be at most 200 characters.'] },
    ],
    ['a name that is not text', { name: 7 }, { name: ['Not a valid string.'] }],
    ['a name that is true', { name: true }, { name: ['Not a valid string.'] }],
    ['an empty name', { name: null }, { name: ['Field may not be null.'] }],
    ['a blank location', { location: '' }, { location: ['Must not be blank.'] }],
    [
      'a location too long',
      { location: 'l'.repeat(201) },
      { location: ['Location must be at most 200 characters.'] },
    ],
    ['a capacity of 0', { capacity: 0 }, { capacity: ['Capacity must be a positive number.'] }],
    ['an empty capacity', { capacity: null }, { capacity: ['Field may not be null.'] }],
    ['a fractional capacity', { capacity: 1.5 }, { capacity: ['Not a valid integer.'] }],
    ['a capacity as text', { capacity: '12' }, { capacity: ['Not a valid integer.'] }],
    [
      'a negative setup time',
      { setup_minutes: -1 },
      { setup_minutes: ['Setup time cannot be negative.'] },
    ],
    [
      'a negative turnaround time',
      { turnaround_minutes: -5 },
      { turnaround_minutes: ['Turnaround time cannot be negative.'] },
    ],
    [
      'a blank facility',
      { facilities: ['stage', ' '] },
      { 'facilities.1': ['Items cannot be blank.'] },
    ],
    [
      'an item with a comma',
      { accessibility_features: ['ramps, lifts'] },
      { 'accessibility_features.0': ['Items cannot contain ",".'] },
    ],
    [
      'an item too long',
      { facilities: ['f'.repeat(51)] },
      { 'facilities.0': ['Items must be at most 50 characters.'] },
    ],
    ['an item that is not text', { facilities: [3] }, { 'facilities.0': ['Not a valid string.'] }],
    [
      'ten items',
      { facilities: Array.from({ length: 10 }, (_, index) => `item ${index}`) },
      { facilities: ['At most 9 items are allowed.'] },
    ],
    [
      'ten items, one of them blank, naming only the blank one',
      { facilities: [...Array.from({ length: 9 }, (_, index) => `item ${index}`), ''] },
      { 'facilities.9': ['Items cannot be blank.'] },
    ],
    ['a list that is not one', { facilities: 'stage' }, { facilities: ['Not a valid list.'] }],
    [
      'a layout the backend does not know',
      { supported_layouts: ['cabaret'] },
      {
        'supported_layouts.0': [
          'Must be one of: classroom, theatre, boardroom, banquet, exhibition, other.',
        ],
      },
    ],
    [
      'seven layouts',
      {
        supported_layouts: [
          'classroom',
          'theatre',
          'boardroom',
          'banquet',
          'exhibition',
          'other',
          'other',
        ],
      },
      { supported_layouts: ['At most 6 layouts are allowed.'] },
    ],
    ['an unknown field', { is_active: false }, { is_active: ['Unknown field.'] }],
  ])('refuses %s', async (_name, fields, expected) => {
    const error = await errorOf(create(newVenue(fields)))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual(expected)
  })

  it('accepts the longest name, location and item, nine items and every layout', async () => {
    const created = await create(
      newVenue({
        name: 'n'.repeat(200),
        location: 'l'.repeat(200),
        capacity: 1,
        setup_minutes: 0,
        turnaround_minutes: 0,
        facilities: ['f'.repeat(50), ...Array.from({ length: 8 }, (_, index) => `item ${index}`)],
        supported_layouts: ['classroom', 'theatre', 'boardroom', 'banquet', 'exhibition', 'other'],
      }),
    )

    expect(created.facilities).toHaveLength(9)
    expect(created.supported_layouts).toHaveLength(6)
  })
})

function hours(...periods: [string, string, string, string][]) {
  return {
    opening_hours: periods.map(([openDay, openTime, closeDay, closeTime]) => ({
      open: { day: openDay, time: openTime },
      close: { day: closeDay, time: closeTime },
    })),
  }
}

describe('SCRUM-25 venue mock: opening hours (ADR-0008)', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it.each([
    [
      'a close time before the open time',
      hours(['monday', '18:00', 'monday', '09:00']),
      {
        'opening_hours.0.close': [
          'Close time must be after open time. For hours past midnight, set the close day to the next day.',
        ],
      },
    ],
    [
      'a period that closes when it opens',
      hours(['monday', '09:00', 'monday', '09:00']),
      {
        'opening_hours.0.close': [
          'Close time must be after open time. For hours past midnight, set the close day to the next day.',
        ],
      },
    ],
    [
      'a period longer than 24 hours',
      hours(['friday', '18:00', 'saturday', '18:01']),
      { 'opening_hours.0.close': ['An opening period cannot be longer than 24 hours.'] },
    ],
    [
      'a close day two days on',
      hours(['monday', '09:00', 'wednesday', '09:00']),
      {
        'opening_hours.0.close': [
          'Close day must be the same day as the open day or the day after.',
        ],
      },
    ],
    [
      'an empty time',
      hours(['monday', '', 'monday', '25:00']),
      {
        'opening_hours.0.open.time': ['Not a valid time.'],
        'opening_hours.0.close.time': ['Not a valid time.'],
      },
    ],
    [
      'the hour 24, a minute of 60 and a time with no hour',
      hours(['monday', '24:00', 'monday', '09:60'], ['tuesday', ':30', 'tuesday', '10:00']),
      {
        'opening_hours.0.open.time': ['Not a valid time.'],
        'opening_hours.0.close.time': ['Not a valid time.'],
        'opening_hours.1.open.time': ['Not a valid time.'],
      },
    ],
    [
      'a bad period without looking for overlaps among the others',
      hours(
        ['monday', '09:00', 'monday', '12:00'],
        ['monday', '11:00', 'monday', '13:00'],
        ['friday', '10:00', 'friday', '09:00'],
      ),
      {
        'opening_hours.2.close': [
          'Close time must be after open time. For hours past midnight, set the close day to the next day.',
        ],
      },
    ],
    [
      'a day the backend does not know',
      hours(['funday', '09:00', 'monday', '10:00']),
      {
        'opening_hours.0.open.day': [
          'Must be one of: monday, tuesday, wednesday, thursday, friday, saturday, sunday.',
        ],
      },
    ],
    [
      'two periods that overlap, naming the later by its position from 0',
      hours(
        ['tuesday', '09:00', 'tuesday', '12:00'],
        ['monday', '09:00', 'monday', '10:00'],
        ['tuesday', '11:59', 'tuesday', '13:00'],
      ),
      { 'opening_hours.2': ['Overlaps opening period 0.'] },
    ],
    [
      'a Sunday night period running into Monday morning',
      hours(['monday', '01:00', 'monday', '05:00'], ['sunday', '22:00', 'monday', '02:00']),
      { 'opening_hours.1': ['Overlaps opening period 0.'] },
    ],
    [
      'hours that are not a list',
      { opening_hours: 'always' },
      { opening_hours: ['Not a valid list.'] },
    ],
  ])('refuses %s', async (_name, fields, expected) => {
    const error = await errorOf(create(newVenue(fields)))

    expect(error.fieldErrors).toEqual(expected)
  })

  it.each([
    [
      'periods that only touch',
      hours(['monday', '09:00', 'monday', '12:00'], ['monday', '12:00', 'monday', '18:00']),
    ],
    ['an overnight period', hours(['friday', '18:00', 'saturday', '02:00'])],
    ['a whole day', hours(['monday', '00:00', 'tuesday', '00:00'])],
    ['the last minute of a day', hours(['monday', '9:00', 'monday', '23:59'])],
    [
      'Sunday into Monday',
      hours(['sunday', '22:00', 'monday', '02:00'], ['monday', '02:00', 'monday', '05:00']),
    ],
    ['no hours at all', { opening_hours: [] }],
  ])('accepts %s', async (_name, fields) => {
    const created = await create(newVenue(fields))

    expect(created.opening_hours).toHaveLength(fields.opening_hours.length)
  })
})

describe('SCRUM-25 venue mock: changing, deactivating and reactivating', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it('changes only the fields it is sent and reports nothing when the times stay', async () => {
    const changed = await change(BOARDROOM_TWO.id, { capacity: 24, facilities: ['Whiteboard'] })

    expect(changed).toEqual({
      ...BOARDROOM_TWO,
      capacity: 24,
      facilities: ['whiteboard'],
      overlap_warnings: [],
      block_overlap_warnings: [],
    })
    await expect(apiRequest(venueUrl(BOARDROOM_TWO.id))).resolves.toMatchObject({ capacity: 24 })
  })

  it('checks the body before looking for the venue', async () => {
    const error = await errorOf(change(UNKNOWN_VENUE_ID, { capacity: 0 }))

    expect(error).toMatchObject({ status: 400 })
    expect(error.fieldErrors).toEqual({ capacity: ['Capacity must be a positive number.'] })
  })

  it('does not ask a change for the required fields', async () => {
    const changed = await change(MARINA_HALL.id, { location: 'Level 2' })

    expect(changed).toMatchObject({ name: 'Marina Hall', location: 'Level 2', capacity: 200 })
  })

  it('takes a venue out of the list on deactivating and back on reactivating', async () => {
    const deactivated = await apiRequest<Venue>(`${venueUrl(MARINA_HALL.id)}/deactivate`, {
      method: 'POST',
    })
    const listedWhileOff = await apiRequest<Venue[]>('/api/venues')
    const reactivated = await apiRequest<Venue>(`${venueUrl(MARINA_HALL.id)}/reactivate`, {
      method: 'POST',
    })
    const listedAgain = await apiRequest<Venue[]>('/api/venues')

    expect(deactivated).toEqual({ ...MARINA_HALL, is_active: false })
    expect(listedWhileOff.map((venue) => venue.id)).not.toContain(MARINA_HALL.id)
    expect(reactivated).toEqual(MARINA_HALL)
    expect(listedAgain.map((venue) => venue.id)).toContain(MARINA_HALL.id)
  })
})

describe('SCRUM-67 venue mock: a buffer change reports what now overlaps (ADR-0033)', () => {
  beforeEach(() => signInAs(ROLE.VENUE_STAFF))

  it('reports the confirmed bookings that now overlap each other and a block, earliest first', async () => {
    const changed = await change(MARINA_HALL.id, { turnaround_minutes: 45 })

    expect(changed.turnaround_minutes).toBe(45)
    expect(changed.overlap_warnings).toEqual([
      {
        booking_ids: [512, 511],
        overlap_start: '2026-11-10T12:30:00+08:00',
        overlap_end: '2026-11-10T12:45:00+08:00',
      },
    ])
    expect(changed.block_overlap_warnings).toEqual([
      {
        booking_id: 511,
        block_id: 71,
        overlap_start: '2026-11-10T17:30:00+08:00',
        overlap_end: '2026-11-10T17:45:00+08:00',
      },
    ])
  })

  it('pads by the setup time too', async () => {
    const changed = await change(MARINA_HALL.id, { setup_minutes: 31 })

    expect(changed.overlap_warnings).toEqual([
      {
        booking_ids: [512, 511],
        overlap_start: '2026-11-10T12:29:00+08:00',
        overlap_end: '2026-11-10T12:30:00+08:00',
      },
    ])
    expect(changed.block_overlap_warnings).toEqual([])
  })

  it('reports every overlap there is after a change, not only new ones', async () => {
    const changed = await change(BOARDROOM_TWO.id, { setup_minutes: 5 })

    expect(changed.overlap_warnings).toEqual([
      {
        booking_ids: [505, 506],
        overlap_start: '2026-11-10T10:55:00+08:00',
        overlap_end: '2026-11-10T12:10:00+08:00',
      },
    ])
  })

  it('reports nothing when shorter times leave the bookings apart', async () => {
    const changed = await change(MARINA_HALL.id, { setup_minutes: 0, turnaround_minutes: 0 })

    expect(changed.overlap_warnings).toEqual([])
    expect(changed.block_overlap_warnings).toEqual([])
  })
})
