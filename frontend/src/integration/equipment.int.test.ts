import {
  addEquipmentLine,
  fetchEventEquipmentLines,
  recordEquipmentOutcome,
  removeEquipmentLine,
  updateEquipmentLine,
} from '@/features/equipment/api'
import { fetchEquipmentTypes } from '@/features/equipmentCatalogue/api'
import { fetchEventRequest } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  hasTechSupport,
  refusal,
  signInAs,
  signInAsNewAttendee,
  signInAsTechSupport,
  staffAccount,
  uniqueEmail,
} from './backend'
import {
  approvedEvent,
  coordinatorPosts,
  LEAD,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-37's equipment lines and SCRUM-27's equipment types against the running backend: the
 * paths, roles, refusals and wording the equipment page relies on (ADR-0019, ADR-0065).
 *
 * The staff account is an Event Coordinator. The checks that need an assigned event take one
 * through plannedEvent.ts when CI has the accounts for it; the rest are still todos.
 */

/** A well-formed reference no database has, so the lookup finds nothing. */
const UNKNOWN_EVENT_REFERENCE = 'EVR-NOSUCH00'
/** A line id no event has. */
const UNKNOWN_LINE_ID = 987654
const NOT_FOUND_MESSAGE = 'Event request not found.'
const MISSING_MESSAGE = 'Missing data for required field.'

/** Every field the frontend's EquipmentType reads, and nothing more. */
const EQUIPMENT_TYPE_FIELDS = [
  'description',
  'id',
  'name',
  'store_name',
  'total_quantity',
  'venue_id',
]

/** Whether a check can take an event to Approved (a Lead assigns it) and record an outcome. */
const canReviewALine = hasTechSupport && LEAD !== null
/** Whether a check can also take the event through the safety check to Confirmed. */
const canConfirm = canReviewALine && VENUE_STAFF !== null && SAFETY_OFFICER !== null

/** As Technical Support: a new equipment type with ten units; answers its id. */
async function newEquipmentType(): Promise<number> {
  await signInAsTechSupport()
  const type = await apiRequest<{ id: number }>('/api/equipment/types', {
    method: 'POST',
    body: {
      name: `Integration Lectern ${uniqueEmail('type')}`,
      total_quantity: 10,
      store_name: 'Integration store',
    },
  })
  return type.id
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-27 equipment types against the backend', () => {
  it('lists the catalogue to a coordinator, each type with exactly the fields the screen reads', async () => {
    await signInAs(staffAccount())

    const types = await fetchEquipmentTypes()

    expect(Array.isArray(types)).toBe(true)
    for (const type of types) {
      expect(Object.keys(type).sort()).toEqual(EQUIPMENT_TYPE_FIELDS)
    }
  })

  it('refuses an attendee (403) and a visitor (401)', async () => {
    const visitor = await refusal(fetchEquipmentTypes())
    await signInAsNewAttendee()
    const attendee = await refusal(fetchEquipmentTypes())

    expect(visitor).toMatchObject({ status: 401, code: 'authentication_error' })
    expect(attendee).toMatchObject({ status: 403, code: 'authorization_error' })
  })
})

