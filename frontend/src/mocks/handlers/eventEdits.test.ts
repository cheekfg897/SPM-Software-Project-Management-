import {
  fetchBookingRequests,
  raiseBookingRequest,
  withdrawArrangement,
} from '@/features/booking/api'
import type { RaiseBookingRequest } from '@/features/booking/api'
import {
  confirmEvent,
  editEventRequest,
  fetchEventHistory,
  fetchEventRequest,
  sendToSafetyReview,
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

  it("keeps a longer event's length when its date moves on its own (ADR-0025)", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    await editEventRequest(PARTNER_SUMMIT, { end_date: '2026-11-14' })

    const edited = await editEventRequest(PARTNER_SUMMIT, { proposed_date: '2026-11-19' })

    expect(edited.end_date).toBe('2026-11-21')
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
    [{ end_time: '09:00' }, 'end_time', 'Event must end after it starts.'],
    [{ end_date: '2026-11-11' }, 'end_date', 'End date cannot be before the proposed date.'],
  ])('refuses %j with the message on %s', async (changes, field, message) => {
    const error = await fieldErrorsOf(changes)

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      fieldErrors: { [field]: [message] },
    })
  })

  // A value of the wrong type is refused with marshmallow's own words, as on the backend.
  it.each([
    [{ expected_attendance: '300' }, 'expected_attendance', 'Not a valid integer.'],
    [{ expected_attendance: 1.5 }, 'expected_attendance', 'Not a valid integer.'],
    [{ expected_attendance: true }, 'expected_attendance', 'Not a valid integer.'],
    [{ description: 42 }, 'description', 'Not a valid string.'],
    [{ internal_planning_notes: ['Call AV.'] }, 'internal_planning_notes', 'Not a valid string.'],
    [{ proposed_date: '19 Nov 2026' }, 'proposed_date', 'Not a valid date.'],
    [{ end_date: 20261119 }, 'end_date', 'Not a valid date.'],
    [{ start_time: '10am' }, 'start_time', 'Not a valid time.'],
    [{ end_time: '18:00:00+08:00' }, 'end_time', 'Time must not include a timezone offset.'],
  ])('refuses the wrong type %j with the message on %s', async (changes, field, message) => {
    const error = await fieldErrorsOf(changes)

    expect(error).toMatchObject({ status: 400, fieldErrors: { [field]: [message] } })
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

  it.each([
    ['awaiting_clarification', MOCK_ACCOUNTS.coordinator, AWAITING_ANSWER],
    ['rejected', MOCK_ACCOUNTS.reviewingCoordinator, 'EVR-RV9H6C1W'],
  ])('refuses an event that is %s, as the backend does', async (_, account, reference) => {
    signInAs(account)

    expect(await refusal(editEventRequest(reference, { description: 'x' }))).toMatchObject({
      status: 409,
      code: 'request_not_editable',
      message: 'Only a submitted, under-review, approved or confirmed event request can be edited.',
    })
  })

  // Each status the backend lets an edit through (EDITABLE_STATUSES), so none is dropped.
  it.each([
    ['submitted', MOCK_ACCOUNTS.reviewingCoordinator, 'EVR-RV4K8N2P'],
    ['under_review', MOCK_ACCOUNTS.coordinator, PARTNER_SUMMIT],
    ['approved', MOCK_ACCOUNTS.coordinator, 'EVR-BOOK0101'],
    ['confirmed', MOCK_ACCOUNTS.coordinator, 'EVR-BOOK0102'],
  ])('lets the coordinator edit an event that is %s', async (status, account, reference) => {
    signInAs(account)

    const edited = await editEventRequest(reference, { description: 'Edited.' })

    expect(edited).toMatchObject({ status, description: 'Edited.' })
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

/**
 * SCRUM-33 AC7 (ADR-0087): once the event has passed its safety check, a significant change
 * withdraws the approval, and a Confirmed event goes back to Approved for a new check. Hana's
 * EVR-PLAN0003 is in Safety Review with the Safety Officer's approval; EVR-PLAN0005 is Confirmed.
 */
describe('SCRUM-33 mock of an edit: the safety approval (AC7)', () => {
  const HANA = MOCK_ACCOUNTS.planningCoordinator

  /** The newest history entry, as the signed-in coordinator reads it. */
  async function newestEntryOf(reference: string) {
    return (await fetchEventHistory(reference)).history.at(-1)
  }

  it('withdraws the approval on a significant change, so a Confirmed event needs a new check', async () => {
    signInAs(HANA)
    await confirmEvent('EVR-PLAN0003')

    // A fall: still significant, but the hall holds everyone, so no arrangement is flagged (AC6).
    const edited = await editEventRequest('EVR-PLAN0003', { expected_attendance: 100 })

    expect(edited.status).toBe('approved')
    expect(await newestEntryOf('EVR-PLAN0003')).toEqual({
      kind: 'safety_approval_withdrawn',
      occurred_at: MOCK_NOW,
      actor_name: HANA.full_name,
      details: { significant_fields: ['expected_attendance'] },
    })
    await sendToSafetyReview('EVR-PLAN0003')
    expect(await refusal(confirmEvent('EVR-PLAN0003'))).toMatchObject({
      status: 409,
      fieldErrors: { safety_check: ['The Safety Officer has not approved the event.'] },
    })
  })

  // The backend confirms only an approved event, so every Confirmed event has an approval.
  it('sends any Confirmed event back to Approved on a significant change', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)

    const edited = await editEventRequest('EVR-BOOK0102', { venue_requirements: 'A stage.' })

    expect(edited.status).toBe('approved')
    expect(await newestEntryOf('EVR-BOOK0102')).toMatchObject({
      kind: 'safety_approval_withdrawn',
      details: { significant_fields: ['venue_requirements'] },
    })
  })

  it.each([
    ['a note', { description: 'New notes.' }],
    ['a significant value sent again', { description: 'New notes.', expected_attendance: 150 }],
  ])('keeps the approval for %s', async (_case, changes) => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0005', changes)

    expect(edited.status).toBe('confirmed')
    expect(await newestEntryOf('EVR-PLAN0005')).toMatchObject({ kind: 'field_changed' })
  })
})

/**
 * SCRUM-33 AC6 (ADR-0094, `flag_arrangements_after_change`): a significant change reassesses each
 * live venue arrangement (Pending, Conflicting or Approved) on its own, and only those it affects
 * are flagged, so the event can't go to Safety Review until they're settled. Hana's EVR-PLAN0001
 * has an approved hall for all 150 guests (41), a withdrawn room (40) and a pending breakout room
 * for 40 (42); EVR-PLAN0002 has only its hall (45), in a venue for 200.
 */
describe('SCRUM-33 mock of an edit: reassessing each venue arrangement (AC6)', () => {
  const HANA = MOCK_ACCOUNTS.planningCoordinator
  const TIMING_CHANGED = "The event's date or time changed."
  const REQUIREMENTS_CHANGED = "The event's venue requirements changed."

  /** Safety Review is refused after `changes` to `reference`, naming exactly `gaps`. */
  async function expectVenueGapsAfter(
    reference: string,
    changes: Record<string, unknown>,
    gaps: string[],
  ) {
    signInAs(HANA)
    await editEventRequest(reference, changes)
    expect(await refusal(sendToSafetyReview(reference))).toMatchObject({
      status: 409,
      fieldErrors: { venue_arrangements: gaps },
    })
  }

  it('flags every live arrangement on a change of time, but not a withdrawn one', async () => {
    await expectVenueGapsAfter('EVR-PLAN0001', { end_time: '17:00' }, [
      'Venue arrangement 42 is pending.',
      `Venue arrangement 41 is flagged (requires reconfirmation): ${TIMING_CHANGED}`,
      `Venue arrangement 42 is flagged (requires reconfirmation): ${TIMING_CHANGED}`,
    ])
  })

  it('flags only the arrangement holding everyone when attendance rises within its venue', async () => {
    await expectVenueGapsAfter('EVR-PLAN0001', { expected_attendance: 180 }, [
      'Venue arrangement 42 is pending.',
      "Venue arrangement 41 is flagged (requires reconfirmation): The event's expected " +
        "attendance rose from 150 to 180, above this arrangement's expected occupancy of 150.",
    ])
  })

  it("flags an arrangement no longer suitable when attendance outgrows its venue's capacity", async () => {
    await expectVenueGapsAfter('EVR-PLAN0002', { expected_attendance: 250 }, [
      "Venue arrangement 45 is flagged (no longer suitable): Expected attendance of 250 exceeds the venue's capacity of 200.",
    ])
  })

  it('names every reason one change gives an arrangement, in the backend order', async () => {
    const changes = { proposed_date: '2026-11-25', venue_requirements: 'Step-free stage.' }

    await expectVenueGapsAfter('EVR-PLAN0002', changes, [
      `Venue arrangement 45 is flagged (requires reconfirmation): ${TIMING_CHANGED}`,
      `Venue arrangement 45 is flagged (requires reconfirmation): ${REQUIREMENTS_CHANGED}`,
    ])
  })

  it.each([
    ['a note', { description: 'New notes.' }],
    ['the equipment requirements', { equipment_requirements: 'Two microphones.' }],
    ['attendance falling', { expected_attendance: 100 }],
    ['attendance rising to exactly the occupancy', { expected_attendance: 150 }],
  ])('flags nothing for %s, so the event goes to Safety Review', async (_case, changes) => {
    signInAs(HANA)
    await editEventRequest('EVR-PLAN0002', changes)

    expect(await sendToSafetyReview('EVR-PLAN0002')).toMatchObject({ status: 'safety_review' })
  })

  /** A request Chloe raises on EVR-BOOK0101 (80 guests), in the hall (venue 1, for 200). */
  function raiseOnCareersFair(details: Partial<RaiseBookingRequest> = {}) {
    return raiseBookingRequest('EVR-BOOK0101', {
      venue_id: 1,
      purpose: 'Hall',
      starts_at: '2026-11-10T09:00:00+08:00',
      ends_at: '2026-11-10T12:00:00+08:00',
      ...details,
    })
  }

  /** EVR-BOOK0101's arrangement `id`, as the booking mock answers it. */
  async function careersFairArrangement(id: number) {
    return (await fetchBookingRequests('EVR-BOOK0101')).find((each) => each.id === id)
  }

  /**
   * The arrangements themselves live in the booking mock: an edit to Chloe's EVR-BOOK0101 flags
   * them there, as the backend's arrangements answer them.
   */
  it('flags the arrangements the booking mock holds, leaving a smaller room alone', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const hall = await raiseOnCareersFair()
    const breakout = await raiseOnCareersFair({
      venue_id: 2,
      purpose: 'Breakout',
      expected_occupancy: 15,
    })

    await editEventRequest('EVR-BOOK0101', { expected_attendance: 100 })

    expect(await careersFairArrangement(hall.id)).toMatchObject({
      flagged_after_change: true,
      reassessment_flags: [
        {
          kind: 'requires_reconfirmation',
          reason:
            "The event's expected attendance rose from 80 to 100, above this arrangement's " +
            'expected occupancy of 80.',
        },
      ],
    })
    expect(await careersFairArrangement(breakout.id)).toMatchObject({
      flagged_after_change: false,
      reassessment_flags: [],
    })
  })

  it('leaves a withdrawn arrangement in the booking mock unflagged', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const withdrawn = await raiseOnCareersFair()
    await withdrawArrangement('EVR-BOOK0101', withdrawn.id)
    const live = await raiseOnCareersFair()

    await editEventRequest('EVR-BOOK0101', { end_time: '18:00' })

    expect((await careersFairArrangement(withdrawn.id))?.flagged_after_change).toBe(false)
    expect((await careersFairArrangement(live.id))?.reassessment_flags).toEqual([
      { kind: 'requires_reconfirmation', reason: TIMING_CHANGED },
    ])
  })

  // As the backend's is_flagged_after_change: only while it holds or asks for its venue.
  it('stops counting a flag once the arrangement is withdrawn, keeping the reason', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const flagged = await raiseOnCareersFair()
    await editEventRequest('EVR-BOOK0101', { end_time: '18:00' })

    const withdrawn = await withdrawArrangement('EVR-BOOK0101', flagged.id)

    expect(withdrawn).toMatchObject({
      status: 'withdrawn',
      flagged_after_change: false,
      reassessment_flags: [{ kind: 'requires_reconfirmation', reason: TIMING_CHANGED }],
    })
  })
})
