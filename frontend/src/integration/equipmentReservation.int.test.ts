import { fetchEventReservations, reserveEquipment } from '@/features/equipment/api'
import { createEquipmentType } from '@/features/equipmentCatalogue/api'
import { fetchNotifications } from '@/features/notifications/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { hasTechSupport, signInAs, signInAsTechSupport, staffAccount, uniqueEmail } from './backend'
import { approvedEvent, LEAD } from './plannedEvent'

/**
 * SCRUM-46 AC5 against the running backend: reserving equipment notifies nobody by itself; the
 * coordinator hears once, when Technical Support record the outcome (SCRUM-48, ADR-0102). The
 * event must be the staff account's, which takes a Lead to assign, and only Technical Support
 * reserve, so the check needs both accounts (plannedEvent.ts, backend.ts) and skips without them.
 */

const canReserveForTheStaffAccount = hasTechSupport && LEAD !== null

/** As the staff account, the event's coordinator: the kinds of their notices about it. */
async function coordinatorNoticeKinds(reference: string): Promise<string[]> {
  await signInAs(staffAccount())
  const notices = await fetchNotifications()
  const kinds = []
  for (const notice of notices) {
    if (notice.event_reference === reference) {
      kinds.push(notice.kind)
    }
  }
  return kinds
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-46 AC5 reserving equipment against the backend', () => {
  it.skipIf(!canReserveForTheStaffAccount)(
    'saves the reservation and tells the coordinator nothing',
    async () => {
      const { reference } = await approvedEvent()
      const before = await coordinatorNoticeKinds(reference)
      await signInAsTechSupport()
      const type = await createEquipmentType({
        name: `Integration microphone ${uniqueEmail('type')}`,
        description: '',
        total_quantity: 5,
        venue_id: null,
        store_name: 'Integration store',
      })

      await reserveEquipment(reference, { equipment_type_id: type.id, quantity: 2 })

      expect(await coordinatorNoticeKinds(reference)).toEqual(before)
      const reservations = await fetchEventReservations(reference)
      expect(reservations.map((reservation) => reservation.quantity)).toEqual([2])
    },
  )
})
