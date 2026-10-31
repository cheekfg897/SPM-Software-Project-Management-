import { fetchStaffEventRecord } from '@/features/eventRequests/api'
import type { SafetyChecklist } from '@/features/safety/api'
import { fetchAwaitingSafetyReview, recordSafetyOutcome } from '@/features/safety/api'
import { ApiError, apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { MOCK_ACCOUNTS, mockTokenFor } from '../fixtures/accounts'

import {
  MOCK_APPROVED_LAUNCH,
  MOCK_FAIR,
  MOCK_GALA,
  MOCK_RETURNED_SUMMIT,
  MOCK_TOWN_HALL,
} from './safetyFixtures'

/**
 * The safety mock stands in for SCRUM-97's list and SCRUM-98's outcome route, so these tests pin
 * it to what backend/app/modules/events/routes.py and services.py answer (ADR-0047).
 */

const OUTCOME_PATH = `/api/events/requests/${MOCK_GALA.event.reference}/safety-outcome`
const MISSING = 'Missing data for required field.'
const BLANK = 'Must not be blank.'

const CHECKLIST: SafetyChecklist = {
  attendance_vs_capacity: '400 expected in a ballroom for 500.',
  venue_layout: 'Banquet rounds, aisles kept clear.',
  emergency_access: 'Three exits, all signed.',
  accessibility: 'Wheelchair spaces at front tables.',
  equipment_placement: 'Projectors on ceiling mounts.',
  crowd_movement: 'Arrivals staggered over an hour.',
  venue_restrictions: 'No candles on tables.',
}

async function errorOf(promise: Promise<unknown>): Promise<ApiError> {
  const error: unknown = await promise.then(
    () => null,
    (caught: unknown) => caught,
  )
  if (!(error instanceof ApiError)) {
    throw new Error('Expected the request to fail with an ApiError.')
  }
  return error
}

/** Post any body, typed or not, to the gala's outcome route. */
function postOutcome(body: unknown) {
  return apiRequest(OUTCOME_PATH, { method: 'POST', body })
}

async function listedReferences(): Promise<string[]> {
  const list = await fetchAwaitingSafetyReview()
  return list.events.map((awaiting) => awaiting.event.reference)
}

function signInAs(account: (typeof MOCK_ACCOUNTS)[keyof typeof MOCK_ACCOUNTS]) {
  sendRequestsAs(mockTokenFor(account))
}

beforeEach(() => signInAs(MOCK_ACCOUNTS.safetyOfficer))

describe('SCRUM-97 safety mock: the list awaiting review', () => {
  it('lists the events in Safety Review not yet approved, soonest date then earliest time first', async () => {
    expect(await listedReferences()).toEqual([
      MOCK_FAIR.event.reference,
      MOCK_TOWN_HALL.event.reference,
      MOCK_GALA.event.reference,
    ])
  })

  it('sends each event with its venues and equipment, and no message while the list has events', async () => {
    const list = await fetchAwaitingSafetyReview()

    expect(list).not.toHaveProperty('message')
    expect(list.events[2]).toEqual({
      event: MOCK_GALA.event,
      venues: MOCK_GALA.venues,
      equipment: MOCK_GALA.equipment,
    })
  })

  it('answers an empty list with the backend message once every event has an outcome', async () => {
    for (const awaiting of [MOCK_FAIR, MOCK_GALA, MOCK_TOWN_HALL]) {
      await recordSafetyOutcome({
        reference: awaiting.event.reference,
        outcome: 'approved',
        checklist: CHECKLIST,
      })
    }

    expect(await fetchAwaitingSafetyReview()).toEqual({
      events: [],
      message: 'No events are waiting for a safety review.',
    })
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['an Event Coordinator Lead', MOCK_ACCOUNTS.lead],
    ['an Attendee', MOCK_ACCOUNTS.attendee],
  ])('refuses %s with a 403', async (_label, account) => {
    signInAs(account)

    expect(await errorOf(fetchAwaitingSafetyReview())).toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it('refuses a visitor with a 401', async () => {
    sendRequestsAs(null)

    expect((await errorOf(fetchAwaitingSafetyReview())).status).toBe(401)
  })
})

describe('SCRUM-98 safety mock: recording the outcome', () => {
  it('keeps an approved event in Safety Review and takes it off the list', async () => {
    const recorded = await recordSafetyOutcome({
      reference: MOCK_GALA.event.reference,
      outcome: 'approved',
      checklist: CHECKLIST,
    })

    expect(recorded).toMatchObject({
      reference: MOCK_GALA.event.reference,
      name: MOCK_GALA.event.name,
      status: 'safety_review',
    })
    expect(await listedReferences()).not.toContain(MOCK_GALA.event.reference)
  })

  it.each(['rejected', 'changes_requested'] as const)(
    'returns the event to Approved on %s, never to Rejected, and off the list',
    async (outcome) => {
      const recorded = await recordSafetyOutcome({
        reference: MOCK_GALA.event.reference,
        outcome,
        checklist: CHECKLIST,
        reason: 'Second exit is blocked.',
      })

      expect(recorded.status).toBe('approved')
      expect(await listedReferences()).not.toContain(MOCK_GALA.event.reference)
    },
  )

  it('refuses a second outcome once the event is approved (409)', async () => {
    const error = await errorOf(
      recordSafetyOutcome({
        reference: MOCK_APPROVED_LAUNCH.event.reference,
        outcome: 'rejected',
        checklist: CHECKLIST,
        reason: 'Late.',
      }),
    )

    expect(error).toMatchObject({
      status: 409,
      code: 'safety_outcome_not_allowed',
      message: 'The Safety Officer has already approved this event.',
    })
  })

  it('refuses an outcome for an event that is no longer in Safety Review (409)', async () => {
    const error = await errorOf(
      recordSafetyOutcome({
        reference: MOCK_RETURNED_SUMMIT.event.reference,
        outcome: 'approved',
        checklist: CHECKLIST,
      }),
    )

    expect(error).toMatchObject({
      status: 409,
      code: 'safety_outcome_not_allowed',
      message: 'Only an event in Safety Review can get a safety outcome.',
    })
  })

  it('answers 404 for an unknown event with a valid body', async () => {
    const error = await errorOf(
      recordSafetyOutcome({ reference: 'EVR-NOSUCH00', outcome: 'approved', checklist: CHECKLIST }),
    )

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Event request not found.',
    })
  })

  it('checks the body before the event: an unknown event with no checklist is a 400', async () => {
    const error = await errorOf(
      apiRequest('/api/events/requests/EVR-NOSUCH00/safety-outcome', {
        method: 'POST',
        body: { outcome: 'approved' },
      }),
    )

    expect(error.status).toBe(400)
    expect(error.fieldErrors).toEqual({ checklist: [MISSING] })
  })

  it('names each missing, blank or wrong-typed checklist note by its path', async () => {
    const withoutCrowdMovement: Partial<SafetyChecklist> = { ...CHECKLIST }
    delete withoutCrowdMovement.crowd_movement

    const error = await errorOf(
      postOutcome({
        outcome: 'approved',
        checklist: { ...withoutCrowdMovement, emergency_access: '  ', venue_layout: 7 },
      }),
    )

    expect(error).toMatchObject({ status: 400, code: 'validation_error' })
    expect(error.fieldErrors).toEqual({
      'checklist.crowd_movement': [MISSING],
      'checklist.emergency_access': [BLANK],
      'checklist.venue_layout': ['Not a valid string.'],
    })
  })

  it('refuses a checklist that is not an object', async () => {
    const error = await errorOf(postOutcome({ outcome: 'approved', checklist: 'all fine' }))

    expect(error.fieldErrors).toEqual({ 'checklist._schema': ['Invalid input type.'] })
  })

  it.each([
    ['missing', undefined, MISSING],
    ['unknown', 'maybe', 'Outcome must be approved, rejected or changes_requested.'],
  ])('refuses a %s outcome on the outcome field', async (_label, outcome, message) => {
    const error = await errorOf(postOutcome({ outcome, checklist: CHECKLIST }))

    expect(error.fieldErrors).toEqual({ outcome: [message] })
  })

  it.each(['rejected', 'changes_requested'] as const)(
    'asks for a reason to %s, and only once every field is valid',
    async (outcome) => {
      const error = await errorOf(postOutcome({ outcome, checklist: CHECKLIST }))
      const withBlankNote = await errorOf(
        postOutcome({ outcome, checklist: { ...CHECKLIST, venue_restrictions: '' } }),
      )

      expect(error.fieldErrors).toEqual({
        reason: ['A reason is required to reject the event or request changes.'],
      })
      expect(withBlankNote.fieldErrors).toEqual({ 'checklist.venue_restrictions': [BLANK] })
    },
  )

  it.each([
    ['blank', '   ', BLANK],
    ['not text', 3, 'Not a valid string.'],
  ])('refuses a %s reason, even with an approval', async (_label, reason, message) => {
    const error = await errorOf(postOutcome({ outcome: 'approved', checklist: CHECKLIST, reason }))

    expect(error.fieldErrors).toEqual({ reason: [message] })
  })

  it('accepts an approval with no reason, or a null one', async () => {
    const recorded = await postOutcome({ outcome: 'approved', checklist: CHECKLIST, reason: null })

    expect(recorded).toMatchObject({ status: 'safety_review' })
  })

  it('refuses a body that is not an object with the backend message and no details', async () => {
    const error = await errorOf(postOutcome(['approved']))

    expect(error).toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'Request body must be a JSON object.',
    })
    expect(error.fieldErrors).toEqual({})
  })

  it.each([
    ['an Event Coordinator', MOCK_ACCOUNTS.coordinator],
    ['Venue Staff', MOCK_ACCOUNTS.venueStaff],
  ])('refuses %s with a 403 before reading the body', async (_label, account) => {
    signInAs(account)

    expect(await errorOf(postOutcome({}))).toMatchObject({
      status: 403,
      code: 'authorization_error',
    })
  })

  it('refuses a visitor with a 401', async () => {
    sendRequestsAs(null)

    expect((await errorOf(postOutcome({}))).status).toBe(401)
  })
})

