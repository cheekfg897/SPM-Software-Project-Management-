import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import {
  addEquipmentLine,
  fetchEquipmentTypes,
  fetchEventAvailability,
  fetchEventEquipmentLines,
  removeEquipmentLine,
  updateEquipmentLine,
} from '@/features/equipment/api'
import type { EquipmentLineBody } from '@/features/equipment/api'
import { apiRequest, ApiError } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'
import {
  MOCK_CLOSED_EVENT_REFERENCE,
  MOCK_OPEN_EVENT_REFERENCE,
  MOCK_OTHER_COORDINATORS_EVENT_REFERENCE,
  mockStatusEventReference,
} from './equipmentFixtures'

/**
 * The equipment line mock mirrors backend/app/modules/events/routes.py (SCRUM-37, ADR-0019,
 * ADR-0028) and the equipment types list (SCRUM-27): the same bodies, refusals, wording and
 * order of checks.
 */

const PROJECTOR_LINE_ID = 41
const MICROPHONE_LINE_ID = 42
const PROJECTOR_TYPE_ID = 1
const MICROPHONE_TYPE_ID = 2
const LECTERN_TYPE_ID = 3
const UNKNOWN_ID = 999

const NOT_FOUND_MESSAGE = 'Event request not found.'
const LINE_NOT_FOUND_MESSAGE = 'Equipment line not found.'
const NOT_EDITABLE_MESSAGE =
  'Equipment can only be changed while the request is submitted, under review or approved.'
const DUPLICATE_MESSAGE =
  'This event already has a line for that equipment type. Edit that line instead.'
const MISSING_MESSAGE = 'Missing data for required field.'
const NOT_AN_INTEGER_MESSAGE = 'Not a valid integer.'

/** Statuses in which an event's equipment may change (EQUIPMENT_EDITABLE_STATUSES). */
const EDITABLE_STATUSES: readonly EventRequestStatus[] = ['submitted', 'under_review', 'approved']
/** The rest, but a draft, which staff never find. Built from every status, so a new one is tested. */
const LOCKED_STATUSES = Object.values(EVENT_REQUEST_STATUS).filter(
  (status) => status !== 'draft' && !EDITABLE_STATUSES.includes(status),
)

const LECTERN: EquipmentLineBody = { equipment_type_id: LECTERN_TYPE_ID, quantity: 2 }

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

/** The coordinator's own event in `status`. */
function eventIn(status: EventRequestStatus): string {
  return mockStatusEventReference(status)
}

/** Send a line body the API functions' types would not let through, as a buggy client might. */
function sendRawLine(body: unknown, lineId?: number) {
  const linesPath = `/api/events/requests/${MOCK_OPEN_EVENT_REFERENCE}/equipment`
  if (lineId === undefined) {
    return apiRequest(linesPath, { method: 'POST', body })
  }
  return apiRequest(`${linesPath}/${lineId}`, { method: 'PATCH', body })
}

/** The ApiError a call was refused with. Fails the test if it succeeded. */
async function refusalOf(call: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await call.then(
    () => expect.fail('Expected the mock to refuse the request.'),
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error(`Expected an ApiError, got ${String(error)}`)
  }
  return error
}

async function openEventLines() {
  const { equipment_lines: lines } = await fetchEventEquipmentLines(MOCK_OPEN_EVENT_REFERENCE)
  return lines
}