describe('SCRUM-37 equipment lines against the backend', () => {
  const calls = [
    ['listing', () => fetchEventEquipmentLines(UNKNOWN_EVENT_REFERENCE)],
    [
      'adding',
      () => addEquipmentLine(UNKNOWN_EVENT_REFERENCE, { equipment_type_id: 1, quantity: 1 }),
    ],
    [
      'changing',
      () =>
        updateEquipmentLine(UNKNOWN_EVENT_REFERENCE, {
          lineId: UNKNOWN_LINE_ID,
          body: { quantity: 2 },
        }),
    ],
    ['removing', () => removeEquipmentLine(UNKNOWN_EVENT_REFERENCE, UNKNOWN_LINE_ID)],
  ] as const

  it.each(calls)('refuses %s without a token (401)', async (_name, call) => {
    const error = await refusal(call())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it.each(calls)('refuses an attendee %s (403)', async (_name, call) => {
    await signInAsNewAttendee()

    const error = await refusal(call())

    expect(error).toMatchObject({ status: 403, code: 'authorization_error' })
  })

  it.each(calls)(
    'answers a coordinator 404 when %s for an event that is not theirs',
    async (_name, call) => {
      await signInAs(staffAccount())

      const error = await refusal(call())

      expect(error).toMatchObject({ status: 404, code: 'not_found', message: NOT_FOUND_MESSAGE })
    },
  )

  it('names each missing field when adding (400), before looking for the event', async () => {
    await signInAs(staffAccount())

    const error = await refusal(addEquipmentLine(UNKNOWN_EVENT_REFERENCE, {}))

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      equipment_type_id: [MISSING_MESSAGE],
      quantity: [MISSING_MESSAGE],
    })
  })

  it.each([0, -1])('refuses a quantity of %i on its field (AC3)', async (quantity) => {
    await signInAs(staffAccount())

    const adding = await refusal(
      addEquipmentLine(UNKNOWN_EVENT_REFERENCE, { equipment_type_id: 1, quantity }),
    )
    const changing = await refusal(
      updateEquipmentLine(UNKNOWN_EVENT_REFERENCE, {
        lineId: UNKNOWN_LINE_ID,
        body: { quantity },
      }),
    )

    for (const error of [adding, changing]) {
      expect(error.status).toBe(400)
      expect(error.fieldErrors).toEqual({ quantity: ['Quantity must be at least 1.'] })
    }
  })

  it('refuses a cleared quantity sent as null on its field', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      updateEquipmentLine(UNKNOWN_EVENT_REFERENCE, {
        lineId: UNKNOWN_LINE_ID,
        body: { quantity: null },
      }),
    )

    expect(error.fieldErrors).toEqual({ quantity: ['Field may not be null.'] })
  })

  it('refuses a body that is not a JSON object, naming no field', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      apiRequest(`/api/events/requests/${UNKNOWN_EVENT_REFERENCE}/equipment`, {
        method: 'POST',
        body: [],
      }),
    )

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Request body must be a JSON object.',
      fieldErrors: {},
    })
  })

  it.todo(
    "lists an assigned event's lines in the order added, each with exactly EquipmentLine's fields, and the event's reference, name, dates and times (needs an assigned event)",
  )
  it.todo('adds a line (201) answering exactly SavedEquipmentLine, with blank notes as null')
  it.todo('refuses a second line for the same equipment type (409 conflict)')
  it.todo('changes only the fields sent, and {} changes nothing (200)')
  it.todo('refuses an unknown equipment type on equipment_type_id (400)')
  it.todo('answers 404 "Equipment line not found." for another event\'s line')
  it.todo('removes a line (204), so the list no longer has it')
  it.skipIf(!canConfirm)(
    'refuses a change once the event is confirmed (409 equipment_not_editable, with the backend wording)',
    async () => {
      const equipmentTypeId = await newEquipmentType()
      const event = await safetyApprovedEvent()
      await coordinatorPosts(event.reference, 'confirm')

      const error = await refusal(
        addEquipmentLine(event.reference, { equipment_type_id: equipmentTypeId, quantity: 1 }),
      )

      expect(error).toMatchObject({
        status: 409,
        code: 'equipment_not_editable',
        message:
          'Equipment can only be changed before the event is confirmed, and not once it is rejected or cancelled.',
      })
    },
  )

  it.skipIf(!canReviewALine)(
    'reopens a reviewed line for Technical Support when its quantity changes, clearing the outcome (SCRUM-37 AC4)',
    async () => {
      const equipmentTypeId = await newEquipmentType()
      const event = await approvedEvent()
      const line = await addEquipmentLine(event.reference, {
        equipment_type_id: equipmentTypeId,
        quantity: 4,
      })
      await signInAsTechSupport()
      await recordEquipmentOutcome(event.reference, {
        lineId: line.id,
        body: { provided_quantity: 4 },
      })
      await signInAs(staffAccount())

      await updateEquipmentLine(event.reference, { lineId: line.id, body: { quantity: 6 } })

      const { equipment_lines: lines } = await fetchEventEquipmentLines(event.reference)
      expect(lines).toEqual([
        expect.objectContaining({
          id: line.id,
          quantity: 6,
          status: 'requested',
          provided_quantity: null,
          outcome_note: null,
          reviewed_by: null,
        }),
      ])
    },
  )
  it.todo("lets Technical Support list any event's lines but refuses them adding one (403)")
})

