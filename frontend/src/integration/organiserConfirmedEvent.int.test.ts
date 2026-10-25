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
 * lists every approved venue arrangement with its venue, date and times, and what was arranged,
 * and shows the Safety Officer's final decision with when it was made (ADR-0099). Before then it
 * shows neither, and the coordinator's record never has them.
 * Confirming an event takes a Lead, Venue Staff and a Safety Officer, which plannedEvent.ts reads;
 * the check skips without them.
 */

const canConfirm = LEAD !== null && VENUE_STAFF !== null && SAFETY_OFFICER !== null

afterEach(() => sendRequestsAs(null))

describe('SCRUM-49 AC11 a confirmed event on its organiser record against the backend', () => {
  it.skipIf(!canConfirm)(
    "shows the venues and the safety decision only once the event is confirmed, and never on the coordinator's record",
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
      expect(beforeConfirming.safety_decision).toBeNull()
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
      // Only the outcome and when: no officer, checklist or reason.
      expect(Object.keys(organisersRecord.safety_decision ?? {}).sort()).toEqual([
        'decided_at',
        'outcome',
      ])
      expect(organisersRecord.safety_decision?.outcome).toBe('approved')
      expect(organisersRecord.safety_decision?.decided_at).toMatch(/[+-]\d\d:\d\d$/)
      expect(coordinatorsRecord).not.toHaveProperty('venue_arrangements')
      expect(coordinatorsRecord).not.toHaveProperty('safety_decision')
    },
  )
})
