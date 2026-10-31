# ADR-0118: Withdrawing an On Hold arrangement releases its hold, and an event's arrangements change only while it is Approved or in Safety Review

- **Status:** Accepted. Decisions 1 and 8's rule are SCRUM-93's own criteria (the Product Owner's decision of 19 Oct, and AC10 as Jira has it since 15 and 17 Oct). Reading "being planned" as Approved and Safety Review, the wording, the order of the checks, and the rest marked **Default to review** are the builder's calls for the reviewer and the team.
- **Date:** 2026-10-31
- **Story:** SCRUM-93 Book several venues for one event (AC6, AC7, AC10, and the "Changing an arrangement" clarification)
- **Extends:** [ADR-0039](0039-venue-arrangements.md) (decision 4's withdrawable statuses, decision 13's missing event-status guard), [ADR-0069](0069-venue-arrangement-actions-in-the-web-app.md) (the Venue requests page and its mock), [ADR-0045](0045-refuse-an-approval-that-clashes.md) (holds), [ADR-0093](0093-reject-an-event-during-planning.md) (`PLANNING_STATUSES`)

## Context
SCRUM-93's description asks for two things `main` did not do:

- **"Withdrawing an On Hold arrangement releases its hold in the same way (Product Owner decision, 19 Oct; matches SCRUM-92)."** `WITHDRAWABLE_REQUEST_STATUSES` held pending, conflicting, rejected and expired, so withdrawing a held arrangement was a `409`, and cancel-all was refused for the whole event while one was held. A held venue went back to the pool only when Venue Staff rejected the hold or it ran out.
- **AC10:** "The coordinator can withdraw, change or cancel an arrangement, or cancel all of an event's arrangements, only while the event is being planned, that is before it is Confirmed. ... It is also refused on a Completed, Cancelled or Rejected event. The refusal message names the event's status." The "Changed after review" note adds: "make sure withdraw, change and cancel-all all check the event's status". None of them did: ADR-0039 decision 13 listed "there is no event-status guard on withdraw, change or cancel-all" as a default to review.

SCRUM-111 (cancel one approved booking, ADR-0117, on an open branch) says in its AC4 that "a pending or held one is withdrawn instead", which is only true once the first point lands.

## Decision

### Withdrawing an On Hold arrangement
1. **`on_hold` is withdrawable, and withdrawing it releases its hold.** `ON_HOLD` joins `WITHDRAWABLE_REQUEST_STATUSES`. The hold's tentative `Booking` becomes `cancelled` in the same commit as the withdrawal and its `venue_arrangement_withdrawn` history entry, so the venue is free for that period at once (the calendar drops the hold, and another event's request for the period can be approved). The cancel is one helper, `_cancel_hold`, which rejecting a hold (SCRUM-75 AC7) now calls too, so the rule lives in one place. (Agreed: the Product Owner's decision of 19 Oct.)
2. **The hold jobs leave it alone.** `expire_holds` and `send_hold_expiry_warnings` read only requests still On Hold, so a withdrawn hold is neither expired nor warned of; tests pin both. The cancelled booking keeps its expiry, and the arrangement stops showing one (`hold_expires_at` is shown only for On Hold and Expired, SCRUM-75 AC9). **Default to review:** a warning already sent before the withdrawal is not followed by a "never mind" notice.
3. **Cancel-all withdraws held arrangements too,** releasing each hold, in its one commit. It is still refused while the event has an approved arrangement (ADR-0039 decision 6; SCRUM-111 cancels those one by one).
4. **Rejecting an event during planning still releases a held arrangement rather than withdrawing it.** `release_event_arrangements` now asks whether the arrangement holds its venue (`VENUE_HOLDING_REQUEST_STATUSES`: approved and On Hold) instead of whether it is withdrawable, so its behaviour is unchanged: a held one becomes Released, its hold cancelled, and Venue Staff are told the venue is free (ADR-0093, ADR-0103).
5. **Only an On Hold arrangement's hold is cancelled.** An Expired one's lapsed hold already frees the venue and is left as the history of when it ran out (ADR-0052). Other statuses have no hold linked to them. **Default to review:** the withdrawal does not go looking for a booking by period, as `_booking_made_by` does for an approved one, because for a conflicting arrangement that could find another arrangement's booking at the same venue and period.
6. **Nobody is told.** As for every withdrawal (ADR-0039 decision 13, ADR-0055 decision 6), no notice goes to Venue Staff, who placed the hold; it drops out of their queue. **Default to review.**
7. **The refusal now lists "held":** "Only a pending, conflicting, held, rejected or expired arrangement can be withdrawn; this one is approved." **Default to review:** the wording ("held" reads better than "on hold" in the list); the status at the end is the API's value, as before.

### AC10: the event's status
8. **"Being planned" means Approved or in Safety Review,** the events module's `PLANNING_STATUSES` (ADR-0093). Any other status refuses withdraw, change and cancel-all. Why these two:
   - there is no Planning status: planning happens while the event is Approved, and an event "returns to planning" by returning to Approved (SCRUM-22, ADR-0048, SCRUM-93's status clarification);
   - Safety Review is before Confirmed, and SCRUM-92 lets a replacement be raised there (ADR-0053), which the coordinator must be able to withdraw;
   - AC10 refuses Confirmed (changes then go through change review, SCRUM-56/57), Completed, Cancelled and Rejected;
   - an event with arrangements is never Submitted, Under Review or Awaiting Clarification on `main`: a request can only be raised for an Approved event (SCRUM-42), and the event's decision is locked once one exists (SCRUM-31 AC7, ADR-0084). (The brief for this fix said arrangements "can exist from Submitted onwards"; the code does not allow that.) **Default to review:** those statuses are refused too rather than allowed, matching the edit window the Product Owner set for SCRUM-110 on 29 Oct (ADR-0116: Approved and Safety Review) and SCRUM-111's cancel (ADR-0117).
9. **One check in the events module:** `get_event_for_arrangement_change` finds the coordinator's own event (`404` as before, ADR-0019) and refuses one that isn't being planned with `409 conflict`: "Only an approved event or one in Safety Review can have its venue arrangements withdrawn, changed or cancelled; this one is confirmed." The status is the API's value (`confirmed`, `completed`, `cancelled`, `rejected`, `submitted`, ...), as `get_approved_event_for_coordinator` and `get_event_for_replacement_booking` name it. The venue module calls it from all three services, so neither module imports the other's models. **Default to review:** one message for the three actions rather than one each.
10. **The order of the checks.** Withdraw and cancel-all: the reference and the coordinator (`404`), the event's status (`409`), then the arrangement (`404`) and its status (`409`), so an unknown arrangement id on a Confirmed event is refused for the event. A change keeps its body first (`400`, which the web app's contract test pins "before looking for the event"), then the same order. Nothing is written on a refusal. **Default to review.**
11. **A draft is still never found** (`404`, ADR-0024), and **listing an event's arrangements stays allowed at any status**: it changes nothing.

### The web app and the mock
12. **The Venue requests page is unchanged.** It already offers Withdraw on every arrangement that isn't retired, held ones included, and shows any refusal in the backend's words (ADR-0069 decisions 2 and 7). **Default to review:** it does not hide the actions on a Confirmed event; the backend's message explains the refusal.
13. **The booking mock follows** (CONVENTIONS §14): `on_hold` is withdrawable, withdrawing or cancelling all clears the hold's expiry (now in `moveTo`, for every status without a hold, which also fixes a hold released by rejecting the event keeping its expiry in the mock), `releaseEventArrangements` releases a held arrangement, and withdraw, change and cancel-all go through `eventToChange`, which answers the backend's `404` and AC10 `409` in the backend's order. The contract tests check both changes against the real backend: a held request withdrawn and its venue free (`holds.int.test.ts`), and the refusals on a Confirmed and a Rejected event, after a Safety Review event let them through (`booking.int.test.ts`, replacing its `it.todo`).

## Consequences
- A coordinator can drop a held venue at once instead of waiting for the hold to run out or asking Venue Staff to reject it, and cancel-all works on an event with a hold.
- SCRUM-111 AC4's "a pending or held one is withdrawn instead" is now true. SCRUM-111's branch (ADR-0117) checks the same `PLANNING_STATUSES` with its own message in `get_event_for_booking_cancellation`; whichever merges second can fold the two into one helper. Both branches touch `cancel_all_arrangements`' docstring and `release_event_arrangements`, so expect small merge conflicts there, and one line in this index.
- A Confirmed event's arrangements can't be withdrawn, changed or cancelled until change review (SCRUM-56/57) exists; that is AC10's intent.
- The unit tests are `tests/venue/test_venue_arrangements.py` (On Hold) and `tests/venue/test_venue_arrangement_event_status.py` (AC10, every event status built from the enum).

## Revisit when
- SCRUM-111 merges: share one planning-status helper, and check its AC4 wording against decision 7's message.
- SCRUM-56/57 (change review) are built: a Confirmed event's arrangement changes go through them.
- The team wants Venue Staff told when a hold they placed is withdrawn (decision 6), or one message per action (decision 9).