describe('SCRUM-37 equipment line mock: listing', () => {
  it('answers the event and its lines in the order added, with each outcome', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const listed = await fetchEventEquipmentLines(MOCK_OPEN_EVENT_REFERENCE)

    expect(listed).toEqual({
      event: {
        reference: MOCK_OPEN_EVENT_REFERENCE,
        name: 'Annual Partner Summit',
        proposed_date: '2026-10-12',
        end_date: '2026-10-12',
        start_time: '19:30:00',
        end_time: '22:00:00',
      },
      equipment_lines: [
        {
          id: PROJECTOR_LINE_ID,
          equipment_type_id: PROJECTOR_TYPE_ID,
          quantity: 8,
          notes: 'Ceiling-mounted, with HDMI at the lectern.',
          status: 'requested',
          provided_quantity: null,
          shortfall: null,
          outcome_note: null,
          reviewed_by: null,
          reviewed_at: null,
        },
        {
          id: MICROPHONE_LINE_ID,
          equipment_type_id: MICROPHONE_TYPE_ID,
          quantity: 4,
          notes: null,
          status: 'fulfilled',
          provided_quantity: 4,
          shortfall: 0,
          outcome_note: null,
          reviewed_by: 'Tariq Hassan',
          reviewed_at: '2026-10-05T10:00:00+08:00',
        },
      ],
    })
  })

  it('works the shortfall out from the quantity and what will be provided', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    await updateEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, {
      lineId: MICROPHONE_LINE_ID,
      body: { quantity: 7 },
    })

    const [, microphone] = await openEventLines()

    expect(microphone).toMatchObject({ quantity: 7, provided_quantity: 4, shortfall: 3 })
  })

  it("lets Technical Support read any event's lines, another coordinator's too", async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const listed = await fetchEventEquipmentLines(MOCK_OTHER_COORDINATORS_EVENT_REFERENCE)

    expect(listed).toMatchObject({ event: { name: 'Alumni Dinner' }, equipment_lines: [] })
  })

  it.each([
    ['an unknown event', 'EVR-NOPE'],
    ['an unassigned event', MOCK_CLOSED_EVENT_REFERENCE],
    ["another coordinator's event", MOCK_OTHER_COORDINATORS_EVENT_REFERENCE],
    ['a draft', eventIn('draft')],
  ])('answers a coordinator 404 for %s', async (_kind, reference) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(fetchEventEquipmentLines(reference)).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
      message: NOT_FOUND_MESSAGE,
    })
  })

  it('answers Technical Support 404 for a draft', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(fetchEventEquipmentLines(eventIn('draft'))).rejects.toMatchObject({
      status: 404,
    })
  })

  it('finds the event whatever its case and surrounding spaces', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const listed = await fetchEventEquipmentLines(' evr-mock0001 ')

    expect(listed.equipment_lines).toHaveLength(2)
  })

  it.each([
    MOCK_ACCOUNTS.organiser,
    MOCK_ACCOUNTS.attendee,
    MOCK_ACCOUNTS.venueStaff,
    MOCK_ACCOUNTS.lead,
  ])('refuses $role with a 403', async (account) => {
    signInAs(account)

    await expect(fetchEventEquipmentLines(MOCK_OPEN_EVENT_REFERENCE)).rejects.toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it('refuses a visitor with a 401', async () => {
    sendRequestsAs(null)

    await expect(fetchEventEquipmentLines(MOCK_OPEN_EVENT_REFERENCE)).rejects.toMatchObject({
      status: 401,
    })
  })
})

