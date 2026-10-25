# ADR-0103: Rejecting an event during planning tells every Venue Staff user about each booking or hold it released

- **Status:** Accepted; telling Venue Staff is the Product Owner's answer of 25 Oct (answer 8); telling them only about released bookings and holds, not withdrawn requests (decision 3), and the wording (decision 4) are defaults to review
- **Date:** 2026-10-25
- **Story:** SCRUM-49 Confirm an event once its arrangements are in place (AC10)
- **Extends:** [ADR-0093](0093-reject-an-event-during-planning.md) (its "Still owed": Venue Staff aren't told), [ADR-0015](0015-in-app-notifications.md), [ADR-0094](0094-reassess-each-venue-arrangement-after-a-significant-change.md) decision 7 (every Venue Staff user is told)

## Context
SCRUM-49 AC10 releases an event's venue bookings and holds when the coordinator rejects it during planning (ADR-0093 decision 5). The ACs don't ask for anyone but the organiser to be told, so ADR-0093 listed "Venue Staff aren't told" under Still owed. On 25 Oct the Product Owner answered (answer 8) that Venue Staff should be notified when such a rejection releases one of their approved bookings or holds.

## Decision
1. **Every Venue Staff user is told, once for each booking or hold released,** with a new `venue_booking_released` notification kind (migration 0045). Venue Staff aren't assigned to venues (SCRUM-93), so every one of them hears, as for a Conflicting booking ([ADR-0055](0055-booking-and-equipment-notices.md)) and a significant change (ADR-0094 decision 7). They share one helper, `_tell_venue_staff`. Nobody else is told: the organiser already gets the rejection with its reason (ADR-0093 decision 4), and the coordinator made it.
2. **The notices go out after the rejection commits, and after the organiser's notice** (ADR-0015). `release_event_arrangements` still doesn't commit; it now returns one notice detail for each arrangement it releases, and `reject_event_during_planning` passes them to `tell_venue_staff_of_releases` once the rejection is saved. A notice that can't be saved is rolled back and logged (`venue_booking_notification_failed`); the rejection, the release and the organiser's notice stand.
3. **Default to review: a request that was only withdrawn is not told about.** A Pending, Conflicting, Rejected or Expired request had no booking or hold, so nothing of Venue Staff's was released. It just leaves their queue, as when the coordinator withdraws one, which tells nobody either (SCRUM-93). Answer 8 is about "approved bookings or holds", and nothing in the ACs or ADR-0093 asks for more. An arrangement already withdrawn or released before the rejection isn't touched, so it isn't told about either.
4. **The wording.** The kind's message says why: "A venue booking or hold was released because its event was rejected during planning." The detail names the arrangement, its venue and its period in business time: `Venue arrangement 12 at Main Hall, 2026-11-01 09:00 to 2026-11-01 12:00, was released.` The notice names the event through its own `event_name` and links to it, as every notice does. Keeping the reason in the kind, not the detail, means `release_event_arrangements` still doesn't know why the event stopped (ADR-0093's consequence), so SCRUM-61's cancellation can reuse it and send its own kind.
5. **The mock backend:** the notifications mock serves only seeded notices, so a rejection in `dev:mock` raises none. The integration test reads the real notice as Venue Staff, and checks that the request withdrawn beside it is not mentioned.

## Consequences
- Venue Staff learn the same day that a booking they approved, or a hold they placed, no longer holds its venue, instead of finding it Released on the event's list.
- One rejection can send several notices to each Venue Staff user, one per booking or hold.

## Revisit when
- SCRUM-61 cancels an event: tell Venue Staff the same way, with a kind whose message says the event was cancelled.
- The team decides Venue Staff should also hear about requests withdrawn by a rejection.
