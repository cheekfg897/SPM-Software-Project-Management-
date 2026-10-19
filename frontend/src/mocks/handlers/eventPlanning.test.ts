import {
  completeEvent,
  confirmEvent,
  decideEventRequest,
  fetchEventHistory,
  fetchAssignedEventRequests,
  rejectEvent,
  sendToSafetyReview,
  updateRegistrationSettings,
} from '@/features/eventRequests/api'
import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import { apiRequest, fieldErrorsOf } from '@/lib/api'
import { refusal } from '@/test/refusal'

import { MOCK_ACCOUNTS } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { MOCK_NOW } from './catalogueFixtures'
import {
  expectInvalid,
  expectNotAnObject,
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
 * request 43 unanswered) and EVR-PLAN0002 (approved and settled); EVR-PLAN0003 (in Safety
 * Review, approved by the Safety Officer and settled) and EVR-PLAN0004 (in Safety Review, not
 * approved, arrangement 48 rejected, equipment request 49 unanswered); and two confirmed events:
 * EVR-PLAN0005, ending exactly at the mock's "now" (MOCK_NOW), and EVR-PLAN0006, which began the
 * day before and ends a minute after it. EVR-PLAN0005's registration is open for 50 with 30
 * registered; EVR-PLAN0006's organiser asked for registration and nothing is set. Chloe
 * coordinates EVR-MOCK0001 (approved, nothing arranged in this mock) and EVR-BOOK0102
 * (confirmed; no registration asked for or set).
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

  it('keeps the decision of an approved event with an equipment request (SCRUM-31 AC7)', async () => {
    signInAs(HANA)

    const error = await refusal(
      decideEventRequest(APPROVED_WITH_GAPS, { outcome: 'rejected', reason: 'No venue.' }),
    )

    expect(error).toMatchObject({ status: 409, code: 'decision_locked' })
    expect(await statusOf(APPROVED_WITH_GAPS)).toBe('approved')
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

describe('SCRUM-69 mock: registration settings', () => {
  const OPEN_FOR_50 = 'EVR-PLAN0005'
  const ASKED_FOR_NOTHING_SET = 'EVR-PLAN0006'
  const CAPACITY_REQUIRED = 'A capacity is required to enable registration.'
  const BELOW_REGISTERED = 'Capacity cannot be lower than the 30 places already taken.'
  const NOT_AN_INTEGER = 'Not a valid integer.'
  const OUT_OF_RANGE = 'Capacity must be between 1 and 2147483647.'

  /** Send `body` to the registration route as it is, whatever its shape. */
  function patchWith(reference: string, body: unknown) {
    return apiRequest(`/api/events/requests/${reference}/registration`, { method: 'PATCH', body })
  }

  it('opens registration with a capacity, answering with the settings as they now are', async () => {
    signInAs(HANA)

    const settings = await updateRegistrationSettings(ASKED_FOR_NOTHING_SET, {
      registration_enabled: true,
      registration_capacity: 120,
    })

    expect(settings).toEqual({
      reference: ASKED_FOR_NOTHING_SET,
      registration_required: true,
      registration_enabled: true,
      registration_capacity: 120,
      withdrawal_cut_off: null,
    })
    const closed = await updateRegistrationSettings(ASKED_FOR_NOTHING_SET, {
      registration_enabled: false,
    })
    expect(closed).toMatchObject({ registration_enabled: false, registration_capacity: 120 })
  })

  it("follows the organiser's answer when only a first capacity is sent (AC1)", async () => {
    signInAs(HANA)
    const asked = await updateRegistrationSettings(ASKED_FOR_NOTHING_SET, {
      registration_capacity: 80,
    })
    expect(asked).toMatchObject({ registration_enabled: true, registration_capacity: 80 })

    signInAs(CHLOE)
    const notAsked = await updateRegistrationSettings(CHLOES_CONFIRMED, {
      registration_capacity: 10,
    })
    expect(notAsked).toMatchObject({ registration_enabled: false, registration_capacity: 10 })
  })

  it('keeps whether registration is open when only a new capacity is sent', async () => {
    signInAs(HANA)

    const settings = await updateRegistrationSettings(OPEN_FOR_50, { registration_capacity: 40 })

    expect(settings).toMatchObject({
      registration_required: false,
      registration_enabled: true,
      registration_capacity: 40,
    })
  })

  it('changes nothing for an empty body, but still asks for a capacity the organiser needs', async () => {
    signInAs(HANA)

    const unchanged = await updateRegistrationSettings(OPEN_FOR_50, {})
    const error = await refusal(updateRegistrationSettings(ASKED_FOR_NOTHING_SET, {}))

    expect(unchanged).toMatchObject({ registration_enabled: true, registration_capacity: 50 })
    expectInvalid(error, { registration_capacity: [CAPACITY_REQUIRED] })
  })

  it('asks for a capacity to open registration on an event that has none', async () => {
    signInAs(HANA)

    const error = await refusal(
      updateRegistrationSettings(ASKED_FOR_NOTHING_SET, { registration_enabled: true }),
    )

    expectInvalid(error, { registration_capacity: [CAPACITY_REQUIRED] })
  })

  it('refuses a capacity below the number registered, open or closed, and allows exactly it', async () => {
    signInAs(HANA)

    const below = await refusal(
      updateRegistrationSettings(OPEN_FOR_50, { registration_capacity: 29 }),
    )
    expectInvalid(below, { registration_capacity: [BELOW_REGISTERED] })
    const belowClosed = await refusal(
      updateRegistrationSettings(OPEN_FOR_50, {
        registration_enabled: false,
        registration_capacity: 29,
      }),
    )
    expectInvalid(belowClosed, { registration_capacity: [BELOW_REGISTERED] })
    const exactly = await updateRegistrationSettings(OPEN_FOR_50, { registration_capacity: 30 })
    expect(exactly.registration_capacity).toBe(30)
  })

  it('refuses to open registration before the event is confirmed, but lets it stay closed', async () => {
    signInAs(HANA)

    const error = await refusal(
      updateRegistrationSettings(APPROVED_AND_SETTLED, {
        registration_enabled: true,
        registration_capacity: 10,
      }),
    )

    expect(error).toMatchObject({
      status: 409,
      code: 'registration_not_enablable',
      message: 'Registration can be enabled only for a confirmed event.',
    })
    const closed = await updateRegistrationSettings(APPROVED_AND_SETTLED, {
      registration_enabled: false,
      registration_capacity: 10,
    })
    expect(closed).toMatchObject({ registration_enabled: false, registration_capacity: 10 })
  })

  it('names every field it refuses, as marshmallow words it', async () => {
    signInAs(HANA)

    expectInvalid(
      await refusal(
        patchWith(OPEN_FOR_50, {
          registration_enabled: 'yes',
          registration_capacity: 1.5,
          size: 3,
        }),
      ),
      {
        registration_enabled: ['Not a valid boolean.'],
        registration_capacity: [NOT_AN_INTEGER],
        size: ['Unknown field.'],
      },
    )
    expectInvalid(
      await refusal(
        patchWith(OPEN_FOR_50, { registration_enabled: null, registration_capacity: 0 }),
      ),
      { registration_enabled: ['Field may not be null.'], registration_capacity: [OUT_OF_RANGE] },
    )
    expectInvalid(await refusal(patchWith(OPEN_FOR_50, { registration_capacity: '5' })), {
      registration_capacity: [NOT_AN_INTEGER],
    })
    expectInvalid(await refusal(patchWith(OPEN_FOR_50, { registration_capacity: true })), {
      registration_capacity: [NOT_AN_INTEGER],
    })
    expectInvalid(await refusal(patchWith(OPEN_FOR_50, { registration_capacity: null })), {
      registration_capacity: ['Field may not be null.'],
    })
    expectInvalid(await refusal(patchWith(OPEN_FOR_50, { registration_capacity: 2147483648 })), {
      registration_capacity: [OUT_OF_RANGE],
    })
    const largest = await updateRegistrationSettings(OPEN_FOR_50, {
      registration_capacity: 2147483647,
    })
    expect(largest.registration_capacity).toBe(2147483647)
  })

  it('refuses a body that is not a JSON object', async () => {
    signInAs(HANA)

    expectNotAnObject(await refusal(patchWith(OPEN_FOR_50, [true])))
  })

  it("answers another coordinator's event as not found before reading the body", async () => {
    signInAs(CHLOE)
    expect(await refusal(patchWith(OPEN_FOR_50, { size: 3 }))).toMatchObject(NOT_FOUND)

    signInAs(MOCK_ACCOUNTS.organiser)
    expect(await refusal(patchWith(OPEN_FOR_50, {}))).toMatchObject(NOT_PERMITTED)

    signInAs(null)
    expect(await refusal(patchWith(OPEN_FOR_50, {}))).toMatchObject(NOT_SIGNED_IN)
  })
})

describe('SCRUM-69 mock: the optional withdrawal cut-off (AC6, ADR-0086)', () => {
  /** EVR-PLAN0002 starts on 14 Nov 2026 at 10:00 in Singapore. */
  const STARTS_14_NOV_10AM = APPROVED_AND_SETTLED
  const DAY_BEFORE = '2026-11-13T10:00:00+08:00'
  const NOT_BEFORE_START = 'The withdrawal cut-off must be before the event starts.'
  const NOT_A_DATETIME = 'Not a valid datetime.'

  /** Record `cutOff` on the event with registration left closed, as the backend allows. */
  function recordCutOff(cutOff: unknown) {
    return apiRequest(`/api/events/requests/${STARTS_14_NOV_10AM}/registration`, {
      method: 'PATCH',
      body: { registration_enabled: false, withdrawal_cut_off: cutOff },
    })
  }

  it('records a cut-off and answers it in business time, keeps it, and clears it with null', async () => {
    signInAs(HANA)

    const recorded = await updateRegistrationSettings(STARTS_14_NOV_10AM, {
      registration_enabled: false,
      withdrawal_cut_off: DAY_BEFORE,
    })
    expect(recorded).toMatchObject({ registration_enabled: false, withdrawal_cut_off: DAY_BEFORE })
    const kept = await updateRegistrationSettings(STARTS_14_NOV_10AM, { registration_capacity: 9 })
    expect(kept.withdrawal_cut_off).toBe(DAY_BEFORE)
    const cleared = await updateRegistrationSettings(STARTS_14_NOV_10AM, {
      withdrawal_cut_off: null,
    })
    expect(cleared.withdrawal_cut_off).toBeNull()
  })

  it('reads a cut-off with no offset as business time, and one in UTC as the same instant', async () => {
    signInAs(HANA)

    expect(await recordCutOff('2026-11-13T10:00:00')).toMatchObject({
      withdrawal_cut_off: DAY_BEFORE,
    })
    expect(await recordCutOff('2026-11-13T02:00:00Z')).toMatchObject({
      withdrawal_cut_off: DAY_BEFORE,
    })
  })

  it('refuses a cut-off at or after the start, compared as instants, and allows a second before', async () => {
    signInAs(HANA)

    for (const cutOff of [
      '2026-11-14T10:00:00+08:00',
      '2026-11-14T02:00:00Z',
      '2026-11-14T12:00:00+08:00',
    ]) {
      expectInvalid(await refusal(recordCutOff(cutOff)), { withdrawal_cut_off: [NOT_BEFORE_START] })
    }
    expect(await recordCutOff('2026-11-14T09:59:59+08:00')).toMatchObject({
      withdrawal_cut_off: '2026-11-14T09:59:59+08:00',
    })
  })

  it('refuses anything that is not a date-time, as marshmallow words it', async () => {
    signInAs(HANA)

    for (const cutOff of [
      'tomorrow',
      '2026-11-13T25:00:00',
      '2026-02-30T10:00:00',
      1763000000,
      true,
    ]) {
      expectInvalid(await refusal(recordCutOff(cutOff)), { withdrawal_cut_off: [NOT_A_DATETIME] })
    }
  })

  it('records setting and clearing it in the history, in business time', async () => {
    signInAs(HANA)

    await recordCutOff('2026-11-13T02:00:00Z')
    await recordCutOff(null)

    const { history } = await fetchEventHistory(STARTS_14_NOV_10AM)
    expect(history.map((entry) => entry.details)).toEqual([
      {
        field: 'withdrawal_cut_off',
        previous_value: null,
        new_value: DAY_BEFORE,
        significant: false,
      },
      {
        field: 'withdrawal_cut_off',
        previous_value: DAY_BEFORE,
        new_value: null,
        significant: false,
      },
    ])
  })
})

describe('SCRUM-49 mock: confirming an event', () => {
  const READY_TO_CONFIRM = 'EVR-PLAN0003'
  const HELD_BACK_EVERYWHERE = 'EVR-PLAN0004'
  const CONFIRMATION_NOT_READY = {
    status: 409,
    code: 'confirmation_not_allowed',
    message:
      'The event can be confirmed once the Safety Officer has approved it, every venue ' +
      'arrangement is approved and every equipment request has an outcome from Technical ' +
      'Support.',
  }

  it('confirms an event in safety review with every approval in, in the reply and the record', async () => {
    signInAs(HANA)

    const confirmed = await confirmEvent(READY_TO_CONFIRM)

    expect(confirmed).toMatchObject({ reference: READY_TO_CONFIRM, status: 'confirmed' })
    expect(confirmed).not.toHaveProperty('coordinator')
    expect(await statusOf(READY_TO_CONFIRM)).toBe('confirmed')
  })

  it('names the missing safety approval, then the venue and equipment gaps, in that order', async () => {
    signInAs(HANA)

    const error = await refusal(confirmEvent(HELD_BACK_EVERYWHERE))

    expect(error).toMatchObject(CONFIRMATION_NOT_READY)
    const gaps = fieldErrorsOf(error)
    expect(Object.keys(gaps)).toEqual(['safety_check', 'venue_arrangements', 'equipment'])
    expect(gaps).toEqual({
      safety_check: ['The Safety Officer has not approved the event.'],
      venue_arrangements: ['Venue arrangement 48 is rejected.'],
      equipment: ['Equipment request 49 has no outcome from Technical Support.'],
    })
    expect(await statusOf(HELD_BACK_EVERYWHERE)).toBe('safety_review')
  })

  it('names only the safety approval for a settled event just sent to safety review', async () => {
    signInAs(HANA)
    await sendToSafetyReview(APPROVED_AND_SETTLED)

    const error = await refusal(confirmEvent(APPROVED_AND_SETTLED))

    expect(error).toMatchObject(CONFIRMATION_NOT_READY)
    expect(fieldErrorsOf(error)).toEqual({
      safety_check: ['The Safety Officer has not approved the event.'],
    })
  })

  it('refuses an event not in safety review, before looking at its approvals', async () => {
    signInAs(HANA)

    const error = await refusal(confirmEvent(APPROVED_WITH_GAPS))

    expect(error).toMatchObject({
      status: 409,
      code: 'confirmation_not_allowed',
      message: 'Only an event in Safety Review can be confirmed.',
    })
    expect(fieldErrorsOf(error)).toEqual({})
  })

  it("answers another coordinator's event as not found, and refuses other roles", async () => {
    signInAs(CHLOE)
    expect(await refusal(confirmEvent(READY_TO_CONFIRM))).toMatchObject(NOT_FOUND)

    signInAs(MOCK_ACCOUNTS.organiser)
    expect(await refusal(confirmEvent(READY_TO_CONFIRM))).toMatchObject(NOT_PERMITTED)

    signInAs(null)
    expect(await refusal(confirmEvent(READY_TO_CONFIRM))).toMatchObject(NOT_SIGNED_IN)
    signInAs(HANA)
    expect(await statusOf(READY_TO_CONFIRM)).toBe('safety_review')
  })
})

/** The statuses no mock coordinator holds an event in: drafts are hidden from staff, and nothing cancels one. */
type HeldStatus = Exclude<EventRequestStatus, 'draft' | 'cancelled'>

/** A coordinator's own event in each status the mocks hold one in. Completed is reached by completing it. */
const ASSIGNED_IN_STATUS: Record<HeldStatus, { account: MockAccount; reference: string }> = {
  submitted: { account: MOCK_ACCOUNTS.reviewingCoordinator, reference: 'EVR-RV4K8N2P' },
  under_review: { account: CHLOE, reference: 'EVR-7K2M9QXA' },
  awaiting_clarification: { account: CHLOE, reference: 'EVR-B6YF2K8V' },
  approved: { account: HANA, reference: APPROVED_AND_SETTLED },
  safety_review: { account: HANA, reference: 'EVR-PLAN0003' },
  confirmed: { account: HANA, reference: ENDS_A_MINUTE_AFTER_NOW },
  completed: { account: HANA, reference: ENDED_AT_NOW },
  rejected: { account: MOCK_ACCOUNTS.reviewingCoordinator, reference: 'EVR-RV9H6C1W' },
}

/** Every held status but `allowed`. The Record above has exactly HeldStatus as its keys. */
function statusesOtherThan(allowed: HeldStatus): HeldStatus[] {
  const held = Object.keys(ASSIGNED_IN_STATUS) as HeldStatus[]
  return held.filter((status) => status !== allowed)
}

/** Sign in as the coordinator of an event in `status`, and give its reference. */
async function ownEventIn(status: HeldStatus): Promise<string> {
  const { account, reference } = ASSIGNED_IN_STATUS[status]
  signInAs(account)
  if (status === EVENT_REQUEST_STATUS.COMPLETED) {
    await completeEvent(reference)
  }
  expect(await statusOf(reference)).toBe(status)
  return reference
}

/** Each planning action, the one status the backend takes it in, and its refusal for any other. */
const STATUS_GATES = [
  {
    action: 'sending to safety review',
    allowed: EVENT_REQUEST_STATUS.APPROVED,
    act: sendToSafetyReview,
    refused: {
      code: 'safety_review_not_allowed',
      message: 'Only an approved event can go to Safety Review.',
    },
  },
  {
    action: 'confirming',
    allowed: EVENT_REQUEST_STATUS.SAFETY_REVIEW,
    act: confirmEvent,
    refused: {
      code: 'confirmation_not_allowed',
      message: 'Only an event in Safety Review can be confirmed.',
    },
  },
  {
    action: 'marking completed',
    allowed: EVENT_REQUEST_STATUS.CONFIRMED,
    act: completeEvent,
    refused: {
      code: 'request_not_completable',
      message: 'Only a confirmed event can be marked completed.',
    },
  },
  {
    action: 'opening registration',
    allowed: EVENT_REQUEST_STATUS.CONFIRMED,
    act: (reference: string) =>
      updateRegistrationSettings(reference, {
        registration_enabled: true,
        registration_capacity: 40,
      }),
    refused: {
      code: 'registration_not_enablable',
      message: 'Registration can be enabled only for a confirmed event.',
    },
  },
] as const

describe.each(STATUS_GATES)(
  'SCRUM-97, SCRUM-49, SCRUM-68, SCRUM-69 mock: $action',
  ({ allowed, act, refused }) => {
    it.each(statusesOtherThan(allowed))(
      'refuses an event that is %s, and leaves it there',
      async (status) => {
        const reference = await ownEventIn(status)

        expect(await refusal(act(reference))).toMatchObject({ status: 409, ...refused })
        expect(await statusOf(reference)).toBe(status)
      },
    )
  },
)

/**
 * SCRUM-33 AC4: each planning action is written to the event's history as the backend writes it
 * (`record_event_history` in send_to_safety_review, confirm_event_request and
 * complete_event_request; `_record_field_changes` in update_registration_settings): its kind, by
 * the coordinator, at the mock's "now", and a refused or empty call writes nothing.
 */
describe('SCRUM-33 mock: the history each planning action writes', () => {
  /** The history `account` reads for `reference`. */
  async function historyOf(account: MockAccount, reference: string) {
    signInAs(account)
    return (await fetchEventHistory(reference)).history
  }

  /** An entry by Hana, now, as the backend shows it. */
  function byHana(kind: string, details: Record<string, unknown> = {}) {
    return { kind, occurred_at: MOCK_NOW, actor_name: HANA.full_name, details }
  }

  it.each([
    [
      'sending it to safety review',
      APPROVED_AND_SETTLED,
      sendToSafetyReview,
      'safety_review_requested',
    ],
    ['confirming it', 'EVR-PLAN0003', confirmEvent, 'event_confirmed'],
    ['marking it completed', ENDED_AT_NOW, completeEvent, 'event_completed'],
  ])('records %s, by the coordinator, now', async (_, reference, act, kind) => {
    signInAs(HANA)

    await act(reference)

    expect(await historyOf(HANA, reference)).toEqual([byHana(kind)])
  })

  it('records each registration setting that changed as a change of that field, in order', async () => {
    signInAs(HANA)

    await updateRegistrationSettings(ENDS_A_MINUTE_AFTER_NOW, { registration_capacity: 80 })

    expect(await historyOf(HANA, ENDS_A_MINUTE_AFTER_NOW)).toEqual([
      byHana('field_changed', {
        field: 'registration_enabled',
        previous_value: false,
        new_value: true,
        significant: false,
      }),
      byHana('field_changed', {
        field: 'registration_capacity',
        previous_value: null,
        new_value: 80,
        significant: false,
      }),
    ])
  })

  it('records only the setting that changed, and nothing for an unchanged one', async () => {
    signInAs(HANA)

    await updateRegistrationSettings(ENDED_AT_NOW, {
      registration_enabled: true,
      registration_capacity: 40,
    })

    expect(await historyOf(HANA, ENDED_AT_NOW)).toEqual([
      byHana('field_changed', {
        field: 'registration_capacity',
        previous_value: 50,
        new_value: 40,
        significant: false,
      }),
    ])
  })

  it('writes nothing for a refused action or a call that changes nothing', async () => {
    signInAs(HANA)

    await refusal(sendToSafetyReview(APPROVED_WITH_GAPS))
    await updateRegistrationSettings(ENDED_AT_NOW, {})

    expect(await historyOf(HANA, APPROVED_WITH_GAPS)).toEqual([])
    expect(await historyOf(HANA, ENDED_AT_NOW)).toEqual([])
  })

  it("shows the organiser a registration change, since it isn't kept internal", async () => {
    const before = await historyOf(MOCK_ACCOUNTS.otherOrganiser, CHLOES_CONFIRMED)

    signInAs(CHLOE)
    await updateRegistrationSettings(CHLOES_CONFIRMED, { registration_capacity: 120 })

    const organisersCopy = await historyOf(MOCK_ACCOUNTS.otherOrganiser, CHLOES_CONFIRMED)
    expect(organisersCopy).toHaveLength(before.length + 1)
    expect(organisersCopy.at(-1)).toMatchObject({
      kind: 'field_changed',
      actor_name: CHLOE.full_name,
      details: { field: 'registration_capacity', previous_value: null, new_value: 120 },
    })
  })
})

/**
 * SCRUM-49 AC9, AC10 (ADR-0093): the assigned coordinator rejects an approved event or one in
 * Safety Review with a reason. It is recorded as a decision, each arrangement not yet approved
 * is withdrawn with its own entry, and an approved one is released, as reject_event_during_planning
 * does.
 */
describe('SCRUM-49 mock: rejecting an event during planning', () => {
  const REASON = 'No venue large enough is free that week.'
  const READY_TO_CONFIRM = 'EVR-PLAN0003'
  const HELD_BACK_EVERYWHERE = 'EVR-PLAN0004'
  const REASON_REQUIRED = 'A reason is required to reject the event.'

  /** An entry by Hana, now, as the backend shows it. */
  function byHana(kind: string, details: Record<string, unknown>) {
    return { kind, occurred_at: MOCK_NOW, actor_name: HANA.full_name, details }
  }

  it.each([APPROVED_WITH_GAPS, READY_TO_CONFIRM])(
    'rejects %s, in the reply and the record',
    async (reference) => {
      signInAs(HANA)

      const rejected = await rejectEvent(reference, { reason: `  ${REASON}  ` })

      expect(rejected).toMatchObject({ reference, status: 'rejected' })
      expect(rejected).not.toHaveProperty('coordinator')
      expect(await statusOf(reference)).toBe('rejected')
    },
  )

  it('records the decision, then withdraws each arrangement not yet approved', async () => {
    signInAs(HANA)

    await rejectEvent(APPROVED_WITH_GAPS, { reason: REASON })

    expect((await fetchEventHistory(APPROVED_WITH_GAPS)).history).toEqual([
      byHana('decision_recorded', { outcome: 'rejected', reason: REASON }),
      byHana('venue_arrangement_withdrawn', { venue_booking_request_id: 42, venue_id: 3 }),
    ])
  })

  it('withdraws a rejected arrangement too, but not an approved one, which is released', async () => {
    signInAs(HANA)

    await rejectEvent(HELD_BACK_EVERYWHERE, { reason: REASON })

    const details = (await fetchEventHistory(HELD_BACK_EVERYWHERE)).history.map(
      (entry) => entry.details,
    )
    expect(details).toEqual([
      { outcome: 'rejected', reason: REASON },
      { venue_booking_request_id: 48, venue_id: 3 },
    ])
  })

  it.each([
    [{}, REASON_REQUIRED],
    [{ reason: null }, REASON_REQUIRED],
    [{ reason: '   ' }, 'Must not be blank.'],
    [{ reason: 7 }, 'Not a valid string.'],
  ])('refuses the body %j on reason, and leaves the event as it was', async (body, message) => {
    signInAs(HANA)

    const error = await refusal(
      apiRequest(`/api/events/requests/${APPROVED_WITH_GAPS}/reject`, { method: 'POST', body }),
    )

    expectInvalid(error, { reason: [message] })
    expect(await statusOf(APPROVED_WITH_GAPS)).toBe('approved')
    expect((await fetchEventHistory(APPROVED_WITH_GAPS)).history).toEqual([])
  })

  it('names a field it does not know beside the reason', async () => {
    signInAs(HANA)

    const error = await refusal(
      apiRequest(`/api/events/requests/${APPROVED_WITH_GAPS}/reject`, {
        method: 'POST',
        body: { reason: REASON, status: 'rejected' },
      }),
    )

    expectInvalid(error, { status: ['Unknown field.'] })
  })

  it('refuses a body that is not a JSON object', async () => {
    signInAs(HANA)

    const error = await refusal(
      apiRequest(`/api/events/requests/${APPROVED_WITH_GAPS}/reject`, { method: 'POST', body: [] }),
    )

    expectNotAnObject(error)
  })

  it.each(
    statusesOtherThan(EVENT_REQUEST_STATUS.APPROVED).filter(
      (status) => status !== EVENT_REQUEST_STATUS.SAFETY_REVIEW,
    ),
  )('refuses an event that is %s, before reading the body, and leaves it there', async (status) => {
    const reference = await ownEventIn(status)

    const error = await refusal(
      apiRequest(`/api/events/requests/${reference}/reject`, { method: 'POST', body: {} }),
    )

    expect(error).toMatchObject({
      status: 409,
      code: 'rejection_not_allowed',
      message: 'Only an approved event or one in Safety Review can be rejected during planning.',
    })
    expect(await statusOf(reference)).toBe(status)
  })

  it("answers another coordinator's event as not found, and refuses other roles", async () => {
    signInAs(CHLOE)
    expect(await refusal(rejectEvent(APPROVED_WITH_GAPS, { reason: REASON }))).toMatchObject(
      NOT_FOUND,
    )

    signInAs(MOCK_ACCOUNTS.organiser)
    expect(await refusal(rejectEvent(APPROVED_WITH_GAPS, { reason: REASON }))).toMatchObject(
      NOT_PERMITTED,
    )

    signInAs(null)
    expect(await refusal(rejectEvent(APPROVED_WITH_GAPS, { reason: REASON }))).toMatchObject(
      NOT_SIGNED_IN,
    )
    signInAs(HANA)
    expect(await statusOf(APPROVED_WITH_GAPS)).toBe('approved')
  })
})
