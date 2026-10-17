# ADR-0048: An event holds one of ten statuses; there is no Planning status

- **Status:** Accepted
- **Date:** 2026-10-17
- **Story:** SCRUM-22 Define the event status model
- **Supersedes:** the list and count of statuses in ADR-0012, ADR-0028 and ADR-0029

## Context
SCRUM-22 was corrected on 2026-10-17. An event holds exactly one of ten statuses: Draft,
Submitted, Under Review, Awaiting Clarification, Approved, Safety Review, Confirmed, Completed,
Cancelled or Rejected. The code already had nine, and SCRUM-97 (ADR-0047) added Safety Review.

ADR-0012 counted seven and read the customer's "Under Review / Planning" as one status,
`under_review`. ADR-0028 and ADR-0029 then added `approved` as an eighth and
`awaiting_clarification` as a ninth. Those counts are now out of date, and the story settles three
points those ADRs left vague.

## Decision
1. **Ten statuses, in lifecycle order:** `draft`, `submitted`, `under_review`,
   `awaiting_clarification`, `approved`, `safety_review`, `confirmed`, `completed`, `cancelled`,
   `rejected`. The customer left the list to the team; this is ours.
2. **There is no Planning status.** Planning work (venue requests, equipment, rework after a change
   or a safety check) happens while the event is `approved`. Wherever a story says an event
   "returns to planning", it returns to `approved`.
3. **`approved` is not the customer's "event approved".** It means the coordinator approved the
   request to go on to planning (SCRUM-31). The customer's "event approved" is `confirmed`
   (SCRUM-49), so nothing treats `approved` as final.
4. **`awaiting_clarification` means the coordinator is waiting for the organiser's reply.** The story
   says the coordinator records the response and returns the event to `under_review`, and the
   organiser does not edit or resubmit. The code still has the organiser resubmitting
   (ADR-0029), which is SCRUM-32's rework, not this ADR's.

## Consequences
- The status list is no longer a count to keep in step: the enum docstring, the status test and the
  README name all ten.
- Which status sets include `safety_review` (`ACTIVE_STATUSES`, `EDITABLE_STATUSES` and the
  others) stays with SCRUM-97 and SCRUM-96 (ADR-0047).

## Revisit when
The team or the customer changes the status list again, or SCRUM-32 moves the clarification
answer to the coordinator and ADR-0029 is superseded.
