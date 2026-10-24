# ADR-0087: A withdrawn safety approval sends the event back to Approved, wherever it was

- **Status:** Accepted; sending a Confirmed event back to Approved is a default pending the customer
- **Date:** 2026-10-19
- **Stories:** SCRUM-33 AC7, SCRUM-37 AC4, SCRUM-47 AC5, SCRUM-48 AC7; extends SCRUM-92 AC10
- **Extends:** [ADR-0047](0047-safety-officer-and-safety-review.md): `has_safety_approval`; [ADR-0053](0053-flag-bookings-when-a-venue-becomes-unavailable.md) decision 13: `withdraw_safety_approval`

## Context
SCRUM-92 AC10 built the first way to lose a safety approval: approving a replacement venue writes a `safety_approval_withdrawn` history entry, which `has_safety_approval` reads as no approval, and an event in Safety Review goes back to Approved so the coordinator can send it again (ADR-0053 decision 13). At that point the event is never Confirmed, because a flagged venue has already taken it back to Approved (ADR-0053 decision 7).

Four Week 7 ACs add more causes, each in the same words: the event "must pass a new safety check before it can be confirmed or prepared".

- SCRUM-33 AC7: a significant change to the event.
- SCRUM-37 AC4: adding, changing or removing an equipment line.
- SCRUM-47 AC5: a reservation flagged because equipment went out of service.
- SCRUM-48 AC7: a revised equipment outcome.

Some of these can reach a **Confirmed** event: a coordinator may still edit one (ADR-0025), and Technical Support may revise an outcome or take equipment out of service at any time. The ACs don't say what a Confirmed event becomes. Left Confirmed with no approval, preparation would stop (SCRUM-84/85 read `has_safety_approval`), but the event could never pass the new check, because only an Approved event can be sent to Safety Review (SCRUM-97).

The customer has said what happens to a Confirmed event that changes, though for change review rather than these direct changes: "once an event is Confirmed its information cannot be changed directly; … after that the event returns to Approved (the planning stage) through change review" (Week 9, recorded on SCRUM-93). SCRUM-58 AC1 says the same for an approved change of date or time.

## Decision
1. **One withdrawal for every cause.** Each cause calls `withdraw_safety_approval` in its own transaction, with its own actor and `details`; the story ADRs say what each one writes ([ADR-0025](0025-event-edits-significant-changes-and-history.md), [ADR-0019](0019-event-equipment-lines.md), [ADR-0046](0046-taking-equipment-out-of-service.md), [ADR-0040](0040-equipment-review-outcome.md)). An event without an approval is left alone, so a second change before the new check writes nothing more.
2. **Default pending the customer: a Confirmed event goes back to Approved too,** as one in Safety Review already did (`RETURNED_TO_PLANNING_ON_WITHDRAWAL`). This is where the customer's Week 9 answer sends a changed Confirmed event; applying it to these direct changes is our reading. The coordinator sends it to Safety Review again and, once approved, confirms it again (SCRUM-49), which tells the organiser again. While it is Approved it is not open for registration (SCRUM-52); people already registered stay registered. This is the same move a flagged venue makes (ADR-0053 decision 7). An Approved event stays Approved.
3. **Who sees it.** The `safety_approval_withdrawn` entry is internal-only (`INTERNAL_ONLY_KINDS`, ADR-0053 decision 7), like the safety outcome it unsettles. The organiser sees the event's status change, and whatever entry the cause itself writes for them. Nobody is notified of the withdrawal itself, since no AC asks for that; a cause that already notifies someone (SCRUM-47 AC3, SCRUM-48 AC4) still does.

## Questions for the customer
1. When a change after the safety check hits a Confirmed event, should it leave Confirmed (closing registration until it passes the new check, as we do), or stay Confirmed with only its preparation on hold?

## Consequences
- `withdraw_safety_approval` is the only place that knows where an event goes when it loses its approval, so a new cause needs no status logic of its own.
- An organiser can see a Confirmed event go back to Approved without a notice saying why; the coordinator explains it.
- An event that leaves Confirmed is hidden from the catalogue until it is confirmed again.

## Revisit when
- The customer answers the question above.
- Change requests for Confirmed events (SCRUM-56, SCRUM-57, SCRUM-58) are built: they may decide this for a Confirmed event instead.
- *Done for the edit by [ADR-0101](0101-direct-edits-stop-at-confirmed.md); SCRUM-37 AC2 by [ADR-0092](0092-equipment-line-changes-reopen-the-review.md).* The coordinator's direct edit of a Confirmed event (ADR-0025 decision 7) is closed. Jira asks for this now: SCRUM-33 AC8 (added 19 Oct) refuses a direct edit of a Confirmed event and makes Awaiting Clarification and Safety Review editable, and SCRUM-37 AC2 locks equipment lines once the event is Confirmed. Once both are built, a significant edit or a line change withdraws an approval in Safety Review (back to Approved) or in Approved, and only Technical Support's changes (SCRUM-47 AC5, SCRUM-48 AC7) reach a Confirmed event here, so decision 2 stays for them.
