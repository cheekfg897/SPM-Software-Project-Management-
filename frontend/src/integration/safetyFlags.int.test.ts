import { fetchFlaggedBookings, reconfirmFlaggedBooking } from '@/features/booking/api'
import { fetchEventRequest, sendToSafetyReview } from '@/features/eventRequests/api'
import { fetchAwaitingSafetyReview, recordSafetyOutcome } from '@/features/safety/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { refusal, signInAs, staffAccount } from './backend'
import {
  CHECKLIST,
  coordinatorPosts,
  EVENT_DATE,
  eventReadyForSafetyReview,
  LEAD,
  required,
  SAFETY_OFFICER,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-99 against the real backend: on a Request Changes the Safety Officer names a venue
 * arrangement, which Venue Staff then see flagged "Flagged by the Safety Officer: <reason>"; the
 * coordinator's record says what was named, and the event can't go back to Safety Review until
 * Venue Staff settle the flag (SCRUM-59).
 */

const needsAccounts = LEAD === null || VENUE_STAFF === null || SAFETY_OFFICER === null
const REASON = 'The east exit is blocked by the stage.'

/** An event in Safety Review with one approved booking; signs the Safety Officer in. */
async function eventInSafetyReview() {
  const event = await eventReadyForSafetyReview()
  await coordinatorPosts(event.reference, 'safety-review')
  await signInAs(required(SAFETY_OFFICER))
  return event
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-99 naming what to rework against the backend', () => {
  it.skipIf(needsAccounts)(
    "lists each booked venue's id for the Safety Officer to name, and refuses names on approval",
    async () => {
      const event = await eventInSafetyReview()
      const list = await fetchAwaitingSafetyReview()
      const listed = list.events.find((awaiting) => awaiting.event.reference === event.reference)
      expect(listed?.venues.map((venue) => venue.id)).toEqual([event.bookingId])

      const approval = await refusal(
        recordSafetyOutcome({
          reference: event.reference,
          outcome: 'approved',
          checklist: CHECKLIST,
          flagged_arrangement_ids: [event.bookingId],
        }),
      )
      expect(approval.status).toBe(400)
      expect(approval.fieldErrors.flagged_arrangement_ids).toEqual([
        'Only a rejection or a request for changes can name what to rework.',
      ])
      const unknownLine = await refusal(
        recordSafetyOutcome({
          reference: event.reference,
          outcome: 'changes_requested',
          checklist: CHECKLIST,
          reason: REASON,
          reopened_line_ids: [987654],
        }),
      )
      expect(unknownLine.fieldErrors.reopened_line_ids).toEqual([
        "Equipment line 987654 is not one of this event's lines.",
      ])
    },
  )

  it.skipIf(needsAccounts)(
    'flags the named booking for Venue Staff, shows the coordinator, and holds resubmission until it is settled',
    async () => {
      const event = await eventInSafetyReview()

      await recordSafetyOutcome({
        reference: event.reference,
        outcome: 'changes_requested',
        checklist: CHECKLIST,
        reason: REASON,
        flagged_arrangement_ids: [event.bookingId],
      })

      await signInAs(required(VENUE_STAFF))
      const flagged = (await fetchFlaggedBookings()).find(
        (entry) => entry.booking.id === event.bookingId,
      )
      expect(flagged?.booking.reassessment_flags).toEqual([
        { kind: 'requires_reconfirmation', reason: `Flagged by the Safety Officer: ${REASON}` },
      ])
      await signInAs(staffAccount())
      const record = await fetchEventRequest(event.reference)
      expect(record.status).toBe('approved')
      expect(record.safety_outcome).toMatchObject({
        outcome: 'changes_requested',
        reason: REASON,
        flagged_arrangement_count: 1,
        reopened_line_count: 0,
      })
      expect((await refusal(sendToSafetyReview(event.reference))).status).toBe(409)

      await signInAs(required(VENUE_STAFF))
      await reconfirmFlaggedBooking(event.bookingId, {
        starts_at: `${EVENT_DATE}T09:00:00+08:00`,
        ends_at: `${EVENT_DATE}T12:00:00+08:00`,
      })
      await signInAs(staffAccount())
      const resubmitted = await sendToSafetyReview(event.reference)

      expect(resubmitted.status).toBe('safety_review')
    },
  )
})
