import { fetchAssignedEventRequests, sendToSafetyReview } from '@/features/eventRequests/api'
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
 * request 43 unanswered) and EVR-PLAN0002 (approved and settled). Chloe coordinates EVR-MOCK0001
 * (approved, nothing arranged in this mock) and EVR-BOOK0102 (confirmed).
 */

const HANA = MOCK_ACCOUNTS.planningCoordinator
const CHLOE = MOCK_ACCOUNTS.coordinator
const APPROVED_WITH_GAPS = 'EVR-PLAN0001'
const APPROVED_AND_SETTLED = 'EVR-PLAN0002'
const APPROVED_WITH_NOTHING_ARRANGED = 'EVR-MOCK0001'
const CHLOES_CONFIRMED = 'EVR-BOOK0102'

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
