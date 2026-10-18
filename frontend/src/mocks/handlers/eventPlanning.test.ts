import {
  completeEvent,
  fetchAssignedEventRequests,
  sendToSafetyReview,
} from '@/features/eventRequests/api'
import { fieldErrorsOf } from '@/lib/api'
import { refusal } from '@/test/refusal'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'

import {
  NOT_FOUND,
  NOT_PERMITTED,
  NOT_SIGNED_IN,
  signInAs,
  statusOf,
} from './test/eventRequestCalls'

/**
 * The mock of the coordinator's planning actions, pinned to what the backend does: only the
 * assigned coordinator, only from the status each accepts, its check order, codes, messages and
 * the gaps it names (ADR-0047, ADR-0075). The integration tests check the same contract against
 * the backend.
 *
 * Hana coordinates EVR-PLAN0001 (approved; arrangement 42 pending, 40 withdrawn, equipment
 * request 43 unanswered) and EVR-PLAN0002 (approved and settled), and two confirmed events:
 * EVR-PLAN0005, ending exactly at the mock's "now" (MOCK_NOW), and EVR-PLAN0006, which began the
 * day before and ends a minute after it. Chloe coordinates EVR-MOCK0001 (approved, nothing
 * arranged in this mock) and EVR-BOOK0102 (confirmed).
 */

const HANA = MOCK_ACCOUNTS.planningCoordinator
const CHLOE = MOCK_ACCOUNTS.coordinator
const APPROVED_WITH_GAPS = 'EVR-PLAN0001'
const APPROVED_AND_SETTLED = 'EVR-PLAN0002'
const APPROVED_WITH_NOTHING_ARRANGED = 'EVR-MOCK0001'
const CHLOES_CONFIRMED = 'EVR-BOOK0102'
const ENDED_AT_NOW = 'EVR-PLAN0005'
const ENDS_A_MINUTE_AFTER_NOW = 'EVR-PLAN0006'

const SAFETY_REVIEW_NOT_READY = {
  status: 409,
  code: 'safety_review_not_allowed',
  message:
    'The event can go to Safety Review once every venue arrangement is approved and every ' +
    'equipment request has an outcome from Technical Support.',
}

describe('SCRUM-97 mock: sending an event to safety review', () => {
  it('moves a settled, approved event to safety review, in the reply, the record and the list', async () => {
    signInAs(HANA)

    const sent = await sendToSafetyReview(APPROVED_AND_SETTLED)

    expect(sent).toMatchObject({ reference: APPROVED_AND_SETTLED, status: 'safety_review' })
    expect(sent).not.toHaveProperty('coordinator')
    expect(await statusOf(APPROVED_AND_SETTLED)).toBe('safety_review')
    const listed = (await fetchAssignedEventRequests()).event_requests
    expect(listed.find((row) => row.reference === APPROVED_AND_SETTLED)?.status).toBe(
      'safety_review',
    )
  })

  it('names every active arrangement not approved and every unanswered equipment request', async () => {
    signInAs(HANA)

    const error = await refusal(sendToSafetyReview(APPROVED_WITH_GAPS))

    expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
    expect(fieldErrorsOf(error)).toEqual({
      venue_arrangements: ['Venue arrangement 42 is pending.'],
      equipment: ['Equipment request 43 has no outcome from Technical Support.'],
    })
    expect(await statusOf(APPROVED_WITH_GAPS)).toBe('approved')
  })

  it('names a missing venue when the event has none arranged', async () => {
    signInAs(CHLOE)

    const error = await refusal(sendToSafetyReview(APPROVED_WITH_NOTHING_ARRANGED))

    expect(error).toMatchObject(SAFETY_REVIEW_NOT_READY)
    expect(fieldErrorsOf(error)).toEqual({
      venue_arrangements: ['The event has no venue arranged.'],
    })
  })

  it('refuses an event that is not approved, before looking at its arrangements', async () => {
    signInAs(CHLOE)

    const error = await refusal(sendToSafetyReview(CHLOES_CONFIRMED))

    expect(error).toMatchObject({
      status: 409,
      code: 'safety_review_not_allowed',
      message: 'Only an approved event can go to Safety Review.',
    })
    expect(fieldErrorsOf(error)).toEqual({})
  })

  it("answers another coordinator's event as not found, and leaves it approved", async () => {
    signInAs(CHLOE)

    expect(await refusal(sendToSafetyReview(APPROVED_AND_SETTLED))).toMatchObject(NOT_FOUND)
    signInAs(HANA)
    expect(await statusOf(APPROVED_AND_SETTLED)).toBe('approved')
  })

  it('refuses an organiser by role, and a visitor without a token', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)
    expect(await refusal(sendToSafetyReview(APPROVED_AND_SETTLED))).toMatchObject(NOT_PERMITTED)

    signInAs(null)
    expect(await refusal(sendToSafetyReview(APPROVED_AND_SETTLED))).toMatchObject(NOT_SIGNED_IN)
  })
})

describe('SCRUM-68 mock: marking an event completed', () => {
  const NOT_CONFIRMED = {
    status: 409,
    code: 'request_not_completable',
    message: 'Only a confirmed event can be marked completed.',
  }

  it('completes a confirmed event whose end is exactly now, in the reply and the record', async () => {
    signInAs(HANA)

    const completed = await completeEvent(ENDED_AT_NOW)

    expect(completed).toMatchObject({ reference: ENDED_AT_NOW, status: 'completed' })
    expect(completed).not.toHaveProperty('coordinator')
    expect(await statusOf(ENDED_AT_NOW)).toBe('completed')
  })

  it('refuses an event ending a minute from now, judged by its end date, not its start', async () => {
    signInAs(HANA)

    expect(await refusal(completeEvent(ENDS_A_MINUTE_AFTER_NOW))).toMatchObject({
      status: 409,
      code: 'request_not_completable',
      message: 'The event has not ended yet.',
    })
    expect(await statusOf(ENDS_A_MINUTE_AFTER_NOW)).toBe('confirmed')
  })

  it('refuses an event that is not confirmed, before looking at its end', async () => {
    signInAs(HANA)

    expect(await refusal(completeEvent(APPROVED_AND_SETTLED))).toMatchObject(NOT_CONFIRMED)
  })

  it('refuses to complete an event twice', async () => {
    signInAs(HANA)
    await completeEvent(ENDED_AT_NOW)

    expect(await refusal(completeEvent(ENDED_AT_NOW))).toMatchObject(NOT_CONFIRMED)
  })

  it("answers another coordinator's event as not found, and refuses other roles", async () => {
    signInAs(CHLOE)
    expect(await refusal(completeEvent(ENDED_AT_NOW))).toMatchObject(NOT_FOUND)

    signInAs(MOCK_ACCOUNTS.organiser)
    expect(await refusal(completeEvent(ENDED_AT_NOW))).toMatchObject(NOT_PERMITTED)

    signInAs(null)
    expect(await refusal(completeEvent(ENDED_AT_NOW))).toMatchObject(NOT_SIGNED_IN)
    signInAs(HANA)
    expect(await statusOf(ENDED_AT_NOW)).toBe('confirmed')
  })
})
