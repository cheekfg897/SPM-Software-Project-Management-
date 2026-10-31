import { raiseBookingRequest } from '@/features/booking/api'
import { editEventRequest, fetchEventRequest } from '@/features/eventRequests/api'
import type { EventRecord } from '@/features/eventRequests/api'
import { apiRequest } from '@/lib/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { signInAs, staffAccount } from './backend'
import {
  approvedEvent,
  CHECKLIST,
  coordinatorPosts,
  EVENT_DATE,
  LEAD,
  newVenue,
  SAFETY_OFFICER,
  safetyApprovedEvent,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-24 AC10 and SCRUM-49 AC13 against the running backend: the organiser's record holds
 * everything on it at every stage (ADR-0104): every venue arrangement in full from the moment it
 * is raised, the planning notes, and the current safety check with its checklist, before and
 * after the event is confirmed. The coordinator's record has none of these. Planning an event
 * takes a Lead and Venue Staff, and confirming it a Safety Officer too, which plannedEvent.ts
 * reads; the checks skip without them.
 */

const canPlan = LEAD !== null && VENUE_STAFF !== null
const canConfirm = canPlan && SAFETY_OFFICER !== null
/** What only the organiser's record sends: everything else on it. */
/** Only the organiser's; the safety outcome is the coordinator's too (SCRUM-99 AC4). */
const ORGANISERS_OWN_KEYS = ['internal_planning_notes', 'equipment_reservations']

afterEach(() => sendRequestsAs(null))

/** The venue's name, read as staff: each integration venue gets a unique one. */
async function venueName(venueId: number): Promise<string> {
  await signInAs(staffAccount())
  const venue = await apiRequest<{ name: string }>(`/api/venues/${String(venueId)}`)
  return venue.name
}

/** The record's keys that only the organiser is sent. */
function organisersOwnKeysOf(record: EventRecord): string[] {
  return Object.keys(record).filter((key) => ORGANISERS_OWN_KEYS.includes(key))
}

describe('SCRUM-24 AC10 everything on the organiser record against the backend', () => {
  it.skipIf(!canPlan)(
    'shows the organiser an arrangement in full as soon as it is raised, and the planning notes',
    async () => {
      const event = await approvedEvent()
      const venueId = await newVenue()
      await signInAs(staffAccount())
      await raiseBookingRequest(event.reference, {
        venue_id: venueId,
        starts_at: `${EVENT_DATE}T09:00:00+08:00`,
        ends_at: `${EVENT_DATE}T12:00:00+08:00`,
        purpose: 'Integration keynote',
      })
      await editEventRequest(event.reference, { internal_planning_notes: 'Call AV.' })
      const coordinatorsRecord = await fetchEventRequest(event.reference)
      const name = await venueName(venueId)
      await signInAs(event.organiser)

      const record = await fetchEventRequest(event.reference)

      expect(record.status).toBe('approved')
      expect(record.internal_planning_notes).toBe('Call AV.')
      expect(record.venue_arrangements).toEqual([
        {
          venue_name: name,
          venue_location: 'Level 1',
          // What the Safety Officer reviews of the venue (SCRUM-24 AC10, 26 Oct).
          venue_capacity: 300,
          venue_facilities: ['projector'],
          venue_accessibility_features: ['wheelchair_access'],
          starts_at: `${EVENT_DATE}T09:00:00+08:00`,
          ends_at: `${EVENT_DATE}T12:00:00+08:00`,
          purpose: 'Integration keynote',
          // The request named no occupancy, so it took the event's attendance.
          expected_occupancy: 120,
          required_layout: null,
          justification: null,
          status: 'pending',
          decision_reason: null,
          suggested_venue_name: null,
          suggested_starts_at: null,
          suggested_ends_at: null,
          hold_expires_at: null,
          needs_alternative_venue: false,
          unavailability: [],
          flagged_after_change: false,
          reassessment_flags: [],
          preparation_status: 'not_started',
          preparation_notes: null,
        },
      ])
      expect(record.equipment_reservations).toEqual([])
      expect(record.safety_outcome).toBeNull()
      expect(organisersOwnKeysOf(coordinatorsRecord)).toEqual([])
      expect(coordinatorsRecord.safety_outcome).toBeNull()
      // SCRUM-93 AC5: the coordinator's record lists every arrangement too (ADR-0105).
      expect(coordinatorsRecord.venue_arrangements).toEqual(record.venue_arrangements)
    },
  )

  it.skipIf(!canConfirm)(
    'shows the organiser the safety check with its checklist before and after the event is confirmed',
    async () => {
      const event = await safetyApprovedEvent()
      await signInAs(event.organiser)
      const beforeConfirming = await fetchEventRequest(event.reference)

      await coordinatorPosts(event.reference, 'confirm')
      await signInAs(event.organiser)
      const confirmed = await fetchEventRequest(event.reference)

      expect(beforeConfirming.status).toBe('safety_review')
      expect(confirmed.status).toBe('confirmed')
      for (const record of [beforeConfirming, confirmed]) {
        expect(record.safety_outcome).toMatchObject({
          outcome: 'approved',
          checklist: CHECKLIST,
          reason: null,
        })
        expect(record.safety_outcome?.recorded_by).toEqual(expect.any(String))
        expect(record.safety_outcome?.recorded_at).toMatch(/[+-]\d\d:\d\d$/)
        expect(record.venue_arrangements?.map((shown) => shown.status)).toEqual(['approved'])
      }
    },
  )
})
