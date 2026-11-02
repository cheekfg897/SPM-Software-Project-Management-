import { fetchBookingRequests, raiseBookingRequest } from '@/features/booking/api'
import {
  decideChangeRequest,
  decideEventRequest,
  editEventRequest,
  fetchEventHistory,
  fetchEventRequest,
  raiseChangeRequest,
  sendToSafetyReview,
  withdrawChangeRequest,
} from '@/features/eventRequests/api'
import type { DecisionChoice, RequestedChange } from '@/features/eventRequests/api'
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
 * decisions are refused (AC9). An approved change reassesses what it unsettles, as an edit does
 * (SCRUM-58, ADR-0129). The mock's "now" is 5 Oct, 12:00 pm.
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
const MORE_PARTNERS: RequestedChange = {
  field: 'expected_attendance',
  previous_value: 250,
  requested_value: 300,
}
/** Chloe's: approved, and Confirmed with no planning of its own; 9:00 am to 5:00 pm, 80 expected. */
const CAREERS_FAIR = 'EVR-BOOK0101'
const TOWN_HALL = 'EVR-BOOK0102'
const TIMING_REASON = "The event's date or time changed."
const LATER_START: RequestedChange = {
  field: 'start_time',
  previous_value: '09:00:00',
  requested_value: '10:00:00',
}
const FEWER_PEOPLE: RequestedChange = {
  field: 'expected_attendance',
  previous_value: 80,
  requested_value: 60,
}
const NEW_PROGRAMME: RequestedChange = {
  field: 'programme_notes',
  previous_value: null,
  requested_value: 'A panel is added.',
}
const HANA = MOCK_ACCOUNTS.planningCoordinator

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

/**
 * A Pending change request kept on `reference` as if its organiser had raised it. Answers its id.
 */
