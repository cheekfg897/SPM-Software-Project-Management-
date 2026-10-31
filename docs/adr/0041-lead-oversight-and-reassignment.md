# ADR-0041: The Event Coordinator Lead alone reassigns, sees every active event and each coordinator's workload; a coordinator reads only their own event's history

- **Status:** Accepted; decision 5's "submitted events nobody holds yet are active" and decision 6's "a coordinator with no active event is left out" superseded by [ADR-0120](0120-lead-oversight-active-events-and-every-coordinator.md)
- **Date:** 2026-10-13
- **Story:** SCRUM-96 Event Coordinator Lead oversees and reassigns coordinators' events
- **Supersedes:** [ADR-0021](0021-coordinator-reassignment.md) decision 1 (only the event's current coordinator reassigns) and decision 10's "the previous coordinator isn't notified (87-19)"; the part of [ADR-0034](0034-coordinators-see-only-their-own-events.md) that left an Event Coordinator able to read any non-draft event's history
- **Extends:** [ADR-0036](0036-event-coordinator-lead.md) (the Lead's queue and first assignment)

## Context
SCRUM-96 gives the Lead oversight of the coordinators' work. Its six ACs: the Lead views all active events under their supervision (AC1) and each coordinator's current workload (AC2); Event Coordinators cannot reassign (AC3); a reassignment keeps the previous assignment in the event history, leaves the event with exactly one coordinator, and removes the previous coordinator's access (AC4); the new coordinator, the previous coordinator and the organiser are notified (AC5); and coordinators view and manage only the events assigned to them (AC6). The ACs never define "active", never say what a coordinator with no events looks like in the workload list, and say nothing of who the previous coordinator's notice should be.

Most of AC4 and two thirds of AC5 were already delivered by SCRUM-87 and SCRUM-39: reassignment writes a `coordinator_reassigned` history entry with both coordinators' ids and names, `coordinator_id` is a single column the reassignment overwrites, every assignment-scoped lookup goes through `_check_assigned_to` / `_assigned_to`, and the new coordinator and the organiser were already told.

## Decision
1. **Reassignment moves to the Lead, and only the Lead.** `POST /requests/<reference>/reassign` is `@requires_role(Role.EVENT_COORDINATOR_LEAD)` and the service's "are you this event's current coordinator?" check is dropped, since the decorator proves the role. AC3 says Event Coordinators cannot reassign, so this replaces ADR-0021 decision 1 rather than adding to it. An Event Coordinator now gets `403` from the decorator. The other refusals are unchanged: an event with no coordinator is `RequestNotReassignableError` (assignment is the `/coordinator` route, ADR-0036), reassigning to the current holder is a `409`, and an event outside the active statuses is refused.
2. **"Active" is `ACTIVE_STATUSES`,** the set SCRUM-87 called `REASSIGNABLE_STATUSES`: `submitted`, `under_review`, `awaiting_clarification`, `approved`, `confirmed`. It is renamed and kept as the single definition, so the Lead's list, the workload list and the reassignment guard cannot drift apart. Drafts are the organiser's private work; `completed`, `cancelled` and `rejected` events have nothing left to coordinate.
3. **"Under their supervision" means every event.** The story's Assumption is that Release 1 has one Lead supervising all coordinators, so AC1 has no per-Lead filter.
4. **The previous coordinator is told, with the existing `request_assigned` kind.** ADR-0021 skipped them because they were the actor. Now the Lead is the actor, so the reason is gone. `request_assigned` is already sent to the organiser on the same event, and reusing it adds no migration, a Postgres enum value never being droppable. The kind's default message is the organiser's ("An Event Coordinator has been assigned to your event request."), so the previous coordinator's notice carries its own `detail` text: "This event has been reassigned to another Event Coordinator and is no longer yours." The notifications schema already returns `detail` for every kind. The notice is a third separate write, rolled back and logged on failure like the other two (ADR-0015). A first assignment has no previous coordinator and sends none.
5. **`GET /requests/active` lists every active event with its coordinator's name and its status** (Lead only, newest first). Submitted events nobody holds yet are active, so they appear with `coordinator: null`. The service returns an `ActiveRequest` (the event and the coordinator's name), because modules may not hold an ORM relationship to `auth`'s users; names come from one `get_user_full_names` query. No user ids are exposed. *Superseded in part by [ADR-0120](0120-lead-oversight-active-events-and-every-coordinator.md) (SCRUM-96 AC2): an event is active only once it has a coordinator, so a submitted event nobody holds is only in the queue, and `coordinator` is never `null`.*
6. **`GET /coordinators/workload` lists each coordinator who has active events, with those events** (Lead only). A coordinator with no active event is left out; the list therefore answers "who is carrying work" and an empty list carries a `message`. A submitted event nobody holds is in no one's workload; it is in the Lead's queue. *Superseded by [ADR-0120](0120-lead-oversight-active-events-and-every-coordinator.md) (SCRUM-96 AC3): every Event Coordinator is listed, an idle one with `active_count: 0` and no events, and the `message` appears only when there is no Event Coordinator.*
7. **AC6 closes a real gap on `main`.** `GET /requests/<reference>/history` allowed every internal role, and `list_event_history` let internal staff read any non-draft event's history, so an Event Coordinator could read the decisions, clarifications, reassignments and field changes of events assigned to someone else. Every write path and every other read path was already assignment-scoped; this was the one exception. **This was a defect, not a new restriction.** The fix is role-dependent: an Event Coordinator reads only their own event's history (`404`, the same as an unknown reference, so references cannot be probed: ADR-0012, ADR-0019, ADR-0034); the Lead, Venue Staff and Technical Support Staff keep access to any non-draft event's history, because their work spans events and no AC restricts them. A reassigned-away coordinator therefore loses history access too, which AC4 wants.
8. **Nothing SCRUM-87 still owns is renamed.** `reassign_coordinator` keeps its name and its `coordinator_reassigned` history kind; only the caller's role and the guard change.

## Defaults to review (not agreed with the team)
- **What "active" means (decision 2).** The ACs do not define it. `ACTIVE_STATUSES` is the single definition.
- **Reusing `request_assigned` for the previous coordinator (decision 4).**
- ~~**A coordinator with no active events is omitted from the workload list (decision 6).** The alternative is to list them with an empty list, so the Lead can see who has capacity.~~ Settled by SCRUM-96 AC3 the other way: built by [ADR-0120](0120-lead-oversight-active-events-and-every-coordinator.md).
- ~~**The active list includes submitted-but-unassigned events, with a null coordinator (decision 5).**~~ Settled by SCRUM-96 AC2 the other way: built by [ADR-0120](0120-lead-oversight-active-events-and-every-coordinator.md). The list still returns the coordinator's name, not just the event.
- **Venue Staff and Technical Support keep reading any event's history (decision 7).**

## Deferred
- A distinct `COORDINATOR_UNASSIGNED` notification kind, if the team prefers one to reusing `request_assigned`. That is a migration and a follow-up ticket.

## Consequences
- No migration.
- SCRUM-87's own ACs are superseded: a coordinator who cannot continue no longer needs a colleague, because the Lead can move the event (ADR-0021's "nobody else can" consequence is gone).
- A reassignment writes one more notification than before; a failure of any of the three is isolated.
- Tests that asserted ADR-0021's rule were updated to the new one, not deleted, and keep their `scrum_87` markers.

## Revisit when
- ~~The team decides whether the workload list should show idle coordinators.~~ Decided by SCRUM-96 AC3 and done by [ADR-0120](0120-lead-oversight-active-events-and-every-coordinator.md).
- More than one Lead exists (AC1 would then need a per-Lead filter).
- The team prefers a separate notification kind for losing an event.
- A role other than the Lead needs to reassign (for example an admin role).
