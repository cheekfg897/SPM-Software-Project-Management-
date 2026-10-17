import {
  answerClarification,
  fetchAssignedEventRequests,
  fetchEventRequest,
  requestClarification,
} from '@/features/eventRequests/api'
import { apiRequest, fieldErrorsOf } from '@/lib/api'
import type { FieldErrors } from '@/lib/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

import { MOCK_NOW } from './catalogueFixtures'

/**
 * The mock of a coordinator asking the organiser a question and an organiser answering it
 * (POST /api/events/requests/<reference>/request-clarification and /resubmit), pinned to what
 * the backend does: who may, from which status, its check order, codes, messages and field
 * messages (SCRUM-32 AC1, AC2, AC4; ADR-0029, ADR-0049). The mock's "now" is MOCK_NOW. The
 * integration tests check the same contract against the backend.
 *
 * Priya coordinates EVR-RV2D5F8J (under review), which Sara's colleague wrote, and Sara's
 * EVR-RV4K8N2P (submitted), EVR-RV7T3M5Q (approved) and EVR-RV9H6C1W (rejected). Chloe
 * coordinates Omar's EVR-B6YF2K8V (awaiting an answer to its second question) and
 * EVR-7K2M9QXA (under review), and EVR-BOOK0102 (confirmed).
 */

const PRIYAS_UNDER_REVIEW = 'EVR-RV2D5F8J'
const CHLOES_UNDER_REVIEW = 'EVR-7K2M9QXA'
const AWAITING_ANSWER = 'EVR-B6YF2K8V'
const PRIYA = MOCK_ACCOUNTS.reviewingCoordinator
const CHLOE = MOCK_ACCOUNTS.coordinator
const OMAR = MOCK_ACCOUNTS.organiser
const SARA = MOCK_ACCOUNTS.otherOrganiser

const NOT_FOUND = { status: 404, code: 'not_found', message: 'Event request not found.' }
const NOT_PERMITTED = { status: 403, code: 'authorization_error' }
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
const NOT_ALLOWED = {
  status: 409,
  code: 'clarification_not_allowed',
  message: 'Clarification can only be requested while the event request is under review.',
}
const NOT_AWAITING = {
  status: 409,
  code: 'request_not_awaiting_clarification',
  message: 'Only an event request awaiting clarification can be answered and resubmitted.',
}
const NO_ORGANISATION = {
  status: 403,
  code: 'organiser_without_organisation',
  message: 'Your account is not linked to a client organisation yet.',
}
const NOT_AN_OBJECT = {
  status: 400,
  code: 'validation_error',
  message: 'Request body must be a JSON object.',
}
const EARLIER_EXCHANGE = {
  message: 'Will the roadshow need a loading bay for the demo vehicles?',
  requested_by: 'Chloe Lim',
  requested_at: '2026-09-26T10:00:00+08:00',
  response: 'Yes, for two vans between 11am and noon.',
  answered_by: 'Omar Rahman',
  answered_at: '2026-09-26T14:30:00+08:00',
}

function signInAs(account: MockAccount | null) {
  sendRequestsAs(account === null ? null : mockTokenFor(account))
}

/** Send `body` to one of the two routes as it is, whatever its shape. */
function postTo(reference: string, route: 'request-clarification' | 'resubmit', body: unknown) {
  return apiRequest(`/api/events/requests/${reference}/${route}`, { method: 'POST', body })
}

/** Check `error` is the backend's 400 with exactly these per-field messages. */
function expectInvalid(error: unknown, details: FieldErrors) {
  expect(error).toMatchObject({
    status: 400,
    code: 'validation_error',
    message: 'Invalid request.',
  })
  expect(fieldErrorsOf(error)).toEqual(details)
}

async function statusOf(reference: string) {
  return (await fetchEventRequest(reference)).status
}