describe('SCRUM-37 equipment line mock: adding (AC1, AC3)', () => {
  it('adds a requested line, trimming the notes, and lists it last', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const added = await addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, {
      ...LECTERN,
      notes: '  Stage left  ',
    })

    expect(added).toEqual({
      id: expect.any(Number) as number,
      equipment_type_id: LECTERN_TYPE_ID,
      quantity: 2,
      notes: 'Stage left',
      status: 'requested',
    })
    const lines = await openEventLines()
    expect(lines.map((line) => line.id)).toEqual([PROJECTOR_LINE_ID, MICROPHONE_LINE_ID, added.id])
    expect(lines[2]).toMatchObject({ provided_quantity: null, shortfall: null })
  })

  it("counts the new line in the event's availability", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, LECTERN)

    const rows = await fetchEventAvailability(MOCK_OPEN_EVENT_REFERENCE)
    expect(rows[0]).toMatchObject({ equipment_type_name: 'Lectern', requested: 2 })
  })

  it('gives each new line its own id', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const first = await addEquipmentLine(eventIn('submitted'), LECTERN)
    const second = await addEquipmentLine(eventIn('under_review'), LECTERN)

    expect(second.id).not.toBe(first.id)
    expect([first.id, second.id]).not.toContain(PROJECTOR_LINE_ID)
  })

  it.each([
    ['blank', { ...LECTERN, notes: '   ' }],
    ['left out', LECTERN],
    ['null', { ...LECTERN, notes: null }],
  ])('stores %s notes as none', async (_kind, body) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const added = await sendRawLine(body)

    expect(added).toMatchObject({ notes: null })
  })

  it('names each missing field', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, {})).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Invalid request.',
      fieldErrors: { equipment_type_id: [MISSING_MESSAGE], quantity: [MISSING_MESSAGE] },
    })
  })

  it.each([0, -1])('refuses a quantity of %i (AC3)', async (quantity) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, { ...LECTERN, quantity }),
    ).rejects.toMatchObject({
      status: 400,
      fieldErrors: { quantity: ['Quantity must be at least 1.'] },
    })
  })

  it('accepts a quantity of 1', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, { ...LECTERN, quantity: 1 }),
    ).resolves.toMatchObject({ quantity: 1 })
  })

  it.each([
    ['text', '1', NOT_AN_INTEGER_MESSAGE],
    ['a fraction', 1.5, NOT_AN_INTEGER_MESSAGE],
    ['true', true, NOT_AN_INTEGER_MESSAGE],
    ['null', null, 'Field may not be null.'],
    ['zero', 0, 'equipment_type_id must be a positive number.'],
  ])('refuses an equipment type id that is %s, and only that', async (_kind, value, message) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const error = await refusalOf(sendRawLine({ quantity: 1, equipment_type_id: value }))

    expect(error.fieldErrors).toEqual({ equipment_type_id: [message] })
  })

  it.each([
    ['text', '2', NOT_AN_INTEGER_MESSAGE],
    ['a fraction', 2.5, NOT_AN_INTEGER_MESSAGE],
    ['true', true, NOT_AN_INTEGER_MESSAGE],
    ['null', null, 'Field may not be null.'],
  ])('refuses a quantity that is %s', async (_kind, value, message) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const error = await refusalOf(
      sendRawLine({ equipment_type_id: LECTERN_TYPE_ID, quantity: value }),
    )

    expect(error.fieldErrors).toEqual({ quantity: [message] })
  })

  it('refuses notes that are not text, and a field it does not know', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const error = await refusalOf(sendRawLine({ ...LECTERN, notes: 5, status: 'fulfilled' }))

    expect(error.fieldErrors).toEqual({
      notes: ['Not a valid string.'],
      status: ['Unknown field.'],
    })
  })

  it.each([
    ['a list', []],
    ['text', 'Lectern'],
    ['nothing', undefined],
  ])('refuses a body that is %s, naming no field', async (_kind, body) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const error = await refusalOf(sendRawLine(body))

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Request body must be a JSON object.',
      fieldErrors: {},
    })
  })

  it('refuses an equipment type the catalogue does not have', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, { ...LECTERN, equipment_type_id: UNKNOWN_ID }),
    ).rejects.toMatchObject({
      status: 400,
      fieldErrors: { equipment_type_id: ['Equipment type not found.'] },
    })
  })

  it('refuses a second line for the same equipment type', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, {
        ...LECTERN,
        equipment_type_id: PROJECTOR_TYPE_ID,
      }),
    ).rejects.toMatchObject({ status: 409, code: 'conflict', message: DUPLICATE_MESSAGE })
    await expect(openEventLines()).resolves.toHaveLength(2)
  })

  it.each(EDITABLE_STATUSES)('adds a line to an event that is %s', async (status) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(addEquipmentLine(eventIn(status), LECTERN)).resolves.toMatchObject({
      equipment_type_id: LECTERN_TYPE_ID,
    })
  })

  it.each(LOCKED_STATUSES)('refuses a line on an event that is %s', async (status) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(addEquipmentLine(eventIn(status), LECTERN)).rejects.toMatchObject({
      status: 409,
      code: 'equipment_not_editable',
      message: NOT_EDITABLE_MESSAGE,
    })
  })

  it('checks the body first, then the event, then whether it is editable, then the type', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const unknownType = { ...LECTERN, equipment_type_id: UNKNOWN_ID }

    await expect(addEquipmentLine('EVR-NOPE', {})).rejects.toMatchObject({ status: 400 })
    await expect(
      addEquipmentLine(MOCK_OTHER_COORDINATORS_EVENT_REFERENCE, unknownType),
    ).rejects.toMatchObject({ status: 404 })
    await expect(addEquipmentLine(eventIn('confirmed'), unknownType)).rejects.toMatchObject({
      status: 409,
    })
  })

  it.each([
    ['an unassigned event', MOCK_CLOSED_EVENT_REFERENCE],
    ["another coordinator's event", MOCK_OTHER_COORDINATORS_EVENT_REFERENCE],
    ['a draft', eventIn('draft')],
  ])('answers a coordinator 404 for %s', async (_kind, reference) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(addEquipmentLine(reference, LECTERN)).rejects.toMatchObject({
      status: 404,
      message: NOT_FOUND_MESSAGE,
    })
  })

  it.each([MOCK_ACCOUNTS.technicalSupport, MOCK_ACCOUNTS.lead, MOCK_ACCOUNTS.organiser])(
    'refuses $role with a 403: only the coordinator records equipment',
    async (account) => {
      signInAs(account)

      await expect(addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, LECTERN)).rejects.toMatchObject({
        status: 403,
      })
    },
  )

  it('refuses a visitor with a 401', async () => {
    sendRequestsAs(null)

    await expect(addEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, LECTERN)).rejects.toMatchObject({
      status: 401,
    })
  })
})

