# ADR-0056: One event detail page for organisers and coordinators, and a coordinator's list on Staff home

- **Status:** Accepted; the deferred history section is added by
  [ADR-0076](0076-event-history-and-registrants-on-the-event-page.md)
- **Date:** 2026-10-16
- **Story:** SCRUM-24 See the events my role is involved in (AC2, AC8, AC9, AC10, AC11)
- **Extends:** ADR-0026, ADR-0034

## Context
The backend has a coordinator's list (`GET /api/events/requests/assigned`, ADR-0018) and an
event's record (`GET /api/events/requests/<reference>`, ADR-0026's point 8), but the web app
uses neither. A coordinator logs in to an empty Staff home that says "The events and requests
you look after will appear here", and can reach an event's Venue requests and Equipment pages
only by typing their address. An organiser can open a draft to edit it, but a submitted request
opens nothing.

As numbered in Jira on 2026-10-15, SCRUM-24 asks for: AC2 "An Event Coordinator sees only the
events assigned to them", AC8 "Every list shows event name, date, time and status", AC9 "Opening
an event from the list shows the event detail view containing only the sections that role may
see", AC10 "An Event Coordinator who is not assigned to an event cannot open, view or change it,
including by direct link", and AC11 "A role with no events matching its filter is shown a message
saying there are none".

Four things are left open:

1. **The address.** Organisers' pages live under `/organiser`, and a coordinator's event pages
   under `/events/<reference>/…` (Venue requests, Equipment). `RequireRole` sends someone signed
   out to one log-in page per route, and organisers and staff log in on different pages
   (ADR-0023).
2. **Which sections.** The record carries the request, its coordinator's contact, its decision,
   its clarification exchange, its programme notes and its equipment lines.
3. **Which rows open it.** A draft already opens its edit form (SCRUM-20 AC3).
4. **Which staff home shows a list.** Staff home is shared by every staff role except the Lead.

## Decision
1. **One page, two addresses.** The same page answers `/organiser/requests/<reference>` for an
   Event Organiser (signed out: the log-in page) and `/events/<reference>` for an Event
   Coordinator (signed out: the staff log-in page). Each sits with its role's other pages, and
   the coordinator's is the parent of `/events/<reference>/venue-requests` and `/equipment`.
2. **The page shows what the backend sends.** Who may open which record, and which sections it
   holds, is the backend's call (AC9, AC10): an event that isn't theirs comes back `404`
   "Event request not found.", and the page shows that message. The page draws each section the
   record holds: the request's details, the coordinator (or that none is assigned yet), the
   decision once there is one, the clarification exchange once there is one, and the programme
   notes once there are some.
3. **A coordinator's page also links on** to the event's Venue requests and Equipment pages,
   which only they (of these two roles) may open. An organiser's page has no such links.
4. **Drafts still open their edit form; every other row opens the detail page**, in both lists.
5. **Staff home shows "Your assigned events" to Event Coordinators only**, with the rows the
   backend sends in its order (newest first) and its message when there are none. Other staff
   roles keep the placeholder until their own lists are built.

## Consequences
- `fetchEventRequest` returns the whole record (`EventRecord`), which the edit-draft page reads
  as before.
- The mock's event requests know their coordinator, decision, clarifications and programme
  notes, so mock mode shows the same events in the organiser's list and the coordinator's, and a
  mock coordinator's events include those the booking and equipment mocks hold
  (`EVR-BOOK0101`, `EVR-BOOK0102`, `EVR-MOCK0001`), so their links lead somewhere.
- A coordinator with no events (`daniel@connectsphere.test` in mock mode) sees the backend's
  "No event requests are assigned to you yet."
- `/events/<reference>` is now a staff page. A public page for one catalogue event would need
  another address.

### Deferred
- **The event's history** (`GET …/<reference>/history`, SCRUM-33): it has 14 kinds of entry,
  each needing its own wording on screen. A page section of its own, in a later PR.
- **Equipment lines**: the record names each line's equipment type only by id. Coordinators
  already see the lines, by name, on the Equipment page. *The organiser's record now names
  them, and their page shows them ([ADR-0098](0098-organiser-sees-their-equipment-without-internal-notes.md)).*
- **The Lead opening an event** (SCRUM-24 AC3, AC10): `GET …/<reference>` allows only organisers
  and coordinators today, so the Lead's lists can't link to a record yet. A backend change first.
- **Technical Support's list** (AC5, `GET …/requests/with-equipment`) and the Safety Officer's
  (AC6, no backend yet) on Staff home.
- **Actions on the page** (review, decide, ask for clarification, mark completed: SCRUM-31,
  SCRUM-32, SCRUM-68).

## Revisit when
- The Lead may open a record: give the Lead's lists links to it, at a staff address.
- A role's sections differ from another's in the backend: the page keeps drawing what is sent,
  but its tests should pin each role's sections.
