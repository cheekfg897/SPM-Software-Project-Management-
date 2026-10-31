import { EVENT_REQUEST_STATUS } from '@/config/eventStatus'
import type { EventRequestStatus } from '@/config/eventStatus'
import {
  fetchBookingRequests,
  fetchFlaggedBookings,
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
 * history, and the refusals come with the backend's codes and messages. An event can be edited
 * in every status before Confirmed, and a Confirmed one is refused with a pointer to a change
 * request (AC8, ADR-0101). The mock's "today" is 5 Oct 2026.
 */

/** Chloe's, under review: 12 Nov, 9:00 am to 5:00 pm, 250 expected. */
const PARTNER_SUMMIT = 'EVR-7K2M9QXA'
/** Marcus's. */
const NOT_CHLOES = 'EVR-W9CR5E7M'
const MOCK_NOW = '2026-10-05T12:00:00+08:00'
const NOT_EDITABLE_MESSAGE =
  'An event request can only be edited before it is confirmed, and not once it is rejected or cancelled.'

/** Every status but a draft's, which no coordinator is assigned. */
type AssignedStatus = Exclude<EventRequestStatus, typeof EVENT_REQUEST_STATUS.DRAFT>

/** Every status before Confirmed (SCRUM-33 AC8 and its status clarification, ADR-0101). */
const EDITABLE_STATUSES: readonly AssignedStatus[] = [
  EVENT_REQUEST_STATUS.SUBMITTED,
  EVENT_REQUEST_STATUS.UNDER_REVIEW,
  EVENT_REQUEST_STATUS.AWAITING_CLARIFICATION,
  EVENT_REQUEST_STATUS.APPROVED,
  EVENT_REQUEST_STATUS.SAFETY_REVIEW,
]
/**
 * Every other assigned status but Confirmed, which has its own message. Built from the statuses,
 * so one added later is checked too.
 */
const REFUSED_STATUSES = Object.values(EVENT_REQUEST_STATUS).filter(
  (status): status is AssignedStatus =>
    status !== EVENT_REQUEST_STATUS.DRAFT &&
    status !== EVENT_REQUEST_STATUS.CONFIRMED &&
    !EDITABLE_STATUSES.includes(status),
)
/** A mock event in each assigned status, with the coordinator it is assigned to. */
const EVENT_IN_STATUS: Record<AssignedStatus, [MockAccount, string]> = {
  submitted: [MOCK_ACCOUNTS.reviewingCoordinator, 'EVR-RV4K8N2P'],
  under_review: [MOCK_ACCOUNTS.coordinator, PARTNER_SUMMIT],
  awaiting_clarification: [MOCK_ACCOUNTS.coordinator, 'EVR-B6YF2K8V'],
  approved: [MOCK_ACCOUNTS.coordinator, 'EVR-BOOK0101'],
  safety_review: [MOCK_ACCOUNTS.planningCoordinator, 'EVR-PLAN0003'],
  confirmed: [MOCK_ACCOUNTS.coordinator, 'EVR-BOOK0102'],
  completed: [MOCK_ACCOUNTS.planningCoordinator, 'EVR-PLAN0007'],
  cancelled: [MOCK_ACCOUNTS.planningCoordinator, 'EVR-PLAN0008'],
  rejected: [MOCK_ACCOUNTS.reviewingCoordinator, 'EVR-RV9H6C1W'],
}

function signInAs(account: MockAccount) {
  sendRequestsAs(mockTokenFor(account))
}

/** An edit to the description, which the mock must refuse. */
function refusedNote(reference: string) {
  return refusal(editEventRequest(reference, { description: 'x' }))
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

  it('shows the organiser the planning notes, on the record and in the history (ADR-0104)', async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const edited = await editEventRequest(PARTNER_SUMMIT, { internal_planning_notes: 'Call AV.' })
    const coordinatorsHistory = await fetchEventHistory(PARTNER_SUMMIT)

    signInAs(MOCK_ACCOUNTS.organiser)
    const record = await fetchEventRequest(PARTNER_SUMMIT)
    const organisersHistory = await fetchEventHistory(PARTNER_SUMMIT)

    expect(edited.internal_planning_notes).toBe('Call AV.')
    expect(coordinatorsHistory.history).toHaveLength(5)
    expect(record.internal_planning_notes).toBe('Call AV.')
    expect(organisersHistory).toEqual(coordinatorsHistory)
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

  it.each(EDITABLE_STATUSES)(
    'lets the coordinator edit an event that is %s, and keeps its status',
    async (status) => {
      const [account, reference] = EVENT_IN_STATUS[status]
      signInAs(account)

      const edited = await editEventRequest(reference, { description: 'Edited.' })

      expect(edited).toMatchObject({ status, description: 'Edited.' })
    },
  )

  it('refuses a Confirmed event, pointing to a change request, and changes nothing (AC8)', async () => {
    const [account, reference] = EVENT_IN_STATUS.confirmed
    signInAs(account)

    expect(await refusedNote(reference)).toMatchObject({
      status: 409,
      code: 'request_not_editable',
      message: 'A confirmed event can only be changed through a change request.',
    })
    expect(await fetchEventRequest(reference)).toMatchObject({
      status: 'confirmed',
      description: null,
    })
  })

  it.each(REFUSED_STATUSES)(
    'refuses an event that is %s with the general message, and changes nothing',
    async (status) => {
      const [account, reference] = EVENT_IN_STATUS[status]
      signInAs(account)

      expect(await refusedNote(reference)).toMatchObject({
        status: 409,
        code: 'request_not_editable',
        message: NOT_EDITABLE_MESSAGE,
      })
      expect((await fetchEventRequest(reference)).description).toBeNull()
    },
  )

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
 * withdraws the approval, and an event in Safety Review goes back to Approved for a new check. A
 * Confirmed event can't be edited (AC8), so Safety Review is where an edit meets an approval.
 * Hana's EVR-PLAN0003 is in Safety Review with the Safety Officer's approval; EVR-PLAN0004 is in
 * Safety Review without one.
 */
describe('SCRUM-33 mock of an edit: the safety approval (AC7)', () => {
  const HANA = MOCK_ACCOUNTS.planningCoordinator

  /** The newest history entry, as the signed-in coordinator reads it. */
  async function newestEntryOf(reference: string) {
    return (await fetchEventHistory(reference)).history.at(-1)
  }

  it('withdraws the approval on a significant change, so the event needs a new check', async () => {
    signInAs(HANA)

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

  it('keeps an event in Safety Review without an approval there on a significant change', async () => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0004', { expected_attendance: 100 })

    expect(edited.status).toBe('safety_review')
    expect(await newestEntryOf('EVR-PLAN0004')).toMatchObject({ kind: 'field_changed' })
  })

  it.each([
    ['a note', { description: 'New notes.' }],
    ['a significant value sent again', { description: 'New notes.', expected_attendance: 150 }],
  ])('keeps the approval for %s', async (_case, changes) => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0003', changes)

    expect(edited.status).toBe('safety_review')
    expect(await newestEntryOf('EVR-PLAN0003')).toMatchObject({ kind: 'field_changed' })
    expect(await confirmEvent('EVR-PLAN0003')).toMatchObject({ status: 'confirmed' })
  })
})

/**
 * SCRUM-33 AC9 (ADR-0107): a significant change in Safety Review that flags a venue arrangement
 * leaves it unsettled, so the event goes back to Approved, once, and can be sent again only once
 * the flag clears. Hana's EVR-PLAN0004 is in Safety Review, not yet approved by the Safety
 * Officer, with an approved hall for everyone (47); EVR-PLAN0003 has the officer's approval.
 */
describe('SCRUM-33 mock of an edit: a significant change in Safety Review (AC9)', () => {
  const HANA = MOCK_ACCOUNTS.planningCoordinator

  /** The kinds of the event's history entries, oldest first. */
  async function historyKindsOf(reference: string) {
    return (await fetchEventHistory(reference)).history.map((entry) => entry.kind)
  }

  it.each([
    ['a new time', { end_time: '23:00' }],
    ['new venue requirements', { venue_requirements: 'Step-free stage.' }],
  ])('sends the event back to Approved for %s, which flags its hall', async (_case, changes) => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0004', changes)

    expect(edited.status).toBe('approved')
    expect((await fetchEventRequest('EVR-PLAN0004')).status).toBe('approved')
    expect(await historyKindsOf('EVR-PLAN0004')).toEqual(['field_changed'])
  })

  it('keeps the event in Safety Review for a change that flags nothing', async () => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0004', { equipment_requirements: 'Two mics.' })

    expect(edited.status).toBe('safety_review')
  })

  it('moves an approved event once, withdrawing its approval once', async () => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0003', { end_time: '23:00' })

    expect(edited.status).toBe('approved')
    expect(await historyKindsOf('EVR-PLAN0003')).toEqual([
      'field_changed',
      'safety_approval_withdrawn',
    ])
  })

  it('leaves an Approved event Approved when a change flags its arrangement', async () => {
    signInAs(HANA)

    const edited = await editEventRequest('EVR-PLAN0002', { end_time: '23:00' })

    expect(edited.status).toBe('approved')
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

  it("moves a flagged booking's pre-filled period by as much as the edit moved the start", async () => {
    signInAs(MOCK_ACCOUNTS.coordinator)
    const hall = await raiseOnCareersFair()

    await editEventRequest('EVR-BOOK0101', { proposed_date: '2026-11-11', start_time: '10:30' })

    signInAs(MOCK_ACCOUNTS.venueStaff)
    const flagged = await fetchFlaggedBookings()
    expect(flagged.find((each) => each.booking.id === hall.id)?.reconfirm_with).toEqual({
      starts_at: '2026-11-11T10:30:00+08:00',
      ends_at: '2026-11-11T13:30:00+08:00',
      expected_occupancy: 80,
      period_adjustable: true,
    })
  })

  // SCRUM-59 AC2, ADR-0112 decision 17: the period may be adjusted only once the timing moved.
  it.each([
    ['an edit to the end alone', { end_time: '15:00' }, true],
    ['an edit that leaves the date and times', { venue_requirements: 'A stage.' }, false],
  ])(
    "says whether a flagged booking's period may be adjusted after %s",
    async (_label, edit, adjustable) => {
      signInAs(MOCK_ACCOUNTS.coordinator)
      const hall = await raiseOnCareersFair()

      await editEventRequest('EVR-BOOK0101', edit)

      signInAs(MOCK_ACCOUNTS.venueStaff)
      const flagged = await fetchFlaggedBookings()
      expect(flagged.find((each) => each.booking.id === hall.id)?.reconfirm_with).toEqual({
        starts_at: '2026-11-10T09:00:00+08:00',
        ends_at: '2026-11-10T12:00:00+08:00',
        expected_occupancy: 80,
        period_adjustable: adjustable,
      })
    },
  )

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
