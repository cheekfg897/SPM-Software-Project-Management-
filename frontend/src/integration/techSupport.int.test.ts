import { fetchEventRequestsWithEquipment } from '@/features/eventRequests/api'
import { fetchEquipmentAwaitingAction, fetchEquipmentTypes } from '@/features/techSupport/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * Technical Support's two lists against the running backend: the equipment awaiting action
 * (SCRUM-38, ADR-0022) and the events with equipment (SCRUM-24 AC5, AC11), and the equipment
 * types the queue's lines are named from (ADR-0061).
 *
 * The staff account CI makes is an Event Coordinator, and only Technical Support Staff may read
 * either list, so here the lists are checked as refused to everyone else. What Technical Support
 * themselves get back waits as todos until the integration setup can make a Technical Support
 * account; until then the mock in src/mocks/handlers/techSupport.ts stands in for it.
 */

const NOT_PERMITTED = {
  status: 403,
  code: 'authorization_error',
  message: 'You do not have permission to perform this action.',
}
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }

const TECHNICAL_SUPPORT_LISTS = [
  ['the equipment awaiting action', fetchEquipmentAwaitingAction],
  ['the events with equipment', fetchEventRequestsWithEquipment],
] as const

describe('SCRUM-38 and SCRUM-24 AC5 Technical Support lists against the backend', () => {
  it.each(TECHNICAL_SUPPORT_LISTS)('refuses %s to an Event Coordinator', async (_list, read) => {
    await signInAs(staffAccount())

    expect(await refusal(read())).toMatchObject(NOT_PERMITTED)
  })

  it.each(TECHNICAL_SUPPORT_LISTS)('refuses %s to an Attendee', async (_list, read) => {
    await signInAsNewAttendee()

    expect(await refusal(read())).toMatchObject(NOT_PERMITTED)
  })

  it.each(TECHNICAL_SUPPORT_LISTS)('refuses %s to a visitor', async (_list, read) => {
    sendRequestsAs(null)

    expect(await refusal(read())).toMatchObject(NOT_SIGNED_IN)
  })

  it.todo(
    'lists each awaiting event as exactly event (the six equipment fields), equipment_lines and days_remaining, soonest first, with only its requested lines',
  )
  it.todo('answers an empty queue as {"equipment_requests": []}, with no message')
  it.todo(
    'lists each event with equipment with exactly the seven list fields, newest first, whatever its status',
  )
  it.todo(
    'answers no events with equipment as an empty list and "No events have an equipment request yet."',
  )
})

describe('equipment types the queue is named from, against the backend', () => {
  it('lets any staff member read them, as a list', async () => {
    await signInAs(staffAccount())

    expect(Array.isArray(await fetchEquipmentTypes())).toBe(true)
  })

  it('refuses an Attendee', async () => {
    await signInAsNewAttendee()

    expect(await refusal(fetchEquipmentTypes())).toMatchObject(NOT_PERMITTED)
  })

  it.todo(
    'names each type with exactly id, name, description, total_quantity, venue_id and store_name, by name',
  )
})
