import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { addEquipmentLine } from '@/features/equipment/api'
import { OTHER_STAFF } from '@/features/equipmentCatalogue/test/staff'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import {
  MOCK_BACK_IN_SERVICE_AT,
  MOCK_OPEN_EVENT_REFERENCE,
  MOCK_OUT_OF_SERVICE_RECORDED_AT,
  mockStatusEventReference,
} from './equipmentFixtures'
import { resetMockEquipment } from './equipment'
import { PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE } from './preparationRules'

/**
 * The out-of-service mock mirrors backend/app/modules/equipment/routes.py (SCRUM-47, ADR-0046):
 * Technical Support take units of a type out of service and put them back, the units stop
 * counting as available, and reservations they leave short are flagged.
 */

interface OutOfServiceEntry {
  id: number
  equipment_type_id: number
  quantity: number
  reason: string
  recorded_by: string | null
  recorded_at: string
  resolved_by: string | null
  resolved_at: string | null
}

interface Availability {
  equipment_type_name: string
  available: number
}

interface Reservation {
  id: number
  equipment_type_name: string
  needs_attention: boolean
}

const PROJECTOR_ID = 1
const MICROPHONE_ID = 2
/** Two are held, so taking three out is more than are in service. */
const LECTERN_ID = 3
const UNKNOWN_ID = 999
const MISSING = 'Missing data for required field.'
const ROUTE_NOT_FOUND =
  'The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.'
const OPEN_EVENT = `/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}`
/** The mock coordinator's Confirmed event: it has passed its safety check, as every one has. */
const CONFIRMED_EVENT_REFERENCE = mockStatusEventReference(EVENT_REQUEST_STATUS.CONFIRMED)
/** A line the coordinator may add only while the event is Approved, not once it is Confirmed. */
const LECTERN_LINE = { equipment_type_id: LECTERN_ID, quantity: 1 }

/** Everyone the backend refuses with a 403: every role but Technical Support. */
const NOT_TECHNICAL_SUPPORT: [string, MockAccount][] = [
  ...OTHER_STAFF,
  ['an Attendee', MOCK_ACCOUNTS.attendee],
  ['an Event Organiser', MOCK_ACCOUNTS.organiser],
]

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

function takeOut(equipmentTypeId: number | string, body: unknown) {
  return apiRequest<OutOfServiceEntry>(`/api/equipment/types/${equipmentTypeId}/out-of-service`, {
    method: 'POST',
    body,
  })
}

function listOut(equipmentTypeId: number | string) {
  return apiRequest<OutOfServiceEntry[]>(`/api/equipment/types/${equipmentTypeId}/out-of-service`)
}

function putBack(entryId: number | string) {
  return apiRequest<OutOfServiceEntry>(`/api/equipment/out-of-service/${entryId}/return`, {
    method: 'POST',
  })
}

/** The three calls, each on a type or entry that exists, to check who may make them. */
const CALLS = [
  ['taking units out', () => takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })],
  ['listing them', () => listOut(PROJECTOR_ID)],
  ['putting them back', () => putBack(1)],
] as const

async function projectorsAvailable(): Promise<number | undefined> {
  const rows = await apiRequest<Availability[]>(`${OPEN_EVENT}/availability`)
  return rows.find((row) => row.equipment_type_name === 'Projector')?.available
}

async function flagsByEquipment(): Promise<[string, boolean][]> {
  const reservations = await apiRequest<Reservation[]>(`${OPEN_EVENT}/reservations`)
  return reservations.map((reservation) => [
    reservation.equipment_type_name,
    reservation.needs_attention,
  ])
}

function reserveFor(reference: string, equipmentTypeId: number, quantity: number) {
  return apiRequest<Reservation>(`/api/equipment/events/${reference}/reservations`, {
    method: 'POST',
    body: { equipment_type_id: equipmentTypeId, quantity },
  })
}

function reserve(equipmentTypeId: number, quantity: number) {
  return reserveFor(MOCK_OPEN_EVENT_REFERENCE, equipmentTypeId, quantity)
}

/** Record that preparing the reservation has started, which needs the event's safety approval. */
function prepare(reservationId: number) {
  return apiRequest<Reservation>(`/api/equipment/reservations/${reservationId}/preparation`, {
    method: 'PUT',
    body: { status: 'in_progress' },
  })
}

const NEEDS_SAFETY_APPROVAL = {
  status: 409,
  code: 'conflict',
  message: PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE,
}

