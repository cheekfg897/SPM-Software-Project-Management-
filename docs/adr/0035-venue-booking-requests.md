# ADR-0035: An assigned coordinator raises a Pending venue booking request for an approved event; every Venue Staff user is told

- **Status:** Accepted
- **Date:** 2026-10-11
- **Story:** SCRUM-42 Request a venue booking for an approved event

## Context
SCRUM-42 lets an Event Coordinator raise a venue booking request from an approved event: a venue, a date, a start and end time, a purpose, an expected occupancy and a required layout. The request starts Pending, carries the event's timing and accessibility needs to Venue Staff, tells Venue Staff, and refuses a second Pending request for the same event, venue and period. The ACs leave several points open: who counts as the right Venue Staff, how a duplicate is detected, what an event's "layout" is when events store none, which event statuses qualify, what a non-assigned coordinator sees, and how much of the request's life this story owns.

## Decision
1. **Every Venue Staff user is notified.** The data model does not say which Venue Staff look after which venue, so nobody can be picked out. As in [ADR-0015](0015-in-app-notifications.md), one in-app notification per recipient is written, to all of them, with a new `NotificationKind`. **Settled on 2026-10-13:** the product owner confirmed that Venue Staff are not assigned to particular venues, and removed the "responsible for" wording from SCRUM-42, SCRUM-24, SCRUM-43, SCRUM-50, SCRUM-84 and SCRUM-93. Notifying every Venue Staff user is now the specified behaviour, not a stopgap, and no story is needed.
2. **AC6 is a database rule: a partial unique index over Pending requests only.** `uq_venue_booking_requests_pending` is unique on event, venue and period (start and end) where `status = 'pending'`. Once a request is decided it drops out of the index, so a new request for the same slot is allowed. The service flushes inside a `try` and turns the `IntegrityError` into a `ConflictError` (409). It recognises the duplicate by the index name in Postgres, and by `UNIQUE constraint failed` in SQLite (the unit suite), because that is the only text each database gives. A different integrity error is re-raised, not mislabelled.
3. **The status enum holds only `pending`.** Deciding a request is SCRUM-43, which adds the other values. Postgres can add enum values but not remove them, so we add them when they have code.
4. **Layout and occupancy defaults (AC3).** An event stores free-text `venue_requirements` and an `expected_attendance`, but no layout. Occupancy defaults to `expected_attendance`; the required layout defaults to none. A later story that gives events a layout adds the default with it.
5. **Only an `approved` event accepts a request (AC1).** Any other status is a `409` that names the event's current status.
6. **A coordinator who is not the event's assigned coordinator gets `404`,** the same as an event that does not exist, so event references are not probed ([ADR-0019](0019-event-equipment-lines.md)). The check sits in the events service lookup, not in the route, and listing an event's requests as another coordinator is a `404` too.
7. **Justification (AC7).** When the venue is unsuitable for this request's own occupancy and layout (the check from [ADR-0017](0017-suitability-check-takes-requirements.md)), a justification is required, and a blank one counts as missing. A suitable venue needs none.
8. **Audit trail: a user requirement, not an acceptance criterion.** The team asked that raising a request be traceable on the event. `EventHistoryKind.VENUE_BOOKING_REQUESTED` (`venue_booking_requested`) is written through `record_event_history` in the same transaction and commit as the request, so there is never a request without its entry or an entry without its request. Its details are the request id, venue id, and `starts_at` and `ends_at` as ISO strings. Venue Staff are notified in a second commit afterwards; a failure there is logged and does not undo the request.
9. **Events service surface.** The venue module may not import `events.models`, so `events/services.py` gains four additive public items: `get_event_for_coordinator(reference, coordinator_id)` (assigned coordinator, any status, used to list), `get_approved_event_for_coordinator(reference, coordinator_id)` (the same, but `approved` only, used to raise). Both look the event up by reference with the events module's existing assigned-coordinator lookup, `record_venue_booking_requested`, and the frozen dataclass `EventForBooking` (the event facts the venue module needs: its internal `id`, which the request is stored against, expected attendance, timing, accessibility needs). `events.services` reaches `equipment`, which reaches `venue`, so `venue.services` imports `events.services` inside the functions that use it. This lazy import is deliberate; moving equipment's venue dependency would remove it.
10. **Response shape (AC4).** A request is returned as `BookingRequestAsShown`, a frozen dataclass dumped by the schema: the request's own fields (instants in UTC with the business offset, [ADR-0009](0009-booking-times-in-utc.md)) plus flat `event_proposed_date`, `event_end_date`, `event_start_time` and `event_end_time` as the event stores them in local business time, and `accessibility_needs`. Request instants and event local times sit side by side in one body.
11. **Routes, keyed by reference.** `POST /api/venues/events/<reference>/booking-requests` (201, Event Coordinator) raises one; `GET` on the same path (200) lists the event's requests. Both are coordinator-only. The event is addressed by its `EVR-…` reference, as every other staff and organiser route is, because [ADR-0004](0004-event-request-reference-format.md) makes the reference the public identifier and the integer `id` internal; the case and surrounding spaces of the reference are ignored. **This supersedes this ADR's earlier decision to address the event by its integer id.** `raise_booking_request` and `list_booking_requests_for_event` take the reference; `venue_booking_requests.event_id` stays an integer foreign key, so there is no schema or migration change, and responses still carry the numeric `event_id`.
12. **Frontend.** The page is `/events/:reference/venue-requests`, reached by URL only: no event screens exist yet to link from. A value that is not shaped like a reference (`EVR-` and 8 letters or digits, any case) shows the not-found page without asking the backend; the page checks the shape only, not the look-alike-free alphabet, so mock references stay valid. The form takes a numeric **Venue ID**, because the frontend has no venue catalogue to pick from; a venue picker is a follow-up ticket for the team to raise. Date-times are typed in business time and sent with the `+08:00` offset (`BUSINESS_UTC_OFFSET`).
13. **Deferred acceptance criteria, each with its owner.**
    - The "Needs Alternative Venue" replacement flow (AC8): **SCRUM-92**.
    - Deciding a request (approve, reject): **SCRUM-43**.
    - Overlap detection when a request is approved (two requests for one venue and time): **SCRUM-44**. AC2 here allows overlapping requests for different venues, and the unique index only stops exact duplicates.
    - Per-arrangement refinements: **SCRUM-93**.
    - Venue Staff reading requests: both routes are coordinator-only, so Venue Staff are told by notification (decision 1) but have no page or API to open the request from. We leave this to **SCRUM-43** (deciding a request), where Venue Staff must open requests anyway. SCRUM-43's scope could not be verified (Jira was unreachable when this was written); if it does not cover a staff read route, one must be added.