describe('SCRUM-37 equipment line mock: changing (AC2, AC3)', () => {
  function change(lineId: number, body: EquipmentLineBody, reference = MOCK_OPEN_EVENT_REFERENCE) {
    return updateEquipmentLine(reference, { lineId, body })
  }

  it('changes only the fields sent', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const changed = await change(PROJECTOR_LINE_ID, { quantity: 9 })

    expect(changed).toEqual({
      id: PROJECTOR_LINE_ID,
      equipment_type_id: PROJECTOR_TYPE_ID,
      quantity: 9,
      notes: 'Ceiling-mounted, with HDMI at the lectern.',
      status: 'requested',
    })
    const [projector] = await openEventLines()
    expect(projector).toMatchObject({ quantity: 9 })
  })

  it('changes nothing for an empty body', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(change(PROJECTOR_LINE_ID, {})).resolves.toMatchObject({ quantity: 8 })
  })

  it.each([
    ['null', null],
    ['blank', '  '],
  ])('clears the notes when they are sent %s', async (_kind, notes) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(sendRawLine({ notes }, PROJECTOR_LINE_ID)).resolves.toMatchObject({
      notes: null,
      quantity: 8,
    })
  })

  it('moves a line to another equipment type, or keeps its own', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      change(PROJECTOR_LINE_ID, { equipment_type_id: PROJECTOR_TYPE_ID }),
    ).resolves.toMatchObject({ equipment_type_id: PROJECTOR_TYPE_ID })
    await expect(
      change(PROJECTOR_LINE_ID, { equipment_type_id: LECTERN_TYPE_ID }),
    ).resolves.toMatchObject({ equipment_type_id: LECTERN_TYPE_ID })
  })

  it("refuses moving a line to a type another of the event's lines has", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      change(PROJECTOR_LINE_ID, { equipment_type_id: MICROPHONE_TYPE_ID }),
    ).rejects.toMatchObject({ status: 409, message: DUPLICATE_MESSAGE })
    const [projector] = await openEventLines()
    expect(projector).toMatchObject({ equipment_type_id: PROJECTOR_TYPE_ID })
  })

  it.each([
    [{ quantity: 0 }, { quantity: ['Quantity must be at least 1.'] }],
    [{ quantity: null }, { quantity: ['Field may not be null.'] }],
    [{ equipment_type_id: true }, { equipment_type_id: [NOT_AN_INTEGER_MESSAGE] }],
    [{ notes: 5 }, { notes: ['Not a valid string.'] }],
    [{ status: 'fulfilled' }, { status: ['Unknown field.'] }],
  ])('checks a sent field as adding does, and asks for no other: %j', async (body, errors) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const error = await refusalOf(sendRawLine(body, PROJECTOR_LINE_ID))

    expect(error.fieldErrors).toEqual(errors)
  })

  it('refuses a change whose body is not a JSON object', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const error = await refusalOf(sendRawLine([], PROJECTOR_LINE_ID))

    expect(error).toMatchObject({ status: 400, message: 'Request body must be a JSON object.' })
  })

  it('refuses an unknown equipment type', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      change(PROJECTOR_LINE_ID, { equipment_type_id: UNKNOWN_ID }),
    ).rejects.toMatchObject({ fieldErrors: { equipment_type_id: ['Equipment type not found.'] } })
  })

  it('refuses a quantity below what Technical Support will provide, but not equal to it', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(change(MICROPHONE_LINE_ID, { quantity: 3 })).rejects.toMatchObject({
      status: 400,
      fieldErrors: {
        quantity: [
          'Quantity cannot be below the 4 units Technical Support has said they will provide.',
        ],
      },
    })
    await expect(change(MICROPHONE_LINE_ID, { quantity: 4 })).resolves.toMatchObject({
      quantity: 4,
    })
  })

  it('lets a line with no outcome go down to 1', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(change(PROJECTOR_LINE_ID, { quantity: 1 })).resolves.toMatchObject({
      quantity: 1,
    })
  })

  it("answers 404 for a line that is not this event's", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const elsewhere = await addEquipmentLine(eventIn('submitted'), LECTERN)

    for (const lineId of [UNKNOWN_ID, elsewhere.id]) {
      await expect(change(lineId, { quantity: 2 })).rejects.toMatchObject({
        status: 404,
        code: 'not_found',
        message: LINE_NOT_FOUND_MESSAGE,
      })
    }
  })

  it.each(EDITABLE_STATUSES)('changes a line of an event that is %s', async (status) => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const added = await addEquipmentLine(eventIn(status), LECTERN)

    await expect(change(added.id, { quantity: 3 }, eventIn(status))).resolves.toMatchObject({
      quantity: 3,
    })
  })

  it.each(LOCKED_STATUSES)('refuses a change on an event that is %s', async (status) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(change(UNKNOWN_ID, { quantity: 2 }, eventIn(status))).rejects.toMatchObject({
      status: 409,
      code: 'equipment_not_editable',
    })
  })

  it('checks the body before the event, and the event before the line', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(change(PROJECTOR_LINE_ID, { quantity: 0 }, 'EVR-NOPE')).rejects.toMatchObject({
      status: 400,
    })
    await expect(
      change(UNKNOWN_ID, { quantity: 2 }, MOCK_OTHER_COORDINATORS_EVENT_REFERENCE),
    ).rejects.toMatchObject({ status: 404, message: NOT_FOUND_MESSAGE })
  })

  it('checks the line before the equipment type', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(change(UNKNOWN_ID, { equipment_type_id: UNKNOWN_ID })).rejects.toMatchObject({
      status: 404,
      message: LINE_NOT_FOUND_MESSAGE,
    })
  })

  it('refuses Technical Support with a 403, and a visitor with a 401', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await expect(change(PROJECTOR_LINE_ID, { quantity: 2 })).rejects.toMatchObject({
      status: 403,
    })

    sendRequestsAs(null)
    await expect(change(PROJECTOR_LINE_ID, { quantity: 2 })).rejects.toMatchObject({
      status: 401,
    })
  })
})

