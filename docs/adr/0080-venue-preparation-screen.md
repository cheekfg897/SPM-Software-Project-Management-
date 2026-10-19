# ADR-0080: Venue Staff record preparation on their booking requests page, from a list of approved bookings

- **Status:** Accepted; the new list route, its order and the page it sits on are defaults to
  review with the team
- **Date:** 2026-10-19
- **Story:** SCRUM-84 Update venue preparation details
- **Builds on:** ADR-0035, ADR-0042, ADR-0049

## Context
The backend for SCRUM-84 is on main: `PUT /api/venues/booking-requests/<id>/preparation` records
a status (`not_started`, `in_progress`, `ready`) and notes on an approved booking, refuses it
(`409`) until the Safety Officer has approved the event, and the coordinator reads both fields on
their event's booking requests (ADR-0049). Nothing on the web used it, and two things were open:

1. **Where Venue Staff reach an approved booking.** Their only read route,
   `GET /api/venues/booking-requests`, lists the requests still waiting for a decision. Once
   approved, a booking leaves it, and no other route gives Venue Staff its id: the venue calendar
   shows periods without ids, and the event history only names a booking after its first
   preparation update. ADR-0049 left "a read route on the approved bookings" for a later ticket.
2. **Where Venue Staff's page is.** The decisions page (`/staff/venue-requests`, SCRUM-43) had no
   link anywhere in the app: Venue Staff land on Staff home, which shows them nothing.

## Decision
1. **A read route: `GET /api/venues/booking-requests/approved`**, Venue Staff only, answering
   every approved booking in the same shape as the decisions queue (the booking with its event's
   timing and accessibility needs, and its preparation status and notes), the earliest event
   first. It shares the queue's query and order, so it is a few lines in `venue/services.py`. No
   migration. This is the smallest change that lets Venue Staff find a booking to prepare without
   typing an id they have no way to see.
2. **No filter beyond "approved"** (a default to review). Every approved booking is listed,
   whether or not the Safety Officer has approved its event yet and whatever its date. A booking
   whose event isn't safety-approved shows the backend's refusal when Venue Staff try to save,
   which is AC5's message rather than a rule the page repeats.
3. **The list sits on the existing decisions page**, under the queue, as "Approved bookings".
   The queue gets its own heading, "Waiting for a decision". Each approved booking shows its
   details, its preparation as last saved ("Preparation: In progress", and the notes), and a form:
   a status drop-down and a notes box, both starting from what is saved, and "Save preparation".
   Approving a request in the queue reads both lists again, so it moves down to this one.
4. **The form sends what it shows.** Each update states the whole picture (ADR-0049 decision 4),
   so empty notes are left out of the body, which clears them; the notes box says so. Blank
   notes, their length and the status are the backend's rules, and its messages show under the
   fields; any other refusal (the safety approval, a booking no longer approved) shows above the
   form. After a save the approved list is read again, so the page shows what the backend saved.
5. **The coordinator sees it on the event's venue requests** (AC2): an approved request shows
   "Preparation: <status>" and the notes under its other details. A request that isn't approved
   shows nothing about preparation. Each update is also an entry in the event's history (AC4,
   ADR-0049 decisions 6 and 7), which the event page's history section words as "Venue
   preparation updated" with the venue, the status in words and the notes, under who and when
   (ADR-0076). That section is on the coordinator's event page; the backend lets every internal
   role read the history, but the other staff roles have no event page on the web yet.
6. **A "Venue bookings" link in the site header for Venue Staff**, as coordinators have "Find a
   venue". It opens the decisions page, so the queue (SCRUM-43) is reachable too.
7. **The status labels and the form are shared** (`src/config/preparation.ts`,
   `src/components/preparation/PreparationForm.tsx`), because SCRUM-85 records the same details
   on an equipment reservation (ADR-0081).

## Consequences
- Venue Staff can find, check and update any approved booking's preparation from one page they can
  reach from the header.
- The list grows with every approved booking, including past events. That is fine for the
  project's data; a long-lived deployment would want only events that haven't ended.
- The route is new backend surface: the README's route table, the backend tests and the frontend
  integration tests cover it.

## Revisit when
- The team settles ADR-0049's defaults (status names, notes replaced on each update), or wants
  the list limited to safety-approved or upcoming events.
- Venue Staff's event list (SCRUM-24, ADR-0085, on main since this was written) gets a detail
  view, which may be a better home for preparation than the decisions page.
