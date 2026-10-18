# ADR-0028: The assigned coordinator reviews and decides a request; `approved` is an eighth status; decisions live in the event history

- **Status:** Accepted; `approved` as the last status added superseded by [ADR-0029](0029-clarification-requests.md) (a ninth, `awaiting_clarification`); the decidable statuses and the TODO for SCRUM-32 extended by [ADR-0029](0029-clarification-requests.md); the count of statuses superseded by [ADR-0048](0048-ten-event-statuses.md), which lists ten; the lock (decision 10) counts venue booking requests too from [ADR-0084](0084-venue-booking-requests-lock-the-decision.md)
- **Date:** 2026-09-27
- **Story:** SCRUM-31 Review and decide a submitted request
- **Supersedes:** part of [ADR-0012](0012-event-status-model.md): "no `approved` value yet"; [ADR-0019](0019-event-equipment-lines.md) decision 3: "awaiting review" as the statuses in which equipment may change
- **Extends:** [ADR-0015](0015-in-app-notifications.md): a notification's `detail`; [ADR-0018](0018-least-loaded-coordinator-and-event-history.md): a coordinator's load and the event history; [ADR-0021](0021-coordinator-reassignment.md): the statuses a request can be reassigned in; [ADR-0025](0025-event-edits-significant-changes-and-history.md): the statuses a request can be edited in; [ADR-0026](0026-role-event-lists.md): the event record

## Context
SCRUM-31's ACs say:

* **AC1:** a decision is the assigned Event Coordinator's ruling on a request: Approved or Rejected.
* **AC2:** the coordinator opens the request and sees everything the organiser supplied.
* **AC3:** the coordinator can move a submitted request to Under Review.
* **AC4:** approving moves the request to Approved; rejecting moves it to Rejected and needs a reason.
* **AC5:** nobody but the assigned coordinator can review or decide it.
* **AC6:** the coordinator can change a decision, with a reason, and the status follows.
* **AC7:** no new decision once a venue booking request or an equipment request exists for the event.
* **AC8:** every decision is kept in the history with its reason, the coordinator and the time; the latest one is current.
* **AC9:** the organiser sees the current decision, its reason and the coordinator who made it.
* **AC10:** the organiser is notified of the decision. SCRUM-39 AC3 adds that the notification carries the reason.

ADR-0012 left `approved` out of the status list and handed the choice to this story: keep a decided request in `under_review` with the decision in the history, or add `approved`. The story has no Jira comments, and "Ask customer" SCRUM-23 is still unanswered. AC2 is already met: ADR-0026 decision 8 opens the full event record to the assigned coordinator.

## Decision
**Statuses**

1. **`approved` is an eighth status, after `under_review` (31-1).** SCRUM-42 raises booking requests "from an approved event", so something has to say "approved" apart from the history. Migration 0017 adds it with `ADD VALUE IF NOT EXISTS`. Rolling it back moves an `approved` request to `under_review`, the nearest status the old type knows, and rebuilds the type in the order Postgres held it (31-2). Like 0006's rollback, it loses information.
2. **An approved request counts wherever an under-review one does:**
   * it is part of its coordinator's load (`OPEN_STATUSES`, ADR-0018; 31-3);
   * its equipment lines can still change (31-4);
   * it can be reassigned (`REASSIGNABLE_STATUSES`, ADR-0021; 31-5);
   * it can be edited (`EDITABLE_STATUSES`, ADR-0025; 31-6).

   Planning goes on until the event is confirmed. For equipment, this replaces ADR-0019 decision 3. The set is renamed `EQUIPMENT_EDITABLE_STATUSES = {submitted, under_review, approved}`, and a refusal is now `409 equipment_not_editable` instead of `request_not_awaiting_review`: "awaiting review" no longer describes the set. The error code string is the one change a client can see.
3. **Some things stay as they were:**
   * Technical Support's "equipment not needed" statuses: an approved event stays on `/awaiting-equipment` (31-7).
   * The unassigned queue: coordinators no longer have one ([ADR-0034](0034-coordinators-see-only-their-own-events.md), written after this). An approved request always has a coordinator, so it never waits in the Lead's queue (SCRUM-95) (31-8).
   * The role lists and the record's scope (31-9).

**Reviewing**

4. **`POST /api/events/requests/<reference>/review` moves a `submitted` request to `under_review` (AC3).** Any other status is a `409 request_not_reviewable` (31-11): starting a review twice is a mistake, not a no-op. A `review_started` history entry names the coordinator, and nobody is notified (31-26).
5. **Only the assigned coordinator (AC5, 31-12).** The route is for `event_coordinator` only (`403` for other roles). The service answers another coordinator's request, or one with no coordinator, with the same `404` as an unknown reference (ADR-0019), and a draft is never found (ADR-0024).

