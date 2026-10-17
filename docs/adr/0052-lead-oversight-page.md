# ADR-0052: The Lead's oversight page shows the backend's workload and active events, and reassigns by email

- **Status:** Accepted; decisions 2, 4, 5 and 7 are defaults to review with the team
- **Date:** 2026-10-17
- **Story:** SCRUM-96 Lead reassigns events and oversees coordinator assignments (AC1, AC3, AC4),
  with SCRUM-24 AC3 ("separately all active events with the coordinator assigned to each")
- **Extends:** [ADR-0041](0041-lead-oversight-and-reassignment.md) (the backend's two lists and the
  Lead's reassignment), [ADR-0036](0036-event-coordinator-lead.md) (the queue page and its typed
  email)

## Context
The backend on `main` gives the Event Coordinator Lead three routes (ADR-0041):

- `GET /api/events/requests/active`: every event in an active status, newest first, each with its
  status and its coordinator's name (`null` for a submitted event nobody holds yet);
- `GET /api/events/coordinators/workload`: each coordinator who holds an active event, by name,
  with those events; an empty list carries a `message`;
- `POST /api/events/requests/<reference>/reassign` with `{"coordinator_email": "..."}`: moves an
  assigned, active event to another Event Coordinator. `POST .../coordinator` is the queue's first
  assignment and refuses a request that already has a coordinator (`409`), so it can't move one.

The web app had only the Lead's queue (`/staff/queue`). Left open for the screen:

1. Where the lists live and how the Lead reaches them.
2. What a row with no coordinator offers, when `/reassign` refuses it.
3. How the workload shows each coordinator's load, when the frontend may not count for itself.
4. Whether a row opens the event, when the backend refuses the Lead the record.
5. What a reassignment and a first assignment invalidate.

Jira's SCRUM-96 changed after review (17 Oct): an unassigned event is no longer active (AC2), the
workload lists every coordinator, with 0 for one who has nothing (AC3), and Safety Review is an
active status. The backend on `main` still follows ADR-0041, so the screen shows what it sends.

## Decision
1. **One page, `/staff/oversight` ("Coordinator oversight"), Lead only.** Its first section is the
   workload, its second the active events, each with a heading and one line saying what it is. A
   small "Lead" navigation (Unassigned queue, Oversight) sits under the title of both Lead pages,
   so the header, which every role shares, is unchanged. The workload comes first because the
   story says it is there to help the Lead choose a coordinator.
2. **A row with no coordinator shows "Not assigned" and a link to the queue, not a reassign
   form.** `/reassign` would answer it with `409` "This event request has no coordinator to
   reassign from."; the queue is where a first assignment is made. *Default to review.* Once the
   backend follows AC2, such rows stop arriving and this branch is never taken.
3. **Reassignment is the event's own form, a typed email, as the queue's assignment is.** No
   picker, because no route lists coordinators with their emails (ADR-0036 decision 8). The
   queue's form is generalised into one `CoordinatorEmailForm` used by both pages, so the two
   show the backend's field error under the email and any other refusal in an alert the same way.
   The form empties its field after a successful reassignment, since the row stays on the page.
4. **The workload lists the coordinators the backend sends, in its order, each with their events.
   A coordinator whose list is empty reads "No active events."** The page shows no count: the
   checklist forbids counting in the browser, and the list is the count. *Default to review:*
   AC3's "shown with 0" needs the backend to list idle coordinators (and, if a number is wanted,
   to send it).
5. **Rows don't open the event.** `GET /requests/<reference>` admits the organiser and the
   assigned coordinator only (ADR-0036's consequences), so a link would lead to a refusal.
   *Default to review*, with the "Lead's view of an event" ADR-0036 deferred.
6. **What is read again after a change.** A reassignment invalidates the two oversight lists (the
   queue can't change). A first assignment from the queue now invalidates every Lead query, the
   queue and both oversight lists, because the event joins a coordinator's workload.
7. **The query keys don't name the viewer.** Every Lead gets the same answer (the story's
   Assumption: every Lead sees everything), any other role is refused, and logging out clears the
   cache. *Default to review* if Leads ever see different things.
8. **The mock keeps one store of events** for the queue, the active list, the workload and both
   actions, so an assignment from the queue shows up in the workload, as on the backend. It
   follows `main`'s backend, not the 17 Oct ACs, and refuses in the backend's order.

## Consequences
- `ROUTES.LEAD_OVERSIGHT` and its route-table entry; the Lead's home stays the queue.
- When the backend adopts the 17 Oct ACs (unassigned events leave the active list, idle
  coordinators join the workload, Safety Review becomes a status), the page needs no change
  beyond a status chip for the new status; the mock and the contract tests change with it.
- The contract tests that need a Lead account are `it.todo`, as the queue's are: the integration
  setup can make an Event Coordinator but not a Lead.

## Revisit when
- The backend follows SCRUM-96's 17 Oct ACs (AC2, AC3, Safety Review).
- A route lists the Event Coordinators: the form could become a picker (ADR-0036 decision 8).
- The Lead is given a view of an event's record: rows could link to it.
