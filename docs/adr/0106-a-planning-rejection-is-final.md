# ADR-0106: An event rejected during planning is never decided again through SCRUM-31, and its decision entry is marked so

- **Status:** Accepted; refusing every new decision on an event rejected during planning is SCRUM-49 AC12 (Product Owner, 25 Oct); telling it apart by a marker on its decision entry, reusing `decision_locked`, leaving planning rejections recorded before the marker re-decidable, and keeping the Decide form on the page are defaults to review
- **Date:** 2026-10-26
- **Story:** SCRUM-49 Confirm an event once its arrangements are in place (AC12)
- **Supersedes:** [ADR-0093](0093-reject-an-event-during-planning.md) decision 8 (a rejected event's decision may still be changed through SCRUM-31)
- **Extends:** [ADR-0028](0028-review-and-decide.md), [ADR-0084](0084-venue-booking-requests-lock-the-decision.md)

## Context
SCRUM-49 AC12, added on 25 Oct: "Given an event was rejected during planning, Then no new decision can be recorded on it through SCRUM-31, even if it never had a venue or equipment request. To go ahead, the Event Organiser submits a new event request (SCRUM-19)." The story's resubmission clarification says a planning rejection is final as a decision, and that the way back is a new request, not reopening the rejected one (Week 4, A38 and A44).

On `main`, ADR-0093 decision 8 let `/decide` re-decide such an event. SCRUM-31 AC7's lock (ADR-0084) counts only an equipment request or a venue request still active, and a planning rejection withdraws or releases every venue request, so an event with no equipment request could be approved again, back into planning with nothing arranged.

SCRUM-31 itself has no final rejection. Its AC6 lets the coordinator "review a decided request again and record a new decision, replacing the current one", Rejected included; its only lock is AC7's. So a rejection recorded through `/decide` must stay re-decidable, and the code has to tell the two kinds of rejection apart. The rows can't do it today:

- both write the same `decision_recorded` entry, `{"outcome": "rejected", "reason": …}`, and leave the event `rejected`;
- both can follow an approval: SCRUM-31 AC6 lets an approved event be rejected through `/decide` while nothing is arranged;
- AC12 covers an event that "never had a venue or equipment request", so the history before the rejection can't tell them apart either.

## Decision
1. **`POST …/decide` on an event rejected during planning is `409 decision_locked`**, with "The decision can't be changed once the event has been rejected during planning. To go ahead, the organiser submits a new event request." (`PLANNING_REJECTION_FINAL_MESSAGE`). It holds for either outcome, whatever the event had arranged. Nothing is saved and nobody is told.
   - **Default to review: the code is AC7's `decision_locked`.** Both refusals say the decision can't change, and the web app shows the message without branching on codes (frontend `CLAUDE.md`). The message says why, and what to do instead.
2. **A planning rejection marks its decision entry.** `reject_event_during_planning` writes `{"outcome": "rejected", "reason": …, "during_planning": true}` (`DURING_PLANNING_KEY`); `/decide` writes no such key. `_apply_decision` now records every key of the decision it is given, so both routes still share it. No migration: `details` is JSON.
   - A new history kind was the other way. It would need a migration for the `event_history_entry_kind` enum, and the organiser's record, which reads the latest `decision_recorded` entry as the current decision (SCRUM-31 AC9), would have to read two kinds.
3. **The check.** `_was_rejected_during_planning` reads the event's `decision_recorded` entries and looks for the marker. It runs only for a `rejected` event. Any marked entry counts, not just the latest. Nothing moves an event out of Rejected once it is rejected during planning, so its marked entry is always the latest anyway, and reading them all needs no ordering.
4. **The order of the checks:** the reference, the coordinator, the status, this lock, AC7's lock, then the body (ADR-0028 decision 11). An event rejected during planning that had an equipment request gets this message, not AC7's: the rejection is the reason, and its lines can no longer change (ADR-0092).
5. **A SCRUM-31 rejection is unchanged.** It can still be decided again under AC6 and AC7, including one that came after an approval with nothing arranged.
6. **Default to review: planning rejections recorded before this change carry no marker,** so they stay re-decidable. Before this merges, only development and test databases hold any; nothing back-fills them.
7. **The marker shows in the history.** The history API shows `details` as stored (ADR-0025), so staff and the organiser see `during_planning: true` on that entry. The web app still shows it as "Request rejected" with its reason. Wording a planning rejection differently is now a change to the web app only (ADR-0093's "Still owed").

### The web app and the mock
8. **The Decide form stays on a rejected event,** as before (ADR-0060: only actions that can't apply in the status are hidden). After a planning rejection, a new decision shows the backend's refusal in the Decide section. **Default to review:** hiding the form would need the record to say how the event was rejected, a change to the record's response left out here.
9. **After a decision, made or refused, the record and the lists are read again** (`useDecideEventRequest` now refreshes `onSettled`, like the edit, ADR-0101 decision 9). A refusal may mean the event moved on since the page was opened.
10. **The mock** keeps a `rejectedDuringPlanning` flag on the stored request. `POST …/reject` sets it and writes the marker into the history entry, and `POST …/decide` refuses a flagged event with the backend's code and message, before reading the body.

## Consequences
- An event rejected during planning stays rejected. The organiser goes ahead by submitting a new request (SCRUM-19), which starts its own review.
- ADR-0093's open question (block re-deciding now, or keep it until resubmission is built) is closed. AC12 makes the new request the way back, so no resubmission story is needed for it.
- `decision_recorded` entries can now carry a key beyond `outcome` and `reason`. A reader of `details` should ignore keys it doesn't know.
- Tests: `tests/events/test_planning_rejection_is_final.py` (marker `scrum_49`); the mock's `eventPlanning.test.ts`; `RecordActions.test.tsx`; `planning.int.test.ts` against the backend.

## Revisit when
- SCRUM-61 cancels an event: a cancelled event isn't decidable at all (ADR-0028), so nothing here changes, but check that cancellation doesn't write a `decision_recorded` entry.
- The team wants the web app to word a planning rejection differently in the history, or to hide the Decide form after one (decision 8).
