# ADR-0075: The coordinator sends an event to safety review, confirms it, sets its registration and marks it completed from the event page

- **Status:** Accepted; every decision below is a default to review with the team
- **Date:** 2026-10-18
- **Stories:** SCRUM-97 Submit an event for operational safety check; SCRUM-68 Mark an event
  as completed after it has taken place; SCRUM-69 Enable registration for an event and set its
  capacity; SCRUM-49 Confirm an event once its arrangements are in place
- **Extends:** [ADR-0027](0027-event-completion.md), [ADR-0043](0043-registration-settings-set-by-the-assigned-coordinator.md),
  [ADR-0047](0047-safety-officer-and-safety-review.md), [ADR-0051](0051-confirm-an-event.md),
  [ADR-0060](0060-review-actions-on-the-event-page.md)

## Context
The backend on `main` has four routes for the event's assigned coordinator, each answering
anyone else with the "not yours" `404`:

- `POST /api/events/requests/<reference>/safety-review` (SCRUM-97, ADR-0047): an `approved`
  event moves to `safety_review`. Any other status is `409 safety_review_not_allowed`, and so is
  an event whose venues or equipment aren't settled, with `details` naming each gap under
  `venue_arrangements` and `equipment` ("Venue arrangement 12 is pending.").
- `POST …/confirm` (SCRUM-49, ADR-0051): an event in `safety_review` becomes `confirmed`. A
  missing approval is `409 confirmation_not_allowed`, with `details` under `safety_check`,
  `venue_arrangements` and `equipment`. The organiser gets the backend's `event_confirmed`
  notification ("Your event has been confirmed.").
- `PATCH …/registration` (SCRUM-69, ADR-0043) with `registration_enabled`,
  `registration_capacity` or both: enabling needs a capacity (`400` on the field) and a
  `confirmed` event (`409 registration_not_enablable`); a capacity below the number registered
  is `400` on the field. It answers with `reference`, `registration_required`,
  `registration_enabled` and `registration_capacity`.
