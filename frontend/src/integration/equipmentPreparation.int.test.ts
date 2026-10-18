import {
  fetchEventReservations,
  reserveEquipment,
  updateReservationPreparation,
} from '@/features/equipment/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount, uniqueEmail } from './backend'
import type { Credentials } from './backend'
import {
  eventReadyForSafetyReview,
  LEAD,
  optionalAccount,
  required,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-85 against the running backend: recording an equipment reservation's preparation
 * (ADR-0050, ADR-0081). The refusals run with the staff account every run has (an Event
 * Coordinator); the rest need a Technical Support account (INTEGRATION_TECH_SUPPORT_*) and, to
 * take an event to the Safety Officer's approval, the accounts plannedEvent.ts reads. Each check
 * skips without them.
 */

const NOT_PERMITTED = { status: 403, code: 'authorization_error' }
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
/** An id no database has, so the lookup finds nothing. */
const UNKNOWN_RESERVATION_ID = 99_999_999
const SAFETY_APPROVAL_MESSAGE =
  "Preparation details can't be recorded until the Safety Officer has approved the event's" +
  ' Operational Safety Check.'

const TECH_SUPPORT = optionalAccount(
  import.meta.env.INTEGRATION_TECH_SUPPORT_EMAIL,
  import.meta.env.INTEGRATION_TECH_SUPPORT_PASSWORD,
)
const hasTechSupport = TECH_SUPPORT !== null
const canReachSafetyApproval =
  hasTechSupport && LEAD !== null && VENUE_STAFF !== null && SAFETY_OFFICER !== null

/** As Technical Support: a new equipment type, and one unit of it reserved for the event. */
async function reserveForEvent(reference: string, technicalSupport: Credentials) {
  await signInAs(technicalSupport)
  const type = await apiRequest<{ id: number }>('/api/equipment/types', {
    method: 'POST',
    body: {
      name: `Integration Projector ${uniqueEmail('type')}`,
      total_quantity: 3,
      store_name: 'Integration store',
    },
  })
  return reserveEquipment(reference, { equipment_type_id: type.id, quantity: 1 })
}

afterEach(() => sendRequestsAs(null))

describe("SCRUM-85 recording a reservation's preparation against the backend", () => {
  it('refuses the update without a token', async () => {
    const error = await refusal(
      updateReservationPreparation(UNKNOWN_RESERVATION_ID, {
        status: 'ready',
      }),
    )

    expect(error).toMatchObject(NOT_SIGNED_IN)
  })

  it('refuses the update to an Event Coordinator', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      updateReservationPreparation(UNKNOWN_RESERVATION_ID, {
        status: 'ready',
      }),
    )

    expect(error).toMatchObject(NOT_PERMITTED)
  })

  it.skipIf(!hasTechSupport)(
    'names the fields it refuses (400) before looking for the reservation',
    async () => {
      await signInAs(required(TECH_SUPPORT))

      const error = await refusal(
        updateReservationPreparation(UNKNOWN_RESERVATION_ID, { status: 'done', notes: '   ' }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({
        status: ['Status must be not_started, in_progress or ready.'],
        notes: ['Must not be blank.'],
      })
    },
  )

  it.skipIf(!hasTechSupport)('answers 404 for a reservation that does not exist', async () => {
    await signInAs(required(TECH_SUPPORT))

    const error = await refusal(
      updateReservationPreparation(UNKNOWN_RESERVATION_ID, { status: 'ready' }),
    )

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Equipment reservation not found.',
    })
  })

  it.skipIf(!canReachSafetyApproval)(
    'refuses a reservation whose event the Safety Officer has not approved (409)',
    async () => {
      const event = await eventReadyForSafetyReview()
      const reservation = await reserveForEvent(event.reference, required(TECH_SUPPORT))

      const error = await refusal(updateReservationPreparation(reservation.id, { status: 'ready' }))

      expect(error).toMatchObject({
        status: 409,
        code: 'conflict',
        message: SAFETY_APPROVAL_MESSAGE,
      })
    },
  )

  it.skipIf(!canReachSafetyApproval)(
    'records the status and trimmed notes, which the coordinator then reads',
    async () => {
      const event = await safetyApprovedEvent()
      const reservation = await reserveForEvent(event.reference, required(TECH_SUPPORT))

      const saved = await updateReservationPreparation(reservation.id, {
        status: 'in_progress',
        notes: '  Cables to test.  ',
      })
      await signInAs(staffAccount())
      const [coordinatorsCopy] = await fetchEventReservations(event.reference)

      const recorded = { preparation_status: 'in_progress', preparation_notes: 'Cables to test.' }
      expect(saved).toMatchObject({ id: reservation.id, ...recorded })
      expect(coordinatorsCopy).toMatchObject({ id: reservation.id, ...recorded })
    },
  )
})
