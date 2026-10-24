# ADR-0051: The assigned coordinator confirms an event from Safety Review once every approval is in

- **Status:** Accepted for the confirmation itself (SCRUM-49 AC1-AC8, AC12); decision 8 was deferred to SCRUM-92 and is now delivered by [ADR-0053](0053-flag-bookings-when-a-venue-becomes-unavailable.md) (the gate names each flagged active arrangement), decision 9 is built by [ADR-0093](0093-reject-an-event-during-planning.md), and decision 10 is superseded by [ADR-0099](0099-organiser-sees-a-confirmed-event.md), which shows the organiser a confirmed event's venues
- **Date:** 2026-10-17
- **Stories:** SCRUM-49 Confirm an event once its arrangements are in place

## Context
SCRUM-49 is the last step of the lifecycle ADR-0047 set up: `approved` → `safety_review` → `confirmed`. The customer wants the coordinator to decide on the event once three approvals are in, each from a different party: Venue Staff (venue), Technical Support (equipment) and the Safety Officer (safety). The story carries the `needs-customer-clarification` label, but no comment or sentence says which part is unsettled. It marks one part as a team assumption: what rejecting an event during planning releases (AC10). The other parts the ACs leave open are decisions 8-10.

## Decision
1. **`POST /api/events/requests/<reference>/confirm`, for Event Coordinators only.** The assigned coordinator confirms; another coordinator gets the usual "not yours" `404` and any other role `403` (ADR-0019). The system never confirms an event itself (AC3), the way nothing sends an event to Safety Review (ADR-0047 decision 3).
2. **Only an event in `safety_review` can be confirmed.** Any other status is `409 confirmation_not_allowed` with `NOT_IN_SAFETY_REVIEW_FOR_CONFIRMATION_MESSAGE`. This is what stops an event reaching `confirmed` without passing through Safety Review.
3. **The gate has three parts, all checked and all named at once:**
   - Safety: `has_safety_approval` (ADR-0047 decision 18). A missing one is named under `safety_check` (AC8).
   - Venue: `_venue_gaps`, the check SCRUM-97 uses. No venue arranged is named; so is every active arrangement that isn't Approved, with its status. A Withdrawn one is ignored (AC4, AC5).
   - Equipment: `_equipment_gaps`. A request with no outcome is named; no requests at all passes (AC2).

   A refusal is `409 confirmation_not_allowed` with `CONFIRMATION_NOT_READY_MESSAGE` and `details` under `safety_check`, `venue_arrangements` and `equipment`. SCRUM-97's two venue and equipment checks now come from one helper, `_arrangement_gaps`, so the two gates cannot drift apart.
4. **Venue and equipment are checked again at confirmation, not only at Safety Review.** ADR-0047's open item stands: nothing stops the coordinator withdrawing, changing or adding a venue arrangement while the event is in Safety Review. Rather than block that, confirmation re-checks, so an arrangement that went Pending or Rejected after the officer approved holds the event back and is named. The approval stays valid; only a new submission voids it (ADR-0047 decision 18).
5. **A tentative hold never counts as a booking (AC7).** The gate reads venue *booking requests* and only an Approved one passes. A hold on the venue's calendar, active or expired, is not read at all.
6. **The confirmation is recorded** as an `event_confirmed` history entry with the coordinator as actor and no details, in the same commit as the status. The organiser can see it, as they see the status.
7. **The organiser is told** with a new `event_confirmed` notification kind (AC12), after the commit (ADR-0015): the organiser who submitted the request, once, and nobody else. A refused confirmation notifies no one. Migration `0035_add_event_confirmed` adds the kind to `event_history_entry_kind` and `notification_kind` outside the transaction; its downgrade deletes those rows and rebuilds both types, like 0032's. It revises 0032 because 0033 and 0034 are on open pull requests; whichever merges last re-points its `down_revision`.

### Deferred and pending the customer
8. **"Needs Alternative Venue" (AC6) is deferred to SCRUM-92.** SCRUM-92 defines the flag: when a venue becomes unavailable, its bookings are flagged Needs Alternative Venue. The system has no such flag yet: nothing sets it and no model holds it, so confirmation does not check it. The gate still holds back any arrangement that isn't Approved. SCRUM-92 adds the check, naming a flagged booking beside the other gaps.
9. **Rejecting an event during planning (AC9, AC10) is not built here.** It is a separate decision with a reason, a notification and a release of venue bookings, holds and equipment, "as for a cancelled event (SCRUM-61)". SCRUM-61 does not exist yet and the story says the release rule is a team assumption. *(Built by [ADR-0093](0093-reject-an-event-during-planning.md): `POST …/reject` for an Approved or Safety Review event, releasing everything at once, as the Product Owner confirmed on 19 Oct.)*
10. **What the organiser sees once confirmed (AC11) is what they see today:** the status, the date and times, and the history. The venue arrangements are not shown to the organiser: the organiser's event record has no venues, and the venue module has no organiser-facing read. It needs its own ticket, and the customer's question below. *Superseded by [ADR-0099](0099-organiser-sees-a-confirmed-event.md): once the event is confirmed, the organiser's record lists every approved arrangement with its venue, period and what was arranged, and shows the Safety Officer's final decision; before then, neither (a default pending the Product Owner).*

## Still owed
- **Frontend:** a Confirm button on the coordinator's event page, the `event_confirmed` notification's message, and showing the 409's `details`. The backend is ready. No response the frontend reads changes, so no mock or integration test changes here.
- **SCRUM-84/85 and registration** already read `confirmed` and `has_safety_approval`; nothing changes for them.
- **Decision 8**, with SCRUM-92 (done, ADR-0053). **Decision 9**, done in ADR-0093. **Decision 10**, above.

## Questions for the customer
1. When an event is rejected during planning because an essential arrangement can't be fulfilled, should its venue bookings, holds and equipment reservations be released at once, as for a cancelled event? *(Answered yes by the Product Owner on 19 Oct (SCRUM-49 AC10); built in ADR-0093.)*
2. Once an event is confirmed, what should the Event Organiser be able to see: every venue, the date and times, and which equipment was confirmed? Should they also see the Technical Support outcomes and the Safety Officer's decision? *(Partly answered by SCRUM-49 AC11, SCRUM-37 AC5 and SCRUM-48 AC5: every venue, the date, time and confirmed arrangements once confirmed (ADR-0099), and each equipment line's status and quantity provided (ADR-0098). The Product Owner answered the Safety Officer's part on 25 Oct: the organiser sees the officer's final decision on the confirmed event (ADR-0099 decision 10). Still open: whether the organiser sees any of it before the event is confirmed.)*

## Consequences
- An event can now reach `confirmed`, so registration (SCRUM-52), completion (SCRUM-68) and preparation (SCRUM-84/85) have events to work on.
- The SCRUM-97 and SCRUM-49 gates share one check, so a change to what "settled" means is made once.

## Revisit when
- The customer answers the questions above (decisions 9-10).
- SCRUM-92's "Needs Alternative Venue" flag, an On Hold or a Cancelled arrangement status lands: check the gate still names them.
