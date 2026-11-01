import {
  fetchEventRequest,
  raiseChangeRequest,
  withdrawChangeRequest,
} from '@/features/eventRequests/api'
import type { ChangeRequestDetails } from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

/**
 * The mock of an organiser's change request (POST .../<reference>/change-requests and
 * .../change-requests/<id>/withdraw), pinned to what the backend does (SCRUM-56, ADR-0126): the
 * request is kept Pending with the values it asks for beside the event's values when raised,
 * the event itself is left as it is, one Pending request at a time, and every refusal comes with
 * the backend's code and message, checked in the backend's order. The mock's "now" is 5 Oct,
 * 12:00 pm, and its "today" 5 Oct 2026.
 */

/** Omar's, under review: 12 Nov, 9:00 am to 5:00 pm, 250 expected. */
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
/** Omar's draft, and his rejected event. */
const OMARS_DRAFT = 'EVR-3HD8PL2W'
const OMARS_REJECTED = 'EVR-M1XJ7T3D'
/** A colleague's submitted event, which Omar can see. */
const COLLEAGUES_EVENT = 'EVR-Q4ZT6N1B'
/** Another organisation's. */
const NOT_OMARS_ORGANISATION = 'EVR-N5QS3V9C'
const MOCK_NOW = '2026-10-05T12:00:00+08:00'
const REASON = 'Our keynote speaker lands at 9:30.'
const LATER_START: ChangeRequestDetails = { start_time: '10:00', reason: REASON }

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

/** Omar's refused change request on `reference`. */
function omarsRefusal(reference: string, details: ChangeRequestDetails | object = LATER_START) {
  signInAs(MOCK_ACCOUNTS.organiser)
  // The body is the test's to choose: some are deliberately not what the type allows.
  return refusal(raiseChangeRequest(reference, details as ChangeRequestDetails))
}

describe('SCRUM-56 mock of raising a change request', () => {
  it('keeps it Pending with each value asked for and its value now, in the backend field order', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const raised = await raiseChangeRequest(PARTNER_SUMMIT, {
      reason: `  ${REASON} `,
      programme_notes: '  Keynote at 10:30. ',
      expected_attendance: 300,
      start_time: '10:00',
      venue_requirements: '',
    })

    expect(raised).toEqual({
      id: expect.any(Number) as number,
      status: 'pending',
      changes: [
        { field: 'start_time', previous_value: '09:00:00', requested_value: '10:00:00' },
        { field: 'expected_attendance', previous_value: 250, requested_value: 300 },
        {
          field: 'venue_requirements',
          previous_value: 'A main hall for 250 and four breakout rooms.',
          requested_value: null,
        },
        {
          field: 'programme_notes',
          previous_value: 'Keynote at 9:30, breakout rooms after lunch.',
          requested_value: 'Keynote at 10:30.',
        },
      ],
      reason: REASON,
      raised_by: 'Omar Rahman',
      raised_at: MOCK_NOW,
      withdrawn_at: null,
      withdrawal_note: null,
    })
  })

  it('puts it on the record and leaves the event as it was (AC3, AC4)', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const raised = await raiseChangeRequest(PARTNER_SUMMIT, LATER_START)

    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.change_requests).toEqual([raised])
    expect(record.start_time).toBe('09:00:00')
    signInAs(MOCK_ACCOUNTS.coordinator)
    expect((await fetchEventRequest(PARTNER_SUMMIT)).change_requests).toEqual([raised])
  })

  it('moves the end date with a date moved on its own, as an edit does', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    const raised = await raiseChangeRequest(PARTNER_SUMMIT, {
      proposed_date: '2026-11-19',
      reason: REASON,
    })

    expect(raised.changes).toEqual([
      { field: 'proposed_date', previous_value: '2026-11-12', requested_value: '2026-11-19' },
      { field: 'end_date', previous_value: '2026-11-12', requested_value: '2026-11-19' },
    ])
  })

  it('refuses a second while the first is Pending (AC7)', async () => {
    signInAs(MOCK_ACCOUNTS.organiser)
    await raiseChangeRequest(PARTNER_SUMMIT, LATER_START)

    await expect(omarsRefusal(PARTNER_SUMMIT)).resolves.toMatchObject({
      status: 409,
      code: 'conflict',
      message:
        'A change request is already waiting for the coordinator. Withdraw it, or wait for ' +
        'their decision, before raising another.',
    })
  })

  it.each([
    [OMARS_DRAFT, 'draft'],
    [OMARS_REJECTED, 'rejected'],
  ])('refuses one on %s, naming its status %s (AC6)', async (reference, status) => {
    await expect(omarsRefusal(reference)).resolves.toMatchObject({
      status: 409,
      code: 'change_request_not_allowed',
      message: `A change can't be requested for a ${status} event.`,
    })
  })

  it("refuses one on a colleague's event, and on another organisation's as not found", async () => {
    await expect(omarsRefusal(COLLEAGUES_EVENT)).resolves.toMatchObject({
      status: 403,
      code: 'not_event_organiser',
    })
    await expect(omarsRefusal(NOT_OMARS_ORGANISATION)).resolves.toMatchObject({
      status: 404,
      code: 'not_found',
    })
  })

  it('refuses one with no reason, a blank one, or an unknown field, all at once', async () => {
    const refused = await omarsRefusal(PARTNER_SUMMIT, { reason: '  ', description: 'x' })

    expect(refused).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { reason: ['Say why the change is needed.'], description: ['Unknown field.'] },
    })
    await expect(omarsRefusal(PARTNER_SUMMIT, { start_time: '10:00' })).resolves.toMatchObject({
      fieldErrors: { reason: ['Say why the change is needed.'] },
    })
  })

  it("refuses a value an edit would refuse, in the edit's words", async () => {
    const refused = await omarsRefusal(PARTNER_SUMMIT, {
      reason: REASON,
      proposed_date: '2026-10-01',
      expected_attendance: 0,
    })

    expect(refused).toMatchObject({
      status: 400,
      fieldErrors: {
        proposed_date: ['Proposed date cannot be in the past.'],
        expected_attendance: ['Expected attendance must be at least 1.'],
      },
    })
    await expect(
      omarsRefusal(PARTNER_SUMMIT, { reason: REASON, end_time: '08:00' }),
    ).resolves.toMatchObject({ fieldErrors: { end_time: ['Event must end after it starts.'] } })
  })

  it('refuses one that changes nothing', async () => {
    await expect(
      omarsRefusal(PARTNER_SUMMIT, { reason: REASON, start_time: '09:00' }),
    ).resolves.toMatchObject({
      status: 400,
      code: 'validation_error',
      message: "Say what should change: give at least one of the event's details a new value.",
    })
  })

  it('refuses a coordinator by role', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await expect(refusal(raiseChangeRequest(PARTNER_SUMMIT, LATER_START))).resolves.toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })
})

