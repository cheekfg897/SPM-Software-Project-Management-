# ADR-0069: The coordinator changes, withdraws or cancels venue arrangements from the event's Venue requests page, and the backend decides which it allows

- **Status:** Accepted; the choices in decision 7 are defaults to review with the team; the AC10 event-status refusal this waited for, withdrawing a held arrangement and cancel-all for approved bookings landed with [ADR-0118](0118-withdraw-a-held-arrangement-and-change-arrangements-only-while-planning.md), with the mock and contract tests; decision 4's cancel-all confirmation is now a form asking for a reason, its button "Cancel them all" (ADR-0118 decision 15)
- **Date:** 2026-10-17
- **Story:** SCRUM-93 Book several venues for one event (AC6, AC8, AC9, AC10)
- **Extends:** ADR-0039, ADR-0042

## Context
The backend has had three SCRUM-93 routes since ADR-0039: change a pending arrangement
(`PATCH /api/venues/events/<reference>/booking-requests/<id>`), withdraw one
(`POST .../<id>/withdraw`) and cancel all of an event's (`POST .../booking-requests/cancel-all`).
The web app's Venue requests page (`/events/<reference>/venue-requests`, SCRUM-42) listed an
event's requests and raised new ones, but offered none of the three, so AC6 ("changing,
withdrawing or cancelling one arrangement leaves the event's other arrangements untouched,
unless the coordinator explicitly chooses to cancel all of them") could only be done through the
API.

The ACs say what the coordinator may do, not how the screen offers it: which arrangements show
which buttons, what a change sends, whether cancelling all asks first, and what the page does
about AC10's event-status rule.

## Decision
1. **The actions sit on the page that already lists the arrangements.** Each arrangement in the
   list gets **Change** and **Withdraw**, and the list ends with **Cancel all venue requests**.
   No new route or page.
2. **The backend decides which action an arrangement allows.** The page offers Change and
   Withdraw on every arrangement that is not retired, and shows the backend's refusal under the
   arrangement it was about (for example "Only a pending arrangement can be changed; this one is
   approved."). It does not copy the backend's status rules (`WITHDRAWABLE_REQUEST_STATUSES`, the
   pending-only change), so a rule the backend changes is not left behind in the browser. A
   retired arrangement (withdrawn, or released when an approved replacement took over it,
   SCRUM-92) is listed with its status and no actions. One flagged "Needs Alternative Venue"
   (SCRUM-92) says so under its details; its reason and a way to raise its replacement are left
   to a SCRUM-92 screen.
3. **A change sends what the form holds.** The form opens with the arrangement's purpose,
   occupancy, layout and justification, and sends the purpose and the layout every time (an empty
   layout as `null`, which clears it, ADR-0039 §9). An empty occupancy or justification is left
   out, so the backend keeps what it has; the justification cannot be cleared, as on the backend.
   The backend works out what actually changed (ADR-0039 §10), so the page does not compare
   values itself.
4. **The venue and the period are not in the change form** (AC9). To move either, the
   coordinator withdraws the arrangement and raises another with the form below the list.
5. **Cancel all asks first.** It touches every venue at once, so the button opens a short
   confirmation ("Withdraw them all" or "Keep them"). Withdrawing one arrangement does not ask:
   it affects only that one, and the same slot can be raised again.
6. **After each action the event's list is read again** (`bookingKeys.forEvent`), never patched
   by hand, as raising a request already did. The four mutations share one helper for it.
7. **Defaults to review (not agreed with the team).**
   - Change and Withdraw are offered on approved arrangements too, and the backend refuses them,
     rather than the page hiding them. Hiding them would mean copying the backend's rule.
   - Withdrawing one arrangement asks for no confirmation; cancelling all does.
   - Cancel all is offered whenever the event has any request listed, even when all are already
     withdrawn (the backend answers with an empty list).
   - The page says nothing extra after a successful action: the re-read list shows the new
     statuses.

## Consequences
- AC10's event-status refusal ("refused once the event is Confirmed ... the refusal message
  names the event's status") is not on the backend's `main` yet: `withdraw_arrangement`,
  `change_arrangement` and `cancel_all_arrangements` check only the coordinator and the
  arrangement's own status. The page needs no change when it lands, because it shows any refusal
  the backend sends; a test pins that with a message only the backend could send. The mock
  backend mirrors `main`, so it has no event-status refusal either. Listed under Tickets to open.
- The mock backend (`mocks/handlers/booking.ts`) now answers the three routes, lists an event's
  requests earliest period first then by id, and lets only a pending, conflicting or held request
  block the same slot (the backend's partial unique index), so a withdrawn or rejected slot can
  be raised again. It follows main's statuses since SCRUM-75, SCRUM-94 and SCRUM-92: an expired
  arrangement can be withdrawn, cancel all leaves out withdrawn and released ones and is refused
  while one is approved or on hold.
- The mock checks the change body the way `ChangeArrangementSchema` does for what the screen can
  send. One known difference: a numeric string as the occupancy, which marshmallow accepts, is
  refused by the mock; the web app only sends numbers.

## Revisit when
- The backend adds the event-status refusal (AC10): mirror it in the mock and turn the contract
  test's `it.todo` into a real one.
- The team decides any of the defaults in decision 7.
