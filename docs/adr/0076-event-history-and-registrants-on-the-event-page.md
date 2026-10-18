# ADR-0076: The event page shows the event's history and who has registered, each read from its own route and worded on the page

- **Status:** Accepted; the wording, the empty states and showing registrants whatever the
  registration setting are defaults to review with the team
- **Date:** 2026-10-18
- **Stories:** SCRUM-33 Update event information and flag significant changes (AC4, AC5);
  SCRUM-55 See who has registered for an event (AC1 to AC5)
- **Extends:** [ADR-0025](0025-event-edits-significant-changes-and-history.md),
  [ADR-0046](0046-event-request-detail-page.md)

## Context
The backend has two read routes the web app doesn't use yet:

- `GET /api/events/requests/<reference>/history` (SCRUM-33, ADR-0025): any staff role may read
  any event's history but a draft's, an Event Coordinator only an event assigned to them, and an
  Event Organiser their organisation's events. The organiser's copy leaves out the kinds in
  `INTERNAL_ONLY_KINDS` (`equipment_reserved`, `equipment_outcome_recorded`,
  `safety_outcome_recorded`) and any `field_changed` entry about `internal_planning_notes`. Each
  entry is `{kind, occurred_at, actor_name, details}`, oldest first, with no user ids;
  `actor_name` is null for the system or a removed account.
- `GET /api/events/requests/<reference>/registrations` (SCRUM-55): an organiser of the event's
  organisation or its assigned coordinator; anyone else's event is `404`, and an attendee is
  `403`. It answers `{capacity, registered_count, places_left, items}`, each item
  `{name, email, registered_at, status}`, oldest first. `capacity` and `places_left` are null
  until the coordinator sets a capacity (SCRUM-69, ADR-0043).

ADR-0046 deferred the history to its own section because each of its kinds (18 on `main` today)
needs its own wording. SCRUM-33 AC5 says the history is visible to internal users and to the
organiser for their own event; SCRUM-55 AC3 lists what each registrant shows and AC4 asks for
the count against the capacity. Open: where they go, how each kind reads, what a kind the
backend adds later does to the page, and when the registrants show.

## Decision
1. **Both are sections at the foot of the event page** (`/events/<reference>` and
   `/organiser/requests/<reference>`), History then Registrants, below the record's own
   sections. Each reads its own route and shows its own loading, error and empty state, so a
   refusal of one leaves the rest of the record on screen.
2. **The page shows what the backend sends to whoever is looking.** Which entries an organiser
   sees is the backend's filter; the page doesn't hide or reorder entries. The history keeps the
   backend's order, oldest first, like a timeline read top to bottom.
3. **Each kind has its own wording**, in `features/eventRequests/eventHistory.ts`: a title ("Review
   started", "Venue booking approved"), then the facts its `details` hold as label and value
   pairs, then when and by whom ("6 Oct, 2:00 pm · Leon Goh", or only when for the system or a
   removed account). The wording is typed over every kind (`Record<EventHistoryKind, …>`), so a
   kind added to the list without wording fails the typecheck.
4. **A change shows its field, the value before and after, and a "Significant change" badge
   when the backend marked it significant** (SCRUM-33 AC2, AC4). Dates and times read as they
   do on the record ("Thu, 12 Nov", "9:00 am"), yes or no for a setting, "Not set" for an empty
   value. Field names are worded from the backend's names ("expected_attendance" reads
   "Expected attendance"), so a field the backend starts recording later needs no change here.
5. **A kind the page doesn't know yet is one plain line**, its title made from the kind's name
   ("venue_preparation_updated" reads "Venue preparation updated"), with when and by whom and
   none of its details. Open pull requests add kinds (venue and equipment preparation, holds
   and expiries); until each is worded, its entries still show and the page never breaks.
6. **Venues are named by their ID** ("Venue ID 12"): the history's venue entries hold
   `venue_id` and no name, and organisers can't read the venue catalogue to look one up.
7. **Registrants are a table of name, email, registration date and status** (SCRUM-55 AC3),
   in the backend's order, under one line counting them against the capacity: "3 registered of
   80 places · 77 left", or "3 registered · no capacity set yet" while the capacity is null
   (AC4). The numbers are the backend's; the page counts nothing itself.
8. **The Registrants section shows whatever the event's registration setting**, since the
   backend answers for every event the viewer is responsible for, and registrations made while
   registration was open stay after it closes. With none, it says "No one has registered yet."
9. **Who sees them is the backend's call**: the page only reaches organisers and coordinators
   (ADR-0046), both of whom the two routes answer. AC5 (an attendee can't see other attendees)
   holds because no attendee page reads the route, and the backend refuses it with `403`.

**The mock** (`src/mocks/handlers/eventRecordSections.ts`) answers both routes through the
event record mock's own lookups (`eventRequests.ts`), with the backend's roles, scope, organiser
filter, refusals and messages. Its data (`eventRecordSectionFixtures.ts`) is keyed by
reference: the mock organiser's Partner Summit and Leadership Offsite each hold entries an
organiser must not see next to ones they must, and Chloe's confirmed Year-End Town Hall has a
full history and three registrants.

## Consequences
- A new history kind on the backend shows at once as a plain line; wording it is one entry in
  `EVENT_HISTORY_KIND` and one in the wording table, which the typecheck then insists on.
- `EVENT_HISTORY_KIND` copies the backend's enum. The unit test pins today's 18 kinds; nothing
  checks the two stay equal, so a backend PR adding a kind should add its wording too.
- The integration tests that need an event assigned to the staff account read an optional
  Event Coordinator Lead from `INTEGRATION_LEAD_EMAIL` / `INTEGRATION_LEAD_PASSWORD` and skip
  without one, like the Venue Staff checks. CI doesn't make a Lead yet, so they run locally only.

## Revisit when
- The backend names venues in their history entries, or organisers may read venue names.
- The customer wants the newest history entries first, or the history paged.
- SCRUM-53 adds registration statuses besides `registered`: the status column shows the
  backend's value worded from its name, and the count stays the backend's.
- The team decides the Registrants section should show only while registration is enabled.
