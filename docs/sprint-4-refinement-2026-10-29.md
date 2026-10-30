# Sprint 4 backlog refinement — 29 Oct 2026

Requirements live in Jira (`SCRUM-<n>` on `smu-team-uu78imq6.atlassian.net`), so this file
records **why** the Sprint 4 tickets changed on 29 Oct, the sprint scope change, and the
follow-ups that belong to people rather than tickets. Read each story's ACs in Jira before
building it.

- **Who:** Gyaltsen Chee, Product Owner.
- **Scope:** every Sprint 4 story not Done, checked against the code on `main @ 5080409d`.
  Clusters 0–2 of the review were decided and applied. Clusters 3 (notifications) and 4
  (venue holds) are with the rest of the team. Cluster 5 (housekeeping) has no owner yet.
- **Working copy of the review**, with the reasoning behind every change:
  <https://claude.ai/artifact/Jo728GVrXapHEZittk8s5y>

## Summary

1. The coordinator now edits event details and equipment only **from Approved**. Before
   approval, changes go through a clarification or the Organiser's change request.
2. The Organiser can raise a **change request from Submitted to Confirmed**, one at a time,
   and can withdraw it.
3. The Organiser **cancels their own event directly**, with no approval step. A coordinator
   never cancels: a business-side stop is a rejection with a reason.
4. Two stories were added (**+6 points**). Three To Do stories turned out to be mostly
   built already (SCRUM-54, 58, 61).
