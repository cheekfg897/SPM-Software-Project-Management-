# ADR-0029: The coordinator asks the organiser for clarification; `awaiting_clarification` is a ninth status; the exchange lives in the event history

- **Status:** Accepted
- **Date:** 2026-09-27
- **Story:** SCRUM-32 Ask the Organiser for clarification
- **Supersedes:** part of [ADR-0028](0028-review-and-decide.md): `approved` as the eighth and last status added. There are now nine.
- **Extends:**
  - [ADR-0018](0018-least-loaded-coordinator-and-event-history.md): a coordinator's load and the event history;
  - [ADR-0020](0020-organisers-see-their-organisations-events.md): which organisers may answer;
  - [ADR-0021](0021-coordinator-reassignment.md): the statuses a request can be reassigned in;
  - [ADR-0025](0025-event-edits-significant-changes-and-history.md): the statuses a request can be edited in, and how changes are recorded and reassessed;
  - [ADR-0026](0026-role-event-lists.md): the event record;
  - [ADR-0028](0028-review-and-decide.md): which requests can be decided, and the approval check it left a TODO for.

## Context
SCRUM-32's ACs say:

* **AC1:** given a request is Under Review, when the coordinator requests clarification with a message, the event returns to the Organiser for amendment and the Organiser is notified.
* **AC2:** given clarification has been requested, when the Organiser amends and resubmits, the event returns to Under Review and the coordinator is notified.
* **AC3:** given a clarification request is outstanding, when the coordinator tries to approve the event, approval is refused.
* **AC4:** given clarification has been exchanged, both the request and the response stay visible on the event record.

SCRUM-39 AC2 asks for the same two notifications, so this story meets it. The story has no Jira comments. ADR-0028 left a `# TODO: SCRUM-32` in `decide_event_request` for AC3.

Four questions changed what the code would be. The user agreed the defaults for all four:
* **32-1:** what "returns to the Organiser" means;
* **32-12:** who may answer;
* **32-13:** whether amending and resubmitting is one action or two;
* **32-17:** whether AC3 also blocks rejection.

## Decision
**The status**

1. **`awaiting_clarification` is a ninth status, between `under_review` and `approved` (32-1, agreed with the user).** "Returns to the Organiser" needs a state the organiser, the coordinator and the approval check can all see. A flag derived from the history would have to be recomputed by every list and check. Migration 0018 adds the value. Rolling it back moves such a request to `under_review`, the status the question was asked from (32-2).
2. **Where it counts:**
   * **Open (32-3):** it stays in its coordinator's load (`OPEN_STATUSES`, ADR-0018). The request comes back to them once the organiser answers.
   * **Reassignable (32-5):** it can still be reassigned (`REASSIGNABLE_STATUSES`, ADR-0021). `NOT_REASSIGNABLE_MESSAGE` names it.
   * **Not editable by the coordinator (32-6):** `EDITABLE_STATUSES` is unchanged, because while the question is outstanding the request is the organiser's to change.
   * **Equipment locked (32-4):** `EQUIPMENT_EDITABLE_STATUSES` is unchanged, for the same reason.
   * **Unchanged elsewhere (32-7, 32-8, 32-9):**
     * Technical Support's lists still show the event while it may run.
     * The unassigned queue: coordinators no longer have one ([ADR-0034](0034-coordinators-see-only-their-own-events.md), written after this).
     * The role lists, the record's scope and the draft routes stay as they were.
     * The organiser's list shows the new status. There is no separate "needs your answer" list.

**Asking (AC1)**

3. **`POST /api/events/requests/<reference>/request-clarification` with `{"message"}` (32-25).** Event Coordinators only (`403` otherwise). It replies `200` with the request.
   * The view is `ask_for_clarification`. Its obvious name, `request_clarification`, is the service's, and `routes.py` imports services by name.
   * The service is `request_clarification`.
