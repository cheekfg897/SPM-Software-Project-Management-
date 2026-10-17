import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'
import { NOT_PERMITTED_MESSAGE } from '../responses'
import { server } from '../server'

import {
  BOTH_LOCATIONS_MESSAGE,
  DUPLICATE_NAME_MESSAGE,
  NO_LOCATION_MESSAGE,
} from './equipmentCatalogue'
import type { MockCatalogueType } from './equipmentCatalogueFixtures'

/** The equipment catalogue mock mirrors backend/app/modules/equipment (SCRUM-27, ADR-0014). */

const TYPES = '/api/equipment/types'
const MISSING = 'Missing data for required field.'
const NOT_NULL = 'Field may not be null.'
const NOT_A_STRING = 'Not a valid string.'
const NOT_AN_INTEGER = 'Not a valid integer.'
const BLANK = 'Must not be blank.'
const NOT_AN_OBJECT = 'Request body must be a JSON object.'
const ROUTE_NOT_FOUND =
  'The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.'
const UNKNOWN_ID = 999
const UNKNOWN_VENUE_ID = 99

/** A valid new type kept in a store, for tests to change one field of. */
const NEW_TYPE = { name: 'Folding table', total_quantity: 2, store_name: 'Jurong store' }

const READERS: [string, MockAccount][] = [
  ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
  ['the Event Coordinator Lead', MOCK_ACCOUNTS.lead],
  ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ['Technical Support', MOCK_ACCOUNTS.technicalSupport],
]
const OUTSIDERS: [string, MockAccount][] = [
  ['an Attendee', MOCK_ACCOUNTS.attendee],
  ['an Event Organiser', MOCK_ACCOUNTS.organiser],
]
const NON_EDITORS = [...OUTSIDERS, ...READERS.slice(0, 3)]

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

function list() {
  return apiRequest<MockCatalogueType[]>(TYPES)
}

function one(id: number | string) {
  return apiRequest<MockCatalogueType>(`${TYPES}/${id}`)
}

function create(body?: unknown) {
  return apiRequest<MockCatalogueType>(TYPES, { method: 'POST', body })
}

function update(id: number | string, body: unknown) {
  return apiRequest<MockCatalogueType>(`${TYPES}/${id}`, { method: 'PATCH', body })
}

/** The ApiError a call was refused with. Fails the test if it succeeded. */
async function refusal(call: Promise<unknown>): Promise<ApiError> {
  const error = await call.then(
    () => expect.fail('Expected the mock to refuse the request.'),
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error(`Expected an ApiError, got ${String(error)}`)
  }
  return error
}

/** The per-field messages a new type with `body` is refused with. */
async function createErrors(body: unknown) {
  return (await refusal(create(body))).fieldErrors
}

async function names() {
  return (await list()).map((type) => type.name)
}

describe('SCRUM-27 equipment catalogue mock: reading (AC2, AC3)', () => {
  it('lists every type by name, with all of its fields', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await list()).toEqual([
      {
        id: 3,
        name: 'Lectern',
        description: null,
        total_quantity: 2,
        venue_id: null,
        store_name: 'Main store',
      },
      {
        id: 2,
        name: 'Microphone',
        description: 'Wireless, handheld.',
        total_quantity: 12,
        venue_id: 3,
        store_name: null,
      },
      {
        id: 1,
        name: 'Projector',
        description: 'Full HD, with HDMI and USB-C.',
        total_quantity: 10,
        venue_id: null,
        store_name: 'Main store',
      },
    ])
  })

  it.each(READERS)('lets %s read the list and one type', async (_who, account) => {
    signInAs(account)

    expect(await names()).toHaveLength(3)
    expect(await one(2)).toMatchObject({ id: 2, name: 'Microphone', total_quantity: 12 })
  })

  it.each(OUTSIDERS)('refuses %s with the 403 the backend sends', async (_who, account) => {
    signInAs(account)

    for (const call of [list(), one(2)]) {
      expect(await refusal(call)).toMatchObject({
        status: 403,
        code: 'authorization_error',
        message: NOT_PERMITTED_MESSAGE,
      })
    }
  })

  it('refuses a visitor with a 401', async () => {
    for (const call of [list(), one(2)]) {
      expect(await refusal(call)).toMatchObject({ status: 401, code: 'authentication_error' })
    }
  })

  it('answers 404 for a type that does not exist', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await refusal(one(UNKNOWN_ID))).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Equipment type not found.',
    })
  })

  it('answers the route 404 for an id that is not a number, before asking who is calling', async () => {
    for (const id of ['abc', '-1', '1.5']) {
      expect(await refusal(one(id))).toMatchObject({
        status: 404,
        code: 'not_found',
        message: ROUTE_NOT_FOUND,
      })
    }
  })
})