5. Change requests have a clear build order with no cycles (see [Build order](#build-order)).

## Sprint scope change

| Added | Points | Why it couldn't wait |
|---|---|---|
| SCRUM-110 Coordinator edits event details and equipment only once the request is approved | 3 | SCRUM-56 and 57 assume the new edit window, so it comes first |
| SCRUM-111 Cancel one approved venue booking while the event is being planned | 3 | Split out of SCRUM-61's old AC7: no story owned it (`cancel_all_arrangements` says so in the code) |

SCRUM-112 (coordinator asks the Lead to cancel a Confirmed event, 5 points) was added on
29 Oct and dropped on 30 Oct (decision 7); it stays in the backlog, outside the sprint. Existing estimates were **not** changed mid-sprint, so the burndown stays
comparable. Estimates for the new stories are relative to SCRUM-67, 75, 87 (3) and SCRUM-56,
98 (5).

## Decisions

| # | Decision | Why | Ticket |
|---|---|---|---|
| 1 | The coordinator edits event details only in Approved or Safety Review. Before approval, the only change is the amendment recorded with a clarification response | The request the coordinator reviews should be the one the Organiser submitted | SCRUM-110 |
| 2 | Equipment lines only from Approved to Confirmed. Lines already on unapproved events are kept | Technical Support were being notified about events that might still be rejected. The Submitted start is left over from before the Approved status existed (ADR-0019 → 0028 → 0092) | SCRUM-110, note on 37 |
| 3 | Change requests can be raised in every status from Submitted to Confirmed | The briefing: Organisers "can request permitted changes after an event has been submitted" | SCRUM-56 AC1 |
| A | One Pending change request per event | Two requests on the same field would clash | SCRUM-56 AC7 |
| B | Approving is refused if a changed field no longer has the value it was raised against | Stops an approval silently overwriting the coordinator's later edit | SCRUM-57 AC8 |
| C | While a change request is Pending, the event can't be approved, rejected or confirmed | Don't sign off an event the Organiser has asked to change. Same idea as SCRUM-32 AC3 | SCRUM-57 AC9 |
| D | Raising, deciding, withdrawing, cancelling and the event's own decisions lock the event row | Two actions in the same second can't both win | SCRUM-57 technical note |
| E | The Organiser can withdraw a Pending change request. A cancelled event's Pending request closes as Withdrawn | Needed because of A | SCRUM-56 AC8, AC9 |
| 5 | A venue that becomes unavailable stays with SCRUM-92 (Done). No new story | 92 already returns a Confirmed event to Approved and notifies the Organiser | — |
| 6 | The Organiser cancels directly, in any status from Submitted to Confirmed, after a confirmation screen. **Replaces the 26 Oct decision** that cancellation is a change request | Cancelling is the Organiser's right ("may postpone or cancel the event"), and SCRUM-61's release steps leave the coordinator nothing to decide | SCRUM-61 AC1 rewritten, AC2 removed; SCRUM-56 AC2 |
| 7 | A coordinator never cancels (30 Oct, replacing the Lead route of 29 Oct). A business-side stop is a rejection with a reason (SCRUM-31, or SCRUM-49 during planning); a Confirmed event whose venue goes first returns to Approved (SCRUM-92). A Confirmed event that can't run for a reason the system doesn't track (e.g. weather) is cancelled by the Organiser after the coordinator contacts them | Cancelled means the Organiser withdrew, Rejected means we couldn't or wouldn't run it. Every business-side reason already reaches Approved, where rejecting is built, so the Lead route guarded almost nothing | SCRUM-61 PO note; SCRUM-112 dropped |
| 8 | SCRUM-58 rewritten: "significant" defined, one-line ACs, an AC5 table, and the return to Approved moved to a new AC7. Numbers and rules kept | The story was too long to read, and "approved" had three meanings | SCRUM-58 |
| 9 | End-to-end tests move into the stories they test (SCRUM-58 AC8, SCRUM-61 AC9). No new test story | A test story fails the V in INVEST and waits on everything else | SCRUM-58, 61, 63 |

### Customer statements read narrowly

Decisions 1, 2 and 6 interpret the customer rather than quote them. If the customer disagrees,
these are the ones to revisit:

- Week 9: the coordinator "can make changes before the final confirmed status", and Week 4
  (on SCRUM-37): equipment lines "at any time before confirmation". Both were answers about
  where the window **ends**, which stays at Confirmed. Decisions 1 and 2 set where it
  **starts**. If overturned, drop SCRUM-110; nothing else depends on it except the order.
- Week 4: "every edit goes through the Coordinator". Decision 6 treats cancelling as not an
  edit. If overturned, cancellation goes back to being a change request in SCRUM-56/57.

## Later decisions (30–31 Oct)

Made after this session, on the same INVEST grounds. The refinement doc's 30 and 31 Oct rows
hold the detail.

| # | Decision | Why | Ticket |
|---|---|---|---|
| 10 | SCRUM-53's old AC3 (who sets the withdrawal cut-off) removed; its no-cut-off rule moved into AC2. Old AC4–AC7 are now AC3–AC6 | It repeated SCRUM-69 AC6 and made 53 wait for 69's settings screen | SCRUM-53 (Jira comment) |
| 11 | SCRUM-44's old AC11 (a request overlapping an active hold shown as Conflicting) dropped, with no new story. Old AC12 is now AC11 | Customer change #4 is met without it: held venues are hidden from search, and a clashing request is refused while the hold is active and can be approved once it ends. "Conflicting" means a clash with a confirmed booking | SCRUM-44 (Jira comment) |
| 12 | A removed AC is deleted from the story, not struck through, and the AC numbers cited in code and tests are updated to match. SCRUM-61's AC2 and AC7 and SCRUM-63's AC2 and AC3 were deleted on 31 Oct | A struck AC still reads as part of the story; Jira history and the refinement doc keep the record. ADRs and merged migrations keep the numbers they were written with | SCRUM-61, 63 (Jira comments); docs PR for the citations |

## Changes made in Jira

| Ticket | Change |
|---|---|
| SCRUM-110, 111 | Created in Sprint 4 (To Do, unassigned, 3 / 3 points) |
| SCRUM-112 | Created 29 Oct, dropped 30 Oct: moved out of the sprint to the backlog with a comment |
| SCRUM-113 | Subtask of SCRUM-90: record the partial pre-fill decision in a new ADR |
| SCRUM-56 | AC1 widened; AC2 loses cancellation; AC3 and AC4 reworded so they can be tested within 56; AC6–AC9 added; notes replaced |
| SCRUM-57 | AC6–AC9 added; technical note on the row lock |
| SCRUM-58 | Retitled "Reassess venue bookings after an approved change request" and rewritten; AC7, AC8 added |
| SCRUM-61 | Now the Organiser's story; AC1 rewritten; AC2 and AC7 removed (deleted 31 Oct, decision 12, so the end-to-end journey added here is now AC9); "already built" note; only the Organiser cancels (30 Oct) |
| SCRUM-63 | AC2 and AC3 moved to SCRUM-58 and 61, then deleted (31 Oct, decision 12); can close on its three remaining ACs (PR #148) |
| SCRUM-37 | Note: the window starts at Approved (SCRUM-110); reservation trimming is SCRUM-60 AC9 |
| SCRUM-54 | AC5 marked as restating SCRUM-69 AC3; note that AC1, AC2 and AC4 were built under SCRUM-52 and AC3 is covered by SCRUM-63's registration journey and SCRUM-53 |
| SCRUM-32, 33 | Comments pointing at SCRUM-110 (32's also records its unbuilt 17 Oct rework) |
| SCRUM-53, 69 | Moved to In Review |
| Links | 110 → 56, 61 → 56, 56 → 57, 57/59/60 → 58 (all "blocks"). The 61 → 112 and 57 → 112 links are still there on the backlog item; remove them in Jira if you want |

## Build order

| Stage | Stories | Waits on |
|---|---|---|
| 0 — start now | SCRUM-110, 61, 111; SCRUM-59 and 60 finish review | Nothing unbuilt |
| 1 | SCRUM-56 | 110, 61 |
| 2 | SCRUM-57 | 56 |
| 3 | SCRUM-58 | 57, 59, 60 |

If 56 and 57 each add a migration on separate branches, stack them or rebase, or `main` gets
two Alembic heads.

## Follow-ups

| What | Who |
|---|---|
| Assign owners to SCRUM-110 and 111 | Team |
| Rank SCRUM-110 above 56 on the board | Ernest |
| Check SCRUM-54 against the code and move it to review | Done 30 Oct: moved straight to Done |
| Close SCRUM-63 | Keene |
| SCRUM-62 AC2 overlaps SCRUM-57 AC7: both tell Attendees of a date or time change, and 62 also names a venue change. Remove the overlap (deleted, not struck: decision 12) and decide where the venue part lives (review item 3-05) | Cluster 3 owners |
| Finish SCRUM-32's 17 Oct rework: the coordinator records the response, and remove the Organiser's `/resubmit` | Seth |
| New ADR for SCRUM-110, superseding ADR-0101 decision 1 | SCRUM-110 owner |
| ADR-0094 decision 11 should cite SCRUM-58 AC7 | SCRUM-58 owner |
| Point the docstring in `tests/e2e/test_registration_journey.py` at SCRUM-58 and 61 | Done in the 31 Oct docs PR |

## Still open

- **Q3:** when a change to "equipment requirements" is approved, does it edit the equipment
  lines (SCRUM-37) or the free-text field? It decides how SCRUM-57 applies the change.
- **Clusters 3 and 4** of the review, with the team: notifications (28, 39, 62) and venue
  holds (94; 44 was settled on 30 Oct, decision 11). SCRUM-94 AC1 ("with no user action")
  needs a decision: reword it, or add a local scheduled expiry job.
- **Cluster 5, decided 29 Oct:** SCRUM-70 and 90 need no AC change (5-01). SCRUM-90's "record
  this in a new ADR" is now subtask SCRUM-113. The stale "This story is To Do, so nothing is
  built yet" line was deleted from SCRUM-59, and still has to be deleted by hand from SCRUM-60
  and 99 (5-02). The description-writing convention (5-03) was dropped.

## For the retro

- SCRUM-56 and 57 gained four ACs each. SCRUM-57 at 3 points is probably low now.
- Many carried-over stories show 1 point, which makes them useless for comparison when
  estimating new stories. Decide whether carry-over keeps its original estimate.
- Done stories were reopened repeatedly because one rule was written in several stories. A
  convention for this (proposal 5-03: one home per rule, change logs in comments) was
  dropped on 29 Oct; worth revisiting if it keeps happening.
