# ADR-0022: Technical Support see one shared list of upcoming events whose equipment lines are still `requested`

- **Status:** Accepted
- **Date:** 2026-09-26
- **Story:** SCRUM-38 See the equipment requests awaiting my action

## Context
SCRUM-38 gives Technical Support Staff a list of the equipment requests that still need their attention. Its five ACs say: list "every equipment request not yet resolved, for events that have not yet taken place" (AC1); each row shows "event name, date and time, the equipment types and quantities requested, and the days remaining" (AC2); order by event date, soonest first (AC3); "fully arranged requests drop off the list" (AC4); only Technical Support Staff can open it (AC5).

SCRUM-37 records an event's equipment as lines, one per equipment type, each with a `status` that is only ever `requested` so far (ADR-0019). SCRUM-46 (Sprint 3) reserves equipment for an event; that is where a line stops being `requested`.

Several things are left open:
1. **What "resolved" and "fully arranged" mean,** when nothing can arrange equipment yet.
2. **What one "equipment request" is:** one line, or one event's lines together.
3. **What "has not yet taken place" means** for an event later today, or one running past midnight (ADR-0002).
4. **How "days remaining" is counted.**
5. **Which events count at all,** among the seven statuses of ADR-0012.
6. **Whose list it is.** Nothing assigns equipment work to a particular Technical Support Staff member.
7. **Whether the row names the equipment type** or gives its id, as every other line response does (ADR-0019).

## Decision
1. **A line is unresolved while its `status` is `requested`.** No new line state and no "mark arranged" endpoint here: SCRUM-46 decides what reserving does to a line, and a Postgres enum value added now could never be removed (ADR-0012).
2. **One row per event,** holding that event's unresolved lines. A request "drops off" (AC4) when none of its lines is still `requested`.
3. **A partly arranged event lists only the lines still `requested`,** in the order they were added. The event's full equipment, with each line's status, stays at `GET /api/events/requests/<reference>/equipment` (ADR-0019).
4. **"Not yet taken place" is `proposed_date >= today`,** where today is the business date (ADR-0001). An event is still listed on its own day, even after it has started, and an overnight event drops off the day after it starts.
5. **Days remaining is `proposed_date - today` in whole days:** 0 on the day, 1 the day before. Setup time (ADR-0011) is not subtracted, since the event has no venue booking yet (ADR-0019).
6. **Events that won't run are left out:** `completed`, `cancelled` and `rejected` (a deny-list, `EQUIPMENT_NOT_NEEDED_STATUSES`). `submitted`, `under_review` and `confirmed` events are listed. A `draft` would be too, but equipment can only be recorded on a `submitted` or `under_review` request (ADR-0019).
7. **One shared list for all Technical Support Staff.** The service takes no user id.
8. **Lines carry `equipment_type_id`, not the type's name,** like every other line response (ADR-0019). A client reads names from the equipment catalogue.
9. **Order: event date, then start time, then as submitted** (the request's id); an event's lines in the order they were added.
10. **`event_requests.proposed_date` is indexed** (migration 0013), since the list filters and sorts on it.
11. **The route is `GET /api/events/requests/awaiting-equipment`,** in the events module beside `/requests/assigned`, because the lines belong to events (ADR-0019). The equipment module can't serve it: it would have to import the events module, which already imports it.
12. **The response is `{"equipment_requests": [{"event": {...}, "equipment_lines": [...], "days_remaining": n}]}`.** `event` has the same fields as the SCRUM-37 equipment list (`reference`, `name`, `proposed_date`, `end_date`, `start_time`, `end_time`), and each line the same shape as everywhere else.

## Consequences
- Until SCRUM-46 ships, nothing drops off the list except by its event passing, or being completed, cancelled or rejected. Removing a line (SCRUM-37) also takes it off.
- SCRUM-46 needs no change here if reserving moves a line out of `requested`. If it can reserve part of a line's quantity, it has to decide whether such a line is still unresolved.
- The unit tests write a status other than `requested` straight into the table to show AC4, because the model has no such value yet.
- There is no pagination: every upcoming event with an unresolved line is returned at once.

## Revisit when
- SCRUM-46 adds partial reservations: "unresolved" may become "reserved less than requested".
- Technical Support work is assigned to individual staff members: filter the list per caller.
- Technical Support ask for equipment names in the row: add a bulk lookup to `equipment.services`.
- The list grows large enough that the join on `event_equipment_lines.status` is slow: index the line status too.