describe('SCRUM-47 equipment mock: units out of service', () => {
  beforeEach(() => signInAs(MOCK_ACCOUNTS.technicalSupport))

  it('takes units out, answering who recorded it and when, and lists them oldest first', async () => {
    const damaged = await takeOut(PROJECTOR_ID, { quantity: 2, reason: 'damaged' })
    await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'under_maintenance' })

    expect(damaged).toEqual({
      id: 1,
      equipment_type_id: PROJECTOR_ID,
      quantity: 2,
      reason: 'damaged',
      recorded_by: 'Tariq Hassan',
      recorded_at: MOCK_OUT_OF_SERVICE_RECORDED_AT,
      resolved_by: null,
      resolved_at: null,
    })
    const listed = await listOut(PROJECTOR_ID)
    expect(listed.map((entry) => [entry.quantity, entry.reason])).toEqual([
      [2, 'damaged'],
      [1, 'under_maintenance'],
    ])
    expect(await listOut(MICROPHONE_ID)).toEqual([])
  })

  it('puts units back, answering who and when, so the list no longer has them', async () => {
    const entry = await takeOut(PROJECTOR_ID, { quantity: 2, reason: 'damaged' })

    const returned = await putBack(entry.id)

    expect(returned).toEqual({
      ...entry,
      resolved_by: 'Tariq Hassan',
      resolved_at: MOCK_BACK_IN_SERVICE_AT,
    })
    expect(await listOut(PROJECTOR_ID)).toEqual([])
  })

  it('refuses putting the same units back twice (409), and an entry that does not exist (404)', async () => {
    const entry = await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })
    await putBack(entry.id)

    await expect(putBack(entry.id)).rejects.toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'These units are already back in service.',
    })
    await expect(putBack(UNKNOWN_ID)).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Out-of-service entry not found.',
    })
  })

  it('refuses more units than are in service, saying how many are, on quantity', async () => {
    await expect(takeOut(LECTERN_ID, { quantity: 3, reason: 'damaged' })).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Only 2 units are in service.',
      fieldErrors: { quantity: ['Only 2 units are in service.'] },
    })

    await takeOut(LECTERN_ID, { quantity: 2, reason: 'damaged' })
    await expect(takeOut(LECTERN_ID, { quantity: 1, reason: 'damaged' })).rejects.toMatchObject({
      message: 'Only 0 units are in service.',
    })
  })

  it.each([
    [{}, { quantity: [MISSING], reason: [MISSING] }],
    [
      { quantity: null, reason: null },
      { quantity: ['Field may not be null.'], reason: ['Field may not be null.'] },
    ],
    [
      { quantity: '2', reason: 'broken', note: 'x' },
      {
        quantity: ['Not a valid integer.'],
        reason: ['Must be one of: damaged, under_maintenance.'],
        note: ['Unknown field.'],
      },
    ],
    [
      { quantity: true, reason: 5 },
      {
        quantity: ['Not a valid integer.'],
        reason: ['Must be one of: damaged, under_maintenance.'],
      },
    ],
    [{ quantity: 0, reason: 'damaged' }, { quantity: ['Quantity must be at least 1.'] }],
  ])('names what is wrong with %j on each field', async (body, fieldErrors) => {
    await expect(takeOut(PROJECTOR_ID, body)).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Invalid request.',
      fieldErrors,
    })
  })

  it('refuses a body that is not a JSON object, naming no field', async () => {
    await expect(takeOut(PROJECTOR_ID, [])).rejects.toMatchObject({
      status: 400,
      message: 'Request body must be a JSON object.',
      fieldErrors: {},
    })
  })

  it('checks the body before it looks for the type, as the backend does', async () => {
    await expect(takeOut(UNKNOWN_ID, {})).rejects.toMatchObject({ status: 400 })
    await expect(takeOut(UNKNOWN_ID, { quantity: 1, reason: 'damaged' })).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Equipment type not found.',
    })
    await expect(listOut(UNKNOWN_ID)).rejects.toMatchObject({
      status: 404,
      message: 'Equipment type not found.',
    })
  })

  it('answers the route 404 for an id that is not a number, before asking who is calling', async () => {
    sendRequestsAs(null)

    for (const call of [takeOut('abc', {}), listOut('abc'), putBack('abc')]) {
      await expect(call).rejects.toMatchObject({ status: 404, message: ROUTE_NOT_FOUND })
    }
  })

  it.each(NOT_TECHNICAL_SUPPORT)('refuses %s every call (403)', async (_who, account) => {
    signInAs(account)

    for (const [, call] of CALLS) {
      await expect(call()).rejects.toMatchObject({ status: 403, code: 'authorization_error' })
    }
  })

  it.each(CALLS)('refuses a visitor %s (401)', async (_name, call) => {
    sendRequestsAs(null)

    await expect(call()).rejects.toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('forgets every entry when the mock is reset', async () => {
    await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })

    resetMockEquipment()

    expect(await listOut(PROJECTOR_ID)).toEqual([])
    const next = await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })
    expect(next.id).toBe(1)
  })
})