/** The wrong text bodies both routes refuse, for the field each one reads. */
function badTextBodies(field: string): [string, unknown, FieldErrors][] {
  return [
    ['no text', {}, { [field]: ['Missing data for required field.'] }],
    ['null text', { [field]: null }, { [field]: ['Field may not be null.'] }],
    ['text as a number', { [field]: 5 }, { [field]: ['Not a valid string.'] }],
    ['blank text', { [field]: '   ' }, { [field]: ['Must not be blank.'] }],
    ['an unknown field', { [field]: 'Fine.', colour: 'red' }, { colour: ['Unknown field.'] }],
  ]
}

describe('SCRUM-32 AC1 mock: asking for clarification', () => {
  beforeEach(() => signInAs(PRIYA))

  it('moves the request to awaiting clarification and keeps the question, trimmed, on the record', async () => {
    const asked = await requestClarification(PRIYAS_UNDER_REVIEW, '  Is the room step-free?  ')

    expect(asked).toMatchObject({
      reference: PRIYAS_UNDER_REVIEW,
      status: 'awaiting_clarification',
    })
    expect((await fetchEventRequest(PRIYAS_UNDER_REVIEW)).clarifications).toEqual([
      {
        message: 'Is the room step-free?',
        requested_by: 'Priya Nair',
        requested_at: MOCK_NOW,
        response: null,
        answered_by: null,
        answered_at: null,
      },
    ])
    const listed = (await fetchAssignedEventRequests()).event_requests
    expect(listed.find((row) => row.reference === PRIYAS_UNDER_REVIEW)?.status).toBe(
      'awaiting_clarification',
    )
  })

  it.each([
    ['submitted', PRIYA, 'EVR-RV4K8N2P'],
    ['approved', PRIYA, 'EVR-RV7T3M5Q'],
    ['rejected', PRIYA, 'EVR-RV9H6C1W'],
    ['awaiting an answer already', CHLOE, AWAITING_ANSWER],
    ['confirmed', CHLOE, 'EVR-BOOK0102'],
  ])('refuses a request that is %s, whatever the body', async (_status, account, reference) => {
    signInAs(account)
    const before = await fetchEventRequest(reference)

    expect(await refusal(postTo(reference, 'request-clarification', {}))).toMatchObject(NOT_ALLOWED)
    expect(await fetchEventRequest(reference)).toEqual(before)
  })

  it.each([
    ["another coordinator's request", CHLOES_UNDER_REVIEW],
    ['a request with no coordinator', 'EVR-Q4ZT6N1B'],
  ])('answers %s as not found, whatever the body', async (_case, reference) => {
    expect(await refusal(postTo(reference, 'request-clarification', {}))).toMatchObject(NOT_FOUND)
  })

  it('refuses an organiser, and a visitor who is not signed in', async () => {
    signInAs(SARA)
    const organiser = await refusal(requestClarification(PRIYAS_UNDER_REVIEW, 'Why?'))
    signInAs(null)
    const visitor = await refusal(requestClarification(PRIYAS_UNDER_REVIEW, 'Why?'))

    expect(organiser).toMatchObject(NOT_PERMITTED)
    expect(visitor).toMatchObject(NOT_SIGNED_IN)
  })

  it.each(badTextBodies('message'))(
    'refuses %s with its field message',
    async (_case, body, details) => {
      expectInvalid(
        await refusal(postTo(PRIYAS_UNDER_REVIEW, 'request-clarification', body)),
        details,
      )
      expect(await statusOf(PRIYAS_UNDER_REVIEW)).toBe('under_review')
    },
  )

  it('refuses a body that is not an object', async () => {
    const error = await refusal(postTo(PRIYAS_UNDER_REVIEW, 'request-clarification', ['Why?']))

    expect(error).toMatchObject(NOT_AN_OBJECT)
    expect(fieldErrorsOf(error)).toEqual({})
  })
})

