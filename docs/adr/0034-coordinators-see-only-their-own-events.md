# ADR-0034: Event Coordinators see and open only the events assigned to them; the unassigned queue waits for the Lead

- **Status:** Accepted; the Lead's queue taken up by [ADR-0036](0036-event-coordinator-lead.md); a coordinator's access to other events' history, left open here, closed by [ADR-0041](0041-lead-oversight-and-reassignment.md); the Safety Officer's list (AC6), blocked here, built by [ADR-0047](0047-safety-officer-and-safety-review.md)
- **Date:** 2026-10-05
- **Story:** SCRUM-24 See the events my role is involved in
- **Supersedes:** [ADR-0026](0026-role-event-lists.md) decisions 1 (the coordinator's `/requests/unassigned` route), 3, 8 (coordinators opening unassigned requests) and 9

## Context
ADR-0026 gave every Event Coordinator a list of the submitted requests no coordinator has (`GET /api/events/requests/unassigned`), and let any coordinator open one. That matched SCRUM-24's AC2 when it was written: a coordinator saw their assigned events "and separately the submitted events not yet assigned to anyone".

Week 7 customer change #5 added the Event Coordinator Lead and rewrote AC2: *"An Event Coordinator sees only the events assigned to them; unassigned events do not appear in their list."* The story's change note says the unassigned queue "now belongs to the Lead". SCRUM-95 AC2 says *"Only the Event Coordinator Lead can view the unassigned queue"*, and SCRUM-96 AC6 *"Event Coordinators can manage only the events assigned to them."*

The Lead role isn't built yet (SCRUM-95), and automatic assignment (SCRUM-30) stays until it is.

## Decision
1. **No coordinator route lists unassigned requests.** `GET /api/events/requests/unassigned` and its service are removed. The path now reaches the record route as a reference no request has, so it answers `404`.
2. **A coordinator opens only a request assigned to them.** `get_event_record_for_coordinator` uses the same `_assigned_to` condition as the coordinator's list, so the list and the record can't disagree. A request with no coordinator, in any status, is `404` to every coordinator, like another coordinator's.
3. **Nothing is built for the Lead.** Their queue, with the name, date, time, expected attendance and submission time SCRUM-95 asks for, is SCRUM-95's. The removed query is in git history if it helps.
4. **AC references follow Jira's current numbering.** Week 7 inserted AC3 (Lead) and AC6 (Safety Officer), so the code and tests cite AC4 for Venue Staff, AC5 for Technical Support, AC7 for Attendees, AC8 for the list fields, AC9 for the detail view and AC10 for the empty-list message. ADR-0026 keeps the numbers it was written with.

## Consequences
- Until SCRUM-95 lands, nobody sees an unassigned request in the app. One only exists when no Event Coordinator account existed at submission, which is logged as `event_request_unassigned` (ADR-0018).
- ADR-0026's other decisions stand: the per-role routes, Technical Support's equipment list, the AC10 message and coordinators opening their own requests.

## Blocked
SCRUM-24's ACs that can't be built on the current domain model:
- **AC3** (the Lead's unassigned queue and active events): blocked by SCRUM-95/96.
- **AC4** (Venue Staff's list): blocked by SCRUM-42 (booking requests and bookings). It also needs a link between Venue Staff and the venues they're responsible for, which no ticket covers yet.
- **AC6** (the Safety Officer's list): blocked by SCRUM-97.
- **AC7** (the Attendee's list): blocked by SCRUM-52 (registering for a confirmed event).

## Revisit when
- SCRUM-95 lands: the Lead's queue and the Lead's own view of an unassigned request.
- SCRUM-96 lands: the Lead's view of every active event with its coordinator (SCRUM-24 AC3).
- SCRUM-42 or SCRUM-52 lands: add Venue Staff's or the Attendee's list in the same shape (ADR-0026).