describe('SCRUM-27 equipment catalogue mock: adding a type (AC1, AC3)', () => {
  it('saves a type kept in a store, trimmed, with an empty description as none', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const created = await create({
      name: '  Folding table ',
      description: '   ',
      total_quantity: 2,
      venue_id: null,
      store_name: ' Jurong store ',
    })

    const expected = {
      id: 4,
      name: 'Folding table',
      description: null,
      total_quantity: 2,
      venue_id: null,
      store_name: 'Jurong store',
    }
    expect(created).toEqual(expected)
    expect(await one(4)).toEqual(expected)
    expect(await names()).toEqual(['Folding table', 'Lectern', 'Microphone', 'Projector'])
  })

  it('saves a type kept at a venue, with its description trimmed', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const created = await create({
      name: 'Stage light',
      description: ' LED, dimmable. ',
      total_quantity: 0,
      venue_id: 8,
    })

    expect(created).toEqual({
      id: 4,
      name: 'Stage light',
      description: 'LED, dimmable.',
      total_quantity: 0,
      venue_id: 8,
      store_name: null,
    })
  })

  it('answers a new type with 201 Created', async () => {
    const statuses: number[] = []
    server.events.on('response:mocked', ({ response }) => statuses.push(response.status))
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await create(NEW_TYPE)

    expect(statuses).toEqual([201])
  })

  it('gives each new type the next id', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await create(NEW_TYPE)
    const second = await create({ ...NEW_TYPE, name: 'Podium' })

    expect(second.id).toBe(5)
  })

  it('uses up an id on a duplicate name, as a Postgres sequence does, but not on a refused body', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await refusal(create({ ...NEW_TYPE, name: 'Projector' }))
    await refusal(create({ ...NEW_TYPE, total_quantity: -1 }))
    await refusal(create({ name: 'Folding table', total_quantity: 2, venue_id: UNKNOWN_VENUE_ID }))
    const created = await create(NEW_TYPE)

    expect(created.id).toBe(5)
  })

  it.each(NON_EDITORS)('refuses %s: only Technical Support add types', async (_who, account) => {
    signInAs(account)

    expect(await refusal(create(NEW_TYPE))).toMatchObject({
      status: 403,
      message: NOT_PERMITTED_MESSAGE,
    })
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect(await names()).not.toContain('Folding table')
  })

  it('refuses a visitor with a 401', async () => {
    expect(await refusal(create(NEW_TYPE))).toMatchObject({ status: 401 })
  })

  it('needs a name and a total quantity', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await createErrors({ store_name: 'Jurong store' })).toEqual({
      name: [MISSING],
      total_quantity: [MISSING],
    })
  })

  it.each([
    ['name', null, [NOT_NULL]],
    ['name', 5, [NOT_A_STRING]],
    ['name', '   ', [BLANK]],
    ['name', 'x'.repeat(201), ['Name must be at most 200 characters.']],
    ['name', ' '.repeat(201), [BLANK, 'Name must be at most 200 characters.']],
    ['description', 5, [NOT_A_STRING]],
    ['total_quantity', null, [NOT_NULL]],
    ['total_quantity', '3', [NOT_AN_INTEGER]],
    ['total_quantity', 1.5, [NOT_AN_INTEGER]],
    ['total_quantity', true, [NOT_AN_INTEGER]],
    ['total_quantity', -1, ['Total quantity cannot be negative.']],
    ['venue_id', '3', [NOT_AN_INTEGER]],
    ['venue_id', 1.5, [NOT_AN_INTEGER]],
    ['venue_id', true, [NOT_AN_INTEGER]],
    ['venue_id', 0, ['venue_id must be a positive number.']],
    ['store_name', 5, [NOT_A_STRING]],
    ['store_name', '  ', [BLANK]],
    ['store_name', 'x'.repeat(201), ['Store name must be at most 200 characters.']],
    ['colour', 'red', ['Unknown field.']],
  ])('refuses %s %j with the backend message', async (field, value, messages) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    // A venue next to the store would be its own refusal, so a venue goes in place of it.
    const base = field === 'venue_id' ? { name: 'Folding table', total_quantity: 2 } : NEW_TYPE

    expect(await createErrors({ ...base, [field]: value })).toEqual({ [field]: messages })
  })

  it.each([
    ['a name of 200 characters', { name: 'x'.repeat(200) }],
    ['a store name of 200 characters', { store_name: 'x'.repeat(200) }],
    ['no description', { description: null }],
    ['a total of 0', { total_quantity: 0 }],
    ['venue 1, the lowest id', { venue_id: 1, store_name: null }],
  ])('accepts %s', async (_case, change) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await create({ ...NEW_TYPE, ...change })).toMatchObject(change)
  })

  it.each([
    ['neither place', { venue_id: null, store_name: null }, NO_LOCATION_MESSAGE],
    ['no place at all', {}, NO_LOCATION_MESSAGE],
    [
      'both a venue and a store',
      { venue_id: 3, store_name: 'Jurong store' },
      BOTH_LOCATIONS_MESSAGE,
    ],
  ])('refuses %s, on venue_id', async (_case, location, message) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await createErrors({ name: 'Folding table', total_quantity: 2, ...location })).toEqual({
      venue_id: [message],
    })
  })

  it('checks the place only once every field is valid', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await createErrors({ name: ' ', total_quantity: 2 })).toEqual({ name: [BLANK] })
  })

  it('refuses a venue that does not exist', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(
      await createErrors({ name: 'Folding table', total_quantity: 2, venue_id: UNKNOWN_VENUE_ID }),
    ).toEqual({ venue_id: ['Venue not found.'] })
  })

  it.each(['Projector', ' Projector '])(
    'refuses the name %j, which another type has, with a 409',
    async (name) => {
      signInAs(MOCK_ACCOUNTS.technicalSupport)

      expect(await refusal(create({ ...NEW_TYPE, name }))).toMatchObject({
        status: 409,
        code: 'conflict',
        message: DUPLICATE_NAME_MESSAGE,
      })
      expect(await names()).toHaveLength(3)
    },
  )

  it('treats a name in other capitals as a different name (ADR-0014)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await create({ ...NEW_TYPE, name: 'projector' })).toMatchObject({ name: 'projector' })
  })

  it.each([
    ['no body', undefined],
    ['a list', [NEW_TYPE]],
    ['a string', 'Folding table'],
  ])('refuses %s as the body, with no details', async (_case, body) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(create(body))

    expect(error).toMatchObject({ status: 400, code: 'validation_error', message: NOT_AN_OBJECT })
    expect(error.fieldErrors).toEqual({})
  })
})