- `POST …/complete` (SCRUM-68, ADR-0027): a `confirmed` event whose end has passed becomes
  `completed`; otherwise `409 request_not_completable` ("Only a confirmed event can be marked
  completed.", "The event has not ended yet.").

ADR-0047 and ADR-0051 left the coordinator's buttons for the web app. The event page
(ADR-0046) already carries the review actions (ADR-0060). The stories say what the coordinator
may do, not how the page offers it.

## Decision
1. **Where.** The four actions sit in a "Planning" section of the coordinator's copy of the
   event page (`/events/<reference>`), straight after the "Review" section. They are drawn by
   their own component, `RecordActions`, which the page includes in one line beside
   `ReviewActions`. The organiser's copy shows none of them; the backend lets only the
   assigned coordinator open the coordinator's copy (ADR-0034).
2. **Which action shows in which status.** An action shows only in the status the backend
   would accept it in. Whether it is allowed there is still the backend's call, and its refusal
   is shown as it comes. One table, `PLANNING_ACTIONS_BY_STATUS`, is typed over every status:

   | Status | Send to safety review | Confirm event | Registration settings | Mark completed |
   |---|---|---|---|---|
   | approved | yes | | | |
   | safety_review | | yes | | |
   | confirmed | | | yes | yes |
   | every other status | | | | |

   - **Confirm event shows for every event in Safety Review**, including one the Safety
     Officer hasn't approved yet. The record doesn't say whether the approval is in
     (`has_safety_approval` is the backend's), so the backend's refusal names it
     ("The Safety Officer has not approved the event.").
   - **Mark completed shows for every confirmed event**, ended or not. The page doesn't compare
     the end with the clock: the backend's "The event has not ended yet." says so.
   - **Registration settings show only for a confirmed event.** Registration can be enabled
     only then (SCRUM-69 AC4), and the backend would refuse anything else. The backend also lets
     the coordinator store a capacity, disabled, before confirmation (ADR-0043 decision 3); the
     page doesn't offer that.
   - With nothing to offer, the section isn't drawn.
3. **A refusal lists every reason the backend gives.** The two gates answer with a message and
   `details` naming each gap. The alert shows the message and, under it, every message in
   `details`, in the backend's words and order. Nothing is rewritten: "Venue arrangement 12 is
   pending." is already plain. `RefusalAlert`, beside `ErrorAlert` in `components/ui`, does it;
   forms keep `ErrorAlert` and show field messages under their fields instead.
4. **The registration settings form.** An Open/Closed choice and a Capacity box, then
   "Save registration".
   - **The record doesn't carry the current settings.** `GET /api/events/requests/<reference>`
     has no `registration_enabled` or `registration_capacity`, and no other route returns
     `registration_enabled`. So the form doesn't guess: neither Open nor Closed is picked and
     the box starts empty. The card says what the organiser asked for, and that leaving the
     choice unpicked keeps registration as it is (until a capacity is first saved, the backend
     follows the organiser's answer, SCRUM-69 AC1).
   - **What is sent:** only what the coordinator changes. `registration_enabled` only when Open
     or Closed is picked, and `registration_capacity` only when a number is typed; "Save
     registration" stays disabled until one of them is. A field left out keeps what the event
     has (ADR-0043 decision 3), so a new capacity alone never opens or closes registration,
     and turning registration off or on again needs no number once one is stored. (Changed in
     review: the first version always sent the choice, starting at the organiser's answer, so
     saving only a new capacity on an event whose organiser hadn't asked closed its open
     registration.) The number is sent as typed; whole-number, range and "at least the number
     registered" checks are the backend's, shown under the box.
   - **Once saved, the card says what the backend now holds**, from its reply: "Registration is
     open." or "Registration is closed.", and "Capacity: 120." when there is one. It is the
     reply, not a guess, but it lasts only while the page is open (see Consequences).
5. **No confirmation step.** Each action is one press, like the review actions (ADR-0060
   decision 3). Confirming tells the organiser and completing can't be undone, but so does
   approving, which already goes without a confirmation.
6. **After each action, every event-request query is read again** (`eventRequestKeys.all`), as
   for the review actions. The new status, and the action the new status offers, show because
   the backend says so. The registration reply is the only response the page reads directly.

**The mock** (`src/mocks/handlers/eventPlanning.ts`) answers the four routes from the same
stored requests as `eventRequests.ts`, so the record the page reads afterwards shows the change.
It decides as the backend does: the assigned coordinator only (`404` for anyone else's, `403`
for another role), the same check order, status changes, codes, messages and field messages.
The venue arrangements, equipment requests and registrations the backend would count live with
each mock event as `planning` (its arrangements with their status, the ids of equipment
requests without an outcome, whether the Safety Officer approved, the registration settings and
the number registered), and the gap messages are built from them as `_venue_gaps` and
`_equipment_gaps` build them. An event with no `planning` has no venue arranged, nothing
waiting on Technical Support, no safety approval and registration closed. The other feature
mocks (booking, equipment) keep their own copies of events, so an arrangement withdrawn there
doesn't change this one. The mock has no Safety Officer route, so an approval is part of the
data, not something an action sets. An event ends at `end_date` + `end_time`, Singapore time,
and the mock's "now" is `MOCK_NOW`. No notification is raised: the notifications mock seeds its
own.

A new coordinator, Hana Yusof (mock account 40), has six events of organisation 2, so the
actions change nothing another test reads: two approved (one with a pending venue arrangement and
an unanswered equipment request, one settled; each also has a withdrawn arrangement the gate must
ignore), two in Safety Review (one approved by the Safety Officer and settled, one not, with a
rejected arrangement and an unanswered equipment request), and two confirmed (one ending exactly
at `MOCK_NOW`, open for 50 with 30 registered; one that began the day before and ends a minute
after it, whose organiser asked for registration).

## Consequences
- The coordinator can take an event from Approved to Completed in the web app, so the lifecycle
  ADR-0047 and ADR-0051 set up can run in a browser.
- **The registration form can't show the current settings when the page opens.** A coordinator
  who reopens the page sees nothing picked and an empty box, not what was saved. Saving only
  what changed keeps the rest, so nothing is lost, but the page can't show it.
  Listed under Tickets to open: add `registration_enabled` and `registration_capacity` to the
  event record, then start the form from them.
- SCRUM-69 AC3 (capacity within the booked venue's) is still deferred on the backend
  (ADR-0043); the form shows its refusal once it lands, with no change.
- SCRUM-49 AC9 and AC10 (rejecting an event during planning) and AC11 (what the organiser sees
  once confirmed) have no backend yet (ADR-0051 decisions 9 and 10), so the page has nothing to
  offer for them.
- SCRUM-68 AC4 and SCRUM-69 AC6 are the backend's: a completed event's equipment and venue
  pages already show the backend's refusals, and the history records who changed the
  registration settings.

## Revisit when
- The event record carries the registration settings: start the form from them.
- The backend adds rejecting an event during planning (SCRUM-49 AC9): add it to the table.
- The record says whether the Safety Officer has approved: Confirm event could show only then.
- The customer wants confirming or completing to ask first.