describe('SCRUM-32 AC2, AC4 mock: answering a question', () => {
  beforeEach(() => signInAs(OMAR))

  it('answers the open question, trimmed, and sends the request back to review', async () => {
    const answered = await answerClarification(AWAITING_ANSWER, '  Yes, 2pm works.  ')

    expect(answered).toMatchObject({ reference: AWAITING_ANSWER, status: 'under_review' })
    expect((await fetchEventRequest(AWAITING_ANSWER)).clarifications).toEqual([
      EARLIER_EXCHANGE,
      {
        message: 'Can the start move to 2pm so the vans can unload first?',
        requested_by: 'Chloe Lim',
        requested_at: '2026-09-27T09:15:00+08:00',
        response: 'Yes, 2pm works.',
        answered_by: 'Omar Rahman',
        answered_at: MOCK_NOW,
      },
    ])
  })

  it('keeps every exchange, oldest first, when the coordinator asks again', async () => {
    await answerClarification(AWAITING_ANSWER, 'Yes, 2pm works.')
    signInAs(CHLOE)

    await requestClarification(AWAITING_ANSWER, 'And the loading bay at 1pm?')

    const { clarifications } = await fetchEventRequest(AWAITING_ANSWER)
    expect(clarifications.map((exchange) => exchange.response)).toEqual([
      EARLIER_EXCHANGE.response,
      'Yes, 2pm works.',
      null,
    ])
    expect(clarifications[2]).toMatchObject({
      message: 'And the loading bay at 1pm?',
      requested_by: 'Chloe Lim',
    })
  })

  it('lets any organiser of the organisation answer, not only the one who wrote it', async () => {
    signInAs(PRIYA)
    await requestClarification(PRIYAS_UNDER_REVIEW, 'Is the room step-free?')
    signInAs(SARA)

    await answerClarification(PRIYAS_UNDER_REVIEW, 'Yes, please.')

    expect(await fetchEventRequest(PRIYAS_UNDER_REVIEW)).toMatchObject({
      status: 'under_review',
      clarifications: [{ response: 'Yes, please.', answered_by: 'Sara Lee' }],
    })
  })

  it.each([
    ['under review', CHLOES_UNDER_REVIEW],
    ['approved', 'EVR-W9CR5E7M'],
    ['rejected', 'EVR-M1XJ7T3D'],
    ['submitted', 'EVR-Q4ZT6N1B'],
    ['their own draft', 'EVR-3HD8PL2W'],
  ])('refuses a request that is %s, whatever the body', async (_status, reference) => {
    const before = await fetchEventRequest(reference)

    expect(await refusal(postTo(reference, 'resubmit', {}))).toMatchObject(NOT_AWAITING)
    expect(await fetchEventRequest(reference)).toEqual(before)
  })

  it.each([
    ["another organisation's request", SARA, AWAITING_ANSWER],
    ["a colleague's draft", OMAR, 'EVR-H2PL8R6K'],
  ])('answers %s as not found', async (_case, account, reference) => {
    signInAs(account)

    expect(await refusal(postTo(reference, 'resubmit', {}))).toMatchObject(NOT_FOUND)
  })

  it('refuses an organiser with no organisation before looking for the request', async () => {
    signInAs(MOCK_ACCOUNTS.unlinkedOrganiser)

    expect(await refusal(postTo('EVR-NOSUCH00', 'resubmit', {}))).toMatchObject(NO_ORGANISATION)
  })

  it('refuses the coordinator, and a visitor who is not signed in', async () => {
    signInAs(CHLOE)
    const coordinator = await refusal(answerClarification(AWAITING_ANSWER, 'Yes.'))
    signInAs(null)
    const visitor = await refusal(answerClarification(AWAITING_ANSWER, 'Yes.'))

    expect(coordinator).toMatchObject(NOT_PERMITTED)
    expect(visitor).toMatchObject(NOT_SIGNED_IN)
  })

  it.each(badTextBodies('response'))(
    'refuses %s with its field message',
    async (_case, body, details) => {
      expectInvalid(await refusal(postTo(AWAITING_ANSWER, 'resubmit', body)), details)
      expect(await statusOf(AWAITING_ANSWER)).toBe('awaiting_clarification')
    },
  )

  it('refuses a body that is not an object', async () => {
    const error = await refusal(postTo(AWAITING_ANSWER, 'resubmit', 'Yes.'))

    expect(error).toMatchObject(NOT_AN_OBJECT)
    expect(fieldErrorsOf(error)).toEqual({})
  })
})
