import { fetchEventEquipmentLines, recordEquipmentOutcome } from '@/features/equipment/api'
import type { EquipmentOutcomeBody } from '@/features/equipment/api'
import { apiRequest } from '@/lib/api'
import { refusal } from '@/test/refusal'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import {
  MOCK_OPEN_EVENT_REFERENCE,
  MOCK_OUTCOME_RECORDED_AT,
  mockStatusEventReference,
} from './equipmentFixtures'
import {
  expectInvalid,
  expectNotAnObject,
  NOT_FOUND,
  NOT_PERMITTED,
  NOT_SIGNED_IN,
  signInAs,
} from './test/eventRequestCalls'

/**
 * SCRUM-48: the equipment line mock records Technical Support's outcome as
 * backend/app/modules/events/routes.py `record_outcome` does (ADR-0040, ADR-0077): the same
 * body, status, refusals, wording and order of checks.
 */

/** Eight projectors asked for, no outcome yet. */
const PROJECTOR_LINE_ID = 41
/** Four microphones, all to be provided. */
const MICROPHONE_LINE_ID = 42
const NOTE_REQUIRED = 'A note is required unless the whole request can be provided.'
const ABOVE_REQUESTED = 'Cannot provide more than was requested.'
const LINE_NOT_FOUND = { status: 404, code: 'not_found', message: 'Equipment line not found.' }

function recordOnProjector(body: EquipmentOutcomeBody) {
  return recordEquipmentOutcome(MOCK_OPEN_EVENT_REFERENCE, { lineId: PROJECTOR_LINE_ID, body })
}

/** Send a body the API function's types would not let through, as a buggy client might. */
function sendRawOutcome(body: unknown) {
  const path = `/api/events/requests/${MOCK_OPEN_EVENT_REFERENCE}/equipment/${PROJECTOR_LINE_ID}/outcome`
  return apiRequest(path, { method: 'POST', body })
}

/** The projector line as the event's list shows it now. */
async function listedProjector() {
  const { equipment_lines: lines } = await fetchEventEquipmentLines(MOCK_OPEN_EVENT_REFERENCE)
  return lines.find((line) => line.id === PROJECTOR_LINE_ID)
}

describe('SCRUM-48 equipment outcome mock: recording', () => {
  it('records part of a request with its note, by whoever is signed in, and lists it (AC1)', async () => {
    // Not the Technical Support member who reviewed the microphones, so the name is the caller's.
    signInAs(MOCK_ACCOUNTS.secondTechnicalSupport)

    const recorded = await recordOnProjector({
      provided_quantity: 6,
      note: '  Two are being repaired.  ',
    })

    const expected = {
      id: PROJECTOR_LINE_ID,
      equipment_type_id: 1,
      quantity: 8,
      notes: 'Ceiling-mounted, with HDMI at the lectern.',
      status: 'partially_fulfilled',
      provided_quantity: 6,
      shortfall: 2,
      outcome_note: 'Two are being repaired.',
      reviewed_by: 'Nadia Rahim',
      reviewed_at: MOCK_OUTCOME_RECORDED_AT,
    }
    expect(recorded).toEqual(expected)
    expect(await listedProjector()).toEqual(expected)
  })

  it('records the whole request as fulfilled, keeping no note (AC2)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const recorded = await recordOnProjector({ provided_quantity: 8, note: 'All in the store.' })

    expect(recorded).toMatchObject({
      status: 'fulfilled',
      provided_quantity: 8,
      shortfall: 0,
      outcome_note: null,
      reviewed_by: 'Tariq Hassan',
    })
  })

  it('records the whole request as fulfilled with no note at all (AC2)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const recorded = await recordOnProjector({ provided_quantity: 8 })

    expect(recorded).toMatchObject({ status: 'fulfilled', outcome_note: null })
  })

  it('records none of it as unavailable, with the reason (AC3)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const recorded = await recordOnProjector({ provided_quantity: 0, note: 'All out on loan.' })

    expect(recorded).toMatchObject({
      status: 'unavailable',
      provided_quantity: 0,
      shortfall: 8,
      outcome_note: 'All out on loan.',
    })
  })

  it('revises an outcome already recorded (AC6)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const revised = await recordEquipmentOutcome(MOCK_OPEN_EVENT_REFERENCE, {
      lineId: MICROPHONE_LINE_ID,
      body: { provided_quantity: 3, note: 'One stopped working.' },
    })

    expect(revised).toMatchObject({
      status: 'partially_fulfilled',
      provided_quantity: 3,
      shortfall: 1,
      outcome_note: 'One stopped working.',
      reviewed_at: MOCK_OUTCOME_RECORDED_AT,
    })
  })

  it('finds the event whatever its case and surrounding spaces', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const recorded = await recordEquipmentOutcome(' evr-mock0001 ', {
      lineId: PROJECTOR_LINE_ID,
      body: { provided_quantity: 8 },
    })

    expect(recorded.status).toBe('fulfilled')
  })
})