**Deciding**

6. **`POST /api/events/requests/<reference>/decide` with `{"outcome", "reason"}` (31-27).** `outcome` is `approved` or `rejected`: a `DecisionOutcome` string enum stored in the history entry's details, not a database type (31-29). A decision can be made straight from `submitted`, without starting a review first (31-10). `confirmed`, `completed` and `cancelled` are a `409 request_not_decidable` (31-14). The reply is `200` with the request, in the same shape as `/reassign` and `/review`, not the whole record (31-23).
7. **The reason (31-15, 31-16).**
   * A rejection needs one, and so does any change of decision.
   * A first approval may carry one, or not.
   * A reason that is sent must not be blank, and is trimmed.
   * The service checks whether a reason is required, not the schema, because the answer depends on the request's current status.
   * A missing reason is `400` with `{"reason": ["A reason is required to reject a request or to change a decision."]}`.
8. **An invalid outcome says "Outcome must be approved or rejected."** This deliberately differs from the auth module's "Role must be one of: …" wording. There are two outcomes, so naming both reads better than a list. The difference was noted in review and kept.
9. **Changing a decision (AC6, 31-13).** An `approved` or `rejected` request may be decided again, with a reason, straight from that status, and the status follows the new outcome. The same outcome may be given again: that is how a coordinator records a new reason.
10. **The lock (AC7, 31-17).** Once the event has an equipment request, a new decision is a `409 decision_locked`. Only a *change* of decision is blocked; the first decision never is. Venue booking requests don't exist yet: `_has_arrangements` has a `# TODO: SCRUM-42` to count them too.
11. **The check order (31-18).**
    1. The reference, then the coordinator (both `404`).
    2. The status (`409 request_not_decidable`).
    3. The lock (`409 decision_locked`).
    4. The payload (`400`).
    5. The SCRUM-32 hook.
    6. The write.

    A request that can't be decided says so, whatever the body.
12. **History (AC8, 31-19, 31-20).** Each decision is one `decision_recorded` entry, with `details = {"outcome", "reason"}`, `actor_id` the coordinator, and `occurred_at` the time. It is saved in the same commit as the status. There are no decision columns on the request: the current decision is the latest `decision_recorded` entry, ordered by time, with the later id winning a tie. The history route shows each one with its coordinator's name.

**Showing and telling**

13. **The record gains a `decision` section (AC9, 31-21, 31-22).** `GET /api/events/requests/<reference>` shows `{"outcome", "reason", "decided_by", "decided_at"}`, or `null` until a decision exists, to the organiser and to the coordinator. `decided_by` is the coordinator's name, looked up when the record is read, so a removed user shows as `null`. The record functions now return an `EventRecord` value, not a tuple.
14. **The organiser is notified (AC10, 31-24, 31-25).** Each decision raises an `event_request_approved` or `event_request_rejected` notification to the organiser who submitted the request only, not their whole organisation. The reason goes in a new nullable `notifications.detail` column, which the notifications API shows as `detail`. This also meets SCRUM-39 AC3. It is raised after the decision's commit; if it can't be saved, it is logged and the decision stands (ADR-0015).

**Migration**

15. **Migration 0017 (31-30).** It adds the `detail` column. Then, in one block outside the transaction, it adds the five enum values: `approved`, `review_started`, `decision_recorded`, `event_request_approved` and `event_request_rejected`. It revises SCRUM-68's 0016. Its downgrade drops 0014's `ck_event_requests_details_unless_draft` before re-typing the status column and re-creates it after, because Postgres can't re-type a column that a check constraint compares against the old enum type.

## Consequences
- **SCRUM-32 (clarification requests)** refuses an approval while a clarification is outstanding. `decide_event_request` has a `# TODO: SCRUM-32` at the point where it goes: after the payload is validated, before anything is written. A request that goes back into review then needs a "move to under review" step that isn't limited to `submitted` (31-28).
- **SCRUM-42 (booking requests)** can check `status == approved`. It must also add venue booking requests to `_has_arrangements`.
- **SCRUM-39 (notifications)** gets its AC3 reason from `detail`. Other kinds leave it `null`.
- **Downgrading 0017** deletes the new kinds' notifications and history entries, and turns approved requests back into ones under review.
- **Coordinator load.** An approved request stays in its coordinator's load until it is confirmed. A coordinator with many approved but unconfirmed events gets fewer new ones.

## Revisit when
- SCRUM-23 is answered and the status list or its transitions change.
- ~~SCRUM-42 lands: count venue booking requests in the lock.~~ Done by [ADR-0084](0084-venue-booking-requests-lock-the-decision.md).
- SCRUM-32 lands: add its approval check at the TODO.
- The customer wants a reason on every decision, or wants a changed decision to notify more than the organiser.
