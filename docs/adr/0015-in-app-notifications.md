# ADR-0015: Notifications are in-app rows, one per recipient, that snapshot their event

- **Status:** Accepted
- **Date:** 2026-09-25
- **Story:** SCRUM-28 Receive notifications about my events (open "Ask customer" subtask SCRUM-29: in-app only, or email too?)

## Context
SCRUM-28 leaves several questions open:
1. **Channel.** SCRUM-29 asks the customer whether in-app notifications are enough or email is needed too. It hasn't been answered.
2. **Who is relevant.** The only link between a user and an event today is the organiser who submitted the request. Coordinator assignment (SCRUM-30), venue responsibility (SCRUM-50) and registrations (SCRUM-62) come later, and each of those stories says whom to notify.
3. **Read state.** What happens when a notification is marked read twice, and what someone gets for a notification that isn't theirs.
4. **Naming and linking the event.** The events module raises notifications, so reading them must not call back into the events module: that would be a circular import, and a lookup per notification. There is no API route for a single event request yet.
5. **When to write.** Submitting a request commits inside a retry loop (ADR-0004), so where the notification write goes matters.

## Decision
- **In-app only.** A notification is a row in `notifications`. If email is added later, those rows are what an email sender reads.
- **The caller decides who is relevant.** `notify_users(recipient_ids, event, kind)` writes one row per recipient, so each has their own read state. For SCRUM-28 the events module passes every Event Coordinator, since coordinators aren't assigned to requests yet. A user only ever reads their own rows.
- **Read state is `read_at`.** `NULL` means unread. Marking a read notification again keeps the first time and writes nothing. The unread count is the caller's rows where `read_at IS NULL`.
- **Someone else's notification is a `404`, not a `403`.** The lookup is scoped to the caller (`id = ? AND recipient_id = ?`), so a missing notification and someone else's get the same answer. A `403` would confirm the id exists, the same enumeration concern as ADR-0004.
- **The event is snapshotted.** Each row keeps `event_request_id` (a database-level foreign key only) plus the event's `event_reference` and `event_name` as they were when the notification was raised. Reading needs no lookup per row, and old notifications keep the name the event had then.
- **The link is `/events/<reference>`.** A client-side path: the reference is the identifier users see (ADR-0004), and there is no single-request API route to link to yet.
- **`kind` says what happened** (the Postgres enum `notification_kind`). The message text comes from the kind, inside the notifications module, so no text is stored.
- **Raised after the request's own commit, in a second commit.** If that commit fails, it is rolled back and logged (`event_request_notification_failed`), and the submission still succeeds: the request is already saved, only its notifications are lost, and a failed reply would invite the organiser to submit it again. With no recipients nothing is written or committed.
- **Timestamps are UTC instants** (`UTCDateTime`), shown in business time (ADR-0009). The service sets `created_at`, so every copy of one notification carries the same instant.

## Consequences
- Listing and counting are one query each, on the `recipient_id` index.
- A later story that notifies adds a `NotificationKind` member, its message, and a migration running `ALTER TYPE notification_kind ADD VALUE ...`, then calls `notify_users` with the users it knows are involved.
- A kind that needs a reason (an approval or rejection) needs a nullable `detail` column. It's added when a story needs it.
- Snapshots go stale on purpose: a renamed event keeps its old name in older notifications. The reference never changes.
- The link is a contract with a frontend that doesn't exist yet. If it changes, only `EVENT_LINK_TEMPLATE` changes.
- A caller that passes the same user twice notifies them twice, so callers de-duplicate.
- There is no pagination, unread-only filter or "mark all read".

## Revisit when
- SCRUM-29 is answered "email too".
- A story needs a reason or other detail on a notification.
- Users collect enough notifications to need paging, an unread filter or "mark all read".
- The events module gains a single-request route and the frontend would rather link to the API.
