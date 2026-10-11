import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import { MOCK_CLOSED_EVENT_REFERENCE, MOCK_OPEN_EVENT_REFERENCE } from './equipmentFixtures'

/** The equipment mock mirrors backend/app/modules/equipment/routes.py (SCRUM-45, SCRUM-46). */

interface Availability {
  equipment_type_id: number
  equipment_type_name: string
  available: number
  requested: number
  shortfall: number
}

const EQUIPMENT = '/api/equipment/events'
const OPEN = `${EQUIPMENT}/${MOCK_OPEN_EVENT_REFERENCE}`

function signInAs(account: (typeof MOCK_ACCOUNTS)[keyof typeof MOCK_ACCOUNTS]) {
  sendRequestsAs(mockTokenFor(account))
}

function reserve(reference: string, body: unknown) {
  return apiRequest(`${EQUIPMENT}/${reference}/reservations`, { method: 'POST', body })
}

function availability(reference = MOCK_OPEN_EVENT_REFERENCE) {
  return apiRequest<Availability[]>(`${EQUIPMENT}/${reference}/availability`)
}

const projector = (rows: Availability[]) =>
  rows.find((row) => row.equipment_type_name === 'Projector')

describe('SCRUM-45 equipment mock: availability', () => {
  it('reports available, requested and the shortfall for each equipment type', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const rows = await availability()

    expect(projector(rows)).toMatchObject({ available: 6, requested: 8, shortfall: 2 })
    expect(rows.find((row) => row.equipment_type_name === 'Microphone')).toMatchObject({
      shortfall: 0,
    })
  })

  it('lets a coordinator read it', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(availability()).resolves.toHaveLength(2)
  })

  it('refuses an organiser with the 403 the backend sends', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    await expect(availability()).rejects.toMatchObject({ status: 403 })
  })

  it('refuses a visitor with a 401', async () => {
    sendRequestsAs(null)

    await expect(availability()).rejects.toMatchObject({ status: 401 })
  })

  it('answers 404 for an unknown event', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(availability('EVR-NOPE')).rejects.toMatchObject({
      status: 404,
      message: 'Event request not found.',
    })
  })
})

describe('SCRUM-46 equipment mock: reservations', () => {
  it('creates a reservation that lowers what is available', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    const projectorId = projector(await availability())?.equipment_type_id

    const reservation = await reserve(MOCK_OPEN_EVENT_REFERENCE, {
      equipment_type_id: projectorId,
      quantity: 4,
    })

    expect(reservation).toMatchObject({
      equipment_type_id: projectorId,
      equipment_type_name: 'Projector',
      quantity: 4,
      reserved_by: 'Tariq Hassan',
    })
    expect(projector(await availability())).toMatchObject({ available: 2, shortfall: 6 })
    await expect(apiRequest(`${OPEN}/reservations`)).resolves.toHaveLength(1)
  })

  it('refuses more than is available, naming how many are', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    const projectorId = projector(await availability())?.equipment_type_id

    await expect(
      reserve(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: projectorId, quantity: 7 }),
    ).rejects.toMatchObject({
      status: 400,
      fieldErrors: { quantity: ['Only 6 available for this period.'] },
    })
    await expect(apiRequest(`${OPEN}/reservations`)).resolves.toEqual([])
  })

  it('reports a missing field and an unknown equipment type', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(reserve(MOCK_OPEN_EVENT_REFERENCE, {})).rejects.toMatchObject({
      status: 400,
      fieldErrors: {
        equipment_type_id: ['Missing data for required field.'],
        quantity: ['Missing data for required field.'],
      },
    })
    await expect(
      reserve(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: 999, quantity: 1 }),
    ).rejects.toMatchObject({
      status: 400,
      fieldErrors: { equipment_type_id: ['Equipment type not found.'] },
    })
  })

  it('refuses a quantity below one and an id below one, in the backend wording', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(
      reserve(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: 0, quantity: 0 }),
    ).rejects.toMatchObject({
      status: 400,
      fieldErrors: {
        equipment_type_id: ['equipment_type_id must be a positive number.'],
        quantity: ['Quantity must be at least 1.'],
      },
    })
  })

  it('refuses a quantity that is not a whole number', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(
      reserve(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: 1, quantity: 'two' }),
    ).rejects.toMatchObject({ fieldErrors: { quantity: ['Not a valid integer.'] } })
  })

  it('checks the body before it looks for the event, as the backend does', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(reserve('EVR-NOPE', {})).rejects.toMatchObject({ status: 400 })
  })

  it('checks the event is open before it looks for the equipment type', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(
      reserve(MOCK_CLOSED_EVENT_REFERENCE, { equipment_type_id: 999, quantity: 1 }),
    ).rejects.toMatchObject({ status: 409 })
  })

  it('answers 409 for an event that is closed', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(
      reserve(MOCK_CLOSED_EVENT_REFERENCE, { equipment_type_id: 1, quantity: 1 }),
    ).rejects.toMatchObject({ status: 409 })
  })

  it('lets only Technical Support reserve', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      reserve(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: 1, quantity: 1 }),
    ).rejects.toMatchObject({ status: 403 })
  })

  it('answers 404 when listing or reserving for an unknown event', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(apiRequest(`${EQUIPMENT}/EVR-NOPE/reservations`)).rejects.toMatchObject({
      status: 404,
    })
    await expect(reserve('EVR-NOPE', { equipment_type_id: 1, quantity: 1 })).rejects.toMatchObject({
      status: 404,
    })
  })

  it('refuses a visitor listing reservations', async () => {
    sendRequestsAs(null)

    await expect(apiRequest(`${OPEN}/reservations`)).rejects.toMatchObject({ status: 401 })
  })
})