describe('SCRUM-48 equipment outcomes against the backend', () => {
  /** An outcome for a line of an event no database has. */
  function recordUnknown(body: unknown) {
    return apiRequest(
      `/api/events/requests/${UNKNOWN_EVENT_REFERENCE}/equipment/${UNKNOWN_LINE_ID}/outcome`,
      { method: 'POST', body },
    )
  }

  function recordWholeRequest() {
    return recordEquipmentOutcome(UNKNOWN_EVENT_REFERENCE, {
      lineId: UNKNOWN_LINE_ID,
      body: { provided_quantity: 1 },
    })
  }

  it('refuses a visitor (401)', async () => {
    const error = await refusal(recordWholeRequest())

    expect(error).toMatchObject({ status: 401, code: 'authentication_error' })
  })

  it('refuses an Event Coordinator and an attendee (403): only Technical Support record one', async () => {
    await signInAs(staffAccount())
    const coordinator = await refusal(recordWholeRequest())
    await signInAsNewAttendee()
    const attendee = await refusal(recordWholeRequest())

    for (const error of [coordinator, attendee]) {
      expect(error).toMatchObject({
        status: 403,
        code: 'authorization_error',
        message: 'You do not have permission to perform this action.',
      })
    }
  })

  it.skipIf(!hasTechSupport)(
    'names a missing quantity (400), before looking for the event',
    async () => {
      await signInAsTechSupport()

      const error = await refusal(
        recordEquipmentOutcome(UNKNOWN_EVENT_REFERENCE, {
          lineId: UNKNOWN_LINE_ID,
          body: { note: 'None to spare.' },
        }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({ provided_quantity: [MISSING_MESSAGE] })
    },
  )

  it.skipIf(!hasTechSupport).each([
    [-1, 'Must be greater than or equal to 0.'],
    [null, 'Field may not be null.'],
    ['6', 'Not a valid integer.'],
  ])('refuses a quantity of %j on its field', async (provided, message) => {
    await signInAsTechSupport()

    const error = await refusal(recordUnknown({ provided_quantity: provided }))

    expect(error.fieldErrors).toEqual({ provided_quantity: [message] })
  })

  it.skipIf(!hasTechSupport)(
    'refuses a note that is not text and a field it does not know',
    async () => {
      await signInAsTechSupport()

      const error = await refusal(
        recordUnknown({ provided_quantity: 1, note: 5, status: 'fulfilled' }),
      )

      expect(error.fieldErrors).toEqual({
        note: ['Not a valid string.'],
        status: ['Unknown field.'],
      })
    },
  )

  it.skipIf(!hasTechSupport)(
    'refuses a body that is not a JSON object, naming no field',
    async () => {
      await signInAsTechSupport()

      const error = await refusal(recordUnknown([]))

      expect(error).toMatchObject({
        status: 400,
        message: 'Request body must be a JSON object.',
        fieldErrors: {},
      })
    },
  )

  it.skipIf(!hasTechSupport)('answers 404 for an event that does not exist', async () => {
    await signInAsTechSupport()

    const error = await refusal(recordWholeRequest())

    expect(error).toMatchObject({ status: 404, code: 'not_found', message: NOT_FOUND_MESSAGE })
  })

  it.todo(
    "records part of an assigned event's line, answering exactly EquipmentLine's fields with partially_fulfilled, the shortfall, the trimmed note and the reviewer's name (needs an assigned event)",
  )
  it.todo(
    'refuses part of a line with no note, on note, and more than was asked for, on provided_quantity',
  )
  it.todo('records the whole line as fulfilled, keeping no note, and revises it')
  it.todo('answers 404 "Equipment line not found." for another event\'s line')

  it.skipIf(!canReviewALine)(
    "shows the organiser each line's type, quantity, status and quantity provided, but not the notes, outcome note or reviewer (AC5, SCRUM-37 AC5)",
    async () => {
      const equipmentTypeId = await newEquipmentType()
      const { name: typeName } = await apiRequest<{ name: string }>(
        `/api/equipment/types/${String(equipmentTypeId)}`,
      )
      const event = await approvedEvent()
      const line = await addEquipmentLine(event.reference, {
        equipment_type_id: equipmentTypeId,
        quantity: 10,
        notes: 'Two at the back of the hall.',
      })
      await signInAsTechSupport()
      await recordEquipmentOutcome(event.reference, {
        lineId: line.id,
        body: { provided_quantity: 6, note: 'Four are out for repair.' },
      })
      await signInAs(event.organiser)

      const organisersRecord = await fetchEventRequest(event.reference)
      await signInAs(staffAccount())
      const coordinatorsRecord = await fetchEventRequest(event.reference)

      expect(organisersRecord.equipment_lines).toEqual([
        {
          id: line.id,
          equipment_type_name: typeName,
          quantity: 10,
          status: 'partially_fulfilled',
          provided_quantity: 6,
        },
      ])
      expect(coordinatorsRecord.equipment_lines).toEqual([
        {
          id: line.id,
          equipment_type_id: equipmentTypeId,
          quantity: 10,
          notes: 'Two at the back of the hall.',
          status: 'partially_fulfilled',
        },
      ])
    },
  )
  // SCRUM-48 AC8 (an outcome on a closed event) is checked in planning.int.test.ts, on an
  // event the coordinator rejected: nothing can cancel an event yet (SCRUM-61).
})
