import {
  addEquipmentLine,
  confirmReassessment,
  fetchEventEquipmentLines,
  fetchEventReassessments,
  fetchEventReservations,
  recordEquipmentOutcome,
  reserveEquipment,
  updateEquipmentLine,
} from '@/features/equipment/api'
import type { EquipmentOutcomeBody } from '@/features/equipment/api'
import { createEquipmentType, takeOutOfService } from '@/features/equipmentCatalogue/api'
import { editEventRequest, sendToSafetyReview } from '@/features/eventRequests/api'
import { fetchNotifications } from '@/features/notifications/api'
import { fetchEquipmentAwaitingAction } from '@/features/techSupport/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import {
  hasTechSupport,
  refusal,
  signInAs,
  signInAsTechSupport,
  staffAccount,
  uniqueEmail,
} from './backend'
import { approvedEvent, EVENT_DATE, LEAD } from './plannedEvent'

/**
 * SCRUM-60 against the running backend (ADR-0114): a timing change marks the event's
 * reservations, held for their old period (AC1, AC6); Technical Support see them with what is free
 * for the event's period now and any shortfall (AC2) and in their queue (AC6); they hold Safety
 * Review back, naming the reservation (AC5); confirming moves them and tells the coordinator once
 * (AC3); an outcome settles a shortfall or a reopened line instead (AC4, AC12); a new quantity
 * marks them (AC8), and a reservation can't pass its line (AC9). Each refusal is checked in the
 * backend's own words. The event must be the staff account's, which takes a Lead to assign, and
 * only Technical Support reserve, so these skip without both accounts (plannedEvent.ts).
 */

const canReassess = hasTechSupport && LEAD !== null

/** The event's period before and after the start moves from 09:00 to 10:00 (business time). */
const OLD_STARTS_AT = `${EVENT_DATE}T09:00:00+08:00`
const NEW_STARTS_AT = `${EVENT_DATE}T10:00:00+08:00`
const ENDS_AT = `${EVENT_DATE}T17:00:00+08:00`
const NOTHING_TO_REASSESS =
  'This event has no reservation of that equipment type awaiting reassessment.'
const RECORD_THE_OUTCOME =
  "This equipment's request has no current outcome. Record its outcome instead: that settles the reservation."

/** An approved event of the staff account's with a line of a new equipment type, reviewed. */
interface ReviewedEvent {
  reference: string
  typeId: number
  typeName: string
  lineId: number
}

interface Equipment {
  /** Units of the new type held in all. */
  total: number
  /** Units the line asks for. */
  quantity: number
  /** Units Technical Support reserve before recording the outcome; none when 0. */
  reserved: number
  /** Units the outcome provides. */
  provided: number
}

/** The outcome as Technical Support send it: a note only when something is short. */
function outcome(provided: number, quantity: number): EquipmentOutcomeBody {
  if (provided === quantity) {
    return { provided_quantity: provided }
  }
  return { provided_quantity: provided, note: 'Only some are free.' }
}

/** As Technical Support: a new equipment type, `total` units of it held in all. */
async function newEquipmentType(total: number): Promise<{ id: number; name: string }> {
  await signInAsTechSupport()
  return createEquipmentType({
    name: `Integration projector ${uniqueEmail('type')}`,
    description: '',
    total_quantity: total,
    venue_id: null,
    store_name: 'Integration store',
  })
}

async function eventWithReviewedEquipment(equipment: Equipment): Promise<ReviewedEvent> {
  const { reference } = await approvedEvent()
  const type = await newEquipmentType(equipment.total)
  await signInAs(staffAccount())
  const line = await addEquipmentLine(reference, {
    equipment_type_id: type.id,
    quantity: equipment.quantity,
  })
  await signInAsTechSupport()
  if (equipment.reserved > 0) {
    await reserveEquipment(reference, { equipment_type_id: type.id, quantity: equipment.reserved })
  }
  await recordEquipmentOutcome(reference, {
    lineId: line.id,
    body: outcome(equipment.provided, equipment.quantity),
  })
  return { reference, typeId: type.id, typeName: type.name, lineId: line.id }
}

/** As the staff account, the event's coordinator: start the event an hour later. */
async function moveTheStart(reference: string): Promise<void> {
  await signInAs(staffAccount())
  await editEventRequest(reference, { start_time: '10:00' })
}

