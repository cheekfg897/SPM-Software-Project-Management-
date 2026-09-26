# ADR-0018: A submitted request goes to the least-loaded Event Coordinator; one event history table records what happens to an event

- **Status:** Accepted; the coordinator's detail view taken up by ADR-0026
- **Date:** 2026-09-25
- **Story:** SCRUM-30 Assign a coordinator to a submitted event (labelled `needs-customer-clarification`; no comments yet)
- **Supersedes:** part of ADR-0015: who is told about a new request

## Context
SCRUM-30's ACs say a submitted request is assigned to exactly one Event Coordinator, who is notified, sees it in their list, and whose name and contact details the organiser can see. They leave these open:

1. **The rule.** "Assigned" but not how. Round-robin, random and least-loaded are the candidates.
2. **Load.** A least-loaded rule needs a definition of which of ADR-0012's seven statuses still count as work for the coordinator.
3. **No coordinator.** Coordinators register themselves and none are seeded, so a request can be submitted when there is no Event Coordinator at all.
4. **"Name and contact details".** Users record a full name and an email and nothing else (SCRUM-65).
5. **"Event record" and "list of events".** No coordinator-facing route exists. ADR-0012 deferred widening the organiser's detail view to SCRUM-30, but SCRUM-31's first AC is the assigned coordinator opening a submitted request, and SCRUM-24 owns the per-role lists.
6. **History.** SCRUM-31 (decisions), SCRUM-87 (reassignment) and SCRUM-33 (edits) all need a record of what happened to an event, and nothing records one yet. The assignment is the first such event.
7. **Notifications.** SCRUM-28 notifies every coordinator of a new request "until coordinators are assigned" (ADR-0015). AC4 wants the assignee told; SCRUM-39 later tells the organiser.

## Decision
- **Least-loaded.** The candidates are every user with the Event Coordinator role. Each one's load is how many requests assigned to them are in `OPEN_STATUSES = {submitted, under_review}`: the phase in which a coordinator works a request, reviewing it and then planning it (ADR-0012 reads `under_review` as "Under Review / Planning"). `confirmed` events are set and only wait for the day; `completed`, `cancelled` and `rejected` are over; a `draft` has no coordinator. The fewest open requests wins, and the **lowest user id** breaks a tie. The coordinators are read once per submission, before the reference-retry loop (ADR-0004), so a retry changes nobody's load. Round-robin was rejected: it needs a stored cursor and keeps sending work to someone whose requests are all still open.
- **No Event Coordinator: saved unassigned.** The request is still saved as `submitted` with `coordinator_id` NULL, with no history entry and no notification to anyone, and `event_request_unassigned reference=…` is logged as a warning. Refusing would punish the organiser for a staffing gap, and a 5xx invites them to submit again (ADR-0015's reasoning). SCRUM-24's list of unassigned requests and SCRUM-87 can pick it up later.
- **One column, atomic with submission (AC2).** `event_requests.coordinator_id` is a nullable, indexed, database-level foreign key to `users`. It is set before the request's commit, and the history entry is added to the same session, so both are saved with the request or neither is; a rolled-back reference collision leaves nothing behind.
- **The event history table.** `event_history_entries` in the events module (model `EventHistoryEntry`): `event_request_id`, `kind` (Postgres enum `event_history_entry_kind`), `actor_id` (nullable foreign key to `users`; NULL means the system acted), `details` (JSON, nullable) and `occurred_at` (UTC, set by the service). `record_event_history(...)` **adds the entry to the session without committing**, so it rides in the caller's transaction. A same-module relationship to `EventRequest` lets an entry be attached before the request has an id. It lives in the events module because only events stories write it and a separate module couldn't hold that relationship. Assignment writes kind `coordinator_assigned`, `actor_id` NULL and `details = {"coordinator_id": <id>}`: ids, not names, so names are resolved when history is shown (SCRUM-33). There is no read route yet.
- **Notifications: only the assigned coordinator is told.** On submission the assignee gets exactly one notification, `coordinator_assigned` ("You have been assigned to coordinate this event."), and nobody else is notified. This **replaces ADR-0015's** "every Event Coordinator is notified, since coordinators aren't assigned to requests yet": now that they are, SCRUM-28 AC3's "raised to Event Coordinators" is read as the one assigned, and a notice to every coordinator would tell most of them about work that isn't theirs. With no Event Coordinator nobody is notified. `event_request_submitted` keeps its `NotificationKind` member, its message and its Postgres value, since enums don't shrink and older rows carry it, but nothing produces it any more. The notification is its own commit after the request's; a failure is rolled back and logged with `kind=`, and the submission still succeeds (ADR-0015). The organiser isn't notified here (SCRUM-39 AC1).
- **The organiser's event record (AC3)** is `GET /api/events/requests/<reference>`. It gains `"coordinator": {"full_name", "email"}`, or `null` until one is assigned. The coordinator's user id is never shown. The list and the `201` on submit don't carry it: that would cost a user lookup per row, and the record is where the organiser looks for their contact.
- **The coordinator's list (AC5)** is `GET /api/events/requests/assigned`: Event Coordinators only, always the caller's own assignments, newest first, in the same shape as the organiser's list. The coordinator's detail view of a request is left to SCRUM-31, whose first AC it is; this moves the widening ADR-0012 expected from SCRUM-30.
- **Migration 0010** adds `coordinator_assigned` to `notification_kind` first, in an autocommit block like 0006, with `IF NOT EXISTS` so a failure later in the upgrade leaves it re-runnable; then the column and the table. The downgrade deletes `coordinator_assigned` notifications and rebuilds `notification_kind` without the value (lossy, like 0006's).

## Consequences
- Each submission runs two small queries (the Event Coordinators, then their open-request counts) and needs no cursor table.
- Every request counts the same towards load, however big the event.
- A rejected or confirmed request frees its coordinator straight away.
- Anything that assumes `coordinator_id` is set must handle NULL; SCRUM-31 has to refuse to review an unassigned request, or assign one.
- A new history kind is one `ADD VALUE` on `event_history_entry_kind`, with the same autocommit pattern as 0010. `details` is schemaless JSON, so each writer documents its keys.
- Each submission raises one notification, to the assignee. Coordinators who aren't assigned hear nothing about it; an unassigned request is only visible in the log until SCRUM-24's unassigned list exists.
- `event_request_submitted` is a kind nothing produces. Only rows written before SCRUM-30 carry it, and they still read with their message.
- The organiser's detail response gains a `coordinator` key.
- Migration 0010's `ADD VALUE` commits before the rest of the upgrade (as 0006's did), but `IF NOT EXISTS` makes a re-run safe. Downgrading deletes `coordinator_assigned` notifications.

## Revisit when
- The customer wants round-robin, manual pick-up, skills or leave taken into account, or confirmed events counted as load (add `CONFIRMED` to `OPEN_STATUSES`).
- SCRUM-87 lands: kind `coordinator_reassigned`, and whether a request can be unassigned.
- SCRUM-24, SCRUM-31 or SCRUM-33 land: the unassigned list, the coordinator's detail view, and a history read route (and whether to snapshot names then).
- SCRUM-39 lands: the organiser is notified.
- The customer wants every coordinator told about new requests again (for example, to pick up unassigned ones).
- Users gain phone numbers: extend `CoordinatorContact`.