4. **Only the assigned coordinator, only from `under_review` (32-10, 32-11).**
   * Another coordinator's request, or one with no coordinator, gets the "not yours" `404` (ADR-0019). A draft is never found (ADR-0024).
   * Any status but `under_review` is a `409 clarification_not_allowed`. That includes `awaiting_clarification`, so a second question can't be asked while one is outstanding.
5. **The message is required, not blank and trimmed, with no maximum length (32-30).** So is the response in decision 7.
6. **What is saved:** the status moves to `awaiting_clarification`, and a `clarification_requested` history entry is written with `details = {"message"}` and the coordinator as actor. Both go in one commit.

**Answering (AC2)**

7. **`POST /api/events/requests/<reference>/resubmit` with `{"response", ...}` (32-13, agreed with the user).**
   * One action: a required `response` plus optional amendments.
   * Event Organisers only (`403` otherwise). It replies `200` with the request.
   * Only a request `awaiting_clarification` can be resubmitted. Anything else, a draft included, is a `409 request_not_awaiting_clarification`.
8. **Any organiser of the request's client organisation may answer (32-12, agreed with the user).** This is the same scope that lets them open it (ADR-0020). Another organisation's request is `404`, and an organiser with no organisation is `403`.
9. **What may be amended (32-14): every field of a submission, each checked as on submission.**
   * Past dates are refused (ADR-0001).
   * Attendance must be at least 1 (ADR-0003).
   * Times may not carry an offset.
   * The time window is checked against the saved values where a field is left out, as on an edit (ADR-0025). Moving the date moves the end date with it.
   * Nothing a submission needs can be cleared.
   * The coordinator's notes and the fields the server controls are unknown fields.
10. **How the amendment schema is built.** `ResubmitEventRequestSchema(_EditedTimingSchema, SaveDraftSchema)` is loaded with `partial=AMENDABLE_FIELDS`, which is every field of a draft. That leaves `response` required.
    * `_EditedTimingSchema` was split out of the edit schema first (C2), and comes first in the class bases. Its non-nullable timing fields therefore replace the draft's nullable ones.
    * Its post-load hooks aren't named `_normalise`. A method of that name would replace `SaveDraftSchema`'s trimming hook instead of running beside it.
    * `EditEventRequestSchema` lists its fields in `Meta.fields`, so the inherited timing fields keep their place. An edit's changes are recorded and returned in field order.
11. **What is saved (32-15).** In one commit:
    * each amended field is a `field_changed` entry by the organiser, through `_record_field_changes`, which is shared with the edit;
    * the answer is a `clarification_answered` entry with `details = {"response"}`;
    * all the entries share one `occurred_at`;
    * the status goes back to `under_review`.

    A value equal to the saved one is not a change.
12. **Reassessment (32-16).** After the commit, an amendment that could affect equipment already requested asks Technical Support to reassess it, as an edit does (ADR-0025).
13. **`/review` stays `submitted`-only (32-18).** The organiser's answer is what returns a request to review. The coordinator can't pull it back themselves, so ADR-0028's "a move to under review not limited to `submitted`" (31-28) isn't needed.

**Approval waits (AC3)**

14. **Approval is refused while a clarification is outstanding; rejection is not (32-17, agreed with the user).**
    * `AWAITING_DECISION_STATUSES` gains `awaiting_clarification`, so such a request is decidable. `NOT_DECIDABLE_MESSAGE` names it.
    * `_check_no_clarification_outstanding` replaces ADR-0028's TODO (32-19). An approval then is a `409 clarification_outstanding`.
    * A rejection still goes through, and needs a reason, as any first decision does.
    * Once the organiser has answered, the request is `under_review` again and can be approved.

**The check orders (32-26)**

15. **Asking:**
    1. the reference (`404`);
    2. the coordinator (`404`);
    3. the status (`409`);
    4. the payload (`400`).

    **Resubmitting:**
    1. the organiser's organisation (`403`);
    2. the reference (`404`);
    3. the status (`409`);
    4. the payload (`400`).

    **Deciding** follows ADR-0028's order, then the outstanding-clarification check. It needs the validated outcome, so it runs after the payload and reason checks and before anything is written.

