# ADR-0109: An Attendee opens an event they registered for at its notification link

- **Status:** Accepted. What the page shows, Withdraw while SCRUM-53 allows it, and Completed and Cancelled events opening read-only are the Product Owner's (SCRUM-24 AC11, 25 Oct). On 26 Oct the Product Owner also decided that the Attendee's list holds every event they have a registration on, whatever its status, withdrawn registrations included (AC7, superseding [ADR-0044](0044-attendee-events-list.md) decision 5), that an event they withdrew from opens read-only, that only approved venues are shown, and that a page whose event was sent back to Approved says its arrangements are being reviewed (AC11). The address is the team's call (Jira's "Attendee view clarification"). The team's own calls, final per the Product Owner's instruction of 26 Oct: offering Withdraw on an event sent back to planning, the 404 for an event the attendee never registered for, which statuses count as "being reviewed", and keeping the Upcoming and Past halves
- **Date:** 2026-10-26 (decisions 11 to 13 added the same day, after the Product Owner's answers)
- **Story:** SCRUM-24 See the events my role is involved in (AC7, AC11); with SCRUM-28 AC1 (links), SCRUM-52 AC1, SCRUM-53
- **Extends:** [ADR-0032](0032-event-catalogue-contract.md) (the catalogue's event), [ADR-0044](0044-attendee-events-list.md) (the Attendee's list), [ADR-0083](0083-withdraw-registration-screen.md) (Withdraw on My events), [ADR-0086](0086-optional-withdrawal-cut-off.md) (the cut-off), [ADR-0015](0015-in-app-notifications.md) (the link)
- **Closes:** "Not built: the Attendee's view of one event" in [ADR-0095](0095-read-only-event-record-for-internal-staff.md)

## Context
SCRUM-24 AC11 was added on 25 Oct: "An Attendee can open a confirmed event they have registered for and sees only its name, description, date, time and each venue's name and location (SCRUM-52), plus their own registration status and the option to withdraw while SCRUM-53 allows it. No internal planning information is shown (SCRUM-21). A Completed or Cancelled event they were registered for still opens, read-only, with its status shown and no option to withdraw. This is the page that the event link in an Attendee's notifications opens (SCRUM-28, SCRUM-62)." The clarification adds that the page address is the team's choice.

Before this change no route answered one event to an Attendee (ADR-0095 "Not built"). "My events" rows carried the event's id but not its reference, and their cards opened nothing. Every notification links to `/events/<reference>` (`EVENT_LINK_TEMPLATE` in `notifications/schemas.py`), and in the web app that address was the assigned coordinator's record, which sends every other role to their own home. The catalogue's own event shape sends `venue: null` until the venue stack fills it (ADR-0032), so it has no location to reuse.

Left open by AC11: the address; whether someone who withdrew still opens the page; what an event that went back to planning after it was confirmed (ADR-0087) shows; which venues count as "each venue".

On 26 Oct the Product Owner reworded two criteria. AC7: "An Attendee sees every event they have a registration on, whatever the event's status (Confirmed, returned to Approved, Completed or Cancelled), including registrations they have withdrawn. Each row shows the event's status and their registration status (SCRUM-53)". AC11 now opens "any event they have a registration on", shows "each approved venue's name and location", says, "when the event is not Confirmed (it has returned to Approved)", that "its arrangements are being reviewed and may change, and that the Attendee will be notified of any change", and opens an event "whose registration they withdrew" read-only. The "Attendee view clarification" explains why: a Confirmed-only list clashed with SCRUM-53 AC1 ("can see each registration with its current status") and would have hidden an event that went back to Approved while its Attendees were still registered.

## Decision
1. **A new route, `GET /api/events/registrations/<reference>`,** for the `attendee` role only, beside the Attendee's list (`/registrations`, ADR-0044). Every other role is `403`, no token is `401`, and the service is not called for either.
2. **Who opens it: an Attendee with a registration for the event,** held or withdrawn. An event they never registered for is `404` "Event not found.", the same as a reference no event has, so whether an event exists can't be told from outside it (ADR-0012). A draft is never found. Someone who withdrew still opens it read-only, so every card on My events opens and a later notice about the event still leads somewhere: the Product Owner's (AC11, 26 Oct).
3. **What it shows, and nothing else.** The catalogue's public fields, now `PublicEventSchema` (id, reference, name, description, start, end), the event's `event_status`, `venues` with each venue's `name` and `location`, the registration's `status`, `registered_at` and `withdrawn_at`, `withdrawals_close_at` (the cut-off, or the start when there is none, ADR-0086), `can_withdraw` and `is_being_reviewed` (decision 12). No capacity, places, notes, coordinator, arrangement statuses or anything else from the record (SCRUM-21).
4. **"Each venue" is each venue Venue Staff approved,** earliest booking first, each venue once (`venue_services.list_booked_venues`). A pending or held arrangement isn't settled yet, and a withdrawn, released or rejected one no longer counts. AC11 now says "each approved venue" (26 Oct). A cancelled event whose bookings were released shows "No venue is booked for this event."
5. **Withdraw is offered while SCRUM-53 allows it.** `can_withdraw` is true while the place is held, the event is still going ahead and it is before `withdrawals_close_at`. "Going ahead" is written out: `confirmed`, and `approved` or `safety_review` for an event a change sent back to planning, whose registrations stay held (ADR-0087). The team's call, since AC11 offers Withdraw "while SCRUM-53 allows it" and the withdrawal route itself accepts these; the page says such an event is being reviewed (decision 12). Every other status opens read-only with its status, Completed and Cancelled among them. The backend decides; the page only shows what it says.
6. **The page's address is the notification link, `/events/<reference>`,** so the link the backend already writes needs no change (SCRUM-28 AC1). In the web app, `AttendeeEventOr` shows an Attendee their page there and gives everyone else what was already at that address: the coordinator's record behind `RequireRole`, so every other role still goes to its own home, and a visitor to the staff login as before.
7. **"My events" opens it.** Each row of `GET /api/events/registrations` now carries the event's `reference` (through `EventHeading`), and each card's name links to the page. Which rows the list holds is decision 11.
8. **Withdraw reuses SCRUM-53's action** (`WithdrawAction`, ADR-0083): the same confirmation, the same refusal with the cut-off. The page says until when withdrawals are open. A withdrawal, refused or not, reads the Attendee's events again (`onSettled`), so after a refusal the page re-reads, loses its button, and still shows the refusal: it reads it from TanStack's record of the withdrawals (`useWithdrawalRefusal`), as the Safety Officer's page keeps its last outcome.
9. **Module boundaries hold.** The registration module finds the event through `events_services.find_public_event(reference)` and the venues through `venue_services.list_booked_venues(event_id)`; it imports neither module's models, and the events module's statuses reach it as plain values.
10. **The mock answers the route as the backend does** (`mocks/handlers/catalogue.ts`), with the same refusals and the same `can_withdraw` and `is_being_reviewed` rules. The catalogue's venues get a location (`MOCK_VENUE_LOCATIONS`), and the events the catalogue no longer lists get a reference, a description and a venue. The mock attendee also holds a place at an event sent back to Approved (Rooftop Film Night, `EVR-MOCK0903`), so the list, the review line and Withdraw on such an event show in `dev:mock`.
11. **The Attendee's list holds every event they have a registration on, whatever its status, withdrawn registrations included** (AC7, 26 Oct). This supersedes ADR-0044 decision 5 (keeping completed and cancelled events was a default; it is now the Product Owner's rule, widened to every status). `GET /api/events/registrations` already lists every registration, so no code changed; tests built from the status enum pin it. Each row already shows the event's status (the status chip) and the registration's ("Registered" or "Withdrawn", ADR-0083). A draft can't hold a registration (registering needs a Confirmed event, and nothing turns one back into a draft), so the list has no rule for one.
    **The Upcoming and Past halves stay** (ADR-0044 decision 2), split by when the event ends, never by its status. They still make sense with every status listed: a Completed event has ended, so it is always under Past; a Cancelled event, or one sent back to Approved, stays under Upcoming until its date passes, so the Attendee sees what happened to it instead of watching it disappear; a withdrawn registration stays in the half its event is in. The team's call.