describe('SCRUM-48 equipment outcome mock: refusals', () => {
  it.each([
    ['part of it', 6],
    ['none of it', 0],
  ])('needs a note when providing %s, and saves nothing (AC1, AC3)', async (_what, provided) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(recordOnProjector({ provided_quantity: provided }))

    expectInvalid(error, { note: [NOTE_REQUIRED] })
    expect(await listedProjector()).toMatchObject({ status: 'requested', provided_quantity: null })
  })

  it('counts a blank note as no note', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(recordOnProjector({ provided_quantity: 6, note: '   ' }))

    expectInvalid(error, { note: [NOTE_REQUIRED] })
  })

  it('refuses more than was asked for, but not exactly that', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(recordOnProjector({ provided_quantity: 9 }))

    expectInvalid(error, { provided_quantity: [ABOVE_REQUESTED] })
    await expect(recordOnProjector({ provided_quantity: 8 })).resolves.toMatchObject({
      status: 'fulfilled',
    })
  })

  it('names a missing quantity', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(recordOnProjector({ note: 'None to spare.' }))

    expectInvalid(error, { provided_quantity: ['Missing data for required field.'] })
  })

  it.each([
    [null, 'Field may not be null.'],
    ['6', 'Not a valid integer.'],
    [1.5, 'Not a valid integer.'],
    [true, 'Not a valid integer.'],
    [-1, 'Must be greater than or equal to 0.'],
  ])('refuses a quantity of %j on its field', async (provided, message) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(sendRawOutcome({ provided_quantity: provided, note: 'Why' }))

    expectInvalid(error, { provided_quantity: [message] })
  })

  it('refuses a note that is not text, and a field it does not know, together', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(
      sendRawOutcome({ provided_quantity: 6, note: 5, status: 'fulfilled' }),
    )

    expectInvalid(error, { note: ['Not a valid string.'], status: ['Unknown field.'] })
  })

  it.each([[[]], ['six'], [null]])(
    'refuses a body of %j that is not a JSON object',
    async (body) => {
      signInAs(MOCK_ACCOUNTS.technicalSupport)

      expectNotAnObject(await refusal(sendRawOutcome(body)))
    },
  )

  it.each([
    ['an unknown event', 'EVR-NOPE'],
    ['a draft', mockStatusEventReference('draft')],
  ])('answers 404 for %s', async (_kind, reference) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(
      recordEquipmentOutcome(reference, {
        lineId: PROJECTOR_LINE_ID,
        body: { provided_quantity: 8 },
      }),
    )

    expect(error).toMatchObject(NOT_FOUND)
  })

  it.each([
    ["another event's line", mockStatusEventReference('submitted'), PROJECTOR_LINE_ID],
    ['a line that does not exist', MOCK_OPEN_EVENT_REFERENCE, 999],
  ])('answers 404 for %s', async (_kind, reference, lineId) => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(
      recordEquipmentOutcome(reference, { lineId, body: { provided_quantity: 1 } }),
    )

    expect(error).toMatchObject(LINE_NOT_FOUND)
  })

  it('checks the body before the event, and the event before the line', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const badBody = await refusal(
      recordEquipmentOutcome('EVR-NOPE', { lineId: 999, body: { provided_quantity: -1 } }),
    )
    const badEvent = await refusal(
      recordEquipmentOutcome('EVR-NOPE', { lineId: 999, body: { provided_quantity: 1 } }),
    )

    expect(badBody).toMatchObject({ status: 400 })
    expect(badEvent).toMatchObject(NOT_FOUND)
  })

  it('checks the line before what it asked for', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const error = await refusal(
      recordEquipmentOutcome(MOCK_OPEN_EVENT_REFERENCE, {
        lineId: 999,
        body: { provided_quantity: 100 },
      }),
    )

    expect(error).toMatchObject(LINE_NOT_FOUND)
  })

  // One account for each role but Technical Support.
  it.each([
    MOCK_ACCOUNTS.attendee,
    MOCK_ACCOUNTS.organiser,
    MOCK_ACCOUNTS.coordinator,
    MOCK_ACCOUNTS.lead,
    MOCK_ACCOUNTS.venueStaff,
    MOCK_ACCOUNTS.safetyOfficer,
  ])('refuses $role with a 403: only Technical Support record an outcome', async (account) => {
    signInAs(account)

    const error = await refusal(recordOnProjector({ provided_quantity: 8 }))

    expect(error).toMatchObject(NOT_PERMITTED)
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect(await listedProjector()).toMatchObject({ status: 'requested' })
  })

  it('refuses a visitor with a 401', async () => {
    signInAs(null)

    expect(await refusal(recordOnProjector({ provided_quantity: 8 }))).toMatchObject(NOT_SIGNED_IN)
  })
})
