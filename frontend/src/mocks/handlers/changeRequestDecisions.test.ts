import {
  decideChangeRequest,
  decideEventRequest,
  editEventRequest,
  fetchEventHistory,
  fetchEventRequest,
  raiseChangeRequest,
  withdrawChangeRequest,
} from '@/features/eventRequests/api'
import type { DecisionChoice } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { addChangeRequest } from './changeRequestStore'

/**
 * The mock of the coordinator's decision on a change request
 * (POST .../<reference>/change-requests/<id>/decide), pinned to what the backend does (SCRUM-57,
 * ADR-0127): approving applies the values asked for, each in the history as the coordinator's
 * change, unless a field has moved since; rejecting needs a reason and changes nothing; the
 * request keeps who decided it, when and why; and while one is Pending, the event's own
 * decisions are refused (AC9). The mock's "now" is 5 Oct, 12:00 pm.
 */

/** Omar's, under review and coordinated by Chloe: 12 Nov, 9:00 am to 5:00 pm, 250 expected. */
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
/** Hana's, approved, and in Safety Review ready to confirm. */
const APPROVED_WITH_GAPS = 'EVR-PLAN0001'
const READY_TO_CONFIRM = 'EVR-PLAN0003'
const MOCK_NOW = '2026-10-05T12:00:00+08:00'
const CHLOE = MOCK_ACCOUNTS.coordinator
const LATER_AND_BIGGER = {
  start_time: '10:00',
  expected_attendance: 300,
  reason: 'The keynote speaker lands later.',
}
const APPROVE: DecisionChoice = { outcome: 'approved' }
const PENDING_MESSAGE =
  'The organiser has a change request waiting for your decision. Decide the change request first.'

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

/** Omar raises the later, bigger Partner Summit; Chloe is then signed in. Answers its id. */
async function raisedOnTheSummit(): Promise<number> {
  signInAs(MOCK_ACCOUNTS.organiser)
  const raised = await raiseChangeRequest(PARTNER_SUMMIT, LATER_AND_BIGGER)
  signInAs(CHLOE)
  return raised.id
}

/** A Pending change request kept on `reference` as if its organiser had raised it. */
function pendingOn(reference: string) {
  addChangeRequest(reference, {
    status: 'pending',
    changes: [{ field: 'expected_attendance', previous_value: 250, requested_value: 300 }],
    reason: 'More partners.',
    raised_by: 'Omar Rahman',
    raised_at: MOCK_NOW,
    withdrawn_at: null,
    withdrawal_note: null,
    decided_by: null,
    decided_at: null,
    decision_reason: null,
  })
}

describe('SCRUM-57 mock of approving a change request', () => {
  it('applies each value, records it as the coordinator, and keeps who decided it', async () => {
    const id = await raisedOnTheSummit()

    const approved = await decideChangeRequest(PARTNER_SUMMIT, id, {
      outcome: 'approved',
      reason: ' The hall holds 300. ',
    })

    expect(approved).toMatchObject({
      id,
      status: 'approved',
      decided_by: CHLOE.full_name,
      decided_at: MOCK_NOW,
      decision_reason: 'The hall holds 300.',
    })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record).toMatchObject({ start_time: '10:00:00', expected_attendance: 300 })
    expect(record.change_requests).toEqual([approved])
    const { history } = await fetchEventHistory(PARTNER_SUMMIT)
    const applied = history.slice(-2).map((entry) => [entry.actor_name, entry.details.field])
    expect(applied).toEqual([
      [CHLOE.full_name, 'start_time'],
      [CHLOE.full_name, 'expected_attendance'],
    ])
  })

  it('refuses a request a field has moved away from, naming it then and now, and keeps it Pending', async () => {
    // Approved first: before that, the coordinator can't edit it directly (SCRUM-110).
    signInAs(CHLOE)
    await decideEventRequest(PARTNER_SUMMIT, APPROVE)
    const id = await raisedOnTheSummit()
    await editEventRequest(PARTNER_SUMMIT, { expected_attendance: 200 })

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_stale',
      message:
        "This change request can't be approved because the event has changed since it was " +
        'raised. Expected attendance: 250 when the change was requested, 200 now. Reject it, ' +
        'and the organiser can raise a new one.',
    })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.change_requests[0]?.status).toBe('pending')
    expect(record.start_time).toBe('09:00:00')
  })
})

describe('SCRUM-57 mock of rejecting a change request', () => {
  it('needs a reason, under its field', async () => {
    const id = await raisedOnTheSummit()

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, { outcome: 'rejected' }))

    expect(refused).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { reason: ['Say why the change request is rejected.'] },
    })
  })

  it('keeps the reason and leaves the event as it was', async () => {
    const id = await raisedOnTheSummit()

    const rejected = await decideChangeRequest(PARTNER_SUMMIT, id, {
      outcome: 'rejected',
      reason: 'The hall holds 250.',
    })

    expect(rejected).toMatchObject({ status: 'rejected', decision_reason: 'The hall holds 250.' })
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record).toMatchObject({ start_time: '09:00:00', expected_attendance: 250 })
  })
})

describe("SCRUM-57 mock's refusals", () => {
  it('refuses deciding one that is no longer Pending, naming its status (AC5)', async () => {
    const id = await raisedOnTheSummit()
    signInAs(MOCK_ACCOUNTS.organiser)
    await withdrawChangeRequest(PARTNER_SUMMIT, id)
    signInAs(CHLOE)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_not_pending',
      message: 'Only a pending change request can be decided; this one is withdrawn.',
    })
  })

  it('answers not found for an id the event does not have', async () => {
    signInAs(CHLOE)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, 999, APPROVE))

    expect(refused).toMatchObject({ status: 404, code: 'not_found' })
  })

  it('answers not found to a coordinator the event is not assigned to, leaving it Pending', async () => {
    const id = await raisedOnTheSummit()
    signInAs(MOCK_ACCOUNTS.freshCoordinator)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Event request not found.',
    })
    signInAs(CHLOE)
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.change_requests[0]?.status).toBe('pending')
  })

  it('refuses the organiser by role', async () => {
    const id = await raisedOnTheSummit()
    signInAs(MOCK_ACCOUNTS.organiser)

    const refused = await refusal(decideChangeRequest(PARTNER_SUMMIT, id, APPROVE))

    expect(refused).toMatchObject({ status: 403, code: 'authorization_error' })
  })
})

describe("SCRUM-57 AC9 mock of the event's decisions waiting for a Pending change request", () => {
  const HANA = MOCK_ACCOUNTS.planningCoordinator

  it.each([
    ['approving or rejecting it', CHLOE, PARTNER_SUMMIT, 'decide', { outcome: 'approved' }],
    ['rejecting it in planning', HANA, APPROVED_WITH_GAPS, 'reject', { reason: 'Out of budget.' }],
    ['confirming it', HANA, READY_TO_CONFIRM, 'confirm', undefined],
  ])('refuses %s', async (_action, coordinator, reference, action, body) => {
    pendingOn(reference)
    signInAs(coordinator)

    const refused = await refusal(
      apiRequest(`/api/events/requests/${reference}/${action}`, { method: 'POST', body }),
    )

    expect(refused).toMatchObject({
      status: 409,
      code: 'change_request_pending',
      message: PENDING_MESSAGE,
    })
  })
})
