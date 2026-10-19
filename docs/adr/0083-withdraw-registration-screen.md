# ADR-0083: Attendees see each registration's status and withdraw from My events

- **Status:** Accepted; offering Withdraw only under Upcoming, asking to confirm first and
  keeping a withdrawn registration in its half are defaults to review with the Product Owner
- **Date:** 2026-10-19
- **Story:** SCRUM-53 See and withdraw my registration
- **Builds on:** ADR-0032 (*Withdrawing*), ADR-0044

## Context
The backend is on main (#84, ADR-0032): `DELETE /api/events/catalogue/<id>/registrations`
withdraws the caller's place and answers with the registration, now `withdrawn`. After the
cut-off it answers `409 withdrawal_closed` with `details.withdrawal_closed_at`, the moment
withdrawals closed in business time. On main that moment is always the event's start
(ADR-0032). Jira changed on 19 Oct (Product Owner decision): the Organiser may set an optional
cut-off before the event starts, recorded by the coordinator with the registration settings
(SCRUM-53 AC3, SCRUM-69 AC6), and withdrawals close at the start when none is set. The backend
doesn't have that field yet; when it does, the same refusal carries the cut-off as
`withdrawal_closed_at`. The Attendee's own list (`GET /api/events/registrations`, ADR-0044)
already sends each registration's `status` and `withdrawn_at`. The Attendee's "My events" page
(SCRUM-24, SCRUM-52) showed only the event's status. The ACs and the ADRs leave a few things
open for the web app:

1. **Where Withdraw is offered.** The list does not send the cut-off, so the screen cannot tell
   in advance whether a withdrawal will be accepted.
2. **How the refusal shows when withdrawals closed (AC4).** The web app's `ApiError` kept only
   the per-field messages from an error's `details`, so `withdrawal_closed_at` was dropped.
3. **Whether to confirm first.** A withdrawn place goes back to the event's capacity at once
   (AC5), and on a full event someone else may take it before the Attendee changes their mind.
4. **AC7** (the Organiser sees the withdrawal in the registration list). The event page's
   Registrants section (SCRUM-55, ADR-0076) is on main and shows each registrant's status.

## Decision
1. **Each event on My events shows the registration's own status,** "Registered" or
   "Withdrawn", beside the event's status (AC1). A withdrawn registration stays in its half, as
   ADR-0032 decided for the API.
2. **Withdraw is offered on each held registration under Upcoming.** Everything under Past has
   ended, so its start, and with it any cut-off, has passed (AC6); offering a button the
   backend must refuse would only mislead. An Upcoming event may still have started (it is
   listed until it ends), so the backend decides, and its refusal is shown. **Default to review.**
3. **Withdrawing asks first:** "Withdraw from <event>? Your place goes back to the event and
   someone else may take it.", with "Yes, withdraw" and "Keep my place". **Default to review.**
4. **A refusal shows the backend's message and the cut-off,** e.g. "Withdrawals for this event
   have closed." and "The cut-off was 7 Oct, 7:00 pm." (AC4). `ApiError` now also keeps the
   error's `details` as sent, so a screen can read a detail such as `withdrawal_closed_at`
   without branching on the error code.
5. **After a withdrawal, the Attendee's events and every catalogue page are read again,** so the
   status, the places left (AC5) and the Register button come from the backend. Registering
   again from the catalogue reuses the registration (ADR-0032).
6. **AC7 needs nothing more here.** The Registrants section already lists a withdrawn
   registrant as "Withdrawn" (its own tests show one), because the API keeps the row with its
   status (ADR-0032). The registrants mock keeps its own rows, so a withdrawal made on My events
   in mock mode does not appear there; against the backend it does.

## Consequences
- An Attendee can give up a place in two clicks and is told why when it is too late.
- Once the optional cut-off (SCRUM-69 AC6) reaches the backend, Upcoming events past their
  cut-off still offer Withdraw and are refused with the cut-off shown, until the list sends the
  cut-off too. No change is needed here for the refusal itself.

## Revisit when
- The backend gains the optional withdrawal cut-off (SCRUM-69 AC6): if the Attendee's list
  starts sending it, offer Withdraw only before it and show it beside the button.
