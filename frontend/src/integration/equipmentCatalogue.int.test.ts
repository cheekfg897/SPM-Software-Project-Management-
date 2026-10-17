import {
  createEquipmentType,
  fetchEquipmentType,
  fetchEquipmentTypes,
  updateEquipmentType,
} from '@/features/equipmentCatalogue/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'

/**
 * SCRUM-27: the equipment catalogue against the real backend. The staff account CI makes is an
 * Event Coordinator, who may read the catalogue but not change it, so reading and every refusal
 * are checked here. Adding and editing need a Technical Support account, which CI doesn't make
 * (ADR-0023), so they wait as todos; until then src/mocks/handlers/equipmentCatalogue.ts stands
 * in for them.
 */

/** An id no database in a test run reaches. */
const UNKNOWN_ID = '987654321'
const NEW_TYPE = {
  name: 'Integration lectern',
  description: '',
  total_quantity: 2,
  venue_id: null,
  store_name: 'Integration store',
}
const EQUIPMENT_TYPE_FIELDS = [
  'description',
  'id',
  'name',
  'store_name',
  'total_quantity',
  'venue_id',
]

afterEach(() => sendRequestsAs(null))

describe('SCRUM-27 equipment catalogue contract (ADR-0014, ADR-0054)', () => {
  it('lets an Event Coordinator read the list, each type with exactly the fields the web app reads', async () => {
    await signInAs(staffAccount())

    const types = await fetchEquipmentTypes()

    expect(Array.isArray(types)).toBe(true)
    for (const type of types) {
      expect(Object.keys(type).sort()).toEqual(EQUIPMENT_TYPE_FIELDS)
    }
  })

  it('answers 404 with its message for a type that does not exist', async () => {
    await signInAs(staffAccount())

    const error = await refusal(fetchEquipmentType(UNKNOWN_ID))

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Equipment type not found.',
    })
  })

  it('answers the route 404 for an id that is not a number, before asking who is calling', async () => {
    const error = await refusal(fetchEquipmentType('abc'))

    expect(error).toMatchObject({ status: 404, code: 'not_found' })
  })

  it('refuses a visitor (401)', async () => {
    const error = await refusal(fetchEquipmentTypes())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses an Attendee the list (403)', async () => {
    await signInAsNewAttendee()

    const error = await refusal(fetchEquipmentTypes())

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it('refuses an Event Coordinator adding or changing a type (403)', async () => {
    await signInAs(staffAccount())

    const adding = await refusal(createEquipmentType(NEW_TYPE))
    const changing = await refusal(
      updateEquipmentType({ equipmentTypeId: UNKNOWN_ID, changes: NEW_TYPE }),
    )

    expect(adding).toMatchObject({ status: 403, code: 'authorization_error' })
    expect(changing).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it.todo(
    'adds a type for Technical Support (201) with every field sent, trimmed, and an empty description as null',
  )
  it.todo('lists a new type among the others, by name, with its total quantity')
  it.todo(
    'changes a type with every field sent (PATCH), moving it from a venue to a store and clearing the venue',
  )
  it.todo(
    'refuses a null total_quantity ("Field may not be null."), a blank name ("Must not be blank.") and a negative total, per field',
  )
  it.todo(
    'refuses neither or both places with the message on venue_id, and an unknown venue with "Venue not found."',
  )
  it.todo(
    'refuses a name another type has (409, "An equipment type with this name already exists.")',
  )
})
