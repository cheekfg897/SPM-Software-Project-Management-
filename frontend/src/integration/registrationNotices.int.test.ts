import {
  decideBookingRequest,
  fetchBookingRequests,
  raiseBookingRequest,
} from '@/features/booking/api'
import { registerForEvent, withdrawFromEvent } from '@/features/catalogue/api'
import { fetchNotifications } from '@/features/notifications/api'
import { blockVenue } from '@/features/venues/api'
import { sendRequestsAs } from '@/test/sendRequestsAs'

import { signInAs, signInAsNewAttendee, staffAccount } from './backend'
import {
  EVENT_DATE,
  LEAD,
  newVenue,
  registrableEvent,
  required,
  SAFETY_OFFICER,
  VENUE_STAFF,
} from './plannedEvent'

/**
 * SCRUM-62 against the real backend (docs/adr/0125). AC4, AC5: registering and withdrawing tell
 * the Attendee and the event's Organiser. AC6: an Attendee holding a place is told when Venue
 * Staff approve a replacement for a venue that became unavailable (SCRUM-92). Registering needs
 * an event taken to Confirmed, which needs the Lead, Venue Staff and Safety Officer accounts CI
 * makes, so these checks skip without them. The web app shows each notice's message and detail
 * as sent.
 */

const canRegister = LEAD !== null && VENUE_STAFF !== null && SAFETY_OFFICER !== null
/** The Attendee's detail: both venues (newVenue's "Integration Hall <unique>") and the event. */
const ATTENDEE_TOLD_REPLACED =
  /^Integration Hall \S+ is no longer available for Integration Event \S+\. Integration Hall \S+ has been approved in its place\.$/

/** The signed-in user's notices about the event, newest first, as (kind, message, detail). */
async function noticesAbout(reference: string) {
  const notices = await fetchNotifications()
  const aboutEvent = notices.filter((notice) => notice.event_reference === reference)
  for (const notice of aboutEvent) {
    expect(notice.link).toBe(`/events/${reference}`)
  }
  return aboutEvent.map((notice) => [notice.kind, notice.message, notice.detail])
}

afterEach(() => sendRequestsAs(null))

describe('SCRUM-62 registration notices against the backend', () => {
  it.skipIf(!canRegister)(
    'tells the attendee and the organiser when a place is taken and given back',
    async () => {
      const event = await registrableEvent()
      await signInAsNewAttendee()

      await registerForEvent(event.id)
      await withdrawFromEvent(event.id)

      // --- The attendee hears of their own registration (AC5) ---
      expect(await noticesAbout(event.reference)).toEqual([
        ['registration_withdrawn', 'Your registration for this event has been withdrawn.', null],
        ['registration_confirmed', 'Your registration for this event is confirmed.', null],
      ])
      // --- The organiser who submitted it hears how many places are left (AC4) ---
      // Its older notices are the planning's (assigned, approved, confirmed).
      await signInAs(event.organiser)
      const newestTwo = (await noticesAbout(event.reference)).slice(0, 2)
      expect(newestTwo).toEqual([
        ['attendee_withdrawn', 'An Attendee withdrew from your event.', '50 of 50 places left.'],
        ['attendee_registered', 'An Attendee registered for your event.', '49 of 50 places left.'],
      ])
    },
  )

  it.skipIf(!canRegister)(
    'tells an attendee holding a place when a replacement venue is approved (AC6)',
    async () => {
      const event = await registrableEvent()
      const attendee = await signInAsNewAttendee()
      await registerForEvent(event.id)
      // --- Venue Staff block the event's venue, and approve a replacement the coordinator raises ---
      await signInAs(staffAccount())
      const [original] = await fetchBookingRequests(event.reference)
      if (original === undefined) {
        throw new Error('The registrable event should have its approved venue arrangement.')
      }
      await signInAs(required(VENUE_STAFF))
      await blockVenue(original.venue_id, {
        start_time: `${EVENT_DATE}T08:00`,
        end_time: `${EVENT_DATE}T18:00`,
        category: 'maintenance',
        reason: 'Roof repairs',
      })
      const otherVenue = await newVenue()
      await signInAs(staffAccount())
      const replacement = await raiseBookingRequest(event.reference, {
        venue_id: otherVenue,
        starts_at: original.starts_at,
        ends_at: original.ends_at,
        purpose: 'Integration replacement',
        replaces_request_id: original.id,
      })
      await signInAs(required(VENUE_STAFF))
      await decideBookingRequest(replacement.id, { outcome: 'approved' })

      await signInAs(attendee)
      const [replaced, confirmed] = await noticesAbout(event.reference)

      expect(confirmed?.[0]).toBe('registration_confirmed')
      expect(replaced?.slice(0, 2)).toEqual([
        'replacement_venue_approved',
        'A replacement venue was approved for your event.',
      ])
      expect(replaced?.[2]).toMatch(ATTENDEE_TOLD_REPLACED)
      expect(replaced?.[2]).toContain(` for ${event.name}. `)
    },
  )
})
