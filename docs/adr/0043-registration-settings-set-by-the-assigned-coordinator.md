# ADR-0043: The assigned coordinator enables registration and sets its capacity; the settings live on the event

- **Status:** Accepted
- **Date:** 2026-10-14, updated 2026-10-19 (customer answer A74: capacity is the organiser's number, not limited by the venue)
- **Story:** SCRUM-69 Enable registration for an event and set its capacity

## Context
SCRUM-69's ACs say registration can be enabled or disabled for an event, defaulting to the Organiser's stated requirement on the original request (AC1); that enabling needs a capacity (AC2); that the capacity is the number the Event Organiser decides, recorded by the assigned Event Coordinator, and is not limited by the capacity of the venue or venues booked for the event (AC3); that registration cannot be enabled before the event is Confirmed (AC4); that the capacity can change after registration opens, but not below the number already registered (AC5); that the coordinator can also record an optional withdrawal cut-off (AC6, see [ADR-0086](0086-optional-withdrawal-cut-off.md)); and that a change records who made it and when (AC7). SCRUM-52 and SCRUM-54 both depend on these settings existing.

Several things were left open when this was first written (14 Oct):

1. **Who sets it.** SCRUM-69's story is written for the Event Coordinator, and its open question asked "Event Organiser or Event Coordinator?". SCRUM-54 AC5 said "The Organiser sets the event's registration capacity". The two stories disagreed.
2. **What "defaulting" means.** `registration_required` already records what the organiser asked for at submission (SCRUM-19), but "enabled" can't simply start true: AC2 says an enabled event has a capacity, and no capacity exists until someone sets one.
3. **AC5.** There was no registrations table: SCRUM-52 creates it.
4. **AC3.** It then said the capacity "cannot exceed the capacity of the venue booked for the event", with the several-venue rule an open team decision on SCRUM-54, and the venue module had no service that returned an event's booked venue.
5. **Where the settings live and what a change writes.**

The customer's answer A74 (Week 4) settled 1 and 4: "Registration is totally controlled by the organiser seperate registration process. It can be under capacity or some time over capacity based on the sole discrete of the organiser which is outside of the system." On 19 Oct SCRUM-69 AC3 and AC5 and SCRUM-54 AC5 were rewritten to match.

## Decision
1. **The organiser decides the capacity and the event's assigned Event Coordinator records it** (A74; every change after submission goes through the coordinator, Week 4 A43, Week 9 A11). Everyone else is refused: another coordinator, or an event with no coordinator, gets the same `404` as a reference that doesn't exist (ADR-0019); an organiser, an attendee or any other role gets `403` from the route; no token gets `401`. The rule is held in two places only: the route's `@requires_role(Role.EVENT_COORDINATOR)` and the one `_event_request_assigned_to` call in `update_registration_settings`, the same assigned-coordinator lookup every other coordinator action uses.
2. **The settings are columns on `event_requests`:** `registration_enabled` (not null, false until enabled) and `registration_capacity` (null until set), and since 19 Oct `withdrawal_cut_off` (ADR-0086). The database refuses a capacity under 1 and an enabled event with no capacity, so no code path can store either.
3. **The default is applied when the coordinator doesn't say.** One endpoint, `PATCH /api/events/requests/<reference>/registration`, takes any of `registration_enabled`, `registration_capacity` and `withdrawal_cut_off`. When `registration_enabled` is left out and the event has never had a capacity, it takes the organiser's `registration_required`; once a capacity exists, leaving it out keeps the current value. So an event whose organiser asked for registration is enabled by the first call that gives it a capacity, and an event whose organiser didn't is left disabled with the capacity stored. A coordinator who wants a capacity stored on an event that isn't yet Confirmed sends `registration_enabled: false` with it.
4. **Enabling is refused unless the event is Confirmed (AC4),** with `409 registration_not_enablable`. The rule looks at the settings the call would leave behind, not at what was sent: raising the capacity of an enabled event that has since completed is refused too, while disabling is allowed in any status.
5. **Enabling without a capacity (AC2) is `400`,** with the message on `registration_capacity`. A capacity that isn't a whole number from 1 to 2,147,483,647 (the largest value of the Postgres column, which SQLite doesn't enforce) is also `400` on that field.
6. **The capacity is not checked against any venue (AC3).** A capacity above, below or equal to what the booked venue or venues hold is stored as sent: the organiser decides it outside the system (A74). The Safety Officer still reviews expected attendance against the venue during planning (SCRUM-97, SCRUM-98).
7. **A change is recorded in the event history as `field_changed` entries** (ADR-0025), one per field that actually changed, with the previous and new value, the caller as the actor and one shared `occurred_at`. This is AC7, and it also records enabling and disabling. No new history kind, so no enum migration. A call that changes nothing writes and commits nothing. The route answers `200` with `reference`, `registration_required`, `registration_enabled`, `registration_capacity` and `withdrawal_cut_off`.
8. **Registrations themselves, and the catalogue that lists events "with registration enabled" (ADR-0032), are SCRUM-52's.** It should treat registration as open when `registration_enabled` is true and the event is Confirmed.

## Done by SCRUM-52
- **AC5, capacity not below the number registered:** there was no registrations table until SCRUM-52, which adds the rule to `update_registration_settings` with the table it counts (ADR-0032). A capacity under the number registered is `400` on `registration_capacity`; equal is allowed; it applies whether or not registration is enabled. Otherwise a capacity can change at any time, after registration opens included (AC5 as rewritten on 19 Oct).

## Changed after A74 (19 Oct)
- **AC3 is no longer deferred.** This record used to defer a venue-capacity rule until the venue stack merged, with a `# TODO` in the service. The rule was built on the SCRUM-69 pull request and taken out again when AC3 was rewritten, and the TODO is gone. There is no several-venue rule to agree on SCRUM-54 any more.
- **The role is no longer a default to review:** A74 answered SCRUM-69's open question, and SCRUM-54 AC5 now points here.

## Consequences
- Every AC of SCRUM-69 is met by the backend: AC5 with SCRUM-52, AC6 with ADR-0086.
- A coordinator can record a capacity larger than the booked venue holds. That is the organiser's call (A74); SCRUM-54 polices "the capacity set for the event", not the venue's.
- The migration adds columns to `event_requests`. Existing rows become disabled with no capacity, whatever their `registration_required`, because nothing can have been Confirmed with registration before this story.
- Tests: `tests/events/test_registration_settings*.py`, `test_registration_settings_migration.py` and `test_withdrawal_cut_off_migration.py` (marker `scrum_69`).

## Revisit when
- Nothing outstanding. (SCRUM-52 has merged and added the registered-count rule, AC5.)
