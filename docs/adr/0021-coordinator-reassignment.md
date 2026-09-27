# ADR-0021: An event's own coordinator may hand it, while open or confirmed, to another coordinator named by email; the history keeps both coordinators' ids and names

- **Status:** Accepted; reassigning a draft is `404`, not `409`, superseded by [ADR-0024](0024-draft-event-requests.md); `approved` added to the reassignable statuses by [ADR-0028](0028-review-and-decide.md); `awaiting_clarification` added by [ADR-0029](0029-clarification-requests.md)
- **Date:** 2026-09-26
- **Story:** SCRUM-87 Reassign an event to a different coordinator
- **Extends:** [ADR-0018](0018-least-loaded-coordinator-and-event-history.md): the coordinator column and the event history table

## Context
SCRUM-30 assigns each submitted request to the least-loaded Event Coordinator (ADR-0018). SCRUM-87 lets an assigned event move to a different Event Coordinator. Its ACs say: the event can be reassigned (AC1) and then has exactly one coordinator (AC2); the previous assignment is kept in the event history "with the coordinator's name and the date and time of the change" (AC3); the new coordinator is notified and sees the event in their list (AC4); the previous coordinator loses coordinator access and no longer sees it (AC5); the organiser sees the new coordinator's name and contact details (AC6); and the reassignment records who did it and when (AC7). SCRUM-39 AC4 adds that the newly assigned coordinator is notified "on assignment and reassignment". The story has no comments.

Left open:
1. **Who may reassign.** There is no lead or admin role; Event Coordinators are the only internal staff who work events.
2. **How the new coordinator is named,** when user ids are never shown to other users.
3. **Which requests.** ADR-0012's seven statuses include drafts and finished events.
4. **Edge cases:** a request with no coordinator (ADR-0018 saves one when no coordinator exists), reassigning to the current coordinator, and unassigning.
5. **What the history keeps.** AC3 asks for "the coordinator's name", and ADR-0018 stores ids.
6. **Who is notified.** AC4 names the new coordinator; the previous one loses the event from their list without being told.
7. **What else changes.** Status, equipment lines and the new coordinator's load.