12. **"Being reviewed" is an event a change sent back to planning: Approved or Safety Review** (AC11, 26 Oct). AC11 says "not Confirmed (it has returned to Approved)"; a Confirmed event that loses its safety approval goes to Approved, and the coordinator then sends it to Safety Review again (ADR-0087), so both are the same review. `is_being_reviewed` is true for those two (`BEING_REVIEWED_EVENT_STATUSES`) and false for every other status: Confirmed is going ahead as planned, Completed and Cancelled are settled, and the other statuses can't hold a registration. The same two statuses, with Confirmed, offer Withdraw (decision 5). The team's call.
13. **The page says it above the date:** "This event's arrangements are being reviewed and may change. You will be notified of any change." The notice itself is SCRUM-62's, which isn't built; the page only says it will come. The venues shown are still only the approved ones, so a venue still being requested never appears (the "Attendee view clarification").

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
  "can_withdraw": true,
  "is_being_reviewed": false
}
```

## Consequences
- SCRUM-24 AC7 and AC11, as reworded on 26 Oct, are met in the backend and the web app, and ADR-0095's last gap for AC9/AC11 closes. An Attendee's notification link opens an event page for them.
- SCRUM-53 AC1 ("can see each registration with its current status") holds on the list, for every registration whatever its event's status.
- Until SCRUM-62 is built, the "You will be notified" line promises a notice nothing sends yet.
- The withdrawal route still accepts a withdrawal from a cancelled event before its start, though the page doesn't offer one. Nothing cancels an event yet (SCRUM-61); when something does, that route should refuse it too.
- The status chip can show an Attendee `Approved` or `Safety review` for an event a change sent back to planning, on this page as already on My events.
- `useWithdrawFromEvent` now reads the events again after a refusal too, on My events as well.
- New backend surface: the README's route table, `tests/registration/test_my_registered_event*.py`, `tests/events/test_public_event.py`, `tests/venue/test_booked_venues.py`; and the frontend's `src/integration/myRegisteredEvent.int.test.ts`, whose registered-event checks need the Lead, Venue Staff and Safety Officer accounts CI makes, and skip without them.

## Revisit when
- SCRUM-61 cancels events, or SCRUM-62 notifies Attendees: their notices link here already, and SCRUM-62 makes the "You will be notified" line true.
- Change requests (SCRUM-56 to SCRUM-58) send a Confirmed event to another status: decide whether it is "being reviewed" too.
- The catalogue's `venue` is filled (ADR-0032): it could reuse `list_booked_venues`.
