import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import { ROLE } from '@/config/roles'
import {
  decideBookingRequest,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import {
  decideEventRequest,
  fetchAssignedEventRequests,
  fetchEventRequest,
  startEventRequestReview,
} from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { refusal } from '@/test/refusal'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import { MOCK_BOOKING_VENUES } from './bookingFixtures'
import { MOCK_NOW } from './catalogueFixtures'
import {
  accountsOfEveryRoleBut,
  expectInvalid,
  expectNotAnObject,
  NOT_FOUND,
  NOT_PERMITTED,
  NOT_SIGNED_IN,
  signInAs,
  statusOf,
} from './test/eventRequestCalls'

/**
 * The mock of a coordinator starting a review and deciding a request (POST
 * /api/events/requests/<reference>/review and /decide), pinned to what the backend does:
 * only the assigned coordinator, only from the statuses it allows, its check order, codes,
 * messages and field messages (SCRUM-31 AC3 to AC7, ADR-0028, ADR-0029, ADR-0060). The mock's
 * "now" is MOCK_NOW. The integration tests check the same contract against the backend.
 *
 * Priya coordinates organisation 2's EVR-RV4K8N2P (submitted), EVR-RV2D5F8J (under review) and
 * EVR-RV7T3M5Q (approved), both with an equipment request, and EVR-RV9H6C1W (rejected). Chloe
 * coordinates EVR-B6YF2K8V (awaiting clarification) and EVR-BOOK0102 (confirmed).
 */

const SUBMITTED = 'EVR-RV4K8N2P'
const UNDER_REVIEW = 'EVR-RV2D5F8J'
const LOCKED_APPROVED = 'EVR-RV7T3M5Q'
const REJECTED = 'EVR-RV9H6C1W'
const AWAITING_ANSWER = 'EVR-B6YF2K8V'
const CONFIRMED = 'EVR-BOOK0102'
const UNASSIGNED = 'EVR-Q4ZT6N1B'
const PRIYA = MOCK_ACCOUNTS.reviewingCoordinator
const CHLOE = MOCK_ACCOUNTS.coordinator

const NOT_REVIEWABLE = {
  status: 409,
  code: 'request_not_reviewable',
  message: 'Only a submitted event request can be moved to under review.',
}
const NOT_DECIDABLE = {
  status: 409,
  code: 'request_not_decidable',
  message:
    'Only a submitted, under-review, awaiting-clarification, approved or rejected event ' +
    'request can be decided.',
}
const LOCKED = {
  status: 409,
  code: 'decision_locked',
  message:
    "The decision can't be changed once the event has an equipment request or a venue " +
    'booking request.',
}
const CLARIFICATION_OUTSTANDING = {
  status: 409,
  code: 'clarification_outstanding',
  message:
    "The request can't be approved until the organiser has answered the clarification request.",
}
const REASON_REQUIRED = 'A reason is required to reject a request or to change a decision.'
const OUTCOME_MESSAGE = 'Outcome must be approved or rejected.'
const EVERY_OTHER_ROLE = accountsOfEveryRoleBut(ROLE.EVENT_COORDINATOR)

/** Send `body` to /decide as it is, whatever its shape. */
function decideWith(reference: string, body: unknown) {
  return apiRequest(`/api/events/requests/${reference}/decide`, { method: 'POST', body })
}

describe('SCRUM-31 AC3 mock: starting a review', () => {
  it('moves a submitted request to under review, in the reply, the record and the list', async () => {
    signInAs(PRIYA)

    const reviewed = await startEventRequestReview(SUBMITTED)

    expect(reviewed).toMatchObject({ reference: SUBMITTED, status: 'under_review' })
    expect(reviewed).not.toHaveProperty('coordinator')
    expect(await statusOf(SUBMITTED)).toBe('under_review')
    const listed = (await fetchAssignedEventRequests()).event_requests
    expect(listed.find((row) => row.reference === SUBMITTED)?.status).toBe('under_review')
  })

  it.each([
    ['under review', PRIYA, UNDER_REVIEW],
    ['approved', PRIYA, LOCKED_APPROVED],
    ['rejected', PRIYA, REJECTED],
    ['awaiting clarification', CHLOE, AWAITING_ANSWER],
    ['confirmed', CHLOE, CONFIRMED],
  ])(
    'refuses a request that is %s, and leaves it as it was',
    async (_status, account, reference) => {
      signInAs(account)
      const before = await statusOf(reference)

      expect(await refusal(startEventRequestReview(reference))).toMatchObject(NOT_REVIEWABLE)
      expect(await statusOf(reference)).toBe(before)
    },
  )

  it.each([
    ["another coordinator's request", SUBMITTED],
    ['a request with no coordinator', UNASSIGNED],
  ])('answers %s as not found (AC5)', async (_case, reference) => {
    signInAs(CHLOE)

    expect(await refusal(startEventRequestReview(reference))).toMatchObject(NOT_FOUND)
  })

  it('refuses the organiser, and a visitor who is not signed in', async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)
    const organiser = await refusal(startEventRequestReview(SUBMITTED))
    signInAs(null)
    const visitor = await refusal(startEventRequestReview(SUBMITTED))

    expect(organiser).toMatchObject(NOT_PERMITTED)
    expect(visitor).toMatchObject(NOT_SIGNED_IN)
    signInAs(PRIYA)
    expect(await statusOf(SUBMITTED)).toBe('submitted')
  })

  it.each(EVERY_OTHER_ROLE)(
    'refuses the %s role before looking for the request (AC5)',
    async (_role, account) => {
      signInAs(account)

      expect(await refusal(startEventRequestReview(SUBMITTED))).toMatchObject(NOT_PERMITTED)
    },
  )
})

