# ADR-0079: The assigned coordinator edits an event's details on a page of its own, which sends only what changed and says which changes were significant

- **Status:** Accepted; the page's place, the link at the foot of the event page, the internal
  notes field opening empty and offering the edit in every status are defaults to review
- **Date:** 2026-10-18
- **Story:** SCRUM-33 Update event information and flag significant changes (AC1 to AC4)
- **Extends:** [ADR-0025](0025-event-edits-significant-changes-and-history.md),
  [ADR-0076](0076-event-history-and-registrants-on-the-event-page.md)

## Context
`PATCH /api/events/requests/<reference>` (ADR-0025) lets the event's assigned Event Coordinator
change eleven fields: the description, programme notes, accessibility needs and internal
planning notes (AC1), and the proposed date, end date, start and end times, expected attendance
and venue and equipment requirements, whose changes are significant (AC2). Any other field is
`400` "Unknown field." (AC3). A date sent without an end date moves the end date by as many
days. Only what is sent changes, and a value equal to the saved one is no change. The reply is
the event with both kinds of notes and `changes`, each `{field, previous_value, new_value,
significant}`, and every change is written to the history (AC4). Another coordinator's event is
`404`, an event outside submitted, under review, approved or confirmed is `409`
`request_not_editable`, and an organiser is `403`.

The web app had no way to call it. Open: where the form lives and how it is reached, what it
sends, how it says a change was significant, and what to do about the internal planning notes,
which no read route returns (the record leaves them out for everyone, ADR-0025 decision 20).

## Decision
1. **A page of its own, `/events/<reference>/edit`,** for Event Coordinators (the staff log-in
   for anyone signed out), beside the event's Venue requests and Equipment pages. Which event a
   coordinator may edit is the backend's call: another's comes back "Event request not found.",
   shown as it comes.
2. **The event page links to it from an "Edit details" section for its coordinator**, at the
   foot of the page above the history, which says what makes a change significant. The
   organiser's copy has no link.
3. **The form opens with what the event holds**, times to the minute, in two groups: the notes
   and needs, and "When, how many and what it needs", whose fields carry the hint that changing
   them is significant. The name, purpose, registration and the venue and equipment
   arrangements are not on the form (AC3).
4. **Saving sends only the fields that differ from the event**, an emptied one as null. So a
   date moved on its own lets the backend move the end date with it, and a field left alone is
   never sent. An emptied date, time or attendance goes as null, and the backend's "Field may
   not be null." shows under it. Every rule (a past date, the window, the attendance) is the
   backend's: its messages show under their fields, and the first one is focused.
5. **The internal planning notes field opens empty**, because no route returns the current
   notes, and is sent only when something is typed: what is typed replaces the notes, and an
   empty field keeps them. The field's hint says so. The notes can't be cleared from the form.
6. **After saving, a "Saved" panel lists each change as the history words it** (ADR-0076), with
   its value before and after and a "Significant change" badge on the backend's significant
   ones, then, if any was significant, "A significant change means the arrangements already
   made for this event will be reassessed." Nothing changed says so. A link goes back to the
   event, whose history shows the changes. The record, its history and the lists are read again.
7. **The form is offered in every status**, and an event that can't be edited now shows the
   backend's message when saved, as the venue arrangement actions do (ADR-0069): the page
   doesn't copy `EDITABLE_STATUSES`.

**The mock** (`src/mocks/handlers/eventEdits.ts`) answers the route as the backend does: the
same check order (role, the coordinator's own event, the status, then the fields), field rules
and messages, the window checked on the values the event would have only once every field
passes its own rules, the end date following the date, trimming and blank as null, changes in
the backend's field order with the moved end date last, and one history entry per change by the
coordinator at the mock's "now". It keeps the internal notes apart, so the record never shows
them.

## Consequences
- A coordinator can't see the current internal planning notes before replacing them; they show
  in the history (each change's before and after) and in the reply to a save.
- The edit's two newest rules on Jira, AC6 (several venue arrangements reassessed separately)
  and AC7 (a significant change withdrawing a passed safety check), are not on `main`'s backend
  yet (`_reassess_arrangements` still says `TODO: SCRUM-58`), so the page says only that
  arrangements will be reassessed, not which.
- The integration tests for the edit need an event assigned to the staff account, so they run
  only with a Lead account (ADR-0076), which CI makes.

## Revisit when
- The backend returns the internal planning notes to the assigned coordinator: open the field
  with them and send an emptied one as null, like the other notes.
- The backend reassesses each venue arrangement or withdraws a safety approval on a
  significant change (AC6, AC7): say which arrangements were flagged, from the reply.
- The team wants the edit hidden in statuses it can't apply to, or the link moved up beside the
  coordinator's other links.
