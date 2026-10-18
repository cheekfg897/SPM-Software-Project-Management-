import {
  editEventRequest,
  fetchEventHistory,
  fetchEventRequest,
} from '@/features/eventRequests/api'
import { refusal } from '@/test/refusal'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'
import type { MockAccount } from '../fixtures/accounts'

/**
 * The mock of the coordinator's edit (PATCH /api/events/requests/<reference>), pinned to what
 * the backend does (SCRUM-33 AC1 to AC4; ADR-0025): only the fields sent change, a change to
 * the date, times, attendance or requirements is significant, every change is written to the
 * history, and the refusals come with the backend's codes and messages. The mock's "today" is
 * 5 Oct 2026.
 */

/** Chloe's, under review: 12 Nov, 9:00 am to 5:00 pm, 250 expected. */
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
/** Chloe's, awaiting the organiser's answer, so not editable. */
const AWAITING_ANSWER = 'EVR-B6YF2K8V'
/** Marcus's. */
const NOT_CHLOES = 'EVR-W9CR5E7M'
const MOCK_NOW = '2026-10-05T12:00:00+08:00'

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

/** The field errors an edit was refused with, by Chloe on Partner Summit. */
async function fieldErrorsOf(changes: Record<string, unknown>) {
  signInAs(MOCK_ACCOUNTS.coordinator)
  return refusal(editEventRequest(PARTNER_SUMMIT, changes))
}

describe('SCRUM-33 mock of an edit: what changes', () => {
  it('changes only the fields sent, and answers with each change and whether it is significant', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const edited = await editEventRequest(PARTNER_SUMMIT, {
      expected_attendance: 300,
      description: '  Two days with our partners. ',
    })

    expect(edited).toMatchObject({
      reference: PARTNER_SUMMIT,
      description: 'Two days with our partners.',
      expected_attendance: 300,
      programme_notes: 'Keynote at 9:30, breakout rooms after lunch.',
      internal_planning_notes: null,
    })
    // In the backend's field order, not the order sent.
    expect(edited.changes).toEqual([
      {
        field: 'description',
        previous_value: null,
        new_value: 'Two days with our partners.',
        significant: false,
      },
      { field: 'expected_attendance', previous_value: 250, new_value: 300, significant: true },
    ])
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    expect(record.expected_attendance).toBe(300)
    expect(record.description).toBe('Two days with our partners.')
  })

  it('marks a change to the venue or equipment requirements significant (AC2)', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const edited = await editEventRequest(PARTNER_SUMMIT, {
      venue_requirements: 'A main hall for 300.',
      equipment_requirements: 'Four wireless microphones.',
    })

    expect(edited.changes.map((change) => [change.field, change.significant])).toEqual([
      ['venue_requirements', true],
      ['equipment_requirements', true],
    ])
  })

  it('writes each change to the history, by the coordinator, now (AC4)', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    await editEventRequest(PARTNER_SUMMIT, { start_time: '10:00', programme_notes: '' })

    const { history } = await fetchEventHistory(PARTNER_SUMMIT)
    expect(history.slice(4)).toEqual([
      {
        kind: 'field_changed',
        occurred_at: MOCK_NOW,
        actor_name: 'Chloe Lim',
        details: {
          field: 'programme_notes',
          previous_value: 'Keynote at 9:30, breakout rooms after lunch.',
          new_value: null,
          significant: false,
        },
      },
      {
        kind: 'field_changed',
        occurred_at: MOCK_NOW,
        actor_name: 'Chloe Lim',
        details: {
          field: 'start_time',
          previous_value: '09:00:00',
          new_value: '10:00:00',
          significant: true,
        },
      },
    ])
  })

  it('moves the end date with a date moved on its own, as a change of its own', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const edited = await editEventRequest(PARTNER_SUMMIT, { proposed_date: '2026-11-19' })

    expect(edited.end_date).toBe('2026-11-19')
    expect(edited.changes.map((change) => [change.field, change.new_value])).toEqual([
      ['proposed_date', '2026-11-19'],
      ['end_date', '2026-11-19'],
    ])
  })

  it('records nothing for a value that is already saved', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const edited = await editEventRequest(PARTNER_SUMMIT, {
      expected_attendance: 250,
      start_time: '09:00',
    })

    expect(edited.changes).toEqual([])
    expect((await fetchEventHistory(PARTNER_SUMMIT)).history).toHaveLength(4)
  })

  it('keeps the internal planning notes from the organiser, in the record and the history', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const edited = await editEventRequest(PARTNER_SUMMIT, { internal_planning_notes: 'Call AV.' })
    const coordinatorsHistory = await fetchEventHistory(PARTNER_SUMMIT)

    signInAs(MOCK_ACCOUNTS.organiser)
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    const organisersHistory = await fetchEventHistory(PARTNER_SUMMIT)

    expect(edited.internal_planning_notes).toBe('Call AV.')
    expect(coordinatorsHistory.history).toHaveLength(5)
    expect(record).not.toHaveProperty('internal_planning_notes')
    expect(organisersHistory.history).toHaveLength(3)
  })
})

describe('SCRUM-33 mock of an edit: what is refused', () => {
  it.each([
    [{ proposed_date: '2026-10-04' }, 'proposed_date', 'Proposed date cannot be in the past.'],
    [{ expected_attendance: 0 }, 'expected_attendance', 'Expected attendance must be at least 1.'],
    [{ expected_attendance: null }, 'expected_attendance', 'Field may not be null.'],
    [{ end_time: null }, 'end_time', 'Field may not be null.'],
    [{ name: 'A new name' }, 'name', 'Unknown field.'],
    [{ end_time: '08:00' }, 'end_time', 'Event must end after it starts.'],
    [{ end_date: '2026-11-11' }, 'end_date', 'End date cannot be before the proposed date.'],
  ])('refuses %j with the message on %s', async (changes, field, message) => {
    const error = await fieldErrorsOf(changes)

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { [field]: [message] },
    })
  })

  it('checks the window only once every field has passed its own rules', async () => {
    const error = await fieldErrorsOf({ end_time: '08:00', expected_attendance: 0 })

    expect(error).toMatchObject({
      fieldErrors: { expected_attendance: ['Expected attendance must be at least 1.'] },
    })
  })

  it('changes nothing when it refuses', async () => {
    await fieldErrorsOf({ description: 'Changed?', expected_attendance: 0 })

    expect((await fetchEventRequest(PARTNER_SUMMIT)).description).toBeNull()
  })

  it('refuses an event in a status that cannot be edited', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    expect(await refusal(editEventRequest(AWAITING_ANSWER, { description: 'x' }))).toMatchObject({
      status: 409,
      code: 'request_not_editable',
      message: 'Only a submitted, under-review, approved or confirmed event request can be edited.',
    })
  })

  it("answers another coordinator's event as not found, and refuses an organiser", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const coordinator = await refusal(editEventRequest(NOT_CHLOES, { description: 'x' }))
    signInAs(MOCK_ACCOUNTS.organiser)
    const organiser = await refusal(editEventRequest(PARTNER_SUMMIT, { description: 'x' }))

    expect(coordinator).toMatchObject({ status: 404, code: 'not_found' })
    expect(organiser).toMatchObject({ status: 403, code: 'authorization_error' })
  })
})
