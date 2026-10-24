# ADR-0095: A read-only event record for Venue Staff, Technical Support, the Safety Officer and the Lead

- **Status:** Accepted. Who may open it is the product owner's (SCRUM-24 AC9, 19 Oct; AC10, Week 7 change #5). A separate route, only the arrangements that still count, the current check's safety outcome, and Technical Support's list opening the record instead of the Equipment page are defaults to review
- **Date:** 2026-10-25
- **Stories:** SCRUM-24 AC9, AC10; SCRUM-33 AC5; SCRUM-84 AC2; SCRUM-85 AC2
- **Extends:** [ADR-0056](0056-event-request-detail-page.md) (the event page), [ADR-0076](0076-event-history-and-registrants-on-the-event-page.md) (its history section); [ADR-0049](0049-venue-preparation-details.md) and [ADR-0050](0050-equipment-preparation-details.md) decision 7 (who reads the preparation details)
- **Closes:** the "Revisit when" items of [ADR-0085](0085-venue-staff-event-list.md) and [ADR-0090](0090-venue-staff-events-on-staff-home.md)

## Context
SCRUM-24 AC9 was changed on 19 Oct: "Venue Staff, Technical Support Staff and the Safety Officer can open the record of any submitted event, read-only: its details, venue arrangements, equipment, safety outcome, history and internal notes. They cannot change the event from this view. The registrant list stays with the Event Organiser and the assigned Event Coordinator (SCRUM-55)." AC10 says only the Event Coordinator Lead can open the events no coordinator has, and the Lead may open every event. Drafts stay private to their author (SCRUM-20, ADR-0024).

Before this change, `GET /api/events/requests/<reference>` let in only organisers and coordinators, so none of these four roles could open an event. The history route already let in every internal role (SCRUM-33 AC5), but no page showed it to them. SCRUM-84 AC2 and SCRUM-85 AC2 say venue and equipment preparation is "visible to the assigned Event Coordinator and to other internal users", and ADR-0049 and ADR-0050 left the other users with only the history entries (decision 7).

Left open: whether to widen the existing route or add one, what the record holds beyond AC9's list, and where the web app opens it from.

## Decision
1. **A new route, `GET /api/events/requests/<reference>/staff-record`,** rather than widening `/requests/<reference>` with a branch per role. The organiser's and coordinator's record keeps its shape: what an organiser sees there is a separate story's (SCRUM-24 AC9, SCRUM-55), and this record holds things theirs never does (the internal notes, the reservations). Its own route lets the role check stay in the decorator, with no role dispatch in the view. The service is `get_staff_event_record`; it doesn't change `get_event_record_for_organiser` or the coordinator's lookup.
2. **Who may open it:** Venue Staff, Technical Support Staff, the Safety Officer and the Event Coordinator Lead (`_STAFF_RECORD_READERS` in `events/routes.py`, `STAFF_RECORD_READER_ROLES` in `src/config/roles.ts`), for **any event but a draft**, whoever coordinates it or whether anyone does. There is no per-event check (AC9: "access is by role only"). Everyone else gets `403`: the organiser and the attendee, and the Event Coordinator too, even for an event assigned to them, because their own record is `/requests/<reference>`, which still opens only their events (AC10, ADR-0034). No token is `401`. A draft or an unknown reference is `404` "Event request not found." (ADR-0012, ADR-0024).
3. **What it holds:** the request's own fields with the programme notes and the internal planning notes; the coordinator, the decision and the clarification exchange, as the other record shows them; the event's **venue arrangements** (venue name, period, the request's status, and Venue Staff's preparation status and notes); the **equipment requested**, by name with Technical Support's outcome, as the Safety Officer's list shows it (SCRUM-97 AC6); the **equipment reservations** (type name, units, period, who reserved them, and the preparation status and notes); and the **safety outcome**. No ids, and no registrants (SCRUM-55).
4. **Only the arrangements that still count are listed:** withdrawn and released ones are left out, as the venue module's own `list_active_arrangements` defines it (ADR-0039, ADR-0085). Their history stays in the event's history. *Default to review.*
5. **The safety outcome is the current check's:** the newest of "sent to Safety Review", "outcome recorded" and "approval withdrawn" decides, as `has_safety_approval` already reads it (ADR-0047, ADR-0087). Once an event is sent for a new check, or its approval is withdrawn, the record shows no outcome until the new one is recorded; the earlier outcomes stay in the history. The outcome shows its checklist, reason, officer and time. Both read the same helper, `_current_safety_outcome_entry`. *Default to review.*
6. **The history is read from its own route**, as on every event page (ADR-0076): `/history` already answers these roles, so the record doesn't repeat it.
7. **Module boundaries hold:** the events module reads the arrangements through `venue_services.list_arrangements_for_record(event_id)` and the reservations through `equipment_services.list_reservations_of_event(event_id)`, both new. It never imports either module's models.
8. **The web app has one read-only page, `/staff/events/<reference>`,** for the same four roles; anyone else is sent to their own home by `RequireRole`. It reuses the event page's pieces (the heading, the details, the coordinator, the decision, the clarifications, the history section and the loading and error states, now in files of their own) and adds sections for the internal notes, the venue arrangements, the equipment and the safety check. It has **no actions**: no edit, review, decide, planning or registration control, and no registrants.
9. **Where it opens from:**
   - Venue Staff's "Events with venue bookings" on Staff home (ADR-0090's rows now open it).
   - Technical Support's "Events with equipment" on Staff home. These rows used to open the Equipment page (ADR-0061); they now open the record, which gives Technical Support (and only them) a link on to the event's Equipment page, where they reserve and prepare. SCRUM-38's queue still opens the Equipment page directly. *Default to review.*
   - Each card on the Safety Officer's list ("Open the event record").
   - Each card in the Lead's queue and among the active events ("Open the event record"), and each event named in a coordinator's workload.