describe('SCRUM-27 equipment catalogue mock: editing a type (AC1, AC3)', () => {
  it('changes only the fields sent', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const updated = await update(2, { total_quantity: 20 })

    const expected = {
      id: 2,
      name: 'Microphone',
      description: 'Wireless, handheld.',
      total_quantity: 20,
      venue_id: 3,
      store_name: null,
    }
    expect(updated).toEqual(expected)
    expect(await one(2)).toEqual(expected)
  })

  it('saves every field sent, trimmed, and an emptied description as none', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const updated = await update(1, {
      name: ' Laser projector ',
      description: '',
      total_quantity: 12,
      venue_id: null,
      store_name: ' Jurong store ',
    })

    expect(updated).toEqual({
      id: 1,
      name: 'Laser projector',
      description: null,
      total_quantity: 12,
      venue_id: null,
      store_name: 'Jurong store',
    })
    expect(await names()).toEqual(['Laser projector', 'Lectern', 'Microphone'])
  })

  it('moves a type from a venue to a store, clearing the venue', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await update(2, { store_name: 'Jurong store' })).toMatchObject({
      venue_id: null,
      store_name: 'Jurong store',
    })
  })

  it('moves a type from a store to a venue, clearing the store', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await update(1, { venue_id: 5 })).toMatchObject({ venue_id: 5, store_name: null })
  })

  it('changes nothing for an empty body', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await update(3, {})).toEqual(await one(3))
    expect(await one(3)).toMatchObject({ name: 'Lectern', total_quantity: 2 })
  })

  it('lets a type keep its own name', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await update(1, { name: 'Projector', total_quantity: 11 })).toMatchObject({
      name: 'Projector',
      total_quantity: 11,
    })
  })

  it("refuses another type's name with a 409 and keeps the old one", async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await refusal(update(1, { name: 'Microphone' }))).toMatchObject({
      status: 409,
      message: DUPLICATE_NAME_MESSAGE,
    })
    expect((await one(1)).name).toBe('Projector')
  })

  it.each(NON_EDITORS)('refuses %s: only Technical Support change types', async (_who, account) => {
    signInAs(account)

    expect(await refusal(update(1, { total_quantity: 1 }))).toMatchObject({
      status: 403,
      message: NOT_PERMITTED_MESSAGE,
    })
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect((await one(1)).total_quantity).toBe(10)
  })

  it('refuses a visitor with a 401', async () => {
    expect(await refusal(update(1, { total_quantity: 1 }))).toMatchObject({ status: 401 })
  })

  it('answers 404 for a type that does not exist, and the route 404 for an id that is not a number', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await refusal(update(UNKNOWN_ID, { total_quantity: 1 }))).toMatchObject({
      status: 404,
      message: 'Equipment type not found.',
    })
    expect(await refusal(update('abc', { total_quantity: 1 }))).toMatchObject({
      status: 404,
      message: ROUTE_NOT_FOUND,
    })
  })

  it.each([
    [
      'a negative total',
      { total_quantity: -1 },
      { total_quantity: ['Total quantity cannot be negative.'] },
    ],
    ['a blank name', { name: '' }, { name: [BLANK] }],
    ['no total', { total_quantity: null }, { total_quantity: [NOT_NULL] }],
    ['neither place', { venue_id: null, store_name: null }, { venue_id: [NO_LOCATION_MESSAGE] }],
    ['a venue alone, as null', { venue_id: null }, { venue_id: [NO_LOCATION_MESSAGE] }],
    [
      'both places',
      { venue_id: 3, store_name: 'Jurong store' },
      { venue_id: [BOTH_LOCATIONS_MESSAGE] },
    ],
    [
      'a venue that does not exist',
      { venue_id: UNKNOWN_VENUE_ID },
      { venue_id: ['Venue not found.'] },
    ],
  ])('refuses %s and keeps the type as it was', async (_case, body, errors) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    const before = await one(2)

    expect((await refusal(update(2, body))).fieldErrors).toEqual(errors)
    expect(await one(2)).toEqual(before)
  })

  it('checks the body before looking the type up, and the type before the venue', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await refusal(update(UNKNOWN_ID, { total_quantity: -1 }))).toMatchObject({ status: 400 })
    expect(await refusal(update(UNKNOWN_ID, { venue_id: UNKNOWN_VENUE_ID }))).toMatchObject({
      status: 404,
    })
  })

  it('refuses a body that is not an object', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await refusal(update(1, ['name']))).toMatchObject({
      status: 400,
      message: NOT_AN_OBJECT,
    })
  })
})
