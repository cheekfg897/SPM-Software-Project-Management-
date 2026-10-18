import { fetchAwaitingSafetyReview, recordSafetyOutcome } from '@/features/safety/api'
import type { SafetyChecklist } from '@/features/safety/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, signInAsNewAttendee, staffAccount } from './backend'
import {
  CHECKLIST,
  coordinatorPosts,
  EVENT_DATE,
  eventReadyForSafetyReview,
  LEAD,
  required,
  SAFETY_OFFICER,
  submittedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * The Safety Officer's list (SCRUM-97 AC5, AC6; SCRUM-24 AC6) and the safety check outcome
 * (SCRUM-98) against the running backend (docs/adr/0047, docs/adr/0071).
 *
 * The refusals run with the staff account every run has (an Event Coordinator) and new
 * attendees. The Safety Officer's own answers need a Safety Officer account, and an event in
 * Safety Review needs a Lead to assign it and Venue Staff to make and approve its venue, so
 * those checks read the accounts from INTEGRATION_SAFETY_OFFICER_*, INTEGRATION_LEAD_* and
 * INTEGRATION_VENUE_STAFF_* and skip without them. CI makes all of them (frontend.yml).
 */

const NOT_PERMITTED = {
  status: 403,
  code: 'authorization_error',
  message: 'You do not have permission to perform this action.',
}
const NOT_SIGNED_IN = { status: 401, code: 'authentication_error' }
const NO_EVENTS_MESSAGE = 'No events are waiting for a safety review.'
const REASON_REQUIRED_MESSAGE = 'A reason is required to reject the event or request changes.'
const NOT_IN_SAFETY_REVIEW_MESSAGE = 'Only an event in Safety Review can get a safety outcome.'
const ALREADY_APPROVED_MESSAGE = 'The Safety Officer has already approved this event.'
/** Every field of the event request the outcome answers with (EventRequestSchema). */
const EVENT_REQUEST_FIELDS = [
  'accessibility_needs',
  'created_at',
  'description',
  'end_date',
  'end_time',
  'equipment_requirements',
  'expected_attendance',
  'name',
  'proposed_date',
  'purpose',
  'reference',
  'registration_required',
  'start_time',
  'status',
  'venue_requirements',
]
/** A well-formed reference no database has, so the lookup finds nothing. */
const UNKNOWN_REFERENCE = 'EVR-NOSUCH00'

const hasSafetyOfficer = SAFETY_OFFICER !== null
const canReachSafetyReview = hasSafetyOfficer && LEAD !== null && VENUE_STAFF !== null

/** As the Safety Officer: the references on their list. */
async function listedReferences(): Promise<string[]> {
  await signInAs(required(SAFETY_OFFICER))
  const list = await fetchAwaitingSafetyReview()
  return list.events.map((awaiting) => awaiting.event.reference)
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-97 and SCRUM-24 AC6 the Safety Officer list against the backend', () => {
  it('refuses the list to an Event Coordinator', async () => {
    await signInAs(staffAccount())

    expect(await refusal(fetchAwaitingSafetyReview())).toMatchObject(NOT_PERMITTED)
  })

  it('refuses the list to an Attendee', async () => {
    await signInAsNewAttendee()

    expect(await refusal(fetchAwaitingSafetyReview())).toMatchObject(NOT_PERMITTED)
  })

  it('refuses the list to a visitor', async () => {
    sendRequestsAs(null)

    expect(await refusal(fetchAwaitingSafetyReview())).toMatchObject(NOT_SIGNED_IN)
  })

  it.skipIf(!hasSafetyOfficer)(
    'adds the "none waiting" message to the list exactly when it is empty',
    async () => {
      await signInAs(required(SAFETY_OFFICER))

      const list = await fetchAwaitingSafetyReview()

      if (list.events.length === 0) {
        expect(list).toEqual({ events: [], message: NO_EVENTS_MESSAGE })
      } else {
        expect(Object.keys(list)).toEqual(['events'])
      }
    },
  )
})

