# ADR-0045: Safety Review is the tenth event status, between `approved` and `confirmed`

- **Status:** Accepted; which statuses the existing status sets include it in is left to SCRUM-97 and SCRUM-96
- **Date:** 2026-10-17
- **Story:** SCRUM-22 Define the event status model (with SCRUM-97, which gives it its meaning)
- **Supersedes:** the status list and count in ADR-0012, ADR-0028 and ADR-0029

## Context
SCRUM-22 now says an event holds exactly one of ten statuses: Draft, Submitted, Under Review,
Awaiting Clarification, Approved, Safety Review, Confirmed, Completed, Cancelled or Rejected. The
repo had nine, so Safety Review was the only one missing. Customer change #6 introduces it for the
operational safety check (SCRUM-97).

The story also settles three things the code's docstrings had wrong or vague:

* There is **no Planning status**. Planning work (venue requests, equipment, rework after a change
  or a safety check) happens while the event is `approved`, and wherever a story says an event
  "returns to planning" it returns to `approved`. ADR-0012 read the customer's "Under Review /
  Planning" as one status, `under_review`; the team's list now splits it into Under Review,
  Awaiting Clarification and Approved.
* `approved` means the coordinator approved the request to go on to planning. It is not the
  customer's "event approved", which is `confirmed`.
* The customer left the status list to the team, so naming Safety Review is our call.

## Decision
1. **`safety_review` is added to `EventRequestStatus` and to Postgres's `event_request_status`**,
   after `approved` and before `confirmed`, in the order of an event's life. Migration 0028 adds it
   with `ADD VALUE IF NOT EXISTS` outside the transaction, as 0017 and 0018 do.
2. **Nothing writes it yet.** Moving an event into Safety Review, what must be true first and what
   a failed check does belong to SCRUM-97 and SCRUM-49, as ADR-0012 left each transition to its own
   story. Until then no event has the status.
3. **Downgrade returns events in `safety_review` to `approved`**, the status they would be sent to
   the check from. It is lossy, like 0017 and 0018.
4. **The existing status sets are unchanged.** `ACTIVE_STATUSES`, `EDITABLE_STATUSES`,
   `EQUIPMENT_EDITABLE_STATUSES` and the decision sets in `events/services.py` do not include
   `safety_review`, so an event in it is not active, editable or decidable. Whether it should be is
   for SCRUM-97 and SCRUM-96 (which defines "active"), and a Product Owner question until they say.
   `EQUIPMENT_NOT_NEEDED_STATUSES` is a deny-list, so Safety Review counts as needing equipment.
5. **The web app shows it as "Safety review"** in `StatusChip`, which is typed over every status
   and would not compile without it.

## Consequences
- Code can name `EventRequestStatus.SAFETY_REVIEW` now; SCRUM-97 needs no migration for the status.
- The Postgres type sorts `safety_review` last, as `ADD VALUE` appends. Nothing orders by status;
  sort in code by `EventRequestStatus` if something needs lifecycle order.
- Until SCRUM-97 lands the status sets disagree with the story's intent if an event ever reaches
  Safety Review, but none can.

## Revisit when
SCRUM-97 or SCRUM-96 is implemented, and decide there which of the status sets include
`safety_review`.