describe('SCRUM-56 mock of withdrawing a change request', () => {
  async function raisedId(): Promise<number> {
    signInAs(MOCK_ACCOUNTS.organiser)
    const raised = await raiseChangeRequest(PARTNER_SUMMIT, LATER_START)
    return raised.id
  }

  it('withdraws a Pending one, now, and then lets another be raised (AC8)', async () => {
    const id = await raisedId()

    const withdrawn = await withdrawChangeRequest(PARTNER_SUMMIT, id)

    expect(withdrawn).toMatchObject({ id, status: 'withdrawn', withdrawn_at: MOCK_NOW })
    expect((await fetchEventRequest(PARTNER_SUMMIT)).change_requests).toEqual([withdrawn])
    await expect(raiseChangeRequest(PARTNER_SUMMIT, LATER_START)).resolves.toMatchObject({
      status: 'pending',
    })
  })

  it('refuses one no longer Pending, naming its status', async () => {
    const id = await raisedId()
    await withdrawChangeRequest(PARTNER_SUMMIT, id)

    await expect(refusal(withdrawChangeRequest(PARTNER_SUMMIT, id))).resolves.toMatchObject({
      status: 409,
      code: 'change_request_not_pending',
      message: 'Only a pending change request can be withdrawn; this one is withdrawn.',
    })
  })

  it('refuses one the event does not have as not found', async () => {
    const id = await raisedId()

    await expect(refusal(withdrawChangeRequest(PARTNER_SUMMIT, id + 1))).resolves.toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Change request not found.',
    })
  })

  it("refuses a colleague's event before looking for the request", async () => {
    signInAs(MOCK_ACCOUNTS.organiser)

    await expect(refusal(withdrawChangeRequest(COLLEAGUES_EVENT, 1))).resolves.toMatchObject({
      status: 403,
      code: 'not_event_organiser',
    })
  })
})