function pendingOn(reference: string, change: RequestedChange = MORE_PARTNERS): number {
  const kept = addChangeRequest(reference, {
    status: 'pending',
    changes: [change],
    reason: 'More partners.',
    raised_by: 'Omar Rahman',
    raised_at: MOCK_NOW,
    withdrawn_at: null,
    withdrawal_note: null,
    decided_by: null,
    decided_at: null,
    decision_reason: null,
  })
  return kept.id
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

describe('SCRUM-58 mock of what an approved change reassesses', () => {
  const RISE_TO_90 =
    "The event's expected attendance rose from 80 to 90, above this arrangement's expected occupancy of 80."

  /** Chloe raises a booking for all 80 on the careers fair, in the hall (venue 1, for 200). */
  function raiseOnCareersFair() {
    signInAs(CHLOE)
    return raiseBookingRequest(CAREERS_FAIR, {
      venue_id: 1,
      purpose: 'Hall',
      starts_at: '2026-11-10T09:00:00+08:00',
      ends_at: '2026-11-10T12:00:00+08:00',
    })
  }

  /** The event's coordinator, already signed in, approves a change of its attendance. */
  function approveAttendance(reference: string, from: number, to: number) {
    const id = pendingOn(reference, {
      field: 'expected_attendance',
      previous_value: from,
      requested_value: to,
    })
    return decideChangeRequest(reference, id, APPROVE)
  }

  it('flags the booking and shows it on the record (AC1)', async () => {
    const hall = await raiseOnCareersFair()
    const id = pendingOn(CAREERS_FAIR, LATER_START)

    await decideChangeRequest(CAREERS_FAIR, id, APPROVE)

    const flags = [{ kind: 'requires_reconfirmation', reason: TIMING_REASON }]
    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking).toMatchObject({ id: hall.id, flagged_after_change: true })
    expect(booking?.reassessment_flags).toEqual(flags)
    const record = await fetchEventRequest(CAREERS_FAIR)
    expect(record.venue_arrangements?.[0]?.reassessment_flags).toEqual(flags)
  })

  it('leaves the booking untouched when anything else changes (AC4)', async () => {
    await raiseOnCareersFair()
    const id = pendingOn(CAREERS_FAIR, NEW_PROGRAMME)

    await decideChangeRequest(CAREERS_FAIR, id, APPROVE)

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking).toMatchObject({ flagged_after_change: false, reassessment_flags: [] })
  })

  it('leaves the booking untouched when the change is rejected', async () => {
    await raiseOnCareersFair()
    const id = pendingOn(CAREERS_FAIR, LATER_START)

    await decideChangeRequest(CAREERS_FAIR, id, { outcome: 'rejected', reason: 'No.' })

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking).toMatchObject({ flagged_after_change: false, reassessment_flags: [] })
  })

  it('marks a booking an earlier rise outgrew when the attendance rises again (AC2)', async () => {
    await raiseOnCareersFair()

    await approveAttendance(CAREERS_FAIR, 80, 90)
    await approveAttendance(CAREERS_FAIR, 90, 250)

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking?.reassessment_flags).toEqual([
      { kind: 'requires_reconfirmation', reason: RISE_TO_90 },
      {
        kind: 'no_longer_suitable',
        reason: "Expected attendance of 250 exceeds the venue's capacity of 200.",
      },
    ])
  })

  it('adds nothing when the attendance falls after a rise (AC5)', async () => {
    await raiseOnCareersFair()

    await approveAttendance(CAREERS_FAIR, 80, 90)
    await approveAttendance(CAREERS_FAIR, 90, 85)

    const [booking] = await fetchBookingRequests(CAREERS_FAIR)
    expect(booking?.reassessment_flags).toEqual([
      { kind: 'requires_reconfirmation', reason: RISE_TO_90 },
    ])
  })

  it('marks an arrangement the gates count on a second rise, naming the capacity (AC2)', async () => {
    signInAs(HANA)

    await approveAttendance(READY_TO_CONFIRM, 150, 160)
    await approveAttendance(READY_TO_CONFIRM, 160, 250)

    const refused = await refusal(sendToSafetyReview(READY_TO_CONFIRM))
    expect(refused).toMatchObject({
      fieldErrors: {
        venue_arrangements: [
          "Venue arrangement 46 is flagged (requires reconfirmation): The event's expected attendance rose from 150 to 160, above this arrangement's expected occupancy of 150.",
          "Venue arrangement 46 is flagged (no longer suitable): Expected attendance of 250 exceeds the venue's capacity of 200.",
        ],
      },
    })
  })

  it('holds the event back from Safety Review, naming the capacity (AC2, AC3)', async () => {
    signInAs(HANA)
    const id = pendingOn(READY_TO_CONFIRM, {
      field: 'expected_attendance',
      previous_value: 150,
      requested_value: 250,
    })

    await decideChangeRequest(READY_TO_CONFIRM, id, APPROVE)

    const refused = await refusal(sendToSafetyReview(READY_TO_CONFIRM))
    expect(refused).toMatchObject({
      fieldErrors: {
        venue_arrangements: [
          "Venue arrangement 46 is flagged (no longer suitable): Expected attendance of 250 exceeds the venue's capacity of 200.",
        ],
      },
    })
  })

  it('withdraws a safety approval and sends the event back to Approved (AC6)', async () => {
    signInAs(HANA)
    const id = pendingOn(READY_TO_CONFIRM, {
      field: 'start_time',
      previous_value: '10:00:00',
      requested_value: '11:00:00',
    })

    await decideChangeRequest(READY_TO_CONFIRM, id, APPROVE)

    const record = await fetchEventRequest(READY_TO_CONFIRM)
    expect(record.status).toBe('approved')
    const { history } = await fetchEventHistory(READY_TO_CONFIRM)
    expect(history.at(-1)).toMatchObject({
      kind: 'safety_approval_withdrawn',
      actor_name: HANA.full_name,
      details: { significant_fields: ['start_time'] },
    })
  })

  it('sends a Confirmed event back to Approved after any significant change (AC7)', async () => {
    signInAs(CHLOE)
    const id = pendingOn(TOWN_HALL, FEWER_PEOPLE)

    await decideChangeRequest(TOWN_HALL, id, APPROVE)

    const record = await fetchEventRequest(TOWN_HALL)
    expect(record.status).toBe('approved')
  })

  it('leaves a Confirmed event Confirmed after a change that is not significant (AC7)', async () => {
    signInAs(CHLOE)
    const id = pendingOn(TOWN_HALL, NEW_PROGRAMME)

    await decideChangeRequest(TOWN_HALL, id, APPROVE)

    const record = await fetchEventRequest(TOWN_HALL)
    expect(record.status).toBe('confirmed')
    const { history } = await fetchEventHistory(TOWN_HALL)
    const kinds = history.map((entry) => entry.kind)
    expect(kinds).not.toContain('safety_approval_withdrawn')
  })
})

describe("SCRUM-57 AC9 mock of the event's decisions waiting for a Pending change request", () => {
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
