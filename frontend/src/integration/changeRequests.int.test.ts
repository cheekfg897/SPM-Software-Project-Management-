import {
  fetchEventRequest,
  raiseChangeRequest,
  saveDraftEventRequest,
  withdrawChangeRequest,
} from '@/features/eventRequests/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount } from './backend'
import { submittedEvent } from './plannedEvent'

/**
 * SCRUM-56 against the running backend (ADR-0126): the organiser who submitted an event raises a
 * change request, which the record shows Pending with the values asked for beside the event's
 * values when raised, while the event itself stays as it was; a second waits for the first; a
 * Pending one is withdrawn; and the refusals come with the codes and messages the page shows.
 * The events come from plannedEvent.ts: 09:00 to 17:00, 120 expected, no coordinator yet.
 */

const REASON = 'Our keynote speaker lands at 9:30.'
const LATER_START = { start_time: '10:00', reason: REASON }
const ALREADY_PENDING_MESSAGE =
  'A change request is already waiting for the coordinator. Withdraw it, or wait for ' +
  'their decision, before raising another.'
/** Every field the frontend's ChangeRequest type reads, and nothing more (no internal ids). */
const CHANGE_REQUEST_FIELDS = [
  'changes',
  'decided_at',
  'decided_by',
  'decision_reason',
  'id',
  'raised_at',
  'raised_by',
  'reason',
  'status',
  'withdrawal_note',
  'withdrawn_at',
]

afterEach(() => sendRequestsAs(null))

describe('SCRUM-56 change requests against the backend', () => {
  it('raises one Pending, in exactly the shape the record shows, leaving the event as it was', async () => {
    const event = await submittedEvent()

    const raised = await raiseChangeRequest(event.reference, {
      start_time: '10:00',
      expected_attendance: 150,
      reason: REASON,
    })

    expect(Object.keys(raised).sort()).toEqual(CHANGE_REQUEST_FIELDS)
    expect(raised).toMatchObject({
      status: 'pending',
      changes: [
        { field: 'start_time', previous_value: '09:00:00', requested_value: '10:00:00' },
        { field: 'expected_attendance', previous_value: 120, requested_value: 150 },
      ],
      reason: REASON,
      raised_by: 'Integration Organiser',
      withdrawn_at: null,
      withdrawal_note: null,
    })
    expect(raised.raised_at).toMatch(/\+08:00$/)
    const record = await fetchEventRequest(event.reference)
    expect(record.change_requests).toEqual([raised])
    expect(record).toMatchObject({ start_time: '09:00:00', expected_attendance: 120 })
  })

  it('refuses a second while the first is Pending, and takes one once it is withdrawn', async () => {
    const event = await submittedEvent()
    const first = await raiseChangeRequest(event.reference, LATER_START)

    const second = await refusal(raiseChangeRequest(event.reference, LATER_START))
    const withdrawn = await withdrawChangeRequest(event.reference, first.id)
    const third = await raiseChangeRequest(event.reference, LATER_START)

    expect(second).toMatchObject({
      status: 409,
      code: 'conflict',
      message: ALREADY_PENDING_MESSAGE,
    })
    expect(withdrawn).toMatchObject({ id: first.id, status: 'withdrawn', withdrawal_note: null })
    expect(withdrawn.withdrawn_at).toMatch(/\+08:00$/)
    expect(third.status).toBe('pending')
  })

  it('refuses withdrawing one that is no longer Pending, naming its status', async () => {
    const event = await submittedEvent()
    const raised = await raiseChangeRequest(event.reference, LATER_START)
    await withdrawChangeRequest(event.reference, raised.id)

    const refused = await refusal(withdrawChangeRequest(event.reference, raised.id))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_not_pending',
      message: 'Only a pending change request can be withdrawn; this one is withdrawn.',
    })
  })

  it('refuses one with no reason under its field, and one that changes nothing', async () => {
    const event = await submittedEvent()

    const unexplained = await refusal(raiseChangeRequest(event.reference, { reason: '  ' }))
    const unchanged = await refusal(
      raiseChangeRequest(event.reference, { start_time: '09:00', reason: REASON }),
    )

    expect(unexplained).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { reason: ['Say why the change is needed.'] },
    })
    expect(unchanged).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: "Say what should change: give at least one of the event's details a new value.",
    })
  })

  it('refuses one on a draft, naming its status', async () => {
    await submittedEvent()
    const draft = await saveDraftEventRequest({ name: 'Integration Draft' })

    const refused = await refusal(raiseChangeRequest(draft.reference, LATER_START))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_not_allowed',
      message: "A change can't be requested for a draft event.",
    })
  })

  it('refuses a coordinator by role', async () => {
    const event = await submittedEvent()
    await signInAs(staffAccount())

    const refused = await refusal(raiseChangeRequest(event.reference, LATER_START))

    expect(refused).toMatchObject({ status: 403, code: 'authorization_error' })
  })
})
