import { fetchEventRequest } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { signInAs, staffAccount } from './backend'
import {
  coordinatorPosts,
  EVENT_DATE,
  LEAD,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-49 AC11 against the running backend: once the event is confirmed, its organiser's record
 * lists every approved venue arrangement with its venue, date and times, and what was arranged
 * (ADR-0099). Before then it lists none, and the coordinator's record never has the list.
 * Confirming an event takes a Lead, Venue Staff and a Safety Officer, which plannedEvent.ts reads;
 * the check skips without them.
 */

const canConfirm = LEAD !== null && VENUE_STAFF !== null && SAFETY_OFFICER !== null

afterEach(() => sendRequestsAs(null))

describe('SCRUM-49 AC11 a confirmed event venues on its organiser record against the backend', () => {
  it.skipIf(!canConfirm)(
    "lists the venues only once the event is confirmed, and never on the coordinator's record",
    async () => {
      const event = await safetyApprovedEvent()
      await signInAs(staffAccount())
      const { name: venueName } = await apiRequest<{ name: string }>(
        `/api/venues/${String(event.venueId)}`,
      )
      await signInAs(event.organiser)
      const beforeConfirming = await fetchEventRequest(event.reference)

      await coordinatorPosts(event.reference, 'confirm')
      const coordinatorsRecord = await fetchEventRequest(event.reference)
      await signInAs(event.organiser)
      const organisersRecord = await fetchEventRequest(event.reference)

      expect(beforeConfirming.venue_arrangements).toEqual([])
      expect(organisersRecord.venue_arrangements).toEqual([
        {
          venue_name: venueName,
          venue_location: 'Level 1',
          starts_at: `${EVENT_DATE}T09:00:00+08:00`,
          ends_at: `${EVENT_DATE}T12:00:00+08:00`,
          purpose: 'Integration safety check',
          layout: null,
          expected_occupancy: 120,
        },
      ])
      expect(coordinatorsRecord).not.toHaveProperty('venue_arrangements')
    },
  )
})
