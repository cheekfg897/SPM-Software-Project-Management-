# ADR-0085: Venue Staff's event list is every event with an active venue arrangement, one list for all of them

- **Status:** Accepted; leaving out events whose only request was withdrawn or released, and having no detail view to open from the list yet, are defaults to review
- **Date:** 2026-10-19
- **Story:** SCRUM-24 See the events my role is involved in
- **Builds:** the Venue Staff list that [ADR-0026](0026-role-event-lists.md) (its AC3, now AC4) and [ADR-0034](0034-coordinators-see-only-their-own-events.md) left blocked on SCRUM-42

## Context
SCRUM-24 AC4 says: "Venue Staff see events that have a booking request or a booking". ADR-0026 and ADR-0034 deferred it for two reasons. There were no booking requests or bookings yet (SCRUM-42, SCRUM-43), and Venue Staff were meant to see only "their" venues, which nothing modelled. Both reasons have gone:

- SCRUM-42 and SCRUM-43 have merged.
- On 13 Oct the product owner confirmed that Venue Staff are not assigned to particular venues, and removed "responsible for" from SCRUM-24 ([ADR-0035](0035-venue-booking-requests.md) decision 1).

The AC leaves open which requests count. A venue booking request can be in eight statuses, and two of them, `withdrawn` and `released`, mean the request no longer belongs to the event's arrangements (ADR-0039, ADR-0053).

## Decision
1. **`GET /api/events/requests/with-venue-bookings`, for `venue_staff` only,** in the same shape as Technical Support's `/with-equipment` (ADR-0026 decisions 1, 6 and 7):
   - each row carries `EVENT_LIST_FIELDS`: the event's reference, name, date, times and status;
   - the list is under `event_requests`, newest first;
   - an empty list adds `"message": "No events have a venue booking request yet."`.

   Every other role gets `403`, and no token gets `401`.
2. **One list for all Venue Staff.** They aren't assigned to venues (ADR-0035 decision 1), so the list doesn't depend on who asks.
3. **An event is listed while it has an active arrangement.** That means a request in any status but `withdrawn` and `released`, the venue module's own definition (`_is_active`, ADR-0039 decision 3). So the list includes:
   - a Pending, On Hold or Conflicting request, which Venue Staff still have to decide;
   - an Approved one, which is a booking;
   - a Rejected or Expired one, which stays one of the event's arrangements until the coordinator withdraws it.

   The event's own status or date doesn't matter, as for Technical Support's list, except that a draft is never listed (ADR-0024: every staff list applies `_not_a_draft()`). Only an approved event can be given an arrangement, so a draft never has one today; the guard keeps it that way.
4. **An event whose only requests were withdrawn or released is not listed.** This is the same reading as ADR-0084 takes for SCRUM-31 AC7's decision lock (in the SCRUM-31 pull request). A removed equipment request takes its event off Technical Support's list, and a withdrawn arrangement is the venue module's way of removing one. *Default to review:* a withdrawn request is still a row in the table, so "has a booking request" could be read to include it.
5. **"Or a booking" is covered by the arrangements.** Only approving an arrangement makes a `Booking` (SCRUM-43), and an approved arrangement is active, so every event with a booking is already listed. The `bookings` table isn't queried. A booking's own `event_id` is a bare integer that can be `null` (ADR-0055), and querying both tables would only repeat the answer.
6. **The venue module answers, the events module lists.** `venue_services.list_event_ids_with_active_arrangements()` returns the ids, and `list_event_requests_with_venue_bookings` lists those events with the shared newest-first query. The events module never reads the venue module's models. Venue Staff's queue of requests still to decide stays SCRUM-43's `GET /api/venues/booking-requests`. This list answers a different question: every event they are involved in, not their next piece of work (as ADR-0026 decision 4 says of Technical Support's two lists).

## Consequences
- AC4 is met. AC9 ("opening an event from the list shows the event detail view containing only the sections that role may see") is not, for Venue Staff: `GET /api/events/requests/<reference>` is for organisers and coordinators only, and the only event route Venue Staff can open is its history. A Venue Staff detail view needs its own ticket, with the team deciding which sections they see.
- Staff home shows this list to Venue Staff since ADR-0090. The mock backend answers it, and its integration tests check the refusals against the real backend. The list itself is checked against the backend only when the run has a Venue Staff account (`INTEGRATION_VENUE_STAFF_EMAIL`), like the decision queue.
- No migration: `venue_booking_requests.event_id` is already indexed (SCRUM-42).
- Tests: `tests/events/test_events_by_role.py` and `test_events_by_role_routes.py` (marker `scrum_24`).

## Revisit when
- The team reads "has a booking request" as including withdrawn and released ones.
- Venue Staff get a detail view of an event (SCRUM-24 AC9).
- Venue Staff are ever assigned to venues: filter the list by those venues.
