# ADR-0043: The assigned coordinator enables registration and sets its capacity; the settings live on the event

- **Status:** Accepted; the role decision is a default to review with the Product Owner
- **Date:** 2026-10-14
- **Story:** SCRUM-69 Enable registration for an event and set its capacity

## Context
SCRUM-69's ACs say registration can be enabled or disabled for an event, defaulting to the Organiser's stated requirement on the original request (AC1); that enabling needs a capacity (AC2); that the capacity cannot exceed the booked venue's (AC3); that registration cannot be enabled before the event is Confirmed (AC4); that the capacity cannot drop below the number already registered (AC5); and that a capacity change records who made it and when (AC6). SCRUM-52 and SCRUM-54 both depend on these settings existing.

Several things are left open:

1. **Who sets it.** SCRUM-69's story is written for the Event Coordinator, and its open question asks "Event Organiser or Event Coordinator?". SCRUM-54 AC5 says "The Organiser sets the event's registration capacity". The two stories disagree.
2. **What "defaulting" means.** `registration_required` already records what the organiser asked for at submission (SCRUM-19), but "enabled" can't simply start true: AC2 says an enabled event has a capacity, and no capacity exists until someone sets one.
3. **AC5.** There is no registrations table: SCRUM-52 creates it.
4. **AC3.** The venue module's `bookings` table has a bare `event_id`, but on `main` its public services (`app/modules/venue/services.py`) have no function that returns the venue booked for an event. Booking requests and decisions (SCRUM-42, SCRUM-43) are in the open stack of pull requests, not on `main`. The multi-venue rule is still an open team decision on SCRUM-54.
5. **Where the settings live and what a change writes.**

## Decision
1. **The event's assigned Event Coordinator sets registration and capacity,** following SCRUM-69. SCRUM-54 AC5 names the Organiser; that conflict is raised with the Product Owner (see *Revisit when*). Everyone else is refused: another coordinator, or an event with no coordinator, gets the same `404` as a reference that doesn't exist (ADR-0019); an organiser, an attendee or any other role gets `403` from the route; no token gets `401`. The decision is held in two places only, so changing it later touches nothing else: the route's `@requires_role(Role.EVENT_COORDINATOR)` and the one `_event_request_assigned_to` call in `update_registration_settings`, the same assigned-coordinator lookup every other coordinator action uses.
2. **The settings are two columns on `event_requests`:** `registration_enabled` (not null, false until enabled) and `registration_capacity` (null until set). The database refuses a capacity under 1 and an enabled event with no capacity, so no code path can store either.
3. **The default is applied when the coordinator doesn't say.** One endpoint, `PATCH /api/events/requests/<reference>/registration`, takes `registration_enabled`, `registration_capacity`, or both. When `registration_enabled` is left out and the event has never had a capacity, it takes the organiser's `registration_required`; once a capacity exists, leaving it out keeps the current value. So an event whose organiser asked for registration is enabled by the first call that gives it a capacity, and an event whose organiser didn't is left disabled with the capacity stored. A coordinator who wants a capacity stored on an event that isn't yet Confirmed sends `registration_enabled: false` with it.
4. **Enabling is refused unless the event is Confirmed (AC4),** with `409 registration_not_enablable`. The rule looks at the settings the call would leave behind, not at what was sent: raising the capacity of an enabled event that has since completed is refused too, while disabling is allowed in any status.
5. **Enabling without a capacity (AC2) is `400`,** with the message on `registration_capacity`. A capacity that isn't a whole number from 1 to 2,147,483,647 (the largest value of the Postgres column, which SQLite doesn't enforce) is also `400` on that field.
6. **A change is recorded in the event history as `field_changed` entries** (ADR-0025), one per field that actually changed, with the previous and new value, the caller as the actor and one shared `occurred_at`. This is AC6, and it also records enabling and disabling. No new history kind, so no enum migration. A call that changes nothing writes and commits nothing. The route answers `200` with `reference`, `registration_required`, `registration_enabled` and `registration_capacity`.
7. **Registrations themselves, and the catalogue that lists events "with registration enabled" (ADR-0032), are SCRUM-52's.** It should treat registration as open when `registration_enabled` is true and the event is Confirmed.

## Deferred
- **AC5, capacity not below the number registered:** there is no registrations table until SCRUM-52. No placeholder check or column is added now; SCRUM-52 adds the rule to `update_registration_settings` with the table it counts.
- **AC3, capacity not above the booked venue's:** `main` has no way to find an event's booked venue through the venue module's public services, and the events module must not read the venue module's models (module boundary). Booking requests and decisions (SCRUM-42, SCRUM-43) are in the open stack of pull requests. When they merge, `update_registration_settings` gains one call to a venue service and one rule, following whatever the team decides on SCRUM-54 for several venues. A `# TODO` in the service marks the place.

## Consequences
- AC3 and AC5 of SCRUM-69 are not met by this change (see *Deferred*), so the story is not Done when this merges. They are listed under *Tickets to open* on the pull request.
- Until AC3 lands, a coordinator can set a capacity larger than the venue holds. SCRUM-54's "never admit more attendees than the booked venue can hold" is not guaranteed yet.
- The migration adds columns to `event_requests`. Existing rows become disabled with no capacity, whatever their `registration_required`, because nothing can have been Confirmed with registration before this story.
- If the Product Owner rules for the Organiser, the change is the route's role and the service's one lookup, which becomes the organisation-scoped lookup an organiser needs (ADR-0020).
- Tests: `tests/events/test_registration_settings*.py` and `test_registration_settings_migration.py` (marker `scrum_69`).

## Revisit when
- The Product Owner answers SCRUM-69's open question and SCRUM-54 AC5's wording: who sets registration capacity, whether it may be lower than the venue's, and whether it may change after registration opens.
- SCRUM-42 and SCRUM-43 merge: add the venue-capacity rule (AC3), after the team settles several venues on SCRUM-54.
- SCRUM-52 merges: add the registered-count rule (AC5).