## Decision
1. **Only the event's current coordinator may reassign it (87-1).** The route is `@requires_role(Role.EVENT_COORDINATOR)`, and the service refuses any other Event Coordinator with the answer SCRUM-37 already gives a coordinator who isn't assigned to an event (ADR-0019, decision 2): `404` "Event request not found.", the same as for an unknown reference. So a coordinator can't take an event over themselves. The alternative, letting any Event Coordinator reassign any assigned event so that someone can act when the current coordinator is away, was rejected: the event's coordinator is the one person who works it everywhere else (its equipment lines, its place in their list), and handing it on should follow the same rule and give the same answer.
2. **`POST /api/events/requests/<reference>/reassign` (87-2),** an action route like the venues' `/deactivate`, answering `200`.
3. **The new coordinator is named by email (87-3):** body `{"coordinator_email": "..."}`, matched ignoring case as login does. The reference ignores case and surrounding spaces (ADR-0004).
4. **Only an Event Coordinator can be given the event (87-4).** An unknown email and another role's email get the same `400` on `coordinator_email`, "No Event Coordinator has this email address.", so the reply doesn't reveal whether someone else holds the address.
5. **`REASSIGNABLE_STATUSES = {submitted, under_review, confirmed}` (87-5).** A confirmed event still needs a coordinator until it happens. A draft has none, and a completed, cancelled or rejected event has nothing left to coordinate: those are `409 request_not_reassignable`.
6. **An unassigned request can't be reassigned (87-6):** `409 request_not_reassignable`, "This event request has no coordinator to reassign from." ADR-0018 left open whether SCRUM-87 would pick up requests saved unassigned; AC1 limits this story to "an assigned event", and picking one up is a first assignment rather than a reassignment, so it belongs with SCRUM-24's unassigned list.
7. **Reassigning to the current coordinator is a `409 conflict` (87-7),** "That coordinator is already assigned to this event request.", and writes nothing, so the history never shows a change that didn't happen.
8. **No unassigning (87-8).** AC2 wants exactly one coordinator afterwards.
9. **The history entry (87-9)** is a new kind, `coordinator_reassigned`, with `actor_id` the caller (AC7), `details = {"previous_coordinator_id", "previous_coordinator_name", "coordinator_id", "coordinator_name"}` and `occurred_at` the current instant in UTC. It is added before the one commit that changes `coordinator_id`, so both are saved or neither is. **The names are stored as they were at the time of the reassignment, next to the ids,** so AC3's "with the coordinator's name" is met as written and the entry still reads correctly after a user is renamed or removed. The ids stay so the entry can still be joined to the users table. The alternative, storing ids only and looking the names up when the history is shown (as ADR-0018 does for `coordinator_assigned`), was rejected: the history would show today's name rather than the name at the time, and nothing at all for a removed user.
10. **Notifications (87-10).** After the commit, the new coordinator gets the existing `coordinator_assigned` notification (AC4, SCRUM-39 AC4): being given an event reads the same either way. **The previous coordinator isn't notified (87-19):** only the current coordinator may reassign (87-1), so they made the change themselves and a notice would only tell them what they just did. So no new notification kind is needed. The organiser isn't notified either (SCRUM-39 AC1). The notification is its own commit; a failure is rolled back and logged, and the reply is still `200` (ADR-0015).
11. **Nothing else changes (87-11).** Status and equipment lines stay; the new coordinator's load isn't checked, since the person reassigning is choosing deliberately.
12. **The reply (87-12)** is the request as `EventRequestSchema` shows it, plus `"coordinator": {"full_name", "email"}`, the same contact the organiser's record shows (AC6). No user ids.
13. **The previous coordinator loses access at once (87-13).** Their list and the equipment routes read the current `coordinator_id` (ADR-0019), so they get the same `404` as for any request that isn't theirs (AC5); nothing else needs changing.
14. **Migration 0012 (87-14)** adds `coordinator_reassigned` to `event_history_entry_kind` only, outside the transaction with `IF NOT EXISTS` as 0010 does; `notification_kind` is untouched. The downgrade deletes the history entries of that kind and rebuilds the type: lossy, like 0010's.
15. **Concurrent reassignments: last write wins (87-15),** and both are in the history. No row lock: reassignment is rare and manual, and the history shows what happened.

The checks run in this order, so the first failure decides the answer: payload `400`; reference `404`; no coordinator `409`; caller not the event's coordinator `404`; status `409`; email `400`; same coordinator `409`. The "no coordinator" check has to come before ownership, or an unassigned event would be the ownership `404` for everyone and 87-6 couldn't be answered; the cost is that the `409` tells any coordinator an unassigned reference exists. Ownership comes before status, as it comes before the awaiting-review check on the equipment routes, so another coordinator learns nothing about a finished event that they wouldn't learn about an open one (87-18).

## Consequences
- The previous coordinator loses the event, its list entry and its equipment routes the moment the commit lands; there is no grace period.
- `actor_id` is set for a manual change and NULL for the system's automatic assignment, so the history tells them apart.
- Showing history (SCRUM-33) can print a reassignment's names straight from `details`. Only SCRUM-30's `coordinator_assigned` entries, which hold just `coordinator_id`, still need the name looked up, and that lookup must handle a user who has since been removed.
- If the current coordinator can't continue and can't reassign the event themselves, nobody else can: no role above coordinator exists yet.
- Unassigned requests still can't be picked up; they wait for SCRUM-24.
- A coordinator can be given more work than the least-loaded rule would give them.
- SCRUM-39 adds the organiser's notice on reassignment.
- Rolling back migration 0012 deletes reassignment history.

## Revisit when
- A lead or admin role appears, or the customer wants coordinators to be able to take over an absent colleague's event. Someone other than the current coordinator could then reassign, so the previous coordinator should be told again (87-19): a notification kind for them comes back as a follow-up.
- SCRUM-24's unassigned list lands: whether picking one up is a first assignment or a reassignment.
- SCRUM-33 adds the history read route: whether `coordinator_assigned` entries should store the name too.
- SCRUM-39 lands: the organiser is notified of a reassignment.
- Reassignment should reset status or equipment, or respect load.