/** As the staff account: the details and kind of each of its notices about the event. */
async function coordinatorNotices(reference: string): Promise<[string, string | null][]> {
  await signInAs(staffAccount())
  const notices = await fetchNotifications()
  const about: [string, string | null][] = []
  for (const notice of notices) {
    if (notice.event_reference === reference) {
      about.push([notice.kind, notice.detail])
    }
  }
  return about
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-60 a timing change against the backend', () => {
  it.skipIf(!canReassess)(
    'marks the reservation, still held for its old period, and shows what the new one can give',
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })

      await moveTheStart(event.reference)

      await signInAsTechSupport()
      const [reassessment] = await fetchEventReassessments(event.reference)
      expect(Object.keys(reassessment ?? {}).sort()).toEqual([
        'available',
        'confirmable',
        'ends_at',
        'equipment_type_id',
        'equipment_type_name',
        'reservations',
        'reserved_quantity',
        'shortfall',
        'starts_at',
      ])
      expect(reassessment).toMatchObject({
        equipment_type_id: event.typeId,
        equipment_type_name: event.typeName,
        reserved_quantity: 2,
        starts_at: NEW_STARTS_AT,
        ends_at: ENDS_AT,
        available: 5,
        shortfall: 0,
        confirmable: true,
      })
      expect(reassessment?.reservations.map((held) => [held.quantity, held.starts_at])).toEqual([
        [2, OLD_STARTS_AT],
      ])
    },
  )

  it.skipIf(!canReassess)(
    "lists the fulfilled line again in Technical Support's queue, naming its type",
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })

      await moveTheStart(event.reference)

      await signInAsTechSupport()
      const queue = await fetchEquipmentAwaitingAction()
      const row = queue.equipment_requests.find(
        (awaiting) => awaiting.event.reference === event.reference,
      )
      expect(row?.equipment_lines.map((line) => [line.id, line.status])).toEqual([
        [event.lineId, 'fulfilled'],
      ])
      expect(row?.equipment_type_ids_to_reassess).toEqual([event.typeId])
    },
  )

  it.skipIf(!canReassess)(
    'holds the event out of Safety Review, naming the reservation',
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })
      await moveTheStart(event.reference)
      await signInAsTechSupport()
      const [reservation] = await fetchEventReservations(event.reference)

      await signInAs(staffAccount())
      const refused = await refusal(sendToSafetyReview(event.reference))

      expect(refused.status).toBe(409)
      expect(refused.details.equipment).toEqual([
        `Equipment reservation ${String(reservation?.id)} (${event.typeName}) is awaiting reassessment by Technical Support.`,
      ])
    },
  )

  it.skipIf(!canReassess)(
    'confirms it for the new period, and tells the coordinator once',
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })
      await moveTheStart(event.reference)
      const before = await coordinatorNotices(event.reference)

      await signInAsTechSupport()
      const confirmed = await confirmReassessment(event.reference, event.typeId)

      expect(confirmed.map((held) => [held.quantity, held.starts_at, held.ends_at])).toEqual([
        [2, NEW_STARTS_AT, ENDS_AT],
      ])
      expect(await fetchEventReassessments(event.reference)).toEqual([])
      expect(await coordinatorNotices(event.reference)).toEqual([
        [
          'equipment_outcome_recorded',
          `${event.typeName}: 2 reserved, confirmed for the event's new date and time.`,
        ],
        ...before,
      ])
    },
  )

  it.skipIf(!canReassess)(
    'refuses a second confirmation, the coordinator and a visitor, in its own words',
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })
      await moveTheStart(event.reference)

      expect(await refusal(confirmReassessment(event.reference, event.typeId))).toMatchObject({
        status: 403,
        code: 'authorization_error',
      })
      sendRequestsAs(null)
      expect(await refusal(confirmReassessment(event.reference, event.typeId))).toMatchObject({
        status: 401,
      })
      await signInAsTechSupport()
      await confirmReassessment(event.reference, event.typeId)
      expect(await refusal(confirmReassessment(event.reference, event.typeId))).toMatchObject({
        status: 404,
        code: 'not_found',
        message: NOTHING_TO_REASSESS,
      })
    },
  )
})

