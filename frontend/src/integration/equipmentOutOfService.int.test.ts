import { fetchCurrentUser, register } from '@/features/auth/api'
import { fetchEventReservations, reserveEquipment } from '@/features/equipment/api'
import {
  createEquipmentType,
  fetchOutOfService,
  returnToService,
  takeOutOfService,
} from '@/features/equipmentCatalogue/api'
import { submitEventRequest } from '@/features/eventRequests/api'
import { createOrganisation } from '@/features/organisations/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  hasTechSupport,
  newOrganiser,
  refusal,
  signInAs,
  signInAsNewAttendee,
  signInAsTechSupport,
  staffAccount,
  uniqueEmail,
} from './backend'

/**
 * SCRUM-47: taking units of an equipment type out of service, and putting them back, against the
 * running backend (ADR-0046, ADR-0089). Only Technical Support may, so most checks need the
 * Technical Support account, and skip without it (backend.ts).
 */

/** Ids no database in a test run reaches. */
const UNKNOWN_TYPE_ID = '987654321'
const UNKNOWN_ENTRY_ID = 987654321
const MISSING_MESSAGE = 'Missing data for required field.'
const ENTRY_FIELDS = [
  'equipment_type_id',
  'id',
  'quantity',
  'reason',
  'recorded_at',
  'recorded_by',
  'resolved_at',
  'resolved_by',
]
/** Every field the frontend's EquipmentReservation reads, and nothing more. */
const RESERVATION_FIELDS = [
  'created_at',
  'ends_at',
  'equipment_type_id',
  'equipment_type_name',
  'id',
  'needs_attention',
  'preparation_notes',
  'preparation_status',
  'quantity',
  'reserved_by',
  'starts_at',
]
/** An ISO date-time with the business offset, as the backend writes them (ADR-0009). */
const BUSINESS_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+08:00$/

/** A date `days` from now, as the backend reads dates ("2026-11-20"). */
function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString().slice(0, 10)
}

/** A type of its own, so no other test's units or reservations change its numbers. */
async function newEquipmentType(totalQuantity: number): Promise<string> {
  const type = await createEquipmentType({
    name: `Integration screen ${uniqueEmail('type')}`,
    description: '',
    total_quantity: totalQuantity,
    venue_id: null,
    store_name: 'Integration store',
  })
  return String(type.id)
}

/**
 * A request a new organiser submits for a month from now, so its reservations are still to come.
 * Staff record the organisation the organiser signs up to (SCRUM-66).
 */
async function submittedEventReference(): Promise<string> {
  await signInAs(staffAccount())
  const organisation = await createOrganisation({
    name: `Integration organisation ${uniqueEmail('organisation')}`,
    contact_name: 'Integration Contact',
    contact_email: uniqueEmail('contact'),
  })
  const organiser = newOrganiser(organisation.id)
  sendRequestsAs(null)
  await register(organiser)
  await signInAs({ email: organiser.email, password: organiser.password })
  const submitted = await submitEventRequest({
    name: 'Integration Out Of Service',
    proposed_date: daysFromNow(30),
    start_time: '09:00',
    end_time: '17:00',
    expected_attendance: 60,
  })
  return submitted.reference
}

/** The three calls, on a type and an entry that don't exist, to check who may make them. */
const CALLS = [
  [
    'taking units out',
    () =>
      takeOutOfService({
        equipmentTypeId: UNKNOWN_TYPE_ID,
        body: { quantity: 1, reason: 'damaged' },
      }),
  ],
  ['listing them', () => fetchOutOfService(UNKNOWN_TYPE_ID)],
  ['putting them back', () => returnToService(UNKNOWN_ENTRY_ID)],
] as const

afterEach(() => sendRequestsAs(null))