describe('SCRUM-99 safety mock: naming what to rework', () => {
  const [ballroom] = MOCK_GALA.venues
  const [projector, microphones] = MOCK_GALA.equipment
  const NOT_ON_APPROVAL = 'Only a rejection or a request for changes can name what to rework.'

  /** A Request Changes on the gala, with a reason, naming what `named` holds. */
  function requestChanges(named: Record<string, unknown>) {
    return postOutcome({
      outcome: 'changes_requested',
      checklist: CHECKLIST,
      reason: 'Clear the east exit.',
      ...named,
    })
  }

  it('counts each arrangement and line named once on the outcome the record shows', async () => {
    await requestChanges({
      flagged_arrangement_ids: [ballroom?.id, ballroom?.id],
      reopened_line_ids: [projector?.id, microphones?.id],
    })

    const record = await fetchStaffEventRecord(MOCK_GALA.event.reference)
    expect(record.safety_outcome).toMatchObject({
      outcome: 'changes_requested',
      flagged_arrangement_count: 1,
      reopened_line_count: 2,
    })
  })

  it('refuses an approval that names anything, on each field named', async () => {
    const error = await errorOf(
      postOutcome({
        outcome: 'approved',
        checklist: CHECKLIST,
        flagged_arrangement_ids: [ballroom?.id],
        reopened_line_ids: [projector?.id],
      }),
    )

    expect([error.status, error.fieldErrors]).toEqual([
      400,
      { flagged_arrangement_ids: [NOT_ON_APPROVAL], reopened_line_ids: [NOT_ON_APPROVAL] },
    ])
  })

  it("refuses a line that isn't the event's, then an arrangement that isn't, naming each", async () => {
    const line = await errorOf(
      requestChanges({ flagged_arrangement_ids: [9999], reopened_line_ids: [9998] }),
    )
    const arrangement = await errorOf(requestChanges({ flagged_arrangement_ids: [9999] }))

    expect(line.fieldErrors).toEqual({
      reopened_line_ids: ["Equipment line 9998 is not one of this event's lines."],
    })
    expect(arrangement.fieldErrors).toEqual({
      flagged_arrangement_ids: [
        "Venue arrangement 9999 is not one of this event's approved arrangements.",
      ],
    })
  })

  // The client reads a list's messages by place, as "flagged_arrangement_ids.0".
  it.each([
    ['text', '1', { flagged_arrangement_ids: ['Not a valid list.'] }],
    ['null', null, { flagged_arrangement_ids: ['Field may not be null.'] }],
    ['a text id', ['a'], { 'flagged_arrangement_ids.0': ['Not a valid integer.'] }],
    ['a boolean id', [true], { 'flagged_arrangement_ids.0': ['Not a valid integer.'] }],
    [
      'zero',
      [0],
      { 'flagged_arrangement_ids.0': ['flagged_arrangement_ids must be a positive number.'] },
    ],
  ])('refuses %s as the ids, as the schema does', async (_label, value, fieldErrors) => {
    const error = await errorOf(requestChanges({ flagged_arrangement_ids: value }))

    expect([error.status, error.fieldErrors]).toEqual([400, fieldErrors])
  })
})
