# ADR-0109: An Attendee opens an event they registered for at its notification link

- **Status:** Accepted. What the page shows, Withdraw while SCRUM-53 allows it, and Completed and Cancelled events opening read-only are the Product Owner's (SCRUM-24 AC11, 25 Oct); the address is the team's call (Jira's "Attendee view clarification"). Offering Withdraw on an event sent back to planning, opening the page after a withdrawal, listing only approved venues and the 404 for an event the attendee never registered for are defaults to review
- **Date:** 2026-10-26
- **Story:** SCRUM-24 See the events my role is involved in (AC7, AC11); with SCRUM-28 AC1 (links), SCRUM-52 AC1, SCRUM-53
- **Extends:** [ADR-0032](0032-event-catalogue-contract.md) (the catalogue's event), [ADR-0044](0044-attendee-events-list.md) (the Attendee's list), [ADR-0083](0083-withdraw-registration-screen.md) (Withdraw on My events), [ADR-0086](0086-optional-withdrawal-cut-off.md) (the cut-off), [ADR-0015](0015-in-app-notifications.md) (the link)
- **Closes:** "Not built: the Attendee's view of one event" in [ADR-0095](0095-read-only-event-record-for-internal-staff.md)

## Context
SCRUM-24 AC11 was added on 25 Oct: "An Attendee can open a confirmed event they have registered for and sees only its name, description, date, time and each venue's name and location (SCRUM-52), plus their own registration status and the option to withdraw while SCRUM-53 allows it. No internal planning information is shown (SCRUM-21). A Completed or Cancelled event they were registered for still opens, read-only, with its status shown and no option to withdraw. This is the page that the event link in an Attendee's notifications opens (SCRUM-28, SCRUM-62)." The clarification adds that the page address is the team's choice.

Before this change no route answered one event to an Attendee (ADR-0095 "Not built"). "My events" rows carried the event's id but not its reference, and their cards opened nothing. Every notification links to `/events/<reference>` (`EVENT_LINK_TEMPLATE` in `notifications/schemas.py`), and in the web app that address was the assigned coordinator's record, which sends every other role to their own home. The catalogue's own event shape sends `venue: null` until the venue stack fills it (ADR-0032), so it has no location to reuse.

Left open by AC11: the address; whether someone who withdrew still opens the page; what an event that went back to planning after it was confirmed (ADR-0087) shows; which venues count as "each venue".

## Decision
1. **A new route, `GET /api/events/registrations/<reference>`,** for the `attendee` role only, beside the Attendee's list (`/registrations`, ADR-0044). Every other role is `403`, no token is `401`, and the service is not called for either.
2. **Who opens it: an Attendee with a registration for the event,** held or withdrawn. An event they never registered for is `404` "Event not found.", the same as a reference no event has, so whether an event exists can't be told from outside it (ADR-0012). A draft is never found. *Default to review:* someone who withdrew still opens it read-only, so every card on My events opens and a later notice about the event still leads somewhere.
3. **What it shows, and nothing else.** The catalogue's public fields, now `PublicEventSchema` (id, reference, name, description, start, end), the event's `event_status`, `venues` with each venue's `name` and `location`, the registration's `status`, `registered_at` and `withdrawn_at`, `withdrawals_close_at` (the cut-off, or the start when there is none, ADR-0086) and `can_withdraw`. No capacity, places, notes, coordinator, arrangement statuses or anything else from the record (SCRUM-21).
4. **"Each venue" is each venue Venue Staff approved,** earliest booking first, each venue once (`venue_services.list_booked_venues`). A pending or held arrangement isn't settled yet, and a withdrawn, released or rejected one no longer counts. *Default to review.* A cancelled event whose bookings were released shows "No venue is booked for this event."
5. **Withdraw is offered while SCRUM-53 allows it.** `can_withdraw` is true while the place is held, the event is still going ahead and it is before `withdrawals_close_at`. "Going ahead" is written out: `confirmed`, and `approved` or `safety_review` for an event a change sent back to planning, whose registrations stay held (ADR-0087). *Default to review*, since AC11 speaks only of confirmed events, and the withdrawal route itself accepts these. Every other status opens read-only with its status, Completed and Cancelled among them. The backend decides; the page only shows what it says.
6. **The page's address is the notification link, `/events/<reference>`,** so the link the backend already writes needs no change (SCRUM-28 AC1). In the web app, `AttendeeEventOr` shows an Attendee their page there and gives everyone else what was already at that address: the coordinator's record behind `RequireRole`, so every other role still goes to its own home, and a visitor to the staff login as before.
7. **"My events" opens it.** Each row of `GET /api/events/registrations` now carries the event's `reference` (through `EventHeading`), and each card's name links to the page. The list itself is unchanged: it still keeps completed and cancelled events (ADR-0044 decision 5); AC11's Completed and Cancelled pages open from the list as well as from a link.
8. **Withdraw reuses SCRUM-53's action** (`WithdrawAction`, ADR-0083): the same confirmation, the same refusal with the cut-off. The page says until when withdrawals are open. A withdrawal, refused or not, reads the Attendee's events again (`onSettled`), so after a refusal the page re-reads, loses its button, and still shows the refusal: it reads it from TanStack's record of the withdrawals (`useWithdrawalRefusal`), as the Safety Officer's page keeps its last outcome.
9. **Module boundaries hold.** The registration module finds the event through `events_services.find_public_event(reference)` and the venues through `venue_services.list_booked_venues(event_id)`; it imports neither module's models, and the events module's statuses reach it as plain values.
10. **The mock answers the route as the backend does** (`mocks/handlers/catalogue.ts`), with the same refusals and the same `can_withdraw` rule. The catalogue's venues get a location (`MOCK_VENUE_LOCATIONS`), and the two events the catalogue no longer lists get a reference, a description and a venue.

`200` body:

```json
{
  "id": 41,
  "reference": "EVR-7K2M9Q4A",
  "name": "Jazz by the Bay",
  "description": "An evening of music.",
  "starts_at": "2026-10-20T19:30:00+08:00",
  "ends_at": "2026-10-20T22:00:00+08:00",
  "event_status": "confirmed",
  "venues": [{ "name": "Main Hall", "location": "Building A, Level 1" }],
  "status": "registered",
  "registered_at": "2026-10-14T12:00:00+08:00",
  "withdrawn_at": null,
  "withdrawals_close_at": "2026-10-19T19:30:00+08:00",
  "can_withdraw": true
}
```

## Consequences
- SCRUM-24 AC11 is met in the backend and the web app, and ADR-0095's last gap for AC9/AC11 closes. An Attendee's notification link opens an event page for them.
- The withdrawal route still accepts a withdrawal from a cancelled event before its start, though the page doesn't offer one. Nothing cancels an event yet (SCRUM-61); when something does, that route should refuse it too.
- The status chip can show an Attendee `Approved` or `Safety review` for an event a change sent back to planning, on this page as already on My events.
- `useWithdrawFromEvent` now reads the events again after a refusal too, on My events as well.
- New backend surface: the README's route table, `tests/registration/test_my_registered_event*.py`, `tests/events/test_public_event.py`, `tests/venue/test_booked_venues.py`; and the frontend's `src/integration/myRegisteredEvent.int.test.ts`, whose registered-event checks need the Lead, Venue Staff and Safety Officer accounts CI makes, and skip without them.

## Revisit when
- The Product Owner answers decision 2, 4 or 5.
- SCRUM-61 cancels events, or SCRUM-62 notifies Attendees: their notices link here already.
- The catalogue's `venue` is filled (ADR-0032): it could reuse `list_booked_venues`.