describe('SCRUM-60 a reservation of a type the event has no line for, against the backend', () => {
  it.skipIf(!canReassess)(
    'is confirmed though short, keeping what is free and releasing the rest (ADR-0114 decision 22)',
    async () => {
      const { reference } = await approvedEvent()
      const type = await newEquipmentType(2)
      await reserveEquipment(reference, { equipment_type_id: type.id, quantity: 2 })
      await moveTheStart(reference)
      await signInAsTechSupport()
      await takeOutOfService({
        equipmentTypeId: String(type.id),
        body: { quantity: 1, reason: 'damaged' },
      })
      const [reassessment] = await fetchEventReassessments(reference)
      expect(reassessment).toMatchObject({ shortfall: 1, confirmable: true })
      const queue = await fetchEquipmentAwaitingAction()
      const row = queue.equipment_requests.find(
        (awaiting) => awaiting.event.reference === reference,
      )
      expect(row?.equipment_lines).toEqual([])
      expect(row?.equipment_type_ids_to_reassess).toEqual([type.id])

      const confirmed = await confirmReassessment(reference, type.id)

      expect(confirmed.map((held) => [held.quantity, held.starts_at])).toEqual([[1, NEW_STARTS_AT]])
      await expect(fetchEventReassessments(reference)).resolves.toEqual([])
      expect(await coordinatorNotices(reference)).toContainEqual([
        'equipment_outcome_recorded',
        `${type.name}: 1 of 2 kept for the event's new date and time; 1 released.`,
      ])
    },
  )
})

describe('SCRUM-60 settling a reservation with an outcome against the backend', () => {
  it.skipIf(!canReassess)(
    'refuses to keep more than is free, then keeps what is free and releases the rest (AC4)',
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 2,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })
      await moveTheStart(event.reference)
      await signInAsTechSupport()
      await takeOutOfService({
        equipmentTypeId: String(event.typeId),
        body: { quantity: 1, reason: 'damaged' },
      })
      const short = `${event.typeName}: only 1 free for the event's period, not the 2 to keep. Record an outcome that provides no more than 1.`

      expect(await refusal(confirmReassessment(event.reference, event.typeId))).toMatchObject({
        status: 409,
        code: 'reservation_cannot_move',
        message: short,
      })
      expect(
        await refusal(
          recordEquipmentOutcome(event.reference, { lineId: event.lineId, body: outcome(2, 2) }),
        ),
      ).toMatchObject({ status: 409, code: 'reservation_cannot_move', message: short })

      await recordEquipmentOutcome(event.reference, { lineId: event.lineId, body: outcome(1, 2) })

      const reservations = await fetchEventReservations(event.reference)
      expect(reservations.map((held) => [held.quantity, held.starts_at])).toEqual([
        [1, NEW_STARTS_AT],
      ])
    },
  )

  it.skipIf(!canReassess)(
    'reopens a partly provided line, refuses to confirm it, and moves its reservation with the fresh outcome (AC12)',
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 3,
        reserved: 1,
        provided: 1,
      })

      await moveTheStart(event.reference)

      await signInAsTechSupport()
      const { equipment_lines: lines } = await fetchEventEquipmentLines(event.reference)
      expect(lines.map((line) => [line.status, line.provided_quantity])).toEqual([
        ['requested', null],
      ])
      expect(await refusal(confirmReassessment(event.reference, event.typeId))).toMatchObject({
        status: 409,
        code: 'conflict',
        message: RECORD_THE_OUTCOME,
      })
      await recordEquipmentOutcome(event.reference, { lineId: event.lineId, body: outcome(3, 3) })
      const reservations = await fetchEventReservations(event.reference)
      expect(reservations.map((held) => [held.quantity, held.starts_at])).toEqual([
        [1, NEW_STARTS_AT],
      ])
    },
  )

  it.skipIf(!canReassess)(
    "marks the reservation when the line's quantity falls, and the outcome trims it (AC8, AC9)",
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 3,
        reserved: 3,
        provided: 3,
      })
      await signInAs(staffAccount())

      await updateEquipmentLine(event.reference, { lineId: event.lineId, body: { quantity: 2 } })

      await signInAsTechSupport()
      const [reassessment] = await fetchEventReassessments(event.reference)
      expect(reassessment).toMatchObject({ reserved_quantity: 3, starts_at: OLD_STARTS_AT })
      await recordEquipmentOutcome(event.reference, { lineId: event.lineId, body: outcome(2, 2) })
      const reservations = await fetchEventReservations(event.reference)
      expect(reservations.map((held) => held.quantity)).toEqual([2])
    },
  )

  it.skipIf(!canReassess)(
    "refuses a reservation past the line's quantity, on quantity (AC9)",
    async () => {
      const event = await eventWithReviewedEquipment({
        total: 5,
        quantity: 2,
        reserved: 2,
        provided: 2,
      })

      const refused = await refusal(
        reserveEquipment(event.reference, { equipment_type_id: event.typeId, quantity: 1 }),
      )

      expect(refused).toMatchObject({
        status: 400,
        fieldErrors: { quantity: ['The event asks for 2 of these and already has 2 reserved.'] },
      })
    },
  )
})