14. **Operating hours gate the request (AC2, added to the ticket on 2026-10-13).** A request
    whose period is not wholly inside the venue's weekly opening hours is refused with a `400`;
    hours are agreed outside the system, so there is no in-system way to ask for different ones
    and nothing for Venue Staff to decide. Four points the AC leaves open:
    - **The arithmetic lives in `opening_hours.py`**, whose docstring already reserved the weekly
      timeline for "later venue-availability work". `covers_period(periods, start, end)` joins the
      venue's periods into continuous openings and asks whether the request fits inside one. The
      piece-building `find_overlap` already did is extracted to `_week_pieces` and shared, so the
      two never disagree about where a period sits in the week. Two periods that touch (09:00-12:00
      then 12:00-18:00) are one opening; a gap between them is not. The week is laid end to end
      twice, so a request from Sunday into Monday is one range rather than two.
    - **Hours are compared in business time.** Request instants are stored UTC ([ADR-0009](0009-booking-times-in-utc.md)),
      but opening hours are a weekday plus a clock time, so both ends are put back through
      `to_business_time` before they are placed on the week ([ADR-0008](0008-venue-opening-hours.md)).
    - **A venue with no opening period is closed all week,** which is what `Venue.opening_periods`
      already means ("a day with no period is a closed day"). It cannot arise through the API,
      because `EditVenueSchema.opening_hours` defaults to every day 09:00-18:00, so this only
      affects rows written directly. The test fixture `make_venue` now applies that same default
      instead of no hours at all, so a fixture venue behaves like a real one; a test that wants a
      closed venue passes `opening_periods=[]`.
    - **The refusal names the hours on the day the request starts,** reported on `starts_at`
      ("The venue is open 09:00-18:00 on Sunday", or "closed on Sunday"), listing every period on
      that day so a venue that shuts for lunch explains itself. The start day is the one the AC
      points at ("its operating hours on that day"); a request that legitimately runs past midnight
      into the next day's hours is accepted by `covers_period`, so the day is only ever reported
      when the request is refused. The check runs **before** AC7's justification check, because a
      justification cannot rescue a request outside the hours.

15. **Defaults to review (not agreed with the team).** The ACs do not settle these, so the code accepts them rather than guessing a rule: a request for a period in the past, a request outside the event's own dates, and a request against a deactivated venue are all saved. "Same period" in AC6 means an exact match of start and end; a request that merely overlaps another for the same venue is allowed (overlap is SCRUM-44).

## Consequences
- AC6 holds under concurrent submissions, because the database enforces it, not a read-then-write check.
- Every Venue Staff user is notified of every request, which is what the customer wants: staff are not assigned to venues.
- A venue whose hours were written straight to the database, bypassing the schema default, accepts no requests at all until hours are set.
- Duplicate detection reads error text. A database or driver upgrade that changes the wording would turn a duplicate into a `500`; the duplicate test would catch it on SQLite, not on Postgres, which CI does not run.
- Event history views must tolerate the new `venue_booking_requested` kind.
- The events service is a little larger, and the lazy import is less greppable.
- The notify, roll back and log block in `_notify_venue_staff` is a near copy of one in the events module. Extracting it into `notifications.services` is a known follow-up, left out here because it edits events code other branches touch.
- The status enum, the history kind and the notification kind are added in migration `0020`.

## Revisit when
- SCRUM-43 decides requests (add statuses, and revisit what the unique index covers).
- Events gain a layout (default the request's layout from it).
- The frontend gets a venue catalogue (replace the Venue ID field with a picker).
- The team decides whether past, out-of-event-dates or deactivated-venue requests should be refused (decision 15).
- A venue needs different hours for one event (today AC2 has no exception, by the customer's instruction).
- Confirmed events should accept replacement requests (SCRUM-92 may relax the `approved`-only rule).
