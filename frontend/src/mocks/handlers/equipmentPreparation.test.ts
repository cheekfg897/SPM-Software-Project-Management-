import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { apiRequest } from '@/lib/api'
import { refusalOf } from '@/test/refusalOf'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import { mockStatusEventReference, MOCK_OPEN_EVENT_REFERENCE } from './equipmentFixtures'
import { PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE } from './preparationRules'

/**
 * The equipment mock's SCRUM-85 endpoint, recording a reservation's preparation, pinned to what
 * backend/app/modules/equipment/routes.py answers. The open event stands in for one the Safety
 * Officer has approved; the event in Safety Review is still waiting.
 */

interface Reservation {
  id: number
  preparation_status: string
  preparation_notes: string | null
}

/** The mock coordinator's event in Safety Review: the Safety Officer hasn't approved it yet. */
const AWAITING_SAFETY_EVENT_REFERENCE = mockStatusEventReference(EVENT_REQUEST_STATUS.SAFETY_REVIEW)

function reservationsUrl(reference: string): string {
  return `/api/equipment/events/${reference}/reservations`
}

/** As Technical Support, reserve one projector for the event. */
function reserveProjector(reference: string) {
  return apiRequest<Reservation>(reservationsUrl(reference), {
    method: 'POST',
    body: { equipment_type_id: 1, quantity: 1 },
  })
}

function prepare(reservationId: number, body: Record<string, unknown>) {
  return apiRequest<Reservation>(`/api/equipment/reservations/${reservationId}/preparation`, {
    method: 'PUT',
    body,
  })
}

beforeEach(() => {
  sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.technicalSupport))
})

describe('SCRUM-85 equipment mock: recording preparation', () => {
  it('saves the status and the trimmed notes, which the coordinator then reads', async () => {
    const reservation = await reserveProjector(MOCK_OPEN_EVENT_REFERENCE)

    const saved = await prepare(reservation.id, { status: 'ready', notes: '  Tested.  ' })
    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    const listed = await apiRequest<Reservation[]>(reservationsUrl(MOCK_OPEN_EVENT_REFERENCE))

    expect(saved).toMatchObject({ preparation_status: 'ready', preparation_notes: 'Tested.' })
    expect(listed[0]).toMatchObject({ preparation_status: 'ready', preparation_notes: 'Tested.' })
  })

  it('clears the notes when they are left out', async () => {
    const reservation = await reserveProjector(MOCK_OPEN_EVENT_REFERENCE)
    await prepare(reservation.id, { status: 'in_progress', notes: 'Cables to do.' })

    const saved = await prepare(reservation.id, { status: 'in_progress' })

    expect(saved).toMatchObject({ preparation_notes: null })
  })

  it('names a missing or unknown status, and blank notes (400)', async () => {
    const reservation = await reserveProjector(MOCK_OPEN_EVENT_REFERENCE)

    const error = await refusalOf(prepare(reservation.id, { status: 'done', notes: ' ' }))

    expect(error.fieldErrors).toEqual({
      status: ['Status must be not_started, in_progress or ready.'],
      notes: ['Must not be blank.'],
    })
  })

  it('answers 404 for a reservation that does not exist', async () => {
    const error = await refusalOf(prepare(99, { status: 'ready' }))

    expect(error).toMatchObject({ status: 404, message: 'Equipment reservation not found.' })
  })

  it('refuses an event the Safety Officer has not approved, saving nothing (409)', async () => {
    const reservation = await reserveProjector(AWAITING_SAFETY_EVENT_REFERENCE)

    const error = await refusalOf(prepare(reservation.id, { status: 'ready' }))

    expect(error).toMatchObject({
      status: 409,
      code: 'conflict',
      message: PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE,
    })
    const listed = await apiRequest<Reservation[]>(reservationsUrl(AWAITING_SAFETY_EVENT_REFERENCE))
    expect(listed[0]).toMatchObject({ preparation_status: 'not_started' })
  })

  it('answers 401 without a token and 403 to anyone but Technical Support', async () => {
    sendRequestsAs(null)
    expect(await refusalOf(prepare(1, { status: 'ready' }))).toMatchObject({ status: 401 })

    sendRequestsAs(mockTokenFor(MOCK_ACCOUNTS.coordinator))
    expect(await refusalOf(prepare(1, { status: 'ready' }))).toMatchObject({ status: 403 })
  })
})
