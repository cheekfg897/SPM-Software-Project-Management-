# ADR-0051: Technical Support's two lists on Staff home, each event opening its Equipment page

- **Status:** Accepted; the wording of days remaining, the empty queue's message and the name
  shown for an equipment type the catalogue doesn't list are defaults to review
- **Date:** 2026-10-17
- **Story:** SCRUM-38 See the equipment requests awaiting my action; SCRUM-24 See the events my
  role is involved in (AC5, AC8, AC11)
- **Extends:** ADR-0022, ADR-0026, ADR-0046

## Context
The backend has both of Technical Support's lists, but the web app uses neither. A Technical
Support Staff member logs in to a Staff home with only a greeting, and reaches an event's
Equipment page only by typing its address.

- `GET /api/events/requests/awaiting-equipment` (SCRUM-38, ADR-0022) is their queue: every
  upcoming event whose equipment lines are still `requested`, soonest first, with only those
  lines and the whole days left until the event. As written in Jira on 2026-10-17, SCRUM-38 asks
  that "each row shows event name, date and time, the equipment types and quantities requested,
  and the days remaining" (AC2), "ordered by event date, soonest first" (AC3), and that "only
  Technical Support Staff can open it" (AC6).
- `GET /api/events/requests/with-equipment` (SCRUM-24 AC5, ADR-0026) is every event with an
  equipment request, newest first, whatever its status. Its rows carry only `EVENT_LIST_FIELDS`
  (reference, name, dates, times and status), and an empty list carries a `message` (AC11).

Five things are left open:

1. **Where an event opens.** ADR-0046's detail page opens only for organisers and coordinators:
   `GET /api/events/requests/<reference>` refuses Technical Support.
2. **Equipment type names.** A line names its type only by `equipment_type_id`; ADR-0022's
   point 8 leaves the names to the client, from the equipment catalogue.
3. **How days remaining reads.** The backend sends a whole number, 0 on the event's day.
4. **An empty queue.** Unlike every SCRUM-24 list, the queue's body has no `message`.
5. **Rows without attendance.** The shared event row (ADR-0046) shows "EVR-… · 250 expected";
   the AC5 rows have no `expected_attendance`.

## Decision
1. **Staff home shows Technical Support two sections**, and no other role sees or asks for
   either: "Equipment awaiting action" (the queue) first, since it is their to-do list, then
   "Events with equipment" (AC5). Each keeps the backend's order.
2. **Every event in both lists opens its Equipment page** (`/events/<reference>/equipment`),
   which Technical Support may open for any event (ADR-0019, ADR-0037).
3. **The web app names each line from `GET /api/equipment/types`**, which any staff role may
   read, as "Projector × 2". A type the catalogue doesn't list (added between the two reads)
   shows as "Equipment type 7 × 2" rather than hiding the line. *Default to review.*
4. **Days remaining reads "Today" for 0, "1 day left" and "N days left"**, from the backend's
   number; the web app never counts days itself. *Default to review.*
5. **An empty queue says "No equipment requests are awaiting action."**, the web app's own
   words, since the backend sends none. *Default to review*: a backend `message`, as the other
   lists have, would replace it (see Tickets in the PR).
6. **The shared row shows only the reference when a list has no attendance**, so the AC5 rows
   reuse ADR-0046's list and row as they are.
7. **Both lists' query keys leave out the viewer.** The lists are the same for every Technical
   Support member (ADR-0022's point 7), other roles never ask, and signing out clears the
   cache, as with Venue Staff's and the Lead's queues.

## Consequences
- In mock mode, `tariq@connectsphere.test` sees both lists. Their events and lines live in the
  Technical Support mock, apart from the event request mock, with the mock's "today"
  (`MOCK_TODAY`, 2026-10-05) for the queue's dates and days. Only `EVR-MOCK0001` and
  `EVR-MOCK0002` open an Equipment page with something on it, since those are the events the
  equipment mock holds; the others open its "Event request not found.".
- The mock answers `GET /api/equipment/types` from the equipment mock's types. The equipment
  catalogue screen (SCRUM-27) needs the same call: whichever lands second should use the first's.
- An event's lines are read through the queue only. The Equipment page still shows the event's
  availability and reservations, not its lines.

### Deferred
- **Recording an outcome from the queue** (SCRUM-48): the queue only links on.
- **The Safety Officer's list** (SCRUM-24 AC6): no backend yet.

## Revisit when
- Technical Support may open an event's record: link the AC5 rows to it.
- The backend names the equipment type in a line, or adds a `message` to an empty queue: drop
  the catalogue read, or the web app's own words.
- Equipment work is assigned to one Technical Support member (ADR-0022's "Revisit"): add the
  viewer to the query keys.
