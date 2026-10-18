# ADR-0081: Technical Support record a reservation's preparation in the event's reserved equipment table

- **Status:** Accepted; showing the details as columns of the reserved equipment table, and the
  form in each row, are defaults to review with the team
- **Date:** 2026-10-19
- **Story:** SCRUM-85 Update equipment preparation details
- **Builds on:** ADR-0037, ADR-0050

## Context
The backend for SCRUM-85 is on main: `PUT /api/equipment/reservations/<id>/preparation` records a
status (`not_started`, `in_progress`, `ready`) and notes on a reservation, for any Technical
Support member, and refuses it (`409`) until the Safety Officer has approved the event. The
assigned coordinator reads both fields on the event's reservations,
`GET /api/equipment/events/<reference>/reservations` (ADR-0050). Nothing on the web used it.

Unlike a venue booking (ADR-0080), a reservation is already where both readers look: the event's
Equipment page (`/events/<reference>/equipment`, SCRUM-45 and SCRUM-46) shows the "Reserved for
this event" table to Technical Support, who reserve there, and to the assigned coordinator, who
reaches it from the event's record. Technical Support reach the page from their list of events
with equipment on Staff home (SCRUM-24 AC5, ADR-0061).

## Decision
1. **No new route and no new page.** Preparation belongs to a reservation, not to an equipment
   line, so it goes in the reserved equipment table rather than the equipment lines table, where
   Technical Support record each line's outcome (SCRUM-48, ADR-0077). That table gets two columns,
   "Preparation" (the status, e.g. "In progress") and "Preparation notes" ("None" when there
   are none), for everyone who can open the page (AC2).
2. **Technical Support get a "Record preparation" column** with a form in each row: a status
   drop-down and a notes box, both starting from what is saved, and "Save preparation". The
   coordinator never sees the column, as they never see the reserve control.
3. **The form is the one Venue Staff use** (`src/components/preparation/PreparationForm.tsx`,
   ADR-0080): empty notes are left out, which clears them (ADR-0050 decision 4); the backend's
   messages for the status and notes show under the fields, and any other refusal (AC5's safety
   approval) shows above the form. After a save the event's reservations are read again.
4. **Any Technical Support member records preparation for any reservation** (Product Owner,
   19 Oct, SCRUM-85 AC1; ADR-0050 decision 3). No one is named responsible for a reservation, so
   the page doesn't narrow who may record it, and neither does the backend. Each update still
   records who made it (decision 5).
5. **Each update is also an entry in the event's history** (AC4, ADR-0050 decisions 6 and 7),
   which the event page's history section words as "Equipment preparation updated" with the
   equipment, the status in words and the notes, under who and when (ADR-0076), as for venues
   (ADR-0080). That section is on the coordinator's event page; the backend lets every internal
   role read the history, but the other staff roles have no event page on the web yet.

## Consequences
- Technical Support reserve and prepare on the same row of the same page; the coordinator sees
  the result there without a new place to look.
- The table is wider. It already scrolls sideways inside its own box on a narrow screen.

## Revisit when
- Reservations and equipment lines are tied together (a reservation filling a line), at which
  point preparation could sit beside the line's outcome.