describe('SCRUM-31 AC4, AC6 mock: deciding', () => {
  beforeEach(() => signInAs(PRIYA))

  it('approves a submitted request without a reason, and the record names who and when', async () => {
    const decided = await decideEventRequest(SUBMITTED, { outcome: 'approved' })

    expect(decided).toMatchObject({ reference: SUBMITTED, status: 'approved' })
    expect((await fetchEventRequest(SUBMITTED)).decision).toEqual({
      outcome: 'approved',
      reason: null,
      decided_by: 'Priya Nair',
      decided_at: MOCK_NOW,
    })
  })

  it('takes a null reason as none', async () => {
    await decideWith(UNDER_REVIEW, { outcome: 'approved', reason: null })

    expect(await fetchEventRequest(UNDER_REVIEW)).toMatchObject({
      status: 'approved',
      decision: { outcome: 'approved', reason: null },
    })
  })

  it('rejects a request under review with its reason, trimmed, though it has an equipment request (AC7 locks only a change)', async () => {
    const decided = await decideEventRequest(UNDER_REVIEW, {
      outcome: 'rejected',
      reason: '  The hall is booked that week.  ',
    })

    expect(decided.status).toBe('rejected')
    expect((await fetchEventRequest(UNDER_REVIEW)).decision).toMatchObject({
      outcome: 'rejected',
      reason: 'The hall is booked that week.',
    })
  })

  it('refuses a rejection without a reason, and changes nothing', async () => {
    const error = await refusal(decideEventRequest(SUBMITTED, { outcome: 'rejected' }))

    expectInvalid(error, { reason: [REASON_REQUIRED] })
    expect(await fetchEventRequest(SUBMITTED)).toMatchObject({
      status: 'submitted',
      decision: null,
    })
  })

  it.each([
    ['a rejected request approved', REJECTED, 'approved'],
    ['a rejected request rejected again', REJECTED, 'rejected'],
  ] as const)('refuses %s without a reason (AC6)', async (_case, reference, outcome) => {
    const error = await refusal(decideEventRequest(reference, { outcome }))

    expectInvalid(error, { reason: [REASON_REQUIRED] })
    expect(await statusOf(reference)).toBe('rejected')
  })

  it('changes a rejection to an approval with a reason, replacing the current decision (AC6)', async () => {
    await decideEventRequest(REJECTED, { outcome: 'approved', reason: 'The atrium reopened.' })

    expect(await fetchEventRequest(REJECTED)).toMatchObject({
      status: 'approved',
      decision: { outcome: 'approved', reason: 'The atrium reopened.', decided_by: 'Priya Nair' },
    })
  })

  it('records a new reason for the same outcome on an approved request without equipment', async () => {
    signInAs(CHLOE)

    await decideEventRequest('EVR-BOOK0101', { outcome: 'approved', reason: 'Venue confirmed.' })

    expect(await fetchEventRequest('EVR-BOOK0101')).toMatchObject({
      status: 'approved',
      decision: { outcome: 'approved', reason: 'Venue confirmed.', decided_by: 'Chloe Lim' },
    })
  })

  it('refuses any new decision once the event has an equipment request, whatever the body (AC7)', async () => {
    const withReason = await refusal(
      decideEventRequest(LOCKED_APPROVED, { outcome: 'rejected', reason: 'Too late.' }),
    )
    const withNothing = await refusal(decideWith(LOCKED_APPROVED, {}))

    expect(withReason).toMatchObject(LOCKED)
    expect(withNothing).toMatchObject(LOCKED)
    expect((await fetchEventRequest(LOCKED_APPROVED)).decision?.decided_at).toBe(
      '2026-09-28T16:00:00+08:00',
    )
  })

  it('refuses a confirmed event as past its decision, whatever the body', async () => {
    signInAs(CHLOE)

    expect(await refusal(decideWith(CONFIRMED, {}))).toMatchObject(NOT_DECIDABLE)
    expect(await statusOf(CONFIRMED)).toBe('confirmed')
  })

  it.each([
    ["another coordinator's request", SUBMITTED],
    ['a request with no coordinator', UNASSIGNED],
  ])('answers %s as not found, whatever the body (AC5)', async (_case, reference) => {
    signInAs(CHLOE)

    expect(await refusal(decideWith(reference, {}))).toMatchObject(NOT_FOUND)
  })

  it('refuses the organiser, and a visitor who is not signed in', async () => {
    signInAs(MOCK_ACCOUNTS.otherOrganiser)
    const organiser = await refusal(decideEventRequest(SUBMITTED, { outcome: 'approved' }))
    signInAs(null)
    const visitor = await refusal(decideEventRequest(SUBMITTED, { outcome: 'approved' }))

    expect(organiser).toMatchObject(NOT_PERMITTED)
    expect(visitor).toMatchObject(NOT_SIGNED_IN)
  })

  it.each(EVERY_OTHER_ROLE)(
    'refuses the %s role before looking for the request (AC5)',
    async (_role, account) => {
      signInAs(account)

      expect(await refusal(decideWith(SUBMITTED, { outcome: 'approved' }))).toMatchObject(
        NOT_PERMITTED,
      )
    },
  )
})

