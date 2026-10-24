# ADR-0049: Venue Staff record a preparation status and notes on an approved booking

- **Status:** Accepted (defaults to review); decision 7 is extended by [ADR-0095](0095-read-only-event-record-for-internal-staff.md), whose read-only record shows other internal users the preparation details
- **Date:** 2026-10-17
- **Stories:** SCRUM-84 Update venue preparation details

## Context
SCRUM-84 lets a Venue Staff member record "preparation notes and a preparation status against a venue booking" (AC1), visible to the assigned coordinator and other internal users (AC2), changing nothing else of the event (AC3), with the user and time of each update (AC4), and only once the Safety Officer has approved the event (AC5, ADR-0047 decision 18). The ACs do not say what the statuses are, what "a venue booking" is in the data, or how an update treats the notes already there.

## Decision
1. **The booking is the approved venue booking request.** Approving a request makes a confirmed `Booking`, but the request is what carries the event, the venue and the decision, and what the coordinator already lists. The details live on the request: `preparation_status` and `preparation_notes`. A request that is pending, rejected or withdrawn is `409` with `PREPARATION_NOT_APPROVED_MESSAGE`.
2. **Three statuses: `not_started` (every booking begins here), `in_progress` and `ready`.** The ACs name none; these are the smallest set that tells a coordinator "the room is ready".
3. **Any Venue Staff member, on any booking** (ADR-0035 decision 1: staff are not assigned to venues, and the product owner removed "responsible for" from this story). Other roles get `403` from the role check.
4. **`PUT /api/venues/booking-requests/<id>/preparation`, body `status` (required) and `notes` (optional).** Each update states the whole picture: notes left out are cleared. A field other than these two is a `400`, which is how AC3 holds: the route has no way to change the purpose, venue or period. Notes that are sent must not be blank, are trimmed, and are at most 1000 characters (the column is `Text`, so this is an API rule, as for a block's reason).
5. **The gate is `events.services.has_safety_approval`** (AC5). Without it the update is `409` with `PREPARATION_NEEDS_SAFETY_APPROVAL_MESSAGE` and nothing is saved.
6. **Each update is a `venue_preparation_updated` history entry** (AC4): the Venue Staff user as actor, the time, and `details` of `venue_booking_request_id`, `venue_id`, `status` and `notes`, saved in the same commit as the details. The history, not a column on the request, is the record of who and when, as for a decision (ADR-0042). It is internal-only, like the equipment outcome (ADR-0040), so the organiser does not see it.
7. **Who can read it** (AC2). The assigned coordinator reads `preparation_status` and `preparation_notes` on the booking requests of their event. Every internal role reads the history entry through the event history route, which is open to all of them (ADR-0047 decision 1). There is no separate read route for other internal users.
8. **Migration `0033_add_venue_preparation`** adds the two columns (existing rows start `not_started`), the `venue_preparation_status` enum and the history kind, outside the transaction. Downgrade is lossy: the entries of the new kind are deleted.

**Defaults to review (not agreed with the team):** decisions 2 (the status names), 4 (an update replaces the notes) and 7 (no read route beyond the coordinator's list and the history).

## Still owed
- **Frontend:** a Venue Staff form for the details, and the coordinator's view of them.
- **Other internal users' view of the details:** if they need more than the history entry, a read route on the approved bookings is a new ticket.
- **SCRUM-85** does the same for equipment reservations in the equipment module, with its own enum and history kind.

## Revisit when
- The team settles decisions 2, 4 or 7.
