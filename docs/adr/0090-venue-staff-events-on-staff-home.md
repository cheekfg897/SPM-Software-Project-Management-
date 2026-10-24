# ADR-0090: Venue Staff's events on Staff home, with rows that open nothing yet

- **Status:** Accepted. Which events Venue Staff may open is decided (SCRUM-24 AC9, 19 Oct). Decision
  2 is superseded by [ADR-0095](0095-read-only-event-record-for-internal-staff.md): each row now opens the event's read-only record
- **Date:** 2026-10-19
- **Story:** SCRUM-24 See the events my role is involved in (AC4, AC8, AC9, AC11)
- **Extends:** ADR-0056, ADR-0061, ADR-0085

## Context
ADR-0085 added Venue Staff's list to the backend: `GET /api/events/requests/with-venue-bookings`
answers every event with a venue booking request or a booking, newest first, in the same rows
as Technical Support's `/with-equipment`, and an empty list carries
"No events have a venue booking request yet." (AC11). The web app doesn't use it, so a Venue
Staff member logs in to a Staff home with only a greeting.

Technical Support's list of the events with equipment is on Staff home already (ADR-0061), and
each of its rows opens the event's Equipment page. Venue Staff have no such page:

- `GET /api/events/requests/<reference>` (the event's record, ADR-0056) is for organisers and
  coordinators only, so AC9's detail view isn't there for Venue Staff (ADR-0085's Consequences).
- The venue requests page for one event (`/events/<reference>/venue-requests`) is the
  coordinator's.
- Venue Staff's own page, "Venue booking requests" (`/staff/venue-requests`, SCRUM-43), holds
  the requests still waiting for a decision and, since SCRUM-84, the approved bookings to prepare
  (ADR-0080). It lists every request across events, not one event's, and an event whose requests
  are all Rejected or Expired is on this list but on neither of that page's lists.

On 19 Oct the product owner settled the access question in Jira (SCRUM-24 AC9): Venue Staff,
Technical Support and the Safety Officer may open **any** submitted event's record, read-only.
The backend doesn't allow it yet; a separate change to the record route will.

## Decision
1. **Staff home shows Venue Staff one more section, "Events with venue bookings"**, and no other
   role sees or asks for it. It reuses ADR-0056's titled list and row as Technical Support's
   list does: the backend's rows in its order, each with its name, date, times, reference and
   status (AC8), and the backend's message when there are none (AC11).
2. **The rows open nothing for now.** Until the backend's record route allows Venue Staff, no
   page can show them one event, and linking every row to their booking requests page would send
   them to a page that lists every event's requests and may not hold that event's at all. The
   shared list takes its `pathFor` as optional, and leaves a row unlinked without one. Once the
   route allows the role, each row links to the event's read-only record, as the product owner
   decided.
3. **The list's query key leaves out the viewer.** The list is the same for every Venue Staff
   member (ADR-0085 decision 2), other roles never ask, and signing out clears the cache, as with
   Technical Support's lists (ADR-0061 decision 7).

## Consequences
- AC4, AC8 and AC11 are met for Venue Staff in the web app. AC9 is not, for them, until the
  backend lets them open an event's record; then this list gets its link.
- In mock mode, `vera@connectsphere.test` sees the seven events the booking mock holds requests
  for (`EVR-BOOK0104` to `EVR-BOOK0110`). Five of them share the booking mock's default name,
  "Partner Summit".
- The list's own checks against the backend (its rows' fields, and the message exactly when it
  is empty) run only when the run has a Venue Staff account (`INTEGRATION_VENUE_STAFF_EMAIL`),
  like the decision queue's. The refusals run every time.
- Tests: `VenueBookingEventRequests.test.tsx`, `src/integration/booking.int.test.ts` and
  `e2e/venueStaffEvents.spec.ts`.

## Revisit when
- ~~The backend's record route allows Venue Staff (the product owner's AC9 decision): give the
  section a `pathFor` to the event's read-only record, at a staff address.~~ Done in [ADR-0095](0095-read-only-event-record-for-internal-staff.md):
  each row opens `/staff/events/<reference>`, and `pathFor` is required again.