describe('SCRUM-47 equipment mock: availability and reservations', () => {
  beforeEach(() => signInAs(MOCK_ACCOUNTS.technicalSupport))

  it('stops counting units out of service as available until they are back (AC2)', async () => {
    const entry = await takeOut(PROJECTOR_ID, { quantity: 2, reason: 'under_maintenance' })

    expect(await projectorsAvailable()).toBe(4)

    await putBack(entry.id)
    expect(await projectorsAvailable()).toBe(6)
  })

  it('flags a reservation left short, leaves other types alone, and clears it once units are back (AC3)', async () => {
    await reserve(PROJECTOR_ID, 6)
    await reserve(MICROPHONE_ID, 2)
    expect(await flagsByEquipment()).toEqual([
      ['Projector', false],
      ['Microphone', false],
    ])

    const entry = await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })
    expect(await flagsByEquipment()).toEqual([
      ['Projector', true],
      ['Microphone', false],
    ])

    await putBack(entry.id)
    expect(await flagsByEquipment()).toEqual([
      ['Projector', false],
      ['Microphone', false],
    ])
  })

  it('leaves a reservation unflagged while the type still has units to spare (AC3)', async () => {
    await reserve(PROJECTOR_ID, 2)

    await takeOut(PROJECTOR_ID, { quantity: 4, reason: 'damaged' })
    expect(await flagsByEquipment()).toEqual([['Projector', false]])

    await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })
    expect(await flagsByEquipment()).toEqual([['Projector', true]])
  })

  it('shows the flag to the coordinator too', async () => {
    await reserve(PROJECTOR_ID, 6)
    await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })

    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await flagsByEquipment()).toEqual([['Projector', true]])
  })
})

describe('SCRUM-47 equipment mock: a reservation left short needs a new safety check (AC5)', () => {
  beforeEach(() => signInAs(MOCK_ACCOUNTS.technicalSupport))

  it("withdraws the event's safety approval, so its preparation is refused even once the units are back", async () => {
    const reservation = await reserve(PROJECTOR_ID, 6)
    await prepare(reservation.id)

    const entry = await takeOut(PROJECTOR_ID, { quantity: 1, reason: 'damaged' })
    await expect(prepare(reservation.id)).rejects.toMatchObject(NEEDS_SAFETY_APPROVAL)

    await putBack(entry.id)
    await expect(prepare(reservation.id)).rejects.toMatchObject(NEEDS_SAFETY_APPROVAL)
  })

  it('keeps the approval while the type has units to spare, or only another type is left short', async () => {
    const projectors = await reserve(PROJECTOR_ID, 2)
    await reserveFor(CONFIRMED_EVENT_REFERENCE, MICROPHONE_ID, 12)

    await takeOut(PROJECTOR_ID, { quantity: 4, reason: 'damaged' })
    await takeOut(MICROPHONE_ID, { quantity: 1, reason: 'damaged' })

    await expect(prepare(projectors.id)).resolves.toMatchObject({
      preparation_status: 'in_progress',
    })
  })

  it('sends a Confirmed event it leaves short back to Approved, so its coordinator can plan again', async () => {
    await reserveFor(CONFIRMED_EVENT_REFERENCE, MICROPHONE_ID, 12)
    signInAs(MOCK_ACCOUNTS.coordinator)
    await expect(addEquipmentLine(CONFIRMED_EVENT_REFERENCE, LECTERN_LINE)).rejects.toMatchObject({
      status: 409,
    })

    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await takeOut(MICROPHONE_ID, { quantity: 1, reason: 'damaged' })

    signInAs(MOCK_ACCOUNTS.coordinator)
    await expect(addEquipmentLine(CONFIRMED_EVENT_REFERENCE, LECTERN_LINE)).resolves.toMatchObject(
      LECTERN_LINE,
    )
  })
})