describe('SCRUM-37 equipment line mock: removing (AC2)', () => {
  it('removes the line, so neither the list nor availability counts it', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      removeEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, PROJECTOR_LINE_ID),
    ).resolves.toBeUndefined()

    const lines = await openEventLines()
    expect(lines.map((line) => line.id)).toEqual([MICROPHONE_LINE_ID])
    const rows = await fetchEventAvailability(MOCK_OPEN_EVENT_REFERENCE)
    expect(rows[2]).toMatchObject({ equipment_type_name: 'Projector', requested: 0 })
  })

  it("answers 404 for a line that is not this event's", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const elsewhere = await addEquipmentLine(eventIn('submitted'), LECTERN)

    for (const lineId of [UNKNOWN_ID, elsewhere.id]) {
      await expect(removeEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, lineId)).rejects.toMatchObject({
        status: 404,
        message: LINE_NOT_FOUND_MESSAGE,
      })
    }
    await expect(fetchEventEquipmentLines(eventIn('submitted'))).resolves.toMatchObject({
      equipment_lines: [{ id: elsewhere.id }],
    })
  })

  it.each(LOCKED_STATUSES)('refuses removing from an event that is %s', async (status) => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(removeEquipmentLine(eventIn(status), UNKNOWN_ID)).rejects.toMatchObject({
      status: 409,
      code: 'equipment_not_editable',
    })
  })

  it("answers 404 for another coordinator's event", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(
      removeEquipmentLine(MOCK_OTHER_COORDINATORS_EVENT_REFERENCE, PROJECTOR_LINE_ID),
    ).rejects.toMatchObject({ status: 404, message: NOT_FOUND_MESSAGE })
  })

  it('refuses Technical Support with a 403, and a visitor with a 401', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await expect(
      removeEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, PROJECTOR_LINE_ID),
    ).rejects.toMatchObject({ status: 403 })

    sendRequestsAs(null)
    await expect(
      removeEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, PROJECTOR_LINE_ID),
    ).rejects.toMatchObject({ status: 401 })
  })
})

