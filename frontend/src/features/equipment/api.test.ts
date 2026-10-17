import { recordRequests } from '@/test/recordRequests'

import {
  addEquipmentLine,
  fetchEquipmentTypes,
  fetchEventAvailability,
  fetchEventEquipmentLines,
  fetchEventReservations,
  removeEquipmentLine,
  reserveEquipment,
  updateEquipmentLine,
} from './api'

/** A reference with characters that would change the path if sent as they are. */
const REFERENCE = 'EVR-AB/12?x'
const ESCAPED = 'EVR-AB%2F12%3Fx'
const LINES = `/api/events/requests/${ESCAPED}/equipment`
/** A line id no fixture uses, so a hard-coded one would show. */
const LINE_ID = 83

/** The method and path a call sent. No one is signed in, so the mock refuses it with a 401. */
async function sentRequest(send: () => Promise<unknown>): Promise<string> {
  const requests = recordRequests()

  await expect(send()).rejects.toMatchObject({ status: 401 })

  const [request] = requests
  return `${request?.method ?? ''} ${new URL(request?.url ?? '').pathname}`
}

describe('SCRUM-45 equipment API paths', () => {
  it.each([
    ['availability', () => fetchEventAvailability(REFERENCE), 'GET', 'availability'],
    ['reservations', () => fetchEventReservations(REFERENCE), 'GET', 'reservations'],
    [
      'reserve',
      () => reserveEquipment(REFERENCE, { equipment_type_id: 1, quantity: 1 }),
      'POST',
      'reservations',
    ],
  ])(
    'keeps the reference one path segment when asking for %s',
    async (_name, send, method, last) => {
      await expect(sentRequest(send)).resolves.toBe(
        `${method} /api/equipment/events/${ESCAPED}/${last}`,
      )
    },
  )
})

describe('SCRUM-37 equipment line API paths', () => {
  it.each([
    ['lists the lines', () => fetchEventEquipmentLines(REFERENCE), `GET ${LINES}`],
    ['adds a line', () => addEquipmentLine(REFERENCE, { quantity: 1 }), `POST ${LINES}`],
    [
      'changes a line',
      () => updateEquipmentLine(REFERENCE, { lineId: LINE_ID, body: { quantity: 2 } }),
      `PATCH ${LINES}/${LINE_ID}`,
    ],
    ['removes a line', () => removeEquipmentLine(REFERENCE, LINE_ID), `DELETE ${LINES}/${LINE_ID}`],
    ['reads the equipment types', () => fetchEquipmentTypes(), 'GET /api/equipment/types'],
  ])('%s at its own path, with the reference as one segment', async (_name, send, expected) => {
    await expect(sentRequest(send)).resolves.toBe(expected)
  })
})