describe('SCRUM-31 AC7 mock: a venue booking request locks the decision (ADR-0084)', () => {
  /** Chloe's approved event, which the booking mock lets her raise venue requests for. */
  const BOOKABLE = 'EVR-BOOK0101'
  const CHANGE = { outcome: 'rejected', reason: 'The venue fell through.' } as const

  /** Chloe raises a venue booking request for BOOKABLE; it starts Pending. */
  async function raiseVenueRequest() {
    const raised = await raiseBookingRequest(BOOKABLE, {
      venue_id: MOCK_BOOKING_VENUES.roomy.id,
      starts_at: '2026-11-10T09:00:00+08:00',
      ends_at: '2026-11-10T12:00:00+08:00',
      purpose: 'Keynote',
    })
    return raised.id
  }

  beforeEach(() => signInAs(CHLOE))

  it('refuses a new decision once the event has a pending venue booking request', async () => {
    await raiseVenueRequest()

    expect(await refusal(decideEventRequest(BOOKABLE, CHANGE))).toMatchObject(LOCKED)
    expect(await statusOf(BOOKABLE)).toBe('approved')
  })

  it('still refuses it once Venue Staff have rejected the venue booking request', async () => {
    const requestId = await raiseVenueRequest()
    signInAs(MOCK_ACCOUNTS.venueStaff)
    await decideBookingRequest(requestId, { outcome: 'rejected', reason: 'Hall closed.' })
    signInAs(CHLOE)

    expect(await refusal(decideEventRequest(BOOKABLE, CHANGE))).toMatchObject(LOCKED)
    expect(await statusOf(BOOKABLE)).toBe('approved')
  })

  it('lets the decision change again once the venue booking request is withdrawn', async () => {
    const requestId = await raiseVenueRequest()
    await withdrawArrangement(BOOKABLE, requestId)

    await decideEventRequest(BOOKABLE, CHANGE)

    expect(await statusOf(BOOKABLE)).toBe('rejected')
  })
})

describe('SCRUM-32 AC3 mock: deciding while a question is outstanding', () => {
  beforeEach(() => signInAs(CHLOE))

  it('refuses an approval, with or without a reason', async () => {
    const bare = await refusal(decideEventRequest(AWAITING_ANSWER, { outcome: 'approved' }))
    const reasoned = await refusal(
      decideEventRequest(AWAITING_ANSWER, { outcome: 'approved', reason: 'Fine by us.' }),
    )

    expect(bare).toMatchObject(CLARIFICATION_OUTSTANDING)
    expect(reasoned).toMatchObject(CLARIFICATION_OUTSTANDING)
    expect(await statusOf(AWAITING_ANSWER)).toBe(EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION)
  })

  it('still allows a rejection with a reason', async () => {
    await decideEventRequest(AWAITING_ANSWER, { outcome: 'rejected', reason: 'No reply in time.' })

    expect(await statusOf(AWAITING_ANSWER)).toBe('rejected')
  })
})

describe('SCRUM-31 mock: what /decide refuses in its body', () => {
  beforeEach(() => signInAs(PRIYA))

  it.each([
    ['no outcome', {}, { outcome: ['Missing data for required field.'] }],
    ['a null outcome', { outcome: null }, { outcome: ['Field may not be null.'] }],
    ['an outcome that is neither', { outcome: 'maybe' }, { outcome: [OUTCOME_MESSAGE] }],
    ['an outcome as a number', { outcome: 1 }, { outcome: [OUTCOME_MESSAGE] }],
    ['a blank reason', { outcome: 'rejected', reason: '   ' }, { reason: ['Must not be blank.'] }],
    [
      'a reason as a number',
      { outcome: 'approved', reason: 5 },
      { reason: ['Not a valid string.'] },
    ],
    ['an unknown field', { outcome: 'approved', colour: 'red' }, { colour: ['Unknown field.'] }],
    [
      'two bad fields at once',
      { outcome: 'maybe', reason: '' },
      { outcome: [OUTCOME_MESSAGE], reason: ['Must not be blank.'] },
    ],
  ])('refuses %s with its field message', async (_case, body, details) => {
    expectInvalid(await refusal(decideWith(SUBMITTED, body)), details)
    expect(await statusOf(SUBMITTED)).toBe('submitted')
  })

  it.each([
    ['a list', ['approved']],
    ['a string', 'approved'],
  ])('refuses a body that is %s, not an object', async (_case, body) => {
    expectNotAnObject(await refusal(decideWith(SUBMITTED, body)))
  })
})