describe('SCRUM-47 units out of service against the backend', () => {
  it.each(CALLS)('refuses a visitor %s (401)', async (_name, call) => {
    const error = await refusal(call())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.each(CALLS)('refuses an Event Coordinator and an attendee %s (403)', async (_name, call) => {
    await signInAs(staffAccount())
    const coordinator = await refusal(call())
    await signInAsNewAttendee()
    const attendee = await refusal(call())

    for (const error of [coordinator, attendee]) {
      expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
    }
  })

  it.skipIf(!hasTechSupport)(
    'takes units out with who and when (AC1, AC4), lists them oldest first, and puts them back',
    async () => {
      await signInAsTechSupport()
      const me = await fetchCurrentUser()
      const typeId = await newEquipmentType(5)

      const damaged = await takeOutOfService({
        equipmentTypeId: typeId,
        body: { quantity: 2, reason: 'damaged' },
      })
      await takeOutOfService({
        equipmentTypeId: typeId,
        body: { quantity: 1, reason: 'under_maintenance' },
      })

      expect(Object.keys(damaged).sort()).toEqual(ENTRY_FIELDS)
      expect(damaged).toMatchObject({
        equipment_type_id: Number(typeId),
        quantity: 2,
        reason: 'damaged',
        recorded_by: me.full_name,
        resolved_by: null,
        resolved_at: null,
      })
      expect(damaged.recorded_at).toMatch(BUSINESS_DATE_TIME)
      const listed = await fetchOutOfService(typeId)
      expect(listed.map((entry) => [entry.quantity, entry.reason])).toEqual([
        [2, 'damaged'],
        [1, 'under_maintenance'],
      ])

      const returned = await returnToService(damaged.id)

      expect(returned).toMatchObject({ id: damaged.id, resolved_by: me.full_name })
      expect(returned.resolved_at).toMatch(BUSINESS_DATE_TIME)
      const stillOut = await fetchOutOfService(typeId)
      expect(stillOut.map((entry) => entry.reason)).toEqual(['under_maintenance'])
    },
  )

  it.skipIf(!hasTechSupport)(
    'refuses putting the same units back twice (409) and an entry that does not exist (404)',
    async () => {
      await signInAsTechSupport()
      const typeId = await newEquipmentType(1)
      const entry = await takeOutOfService({
        equipmentTypeId: typeId,
        body: { quantity: 1, reason: 'damaged' },
      })
      await returnToService(entry.id)

      const twice = await refusal(returnToService(entry.id))
      const unknown = await refusal(returnToService(UNKNOWN_ENTRY_ID))

      expect(twice).toMatchObject({
        status: 409,
        code: 'conflict',
        message: 'These units are already back in service.',
      })
      expect(unknown).toMatchObject({
        status: 404,
        code: 'not_found',
        message: 'Out-of-service entry not found.',
      })
    },
  )

  it.skipIf(!hasTechSupport)(
    'refuses more units than are in service, with the same message on quantity',
    async () => {
      await signInAsTechSupport()
      const typeId = await newEquipmentType(2)

      const error = await refusal(
        takeOutOfService({ equipmentTypeId: typeId, body: { quantity: 3, reason: 'damaged' } }),
      )

      expect(error).toMatchObject({
        status: 400,
        code: 'validation_error',
        message: 'Only 2 units are in service.',
        fieldErrors: { quantity: ['Only 2 units are in service.'] },
      })
    },
  )

  it.skipIf(!hasTechSupport).each([
    [{}, { quantity: [MISSING_MESSAGE], reason: [MISSING_MESSAGE] }],
    [{ quantity: 0, reason: 'damaged' }, { quantity: ['Quantity must be at least 1.'] }],
    [
      { quantity: '2', reason: 'broken', note: 'x' },
      {
        quantity: ['Not a valid integer.'],
        reason: ['Must be one of: damaged, under_maintenance.'],
        note: ['Unknown field.'],
      },
    ],
  ])(
    'names what is wrong with %j on each field, before looking for the type',
    async (body, fieldErrors) => {
      await signInAsTechSupport()

      const error = await refusal(
        apiRequest(`/api/equipment/types/${UNKNOWN_TYPE_ID}/out-of-service`, {
          method: 'POST',
          body,
        }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error', fieldErrors })
    },
  )

  it.skipIf(!hasTechSupport)('answers 404 for a type that does not exist', async () => {
    await signInAsTechSupport()

    const listing = await refusal(fetchOutOfService(UNKNOWN_TYPE_ID))
    const taking = await refusal(
      takeOutOfService({
        equipmentTypeId: UNKNOWN_TYPE_ID,
        body: { quantity: 1, reason: 'damaged' },
      }),
    )

    for (const error of [listing, taking]) {
      expect(error).toMatchObject({
        status: 404,
        code: 'not_found',
        message: 'Equipment type not found.',
      })
    }
  })

  it.skipIf(!hasTechSupport)(
    "flags a reservation left short and clears the flag once the units are back (AC3), in the reservation's own fields",
    async () => {
      const reference = await submittedEventReference()
      await signInAsTechSupport()
      const typeId = await newEquipmentType(2)
      await reserveEquipment(reference, { equipment_type_id: Number(typeId), quantity: 2 })

      const before = await fetchEventReservations(reference)
      const entry = await takeOutOfService({
        equipmentTypeId: typeId,
        body: { quantity: 1, reason: 'damaged' },
      })
      const flagged = await fetchEventReservations(reference)
      await returnToService(entry.id)
      const cleared = await fetchEventReservations(reference)

      for (const reservations of [before, flagged, cleared]) {
        expect(reservations).toHaveLength(1)
        expect(Object.keys(reservations[0] ?? {}).sort()).toEqual(RESERVATION_FIELDS)
      }
      expect(before[0]?.needs_attention).toBe(false)
      expect(flagged[0]?.needs_attention).toBe(true)
      expect(cleared[0]?.needs_attention).toBe(false)
    },
  )
})
