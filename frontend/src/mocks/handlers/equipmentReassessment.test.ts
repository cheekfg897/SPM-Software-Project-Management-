import {
  confirmReassessment,
  fetchEventEquipmentLines,
  fetchEventReassessments,
  fetchEventReservations,
  recordEquipmentOutcome,
  reserveEquipment,
  updateEquipmentLine,
  updateReservationPreparation,
} from '@/features/equipment/api'
import { fetchEquipmentAwaitingAction } from '@/features/techSupport/api'
import { apiRequest } from '@/lib/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import {
  MOCK_CLOSED_EVENT_REFERENCE,
  MOCK_EVENT_PERIOD,
  MOCK_MOVED_EVENT_REFERENCE,
  MOCK_OLD_EVENT_PERIOD,
  MOCK_OPEN_EVENT_REFERENCE,
  MOCK_OTHER_COORDINATORS_EVENT_REFERENCE,
  mockStatusEventReference,
} from './equipmentFixtures'
import { markReservationsOfType, saveReservation } from './equipmentReservations'

/**
 * SCRUM-60 in the mock backend, pinned to what backend/app/modules/equipment answers (ADR-0114):
 * what a change left to reassess and its shortfall (AC2), confirming it for the event's period now
 * (AC3) with each refusal, an outcome settling it (AC4, AC9, AC12), a new quantity marking it
 * (AC8), a reservation capped at its line (AC9), the queue listing it again (AC6), and whether
 * confirming settles it, a type with no line included (ADR-0114 decisions 22, 23). The moved
 * event's reservations were marked by a date change, which the mock starts with: its event store
 * isn't the edit mock's. The integration tests check the same against the running backend.
 */

const PROJECTOR = 1
const MICROPHONE = 2
const LECTERN = 3
const NOTHING_TO_REASSESS =
  'This event has no reservation of that equipment type awaiting reassessment.'
const RECORD_THE_OUTCOME =
  "This equipment's request has no current outcome. Record its outcome instead: that settles the reservation."

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

/** As Technical Support: reserve `quantity` projectors for the open event, in the period now. */
async function reserveProjectorsForTheOpenEvent(quantity: number) {
  signInAs(MOCK_ACCOUNTS.technicalSupport)
  await reserveEquipment(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: PROJECTOR, quantity })
}

/** Each reassessment as (type, reserved, available, shortfall). */
async function reassessmentNumbers(reference = MOCK_MOVED_EVENT_REFERENCE) {
  const reassessments = await fetchEventReassessments(reference)
  return reassessments.map((row) => [
    row.equipment_type_name,
    row.reserved_quantity,
    row.available,
    row.shortfall,
  ])
}