describe('SCRUM-98 recording a safety outcome against the backend', () => {
  it('refuses an outcome from an Event Coordinator', async () => {
    await signInAs(staffAccount())

    const error = await refusal(
      recordSafetyOutcome({
        reference: UNKNOWN_REFERENCE,
        outcome: 'approved',
        checklist: CHECKLIST,
      }),
    )

    expect(error).toMatchObject(NOT_PERMITTED)
  })

  it('refuses an outcome from a visitor', async () => {
    sendRequestsAs(null)

    const error = await refusal(
      recordSafetyOutcome({
        reference: UNKNOWN_REFERENCE,
        outcome: 'approved',
        checklist: CHECKLIST,
      }),
    )

    expect(error).toMatchObject(NOT_SIGNED_IN)
  })

  it.skipIf(!hasSafetyOfficer)(
    'names each blank or missing checklist note by its path (400), before looking for the event',
    async () => {
      await signInAs(required(SAFETY_OFFICER))
      const withoutCrowdMovement: Partial<SafetyChecklist> = { ...CHECKLIST }
      delete withoutCrowdMovement.crowd_movement

      const error = await refusal(
        recordSafetyOutcome({
          reference: UNKNOWN_REFERENCE,
          outcome: 'approved',
          checklist: { ...withoutCrowdMovement, emergency_access: '   ' } as SafetyChecklist, // -- crowd_movement left out on purpose
        }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({
        'checklist.crowd_movement': ['Missing data for required field.'],
        'checklist.emergency_access': ['Must not be blank.'],
      })
    },
  )

  it.skipIf(!hasSafetyOfficer)(
    'asks for a reason to request changes (400 on reason), before looking for the event',
    async () => {
      await signInAs(required(SAFETY_OFFICER))

      const error = await refusal(
        recordSafetyOutcome({
          reference: UNKNOWN_REFERENCE,
          outcome: 'changes_requested',
          checklist: CHECKLIST,
        }),
      )

      expect(error).toMatchObject({ status: 400, code: 'validation_error' })
      expect(error.fieldErrors).toEqual({ reason: [REASON_REQUIRED_MESSAGE] })
    },
  )

  it.skipIf(!hasSafetyOfficer)('answers 404 for an event that does not exist', async () => {
    await signInAs(required(SAFETY_OFFICER))

    const error = await refusal(
      recordSafetyOutcome({
        reference: UNKNOWN_REFERENCE,
        outcome: 'approved',
        checklist: CHECKLIST,
      }),
    )

    expect(error).toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Event request not found.',
    })
  })

  it.skipIf(!hasSafetyOfficer)(
    'refuses an outcome for an event not in Safety Review (409)',
    async () => {
      const event = await submittedEvent()
      await signInAs(required(SAFETY_OFFICER))

      const error = await refusal(
        recordSafetyOutcome({
          reference: event.reference,
          outcome: 'approved',
          checklist: CHECKLIST,
        }),
      )

      expect(error).toMatchObject({
        status: 409,
        code: 'safety_outcome_not_allowed',
        message: NOT_IN_SAFETY_REVIEW_MESSAGE,
      })
      expect(error.fieldErrors).toEqual({})
    },
  )

  it.skipIf(!canReachSafetyReview)(
    'lists an event sent to Safety Review, sends it back on Request Changes, and drops it once approved',
    async () => {
      const event = await eventReadyForSafetyReview()
      await coordinatorPosts(event.reference, 'safety-review')

      // --- Listed, with exactly the fields the screen reads (SCRUM-97 AC6) ---
      await signInAs(required(SAFETY_OFFICER))
      const list = await fetchAwaitingSafetyReview()
      const listed = list.events.find((awaiting) => awaiting.event.reference === event.reference)
      expect(listed?.event).toEqual({
        reference: event.reference,
        name: event.name,
        proposed_date: EVENT_DATE,
        end_date: EVENT_DATE,
        start_time: '09:00:00',
        end_time: '17:00:00',
        status: 'safety_review',
        expected_attendance: 120,
        accessibility_needs: 'Step-free entrance',
      })
      expect(listed?.venues).toEqual([
        {
          name: expect.stringMatching(/^Integration Hall /) as unknown,
          capacity: 300,
          layouts: ['theatre'],
          facilities: ['projector'],
          accessibility_features: ['wheelchair_access'],
          starts_at: `${EVENT_DATE}T09:00:00+08:00`,
          ends_at: `${EVENT_DATE}T12:00:00+08:00`,
        },
      ])
      expect(listed?.equipment).toEqual([])

      // --- Request Changes, then Reject: each sends it back to Approved, off the list (AC6) ---
      for (const outcome of ['changes_requested', 'rejected'] as const) {
        const returned = await recordSafetyOutcome({
          reference: event.reference,
          outcome,
          checklist: CHECKLIST,
          reason: 'Second exit is blocked.',
        })
        expect(Object.keys(returned).sort()).toEqual(EVENT_REQUEST_FIELDS)
        expect(returned).toMatchObject({
          reference: event.reference,
          name: event.name,
          status: 'approved',
        })
        expect(await listedReferences()).not.toContain(event.reference)
        await coordinatorPosts(event.reference, 'safety-review')
        expect(await listedReferences()).toContain(event.reference)
      }

      // --- Approved: it stays in Safety Review for the coordinator but leaves the list (AC5) ---
      const approved = await recordSafetyOutcome({
        reference: event.reference,
        outcome: 'approved',
        checklist: CHECKLIST,
      })
      expect(approved).toMatchObject({ reference: event.reference, status: 'safety_review' })
      expect(await listedReferences()).not.toContain(event.reference)

      // --- A second outcome on an approved event is refused (ADR-0047 decision 18) ---
      const again = await refusal(
        recordSafetyOutcome({
          reference: event.reference,
          outcome: 'rejected',
          checklist: CHECKLIST,
          reason: 'Too late.',
        }),
      )
      expect(again).toMatchObject({
        status: 409,
        code: 'safety_outcome_not_allowed',
        message: ALREADY_APPROVED_MESSAGE,
      })
    },
  )
})
