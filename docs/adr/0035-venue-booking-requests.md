# ADR-0035: An assigned coordinator raises a Pending venue booking request for an approved event; every Venue Staff user is told

- **Status:** Accepted
- **Date:** 2026-10-11
- **Story:** SCRUM-42 Request a venue booking for an approved event

## Context
SCRUM-42 lets an Event Coordinator raise a venue booking request from an approved event: a venue, a date, a start and end time, a purpose, an expected occupancy and a required layout. The request starts Pending, carries the event's timing and accessibility needs to Venue Staff, tells Venue Staff, and refuses a second Pending request for the same event, venue and period. The ACs leave several points open: who counts as the right Venue Staff, how a duplicate is detected, what an event's "layout" is when events store none, which event statuses qualify, what a non-assigned coordinator sees, and how much of the request's life this story owns.

## Decision
1. **Every Venue Staff user is notified.** The data model does not say which Venue Staff look after which venue, so nobody can be picked out. As in [ADR-0015](0015-in-app-notifications.md), one in-app notification per recipient is written, to all of them, with a new `NotificationKind`. Narrowing it to the staff responsible for the venue needs a story that models responsibility; no ticket exists for that yet.
2. **AC6 is a database rule: a partial unique index over Pending requests only.** `uq_venue_booking_requests_pending` is unique on event, venue and period (start and end) where `status = 'pending'`. Once a request is decided it drops out of the index, so a new request for the same slot is allowed. The service flushes inside a `try` and turns the `IntegrityError` into a `ConflictError` (409). It recognises the duplicate by the index name in Postgres, and by `UNIQUE constraint failed` in SQLite (the unit suite), because that is the only text each database gives. A different integrity error is re-raised, not mislabelled.
3. **The status enum holds only `pending`.** Deciding a request is SCRUM-43, which adds the other values. Postgres can add enum values but not remove them, so we add them when they have code.
4. **Layout and occupancy defaults (AC3).** An event stores free-text `venue_requirements` and an `expected_attendance`, but no layout. Occupancy defaults to `expected_attendance`; the required layout defaults to none. A later story that gives events a layout adds the default with it.
5. **Only an `approved` event accepts a request (AC1).** Any other status is a `409` that names the event's current status.
6. **A coordinator who is not the event's assigned coordinator gets `404`,** the same as an event that does not exist, so event ids are not leaked ([ADR-0019](0019-event-equipment-lines.md)). The check sits in the events service lookup, not in the route.
7. **Justification (AC7).** When the venue is unsuitable for this request's own occupancy and layout (the check from [ADR-0017](0017-suitability-check-takes-requirements.md)), a justification is required, and a blank one counts as missing. A suitable venue needs none.
8. **Audit trail: a user requirement, not an acceptance criterion.** The team asked that raising a request be traceable on the event. `EventHistoryKind.VENUE_BOOKING_REQUESTED` (`venue_booking_requested`) is written through `record_event_history` in the same transaction and commit as the request, so there is never a request without its entry or an entry without its request. Its details are the request id, venue id, and `starts_at` and `ends_at` as ISO strings. Venue Staff are notified in a second commit afterwards; a failure there is logged and does not undo the request.
9. **Events service surface.** The venue module may not import `events.models`, so `events/services.py` gains four additive public items: `get_event_for_coordinator` (assigned coordinator, any status, used to list), `get_approved_event_for_coordinator` (the same, but `approved` only, used to raise), `record_venue_booking_requested`, and the frozen dataclass `EventForBooking` (the event facts the venue module needs: expected attendance, timing, accessibility needs). `events.services` reaches `equipment`, which reaches `venue`, so `venue.services` imports `events.services` inside the functions that use it. This lazy import is deliberate; moving equipment's venue dependency would remove it.
10. **Response shape (AC4).** A request is returned as `BookingRequestAsShown`, a frozen dataclass dumped by the schema: the request's own fields (instants in UTC with the business offset, [ADR-0009](0009-booking-times-in-utc.md)) plus flat `event_proposed_date`, `event_end_date`, `event_start_time` and `event_end_time` as the event stores them in local business time, and `accessibility_needs`. Request instants and event local times sit side by side in one body.
11. **Routes.** `POST /api/venues/events/<event_id>/booking-requests` (201, Event Coordinator) raises one; `GET` on the same path (200) lists the event's requests. Both are coordinator-only.
12. **Frontend.** The page is `/events/:eventId/venue-requests`, reached by URL only: no event screens exist yet to link from. A non-numeric event id shows the not-found page. The form takes a numeric **Venue ID**, because the frontend has no venue catalogue to pick from; a venue picker is a follow-up ticket for the team to raise. Date-times are typed in business time and sent with the `+08:00` offset (`BUSINESS_UTC_OFFSET`).
13. **Deferred acceptance criteria, each with its owner.**
    - The "Needs Alternative Venue" replacement flow (AC8): **SCRUM-92**.
    - Deciding a request (approve, reject): **SCRUM-43**.
    - Overlap detection when a request is approved (two requests for one venue and time): **SCRUM-44**. AC2 here allows overlapping requests for different venues, and the unique index only stops exact duplicates.
    - Per-arrangement refinements: **SCRUM-93**.
    - Narrowing notifications to the Venue Staff responsible for a venue: no ticket yet; it first needs a story that models venue responsibility.

## Consequences
- AC6 holds under concurrent submissions, because the database enforces it, not a read-then-write check.
- Every Venue Staff user is notified of every request, including for venues they do not handle, until responsibility is modelled.
- Duplicate detection reads error text. A database or driver upgrade that changes the wording would turn a duplicate into a `500`; the duplicate test would catch it on SQLite, not on Postgres, which CI does not run.
- Event history views must tolerate the new `venue_booking_requested` kind.
- The events service is a little larger, and the lazy import is less greppable.
- The status enum, the history kind and the notification kind are added in migration `0020`.

## Revisit when
- SCRUM-43 decides requests (add statuses, and revisit what the unique index covers).
- A story models which Venue Staff look after which venue (narrow the notifications).
- Events gain a layout (default the request's layout from it).
- The frontend gets a venue catalogue (replace the Venue ID field with a picker).
- Confirmed events should accept replacement requests (SCRUM-92 may relax the `approved`-only rule).
