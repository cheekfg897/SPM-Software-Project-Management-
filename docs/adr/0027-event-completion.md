# ADR-0027: The assigned coordinator marks a confirmed event completed once its end has passed; the history records who and when

- **Status:** Accepted
- **Date:** 2026-09-26
- **Story:** SCRUM-68 Mark an event as completed after it has taken place
- **Extends:** [ADR-0012](0012-event-status-model.md) (the `completed` status) and [ADR-0018](0018-least-loaded-coordinator-and-event-history.md) (the event history table)

## Context
SCRUM-68's ACs say a confirmed event whose end time has passed can be marked Completed (AC1); one whose end time hasn't passed can't (AC2); a cancelled or rejected event can't (AC3); a completed event can no longer be edited and accepts no new registrations (AC4); and the change records which user did it and when (AC5). The story has no comments. It is labelled `needs-customer-clarification`, and the open question is whether completion is automatic or manual.

What already exists:
- The `completed` status, since migration 0006 (ADR-0012), which nothing has written until now.
- The event history table (ADR-0018), with one row per thing that happens to an event.
- `EDITABLE_STATUSES` (ADR-0025, decision 7), which already leaves out `completed`, so the edit half of AC4 holds as soon as the status is set.
- `REASSIGNABLE_STATUSES`, `AWAITING_REVIEW_STATUSES` and SCRUM-38's list, which already treat `completed` as over.

Nothing sets `confirmed` yet (SCRUM-49, To Do), and registrations don't exist yet (SCRUM-52, To Do).

Left open:
1. Automatic or manual, and if manual, who.
2. What "end time" means, and in which timezone.
3. Whether the event has "passed" at the exact end instant.
4. How "which user and when" is recorded.
5. The route, the refusals and their order.
6. The registrations half of AC4.

## Decision
1. **Manual, by the event's assigned coordinator (68-1, 68-9).** The ACs describe a user marking the event and AC5 records "which user", so completion is an action, not a scheduled job. The route is `@requires_role(Role.EVENT_COORDINATOR)`, and the service refuses any other coordinator with the "not yours" `404` the equipment, reassignment and edit routes give (ADR-0019, ADR-0021, ADR-0025). The alternatives were rejected. A scheduled job would leave AC5's "which user" empty and would complete events nobody had checked. Letting any coordinator complete any event breaks the rule that an event's own coordinator is the one who works it.
2. **The end is `end_date` + `end_time`, a wall-clock time in business time (68-2).** It is read with `app.common.clock.as_utc`, as booking times are (ADR-0002, ADR-0009), and compared with an aware `now`. `end_date` is used, not `proposed_date`, because an event may run overnight or over several days (ADR-0002).
3. **The event has ended at its end instant (68-3):** it can be completed when `now >= ends_at`. The event is over at 17:00, so there is nothing left to wait for. Waiting until strictly after would refuse a coordinator who clicks at 17:00:00 exactly.
4. **One `event_completed` history entry, and no new columns (68-4, 68-14).** `actor_id` is the caller, `details` is NULL, and `occurred_at` is the same `now` the end was checked against. It is added in the same commit as the status change. `completed_at` and `completed_by` columns were rejected: the history table already holds "who did what, when", the history route shows it with the name resolved, and extra columns would say the same thing twice. There are no details because the previous status is always `confirmed`.
5. **`POST /api/events/requests/<reference>/complete`, with no body, answering `200` with the request (68-5, 68-16).** It is an action route like `/reassign`. `PATCH` with a status was rejected because it would suggest any status can be set. The reply is just the request as `EventRequestSchema` shows it, with no user ids.
6. **Refusals (68-6, 68-7).** There is one `409 request_not_completable` class with two messages, following `RequestNotReassignableError`:
   - "Only a confirmed event can be marked completed." for `submitted`, `under_review`, `cancelled`, `rejected` and an event that is already `completed`. An idempotent `200` for an event that is already completed was rejected: the history would get a second completion, or the call would lie about doing something.
   - "The event has not ended yet." for a confirmed event whose end hasn't passed.

   A draft is `404`, since staff never see a draft at all (ADR-0024).
7. **Check order (68-8):** reference `404`, then ownership `404`, then status `409`, then end `409`, the same order edits and reassignment use. Ownership comes before status, so another coordinator learns nothing about an event that isn't theirs. Status comes before the end, so an event that can never be completed is told why, not "not yet".
8. **No notifications (68-10).** None of the ACs asks for one, and SCRUM-39 doesn't list completion.
9. **Clock injection (68-13).** The service takes a keyword-only, aware `now: datetime | None`, defaulting to the current UTC instant, so tests pin the clock. `today: date` wasn't enough, because the end is a time of day.
10. **Migration 0016 (68-15)** adds `event_completed` to `event_history_entry_kind`, outside the transaction with `IF NOT EXISTS`, as 0012 and 0015 do. The downgrade deletes the entries of that kind and rebuilds the type. Refusing to downgrade was rejected, to stay consistent with 0010-0015.

## Consequences
- Each completion adds one history row, and the table gains no new columns. The history route shows it with the coordinator's name.
- A completed event drops out of everything that reads the existing status sets: it is no longer editable (AC4) or reassignable, its equipment can't change, and it leaves Technical Support's awaiting list. Coordinator load doesn't change, since a `confirmed` event already doesn't count towards it (ADR-0018).
- Until SCRUM-49 sets `confirmed`, no real event can be completed through the API. The tests set the status directly.
- An event nobody marks stays `confirmed` for ever.
- Rolling back migration 0016 deletes completion history. Events already `completed` stay `completed`, because that status predates 0016.

## Deferred
- **The registrations half of AC4 (68-11):** registrations don't exist yet. SCRUM-52 must refuse a new registration for a `completed` event.
- **Automatic completion:** waits for the customer's answer.

## Revisit when
- The customer answers the automatic-or-manual question.
- SCRUM-52 lands: registrations must be closed for a completed event.
- SCRUM-49 lands: check that `confirmed` is set as this story assumes.
- SCRUM-61 lands: whether a completed event can still be cancelled (it shouldn't be).
- SCRUM-53 lands: it refuses a withdrawal from an event that is already `completed`, so it reads the status this story writes.
