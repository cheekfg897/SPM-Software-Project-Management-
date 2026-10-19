import { recordRequests } from '@/test/recordRequests'

import { fetchEquipmentType, fetchOutOfService, takeOutOfService, updateEquipmentType } from './api'

/** An id from the address with characters that would change the path if sent as they are. */
const EQUIPMENT_TYPE_ID = '7/edit?x'
const ESCAPED = '7%2Fedit%3Fx'
const CHANGES = {
  name: 'Lectern',
  description: '',
  total_quantity: 2,
  venue_id: null,
  store_name: 'Jurong store',
}

describe('SCRUM-27 equipment catalogue API paths', () => {
  it.each([
    ['reading', () => fetchEquipmentType(EQUIPMENT_TYPE_ID)],
    [
      'changing',
      () => updateEquipmentType({ equipmentTypeId: EQUIPMENT_TYPE_ID, changes: CHANGES }),
    ],
  ])('keeps the id one path segment when %s a type', async (_name, send) => {
    const requests = recordRequests()

    // The id is not a number, so the mock answers the route's 404: only the path matters here.
    await expect(send()).rejects.toMatchObject({ status: 404 })

    expect(new URL(requests[0]?.url ?? '').pathname).toBe(`/api/equipment/types/${ESCAPED}`)
  })
})

describe('SCRUM-47 out-of-service API paths', () => {
  it.each([
    ['listing', () => fetchOutOfService(EQUIPMENT_TYPE_ID)],
    [
      'taking units out',
      () =>
        takeOutOfService({
          equipmentTypeId: EQUIPMENT_TYPE_ID,
          body: { quantity: 1, reason: 'damaged' },
        }),
    ],
  ])("keeps the type's id one path segment when %s", async (_name, send) => {
    const requests = recordRequests()

    // The id is not a number, so the mock answers the route's 404: only the path matters here.
    await expect(send()).rejects.toMatchObject({ status: 404 })

    expect(new URL(requests[0]?.url ?? '').pathname).toBe(
      `/api/equipment/types/${ESCAPED}/out-of-service`,
    )
  })
})