**The record, the history and notifications (AC4, AC1, AC2)**

16. **The history keeps both sides (32-20).** There are two kinds, `clarification_requested` and `clarification_answered`, with the text in `details`. The history route shows both to the organiser and to staff, with names resolved.
17. **The record gains a `clarifications` list (32-21).**
    * Each item is `{"message", "requested_by", "requested_at", "response", "answered_by", "answered_at"}`, oldest first. The answer's fields are `null` while the question is outstanding.
    * An answer belongs to the question just before it. An answer with no question before it is skipped.
    * Names are looked up when the record is read, so a removed user shows as `null` (32-22).
    * `EventRecord.clarifications` defaults to an empty tuple, so a record with no exchange still equals the old two-field value.
18. **Notifications (32-23).** There are two kinds, each with the text as the notification's `detail`, raised after the change's own commit (ADR-0015):
    * `clarification_requested` goes to the organiser who submitted the request.
    * `clarification_answered` goes to the request's *current* coordinator, which may not be who asked.

    Nobody else is told.
19. **No coordinator to tell the answer to (32-24).** The answer is still saved, and `event_request_unassigned` is logged, as submission does. Refusing the answer would leave the organiser stuck.
20. **Three error classes (32-29):** `ClarificationNotAllowedError`, `RequestNotAwaitingClarificationError` and `ClarificationOutstandingError`. Each has its own code, so a client can tell them apart.

**Migration**

21. **Migration 0018 (32-27).**
    * **Upgrade:** it adds the status, the two history kinds and the two notification kinds, in one block outside the transaction. It adds no columns.
    * **Downgrade:**
      1. deletes notifications and history entries of the new kinds;
      2. moves `awaiting_clarification` requests to `under_review`;
      3. rebuilds the three enum types.
    * **The constraint:** before re-typing the status column, the downgrade drops 0014's `ck_event_requests_details_unless_draft`, and re-creates it with 0014's condition afterwards. Postgres can't re-type a column that a check constraint compares against the old type. The condition is copied into 0018, since migrations don't import each other, and its test reads it from 0014 to prove the copy matches.
    * **Verified:** 0018 was replayed on Postgres 16: one head, upgrade, check, downgrade base, upgrade, check.

**How it was built**

22. **Sharing code with SCRUM-33 (32-28).** The edit's timing rules (`_EditedTimingSchema`) and its change recording (`_record_field_changes`) were extracted in a refactor commit before their second use, not copied.
23. **Test-process notes, kept for the record:**
    * The C6 trim guard (`test_amended_text_is_trimmed_and_a_blank_one_is_cleared`) was added at GREEN, not RED. It is shown to fail when the response hook is renamed `_normalise`.
    * The approval-refused test is parametrised over no reason and a reason.

## Consequences
- **SCRUM-39** gets its AC2 from this story. It should mark `tests/events/test_clarification_notifications.py` with `scrum_39` as well. Its own migration, 0019, must chain onto 0018, and its previous notification kinds must include both clarification kinds.
- **SCRUM-41 (end-to-end test)** can drive the journey through the real routes: draft, submit, assign, `/request-clarification`, `/resubmit`, then `/decide`.
- **Coordinator load.** A request waiting on the organiser still counts towards its coordinator's load.
- **Downgrading 0018** deletes the exchange's history entries and notifications, and moves waiting requests back to `under_review`.
- **Equipment is frozen while a clarification is outstanding.** A coordinator who needs to change it must wait for the answer, or reject the request.

## Revisit when
- The customer wants several questions outstanding at once, or a question asked from another status.
- Only the submitting organiser should be allowed to answer, or the whole organisation should be told of a question.
- A maximum length is needed for messages or responses.
- The coordinator needs to withdraw a question without an answer.