/** Save `quantity` microphones for the event in `period`, as Technical Support would. */
function saveMicrophones(
  reference: string,
  quantity: number,
  period: { starts_at: string; ends_at: string },
) {
  saveReservation(reference, {
    equipment_type_id: MICROPHONE,
    equipment_type_name: 'Microphone',
    quantity,
    ...period,
    reserved_by: MOCK_ACCOUNTS.technicalSupport.full_name,
    created_at: '2026-10-02T09:10:00+08:00',
    preparation_status: 'not_started',
    preparation_notes: null,
  })
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-60 mock: what a change left to reassess (AC2)', () => {
  it('lists each type by name with its reservations as held, the period now and what is free', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const [lectern, projector] = await fetchEventReassessments(MOCK_MOVED_EVENT_REFERENCE)

    expect(lectern).toEqual({
      equipment_type_id: LECTERN,
      equipment_type_name: 'Lectern',
      reservations: [
        {
          id: 902,
          equipment_type_id: LECTERN,
          equipment_type_name: 'Lectern',
          quantity: 1,
          ...MOCK_OLD_EVENT_PERIOD,
          reserved_by: 'Tariq Hassan',
          created_at: '2026-10-02T09:05:00+08:00',
          needs_attention: false,
          preparation_status: 'not_started',
          preparation_notes: null,
        },
      ],
      reserved_quantity: 1,
      ...MOCK_EVENT_PERIOD,
      available: 2,
      shortfall: 0,
      confirmable: false,
    })
    expect(projector).toMatchObject({ reserved_quantity: 3, available: 6, shortfall: 0 })
  })

  it('shows a shortfall once other events hold what the new period needs', async () => {
    await reserveProjectorsForTheOpenEvent(4)

    expect(await reassessmentNumbers()).toEqual([
      ['Lectern', 1, 2, 0],
      ['Projector', 3, 2, 1],
    ])
  })

  it("leaves out another event's marked reservations", async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(fetchEventReassessments(MOCK_OPEN_EVENT_REFERENCE)).resolves.toEqual([])
  })

  it('lets the assigned coordinator read it, and nobody else of the coordinators', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(fetchEventReassessments(MOCK_MOVED_EVENT_REFERENCE)).resolves.toHaveLength(2)
    expect(
      await refusal(fetchEventReassessments(MOCK_OTHER_COORDINATORS_EVENT_REFERENCE)),
    ).toMatchObject({ status: 404, message: 'Event request not found.' })
  })

  it.each([
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff, 403],
    ['an Event Organiser', MOCK_ACCOUNTS.organiser, 403],
    ['a visitor', null, 401],
  ])('refuses %s', async (_who, account, status) => {
    signInAs(account)

    expect(await refusal(fetchEventReassessments(MOCK_MOVED_EVENT_REFERENCE))).toMatchObject({
      status,
    })
  })
})

describe('SCRUM-60 mock: confirming a marked reservation (AC3)', () => {
  it('moves it to the event period now, keeping its preparation, and drops it from the list', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const confirmed = await confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, PROJECTOR)

    expect(confirmed).toEqual([
      expect.objectContaining({
        id: 901,
        quantity: 3,
        ...MOCK_EVENT_PERIOD,
        preparation_status: 'in_progress',
        preparation_notes: 'Bulbs checked.',
      }),
    ])
    expect(await reassessmentNumbers()).toEqual([['Lectern', 1, 2, 0]])
  })

  it('takes the moved units from what is free for the period now', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, PROJECTOR)

    const availability = await apiRequest<{ equipment_type_id: number; available: number }[]>(
      `/api/equipment/events/${MOCK_OPEN_EVENT_REFERENCE}/availability`,
    )
    expect(availability.find((row) => row.equipment_type_id === PROJECTOR)?.available).toBe(3)
  })

  it('withdraws the safety approval, so its reservations cannot be prepared (AC10)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    const preparation = { status: 'ready' as const }
    await updateReservationPreparation(902, preparation)

    await confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, PROJECTOR)

    expect(await refusal(updateReservationPreparation(902, preparation))).toMatchObject({
      status: 409,
    })
  })

  it('confirms one when exactly as many are free as are reserved', async () => {
    await reserveProjectorsForTheOpenEvent(3)

    const confirmed = await confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, PROJECTOR)

    expect(confirmed.map((reservation) => reservation.quantity)).toEqual([3])
  })

  it('refuses one the period now is short of, changing nothing', async () => {
    await reserveProjectorsForTheOpenEvent(4)

    expect(await refusal(confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, PROJECTOR))).toMatchObject(
      {
        status: 409,
        code: 'reservation_cannot_move',
        message:
          "Projector: only 2 free for the event's period, not the 3 to keep. Record an outcome that provides no more than 2.",
      },
    )
    expect(await reassessmentNumbers()).toEqual([
      ['Lectern', 1, 2, 0],
      ['Projector', 3, 2, 1],
    ])
  })

  it('refuses one whose line has no current outcome, which an outcome settles instead', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(await refusal(confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, LECTERN))).toMatchObject({
      status: 409,
      code: 'conflict',
      message: RECORD_THE_OUTCOME,
    })
    expect(await reassessmentNumbers()).toHaveLength(2)
  })

  it('answers 404 for a type with nothing marked, and for a path that is not a number', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(
      await refusal(confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, MICROPHONE)),
    ).toMatchObject({ status: 404, message: NOTHING_TO_REASSESS })
    expect(
      await refusal(
        apiRequest(`/api/equipment/events/${MOCK_MOVED_EVENT_REFERENCE}/reassessments/x/confirm`, {
          method: 'POST',
        }),
      ),
    ).toMatchObject({ status: 404 })
  })

  it('refuses an event that is over, and does not find a draft', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    expect(
      await refusal(confirmReassessment(MOCK_CLOSED_EVENT_REFERENCE, PROJECTOR)),
    ).toMatchObject({ status: 409, code: 'equipment_not_reservable' })
    expect(
      await refusal(confirmReassessment(mockStatusEventReference('draft'), PROJECTOR)),
    ).toMatchObject({ status: 404, message: 'Event request not found.' })
  })

  it.each([
    ['the event coordinator', MOCK_ACCOUNTS.coordinator, 403],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff, 403],
    ['a visitor', null, 401],
  ])('refuses %s', async (_who, account, status) => {
    signInAs(account)

    expect(await refusal(confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, PROJECTOR))).toMatchObject(
      { status },
    )
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect(await reassessmentNumbers()).toHaveLength(2)
  })
})