10. **The Lead's queue shows each request's status** (AC8: "every list shows event name, date, time and status"). `GET /api/events/requests/unassigned` now sends `status` with each row, after the reference and AC2's six fields (ADR-0036), and each queue card shows it with the shared status chip, as the active events do. Every queued request is Submitted today, but the card shows what the backend sends rather than assuming it.
11. **The mock answers the route as the backend does** (`src/mocks/handlers/staffEventRecord.ts`), refusing the same roles. Each mock keeps its own events, so the handler takes the event from the first mock that holds it (the event-request mock's full records first, then the Lead's, the Safety Officer's, the booking and Technical Support's mocks), and each section from the mock that keeps it. The Safety Officer's mock now keeps the outcome it records, so the record shows it.

## Not built: the Attendee's view of one event (AC9)
AC9 also covers the Attendee: opening an event from "My events" should show the event's detail view. The web app has no page an Attendee can open for one event, so "My events" cards (`MyEventCard`) still open nothing. This change doesn't build one. What's missing:

- **Backend:** no route answers one event to an Attendee. The catalogue route (`GET /api/events/catalogue`, SCRUM-52) lists only confirmed events with registration open that haven't ended, so many of an Attendee's own events (past, cancelled, registration closed) aren't in it. `GET /api/events/registrations` lists the Attendee's registrations, with the event's id, name, times and status, but has no route for one of them.
- **Frontend:** the catalogue (`/events`) is a list with no page per event, and `/events/<reference>` is the assigned coordinator's record. "My events" rows carry the event's id, not its reference.
- **Decisions for the team and the product owner:** which sections an Attendee sees (the public details only, or also the venue and their registration with its withdraw action), at what address, and whether past and cancelled events open.

Until then AC9 is met for every role but the Attendee.

## Consequences
- SCRUM-24 AC9 and AC10 are met for these roles in the backend and the web app; SCRUM-33 AC5 has a screen for every internal user; SCRUM-84 AC2 and SCRUM-85 AC2 are met on screen for internal users other than the coordinator.
- ADR-0049 and ADR-0050 decision 7 ("no separate read route for other internal users") no longer holds: this record is that read route.
- The shared list on Staff home now always links its rows, so `pathFor` is required again.
- New backend surface: the README's route table, `tests/events/test_staff_event_record*.py`, `tests/venue/test_arrangements_for_record.py`, `tests/equipment/test_reservations_of_event.py`, and the frontend's `src/integration/staffEventRecord.int.test.ts`. The integration checks that read a record need the Lead, Venue Staff and Safety Officer accounts CI makes, and skip without them; the refusals run every time.
- In mock mode, an event two mocks know under the same reference with different details (for example `EVR-MOCK0002`, queued in the Lead's mock and cancelled in Technical Support's) opens with the details of the first mock that holds it.

## Revisit when
- The team settles a default above, especially whether retired arrangements belong on the record.
- An Event Coordinator should read other coordinators' events (today AC10 says no).
- Venue Staff get a per-event page for their own work: the record could link to it, as it does to the Equipment page for Technical Support.