describe('SCRUM-27 equipment types mock', () => {
  it('lists every type by name, as the catalogue shows it', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const types = await fetchEquipmentTypes()

    expect(types.map((type) => type.name)).toEqual(['Lectern', 'Microphone', 'Projector'])
    expect(types[2]).toEqual({
      id: PROJECTOR_TYPE_ID,
      name: 'Projector',
      description: 'Full HD, with HDMI and USB-C.',
      total_quantity: 10,
      venue_id: null,
      store_name: 'Main store',
    })
  })

  it.each([
    MOCK_ACCOUNTS.coordinator,
    MOCK_ACCOUNTS.lead,
    MOCK_ACCOUNTS.venueStaff,
    MOCK_ACCOUNTS.technicalSupport,
  ])('lets $role read it', async (account) => {
    signInAs(account)

    await expect(fetchEquipmentTypes()).resolves.toHaveLength(3)
  })

  it.each([MOCK_ACCOUNTS.organiser, MOCK_ACCOUNTS.attendee])(
    'refuses $role with a 403',
    async (account) => {
      signInAs(account)

      await expect(fetchEquipmentTypes()).rejects.toMatchObject({ status: 403 })
    },
  )

  it('refuses a visitor with a 401', async () => {
    sendRequestsAs(null)

    await expect(fetchEquipmentTypes()).rejects.toMatchObject({ status: 401 })
  })
})