describe('SCRUM-60 mock: an outcome settles the marked reservation (AC4, AC12)', () => {
  it("moves a reopened line's reservation, keeping no more than it held", async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await recordEquipmentOutcome(MOCK_MOVED_EVENT_REFERENCE, {
      lineId: 72,
      body: { provided_quantity: 2 },
    })

    const reservations = await fetchEventReservations(MOCK_MOVED_EVENT_REFERENCE)
    expect(reservations.find((reservation) => reservation.id === 902)).toMatchObject({
      quantity: 1,
      ...MOCK_EVENT_PERIOD,
    })
    expect(await reassessmentNumbers()).toEqual([['Projector', 3, 6, 0]])
  })

  it('releases it all for an unavailable outcome', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await recordEquipmentOutcome(MOCK_MOVED_EVENT_REFERENCE, {
      lineId: 71,
      body: { provided_quantity: 0, note: 'None free on the new date.' },
    })

    const reservations = await fetchEventReservations(MOCK_MOVED_EVENT_REFERENCE)
    expect(reservations.map((reservation) => reservation.id)).toEqual([902])
  })

  it('refuses an outcome that keeps more than is free, leaving the line as it was', async () => {
    await reserveProjectorsForTheOpenEvent(4)

    expect(
      await refusal(
        recordEquipmentOutcome(MOCK_MOVED_EVENT_REFERENCE, {
          lineId: 71,
          body: { provided_quantity: 3 },
        }),
      ),
    ).toMatchObject({ status: 409, code: 'reservation_cannot_move' })
    const { equipment_lines: lines } = await fetchEventEquipmentLines(MOCK_MOVED_EVENT_REFERENCE)
    expect(lines.find((line) => line.id === 71)).toMatchObject({
      status: 'fulfilled',
      provided_quantity: 3,
    })
  })

  it('withdraws the safety approval when it settles one (AC10)', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await recordEquipmentOutcome(MOCK_MOVED_EVENT_REFERENCE, {
      lineId: 72,
      body: { provided_quantity: 2 },
    })

    expect(await refusal(updateReservationPreparation(901, { status: 'ready' }))).toMatchObject({
      status: 409,
    })
  })
})

describe('SCRUM-60 mock: a new quantity marks the reservation (AC8)', () => {
  it("marks that line's reservation, and new notes alone mark nothing", async () => {
    await reserveProjectorsForTheOpenEvent(2)
    signInAs(MOCK_ACCOUNTS.coordinator)
    await updateEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, { lineId: 41, body: { notes: 'Spare' } })
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect(await reassessmentNumbers(MOCK_OPEN_EVENT_REFERENCE)).toEqual([])

    signInAs(MOCK_ACCOUNTS.coordinator)
    await updateEquipmentLine(MOCK_OPEN_EVENT_REFERENCE, { lineId: 41, body: { quantity: 6 } })

    signInAs(MOCK_ACCOUNTS.technicalSupport)
    expect(await reassessmentNumbers(MOCK_OPEN_EVENT_REFERENCE)).toEqual([['Projector', 2, 6, 0]])
  })
})

