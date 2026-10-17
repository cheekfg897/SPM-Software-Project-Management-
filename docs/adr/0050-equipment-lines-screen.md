# ADR-0050: The assigned coordinator records an event's equipment lines on its Equipment page

- **Status:** Accepted; decisions 2 to 6 are defaults to review with the team
- **Date:** 2026-10-17
- **Story:** SCRUM-37 Record what equipment an event needs (AC1, AC2, AC3, AC5)
- **Extends:** ADR-0019, ADR-0028, ADR-0037

## Context
The backend has had SCRUM-37's routes since ADR-0019: `POST` and `GET
/api/events/requests/<reference>/equipment`, and `PATCH` and `DELETE` on
`.../equipment/<line_id>`. The web app had no screen for them. As numbered in Jira on
2026-10-17, the ACs a screen serves are AC1 "add one or more equipment lines to an event, each
with equipment type, quantity and technical notes", AC2 "add, edit or remove a line at any time
before the event is Confirmed", AC3 "a quantity of zero or less is refused" and AC5 "the
equipment request and its current state are visible ... to internal staff". AC4 (a changed line
is a significant change and reopens its review) and AC6 (Technical Support are notified) happen
in the backend.

The ACs leave open where the screen lives, who sees its controls, and how an edit and a removal
behave on screen. The lines name their equipment type by id only (ADR-0019), so the names come
from `GET /api/equipment/types`.

## Decision
1. **On the event's Equipment page**, `/events/<reference>/equipment`, which coordinators and
   Technical Support already open (ADR-0037). A "What this event needs" section comes first,
   above availability and reservations, because what the event asks for is what the other two
   are measured against. Each line shows its equipment type's name, the quantity, the technical
   notes and its status, in the order the backend sends (the order the lines were added).
2. **Every coordinator who can open the page sees the add, change and remove controls**;
   Technical Support see the lines only. The backend lists an event's lines to a coordinator
   only when the event is assigned to them, so a coordinator who sees the lines is the assigned
   one. The list does not carry the event's status, so the controls are not hidden outside the
   editable statuses: the backend's refusal ("Equipment can only be changed while the request is
   submitted, under review or approved.") is shown instead.
3. **A change sends only the fields that changed** (`PATCH` is partial, ADR-0019 decision 8),
   so a line whose quantity was not touched is not reported as a changed quantity once AC4's
   reopening lands. Saving with nothing changed sends `{}`, which the backend accepts.
4. **A blank field is not sent.** Adding a line with no equipment type or no quantity gets the
   backend's "Missing data for required field." under that field; clearing a field while
   changing a line sends it as `null`, and the backend's message for that shows. The screen
   checks nothing itself (`frontend/CLAUDE.md`).
5. **Removing a line asks first**, in the place of the add form: "Remove Projector from this
   event?" with Remove and Keep it. A removal is a hard delete (ADR-0019) and loses the notes.
6. **Status words:** `requested` is "Awaiting Technical Support", `fulfilled` "Fulfilled",
   `partially_fulfilled` "Partly fulfilled" and `unavailable` "Unavailable", written out rather
   than shown by colour alone. The outcome's details (the quantity provided, the note, who
   reviewed it) are SCRUM-48's to show.

Also:
- A line whose equipment type is missing from the catalogue list shows as "Equipment type 7"
  rather than breaking the page.
- After an add, change or removal, the event's lines, availability and reservations are all read
  again: availability's "Requested" is the lines' quantities.
- The mock backend's events carry a status, and availability's "Requested" comes from the
  event's lines, as the backend's does.

## Consequences
- A coordinator may meet a refusal for an event that is no longer editable rather than finding
  no controls. If the list gains the event's status, the controls can be hidden instead.
- SCRUM-48's Technical Support controls can add columns to the same table.
- The screen follows whatever edit window the backend enforces, so the rework in Jira's AC2
  ("any time before the event is Confirmed") and AC4 needs no change here.

## Revisit when
- The backend sends the event's status with its lines: hide the controls outside the edit window.
- The team prefers removing without a question, or an undo instead.
- SCRUM-48's screen lands: show each line's outcome next to its status.
