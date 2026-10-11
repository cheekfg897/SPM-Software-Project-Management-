import { recordRequests } from '@/test/recordRequests'

import { fetchEventAvailability, fetchEventReservations, reserveEquipment } from './api'

/** A reference with characters that would change the path if sent as they are. */
const REFERENCE = 'EVR-AB/12?x'
const ESCAPED = 'EVR-AB%2F12%3Fx'

describe('SCRUM-45 equipment API paths', () => {
  it.each([
    ['availability', () => fetchEventAvailability(REFERENCE), 'availability'],
    ['reservations', () => fetchEventReservations(REFERENCE), 'reservations'],
    [
      'reserve',
      () => reserveEquipment(REFERENCE, { equipment_type_id: 1, quantity: 1 }),
      'reservations',
    ],
  ])('keeps the reference one path segment when asking for %s', async (_name, send, last) => {
    const requests = recordRequests()

    // No one is signed in, so the mock refuses: only the path matters here.
    await expect(send()).rejects.toMatchObject({ status: 401 })

    expect(new URL(requests[0]?.url ?? '').pathname).toBe(
      `/api/equipment/events/${ESCAPED}/${last}`,
    )
  })
})