describe('SCRUM-60 mock: a reservation never exceeds its line (AC9)', () => {
  it('refuses one more than the line asks for, with what is already reserved', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    await reserveEquipment(MOCK_OPEN_EVENT_REFERENCE, {
      equipment_type_id: MICROPHONE,
      quantity: 3,
    })

    expect(
      await refusal(
        reserveEquipment(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: MICROPHONE, quantity: 2 }),
      ),
    ).toMatchObject({
      status: 400,
      fieldErrors: { quantity: ['The event asks for 4 of these and already has 3 reserved.'] },
    })
    await expect(
      reserveEquipment(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: MICROPHONE, quantity: 1 }),
    ).resolves.toMatchObject({ quantity: 1 })
  })

  it('reserves a type the event has no line for up to what is free', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    await expect(
      reserveEquipment(MOCK_OPEN_EVENT_REFERENCE, { equipment_type_id: LECTERN, quantity: 2 }),
    ).resolves.toMatchObject({ quantity: 2 })
  })
})

describe("SCRUM-60 mock: the queue lists a marked reservation's line again (AC6)", () => {
  it('lists the moved event with its fulfilled and reopened lines and the types to reassess', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const queue = await fetchEquipmentAwaitingAction()

    const moved = queue.equipment_requests.find(
      (row) => row.event.reference === MOCK_MOVED_EVENT_REFERENCE,
    )
    expect(moved?.equipment_lines.map((line) => [line.id, line.status])).toEqual([
      [71, 'fulfilled'],
      [72, 'requested'],
    ])
    expect(moved?.equipment_type_ids_to_reassess).toEqual([PROJECTOR, LECTERN])
  })
})

describe('SCRUM-60 mock: whether confirming settles it (ADR-0114 decisions 22, 23)', () => {
  it('says a line with an outcome can be confirmed, and one with no outcome cannot', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)

    const reassessments = await fetchEventReassessments(MOCK_MOVED_EVENT_REFERENCE)

    expect(reassessments.map((row) => [row.equipment_type_name, row.confirmable])).toEqual([
      ['Lectern', false],
      ['Projector', true],
    ])
  })

  it("says one short of what its line's outcome keeps cannot be confirmed", async () => {
    await reserveProjectorsForTheOpenEvent(4)

    const [, projector] = await fetchEventReassessments(MOCK_MOVED_EVENT_REFERENCE)

    expect(projector).toMatchObject({ shortfall: 1, confirmable: false })
  })

  it('confirms a type the event has no line for, keeping what is free and releasing the rest', async () => {
    signInAs(MOCK_ACCOUNTS.technicalSupport)
    saveMicrophones(MOCK_MOVED_EVENT_REFERENCE, 2, MOCK_OLD_EVENT_PERIOD)
    markReservationsOfType(MOCK_MOVED_EVENT_REFERENCE, MICROPHONE)
    saveMicrophones(MOCK_OTHER_COORDINATORS_EVENT_REFERENCE, 11, MOCK_EVENT_PERIOD)
    const [, microphone] = await fetchEventReassessments(MOCK_MOVED_EVENT_REFERENCE)
    expect(microphone).toMatchObject({ reserved_quantity: 2, shortfall: 1, confirmable: true })

    const confirmed = await confirmReassessment(MOCK_MOVED_EVENT_REFERENCE, MICROPHONE)

    expect(confirmed).toEqual([expect.objectContaining({ quantity: 1, ...MOCK_EVENT_PERIOD })])
    expect(await reassessmentNumbers()).toEqual([
      ['Lectern', 1, 2, 0],
      ['Projector', 3, 6, 0],
    ])
  })
})
